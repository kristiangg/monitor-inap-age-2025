import hashlib
import html
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

PAGE_URL = "https://sede.inap.gob.es/es/procedimientos-y-servicios/seleccion/procesos-selectivos-de-cuerpos-y-escalas-generales/cuerpo-general-administrativo-de-la-administracion-del-estado-ingreso-libre-convocatoria-2025"
STATE_FILE = Path("state.json")
HISTORY_FILE = Path("history.json")
PDF_DIR = Path("pdfs")
TIMEOUT = 45
CONFIRM_DELAY_SECONDS = 30

RELEVANT_WORDS = (
    "resolución", "resolucion", "nota", "informativa", "listado", "lista",
    "admitid", "excluid", "plantilla", "cuestionario", "ejercicio", "examen",
    "fecha", "sede", "distribución", "distribucion", "resultado", "calificación",
    "calificacion", "aprobado", "convocatoria", "nombramiento", "destino",
    "certificado", "subsanación", "subsanacion", "alegación", "alegacion",
    "acuerdo", "corrección", "correccion",
)
EXCLUDED_WORDS = (
    "inicio", "contacto", "mapa web", "accesibilidad", "aviso legal", "privacidad",
    "cookies", "facebook", "twitter", "x.com", "linkedin", "youtube", "instagram",
    "volver a procesos", "compartir", "imprimir",
)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; INAP-change-monitor/3.0; +https://github.com/)",
    "Accept-Language": "es-ES,es;q=0.9",
})


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: str) -> str:
    return " ".join(value.split())


def normalized_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()


def is_pdf(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


def looks_relevant(text: str, url: str) -> bool:
    candidate = f"{text} {url}".lower()
    if any(word in candidate for word in EXCLUDED_WORDS):
        return False
    return is_pdf(url) or any(word in candidate for word in RELEVANT_WORDS)


def item_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def publication_type(title: str, url: str) -> tuple[str, str]:
    text = f"{title} {url}".lower()
    types = (
        (("resolución", "resolucion"), "Resolución", "📜"),
        (("nota informativa", "nota"), "Nota informativa", "📢"),
        (("plantilla",), "Plantilla", "✅"),
        (("cuestionario",), "Cuestionario", "📝"),
        (("listado", "lista", "admitid", "excluid"), "Listado", "📋"),
        (("acuerdo",), "Acuerdo", "🤝"),
        (("fecha", "examen", "ejercicio"), "Examen / ejercicio", "🗓️"),
        (("resultado", "calificación", "calificacion", "aprobado"), "Resultados", "🏁"),
        (("corrección", "correccion"), "Corrección", "✏️"),
    )
    for needles, label, emoji in types:
        if any(needle in text for needle in needles):
            return label, emoji
    if is_pdf(url):
        return "Documento PDF", "📄"
    return "Publicación", "🔔"


def parse_page(response: requests.Response) -> dict[str, dict]:
    soup = BeautifulSoup(response.text, "html.parser")
    content = (
        soup.select_one("main")
        or soup.select_one("article")
        or soup.select_one(".region-content")
        or soup.select_one("#block-mainpagecontent")
    )
    if content is None:
        raise RuntimeError("No se encontró el bloque principal de contenido de la página.")

    items: dict[str, dict] = {}
    for link in content.select("a[href]"):
        text = clean_text(link.get_text(" ", strip=True))
        href = normalized_url(urljoin(PAGE_URL, link.get("href", "").strip()))
        if not text or not href.startswith(("http://", "https://")):
            continue
        if not looks_relevant(text, href):
            continue
        kind, emoji = publication_type(text, href)
        items[href] = {
            "id": item_id(href),
            "title": text,
            "url": href,
            "pdf": is_pdf(href),
            "kind": kind,
            "emoji": emoji,
        }

    if len(items) < 5:
        raise RuntimeError(
            f"Solo se detectaron {len(items)} publicaciones relevantes; se cancela para evitar falsos avisos."
        )
    return items


def fetch_items(previous_state: dict | None, use_cache: bool = True) -> tuple[dict[str, dict], dict[str, str], bool]:
    headers: dict[str, str] = {}
    if use_cache and previous_state:
        if previous_state.get("etag"):
            headers["If-None-Match"] = previous_state["etag"]
        if previous_state.get("last_modified"):
            headers["If-Modified-Since"] = previous_state["last_modified"]

    response = SESSION.get(PAGE_URL, timeout=TIMEOUT, headers=headers)
    if response.status_code == 304:
        return previous_state.get("items", {}), {
            "etag": previous_state.get("etag", ""),
            "last_modified": previous_state.get("last_modified", ""),
        }, True
    response.raise_for_status()
    items = parse_page(response)
    cache_headers = {
        "etag": response.headers.get("ETag", ""),
        "last_modified": response.headers.get("Last-Modified", ""),
    }
    return items, cache_headers, False


def pdf_sha256(url: str) -> str:
    digest = hashlib.sha256()
    with SESSION.get(url, timeout=TIMEOUT, stream=True) as response:
        response.raise_for_status()
        for chunk in response.iter_content(chunk_size=1024 * 128):
            if chunk:
                digest.update(chunk)
    return digest.hexdigest()


def telegram_request(method: str, payload: dict) -> dict:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Falta TELEGRAM_BOT_TOKEN en GitHub Secrets.")
    response = requests.post(
        f"https://api.telegram.org/bot{token}/{method}", timeout=TIMEOUT, json=payload
    )
    try:
        data = response.json()
    except ValueError:
        data = {}
    if not response.ok or not data.get("ok"):
        description = data.get("description", response.text[:300])
        raise RuntimeError(f"Telegram {method} falló: {response.status_code} · {description}")
    return data


def telegram_chat_ids() -> list[str]:
    raw = (
        os.environ.get("TELEGRAM_CHAT_IDS", "").strip()
        or os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    )
    chat_ids = [value.strip() for value in raw.split(",") if value.strip()]
    if not chat_ids:
        raise RuntimeError("Falta TELEGRAM_CHAT_ID o TELEGRAM_CHAT_IDS en GitHub Secrets.")
    return chat_ids


def telegram_base(chat_id: str) -> dict:
    return {"chat_id": chat_id}


def inline_keyboard(url: str) -> dict:
    return {"inline_keyboard": [[{"text": "🌐 Ver en INAP", "url": url}]]}


def send_item_to_chat(chat_id: str, item: dict, event_type: str, old_title: str | None = None) -> None:
    title = html.escape(item["title"])
    url = item["url"]
    kind = html.escape(item.get("kind", "Publicación"))
    emoji = item.get("emoji", "🔔")

    if event_type == "new":
        heading = "🚨 <b>Nueva publicación en INAP</b>"
        detail = f"{emoji} <b>{kind}</b>\n\n{title}"
    elif event_type == "pdf_changed":
        heading = "♻️ <b>Documento actualizado en INAP</b>"
        detail = f"{emoji} <b>{kind}</b>\n\n{title}\n\nEl PDF ha cambiado aunque conserva el mismo enlace."
    else:
        heading = "✏️ <b>Publicación actualizada en INAP</b>"
        detail = f"{emoji} <b>{kind}</b>\n\n{title}"
        if old_title:
            detail += f"\n\n<b>Título anterior:</b> {html.escape(old_title)}"

    payload = telegram_base(chat_id) | {
        "parse_mode": "HTML",
        "reply_markup": inline_keyboard(url),
    }

    if item.get("pdf"):
        try:
            telegram_request("sendDocument", payload | {
                "document": url,
                "caption": f"{heading}\n\n{detail}"[:1024],
            })
            return
        except Exception as exc:
            print(f"No se pudo adjuntar el PDF; se enviará como enlace: {exc}", file=sys.stderr)

    telegram_request("sendMessage", payload | {
        "text": f"{heading}\n\n{detail}",
        "disable_web_page_preview": True,
    })


def send_item(item: dict, event_type: str, old_title: str | None = None) -> None:
    for chat_id in telegram_chat_ids():
        send_item_to_chat(chat_id, item, event_type, old_title=old_title)


def safe_filename(value: str, limit: int = 90) -> str:
    allowed = []
    for char in value:
        if char.isalnum() or char in ("-", "_", " "):
            allowed.append(char)
    name = "_".join("".join(allowed).split())[:limit].strip("_")
    return name or "documento"


def archive_pdf(item: dict) -> str | None:
    if not item.get("pdf"):
        return None
    PDF_DIR.mkdir(exist_ok=True)
    suffix = item.get("sha256", "")[:12] or item_id(item["url"])
    filename = f"{safe_filename(item.get('title', 'documento'))}_{suffix}.pdf"
    path = PDF_DIR / filename
    if path.exists():
        return str(path)
    with SESSION.get(item["url"], timeout=TIMEOUT, stream=True) as response:
        response.raise_for_status()
        with path.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 128):
                if chunk:
                    fh.write(chunk)
    return str(path)


def send_activation(count: int) -> None:
    for chat_id in telegram_chat_ids():
        telegram_request("sendMessage", telegram_base(chat_id) | {
            "text": (
                "✅ <b>Monitor INAP activado</b>\n\n"
                f"Se han guardado {count} publicaciones relevantes como punto inicial. "
                "Desde ahora recibirás avisos con el tipo de publicación, enlace directo y, cuando sea posible, el PDF adjunto."
            ),
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": inline_keyboard(PAGE_URL),
        })


def load_state() -> dict | None:
    if not STATE_FILE.exists():
        return None
    with STATE_FILE.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    raw_items = data.get("items", {})
    migrated: dict[str, dict] = {}
    for url, value in raw_items.items():
        if isinstance(value, str):
            value = {"title": value}
        title = value.get("title", "")
        kind, emoji = publication_type(title, url)
        migrated[url] = {
            "id": value.get("id", item_id(url)),
            "title": title,
            "url": url,
            "pdf": value.get("pdf", is_pdf(url)),
            "kind": value.get("kind", kind),
            "emoji": value.get("emoji", emoji),
            "sha256": value.get("sha256", ""),
        }
    data["items"] = migrated
    data.setdefault("notified_events", [])
    return data


def save_state(items: dict[str, dict], cache_headers: dict[str, str], notified_events: list[str]) -> None:
    payload = {
        "checked_at": now_iso(),
        "page": PAGE_URL,
        "etag": cache_headers.get("etag", ""),
        "last_modified": cache_headers.get("last_modified", ""),
        "items": items,
        "notified_events": notified_events[-1000:],
    }
    STATE_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def append_history(events: list[dict]) -> None:
    history: list[dict] = []
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            history = []
    history.extend(events)
    HISTORY_FILE.write_text(
        json.dumps(history[-500:], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def event_key(event_type: str, item: dict, extra: str = "") -> str:
    raw = f"{event_type}|{item['url']}|{item.get('title', '')}|{extra}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def detect_page_changes(previous: dict[str, dict], current: dict[str, dict]) -> tuple[list[str], list[str]]:
    new_urls = [url for url in current if url not in previous]
    changed_urls = [
        url for url in current
        if url in previous and current[url]["title"] != previous[url].get("title", "")
    ]
    return new_urls, changed_urls


def main() -> int:
    previous_state = load_state()
    current, cache_headers, not_modified = fetch_items(previous_state)

    if previous_state is None:
        save_state(current, cache_headers, [])
        append_history([{"type": "initialized", "at": now_iso(), "count": len(current), "page": PAGE_URL}])
        print(f"Estado inicial creado silenciosamente con {len(current)} publicaciones relevantes.")
        return 0

    previous = previous_state.get("items", {})
    notified = list(previous_state.get("notified_events", []))
    notified_set = set(notified)

    new_urls, changed_urls = detect_page_changes(previous, current)

    # Si hay una novedad visible en la página, la confirmamos 30 segundos después.
    if new_urls or changed_urls:
        print(f"Cambio candidato detectado; esperando {CONFIRM_DELAY_SECONDS}s para confirmarlo.")
        time.sleep(CONFIRM_DELAY_SECONDS)
        confirmed, confirmed_headers, _ = fetch_items(previous_state, use_cache=False)
        new_urls, changed_urls = detect_page_changes(previous, confirmed)
        current = confirmed
        cache_headers = confirmed_headers

    # Inicializa hashes que aún no existían sin generar avisos antiguos.
    for url, item in current.items():
        if item.get("pdf") and url in previous and not previous[url].get("sha256"):
            try:
                item["sha256"] = pdf_sha256(url)
            except Exception as exc:
                print(f"No se pudo inicializar hash de {url}: {exc}", file=sys.stderr)

    pdf_changed_urls: list[str] = []
    for url, item in current.items():
        if not item.get("pdf") or url not in previous or not previous[url].get("sha256"):
            continue
        try:
            current_hash = pdf_sha256(url)
        except Exception as exc:
            print(f"No se pudo comprobar PDF {url}: {exc}", file=sys.stderr)
            item["sha256"] = previous[url].get("sha256", "")
            continue
        item["sha256"] = current_hash
        if current_hash != previous[url].get("sha256"):
            # Segunda comprobación del PDF para evitar avisos por una subida incompleta.
            time.sleep(CONFIRM_DELAY_SECONDS)
            confirm_hash = pdf_sha256(url)
            item["sha256"] = confirm_hash
            if confirm_hash != previous[url].get("sha256"):
                pdf_changed_urls.append(url)

    # Para PDFs nuevos, guardamos su hash desde el primer momento.
    for url in new_urls:
        if current[url].get("pdf"):
            try:
                current[url]["sha256"] = pdf_sha256(url)
            except Exception as exc:
                print(f"No se pudo calcular hash del PDF nuevo {url}: {exc}", file=sys.stderr)

    events: list[dict] = []
    candidates: list[tuple[str, str, str | None]] = []
    candidates.extend(("new", url, None) for url in new_urls)
    candidates.extend(("updated", url, previous[url].get("title", "")) for url in changed_urls)
    candidates.extend(("pdf_changed", url, None) for url in pdf_changed_urls if url not in new_urls)

    for event_type, url, old_title in candidates:
        item = current[url]
        extra = item.get("sha256", "") if event_type == "pdf_changed" else (old_title or "")
        key = event_key(event_type, item, extra)
        if key in notified_set:
            print(f"Aviso duplicado omitido: {event_type} {url}")
            continue
        send_item(item, event_type, old_title=old_title)
        archived_pdf = None
        if item.get("pdf"):
            try:
                archived_pdf = archive_pdf(item)
            except Exception as exc:
                print(f"No se pudo archivar el PDF {url}: {exc}", file=sys.stderr)
        notified.append(key)
        notified_set.add(key)
        events.append({
            "type": event_type,
            "at": now_iso(),
            "old_title": old_title,
            "archived_pdf": archived_pdf,
            **item,
        })

    if events:
        append_history(events)
        print(f"Avisos enviados: {len(events)}.")
    elif not_modified:
        print("La web respondió 304; se comprobaron los PDFs almacenados y no hay novedades.")
    else:
        print("Sin novedades relevantes.")

    save_state(current, cache_headers, notified)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise

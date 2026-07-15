import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

PAGE_URL = "https://sede.inap.gob.es/es/procedimientos-y-servicios/seleccion/procesos-selectivos-de-cuerpos-y-escalas-generales/cuerpo-general-administrativo-de-la-administracion-del-estado-ingreso-libre-convocatoria-2025"
STATE_FILE = Path("state.json")
HISTORY_FILE = Path("history.json")
TIMEOUT = 45

RELEVANT_WORDS = (
    "resolución", "resolucion", "nota", "informativa", "listado", "lista",
    "admitid", "excluid", "plantilla", "cuestionario", "ejercicio", "examen",
    "fecha", "sede", "distribución", "distribucion", "resultado", "calificación",
    "calificacion", "aprobado", "convocatoria", "nombramiento", "destino",
    "certificado", "subsanación", "subsanacion", "alegación", "alegacion",
)
EXCLUDED_WORDS = (
    "inicio", "contacto", "mapa web", "accesibilidad", "aviso legal", "privacidad",
    "cookies", "facebook", "twitter", "x.com", "linkedin", "youtube", "instagram",
    "volver a procesos", "compartir", "imprimir",
)


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


def fetch_items(previous_state: dict | None) -> tuple[dict[str, dict], dict[str, str], bool]:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; INAP-change-monitor/2.0; +https://github.com/)",
        "Accept-Language": "es-ES,es;q=0.9",
    }
    if previous_state:
        if previous_state.get("etag"):
            headers["If-None-Match"] = previous_state["etag"]
        if previous_state.get("last_modified"):
            headers["If-Modified-Since"] = previous_state["last_modified"]

    response = requests.get(PAGE_URL, timeout=TIMEOUT, headers=headers)
    if response.status_code == 304:
        return previous_state.get("items", {}), {
            "etag": previous_state.get("etag", ""),
            "last_modified": previous_state.get("last_modified", ""),
        }, True
    response.raise_for_status()

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
        items[href] = {
            "id": item_id(href),
            "title": text,
            "url": href,
            "pdf": is_pdf(href),
        }

    if len(items) < 5:
        raise RuntimeError(
            f"Solo se detectaron {len(items)} publicaciones relevantes; se cancela para evitar falsos avisos."
        )

    cache_headers = {
        "etag": response.headers.get("ETag", ""),
        "last_modified": response.headers.get("Last-Modified", ""),
    }
    return items, cache_headers, False


def telegram_request(method: str, payload: dict) -> dict:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Falta TELEGRAM_BOT_TOKEN en GitHub Secrets.")

    response = requests.post(
        f"https://api.telegram.org/bot{token}/{method}",
        timeout=TIMEOUT,
        json=payload,
    )
    try:
        data = response.json()
    except ValueError:
        data = {}
    if not response.ok or not data.get("ok"):
        description = data.get("description", response.text[:300])
        raise RuntimeError(f"Telegram {method} falló: {response.status_code} · {description}")
    return data


def telegram_base() -> dict:
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not chat_id:
        raise RuntimeError("Falta TELEGRAM_CHAT_ID en GitHub Secrets.")
    return {"chat_id": chat_id}


def inline_keyboard(url: str) -> dict:
    return {"inline_keyboard": [[{"text": "🔗 Abrir publicación", "url": url}]]}


def send_item(item: dict, old_title: str | None = None) -> None:
    title = html.escape(item["title"])
    url = item["url"]
    if old_title is None:
        heading = "🚨 <b>Nueva publicación en INAP</b>"
        detail = f"📄 {title}"
    else:
        heading = "✏️ <b>Publicación actualizada en INAP</b>"
        detail = (
            f"📄 {title}\n\n"
            f"<b>Título anterior:</b> {html.escape(old_title)}"
        )

    payload = telegram_base() | {
        "parse_mode": "HTML",
        "reply_markup": inline_keyboard(url),
    }

    if item.get("pdf") and old_title is None:
        # Telegram descarga el PDF desde el INAP y lo adjunta al chat.
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


def send_activation(count: int) -> None:
    telegram_request("sendMessage", telegram_base() | {
        "text": (
            "✅ <b>Monitor INAP activado</b>\n\n"
            f"Se han guardado {count} publicaciones relevantes como punto inicial. "
            "A partir de ahora recibirás un aviso con enlace directo y, cuando sea posible, el PDF adjunto."
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

    # Compatibilidad con la versión antigua: {"items": {url: titulo}}.
    raw_items = data.get("items", {})
    migrated: dict[str, dict] = {}
    for url, value in raw_items.items():
        if isinstance(value, str):
            migrated[url] = {
                "id": item_id(url), "title": value, "url": url, "pdf": is_pdf(url)
            }
        else:
            migrated[url] = value
    data["items"] = migrated
    return data


def save_state(items: dict[str, dict], cache_headers: dict[str, str]) -> None:
    payload = {
        "checked_at": now_iso(),
        "page": PAGE_URL,
        "etag": cache_headers.get("etag", ""),
        "last_modified": cache_headers.get("last_modified", ""),
        "items": items,
    }
    with STATE_FILE.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


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


def main() -> int:
    previous_state = load_state()
    current, cache_headers, not_modified = fetch_items(previous_state)

    if not_modified:
        print("La web respondió 304: no ha cambiado desde la última comprobación.")
        return 0

    previous = previous_state.get("items", {}) if previous_state else None
    if previous is None:
        save_state(current, cache_headers)
        append_history([{
            "type": "activated", "at": now_iso(), "count": len(current), "page": PAGE_URL
        }])
        send_activation(len(current))
        print(f"Estado inicial creado con {len(current)} publicaciones relevantes.")
        return 0

    new_urls = [url for url in current if url not in previous]
    changed_urls = [
        url for url in current
        if url in previous and current[url]["title"] != previous[url].get("title", "")
    ]

    events: list[dict] = []
    for url in new_urls:
        send_item(current[url])
        events.append({"type": "new", "at": now_iso(), **current[url]})
    for url in changed_urls:
        old_title = previous[url].get("title", "")
        send_item(current[url], old_title=old_title)
        events.append({
            "type": "updated", "at": now_iso(), "old_title": old_title, **current[url]
        })

    if events:
        append_history(events)
        print(f"Avisos enviados: {len(new_urls)} nuevos, {len(changed_urls)} actualizados.")
    else:
        print("Sin novedades relevantes.")

    save_state(current, cache_headers)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise

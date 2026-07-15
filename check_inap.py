import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

PAGE_URL = "https://sede.inap.gob.es/es/procedimientos-y-servicios/seleccion/procesos-selectivos-de-cuerpos-y-escalas-generales/cuerpo-general-administrativo-de-la-administracion-del-estado-ingreso-libre-convocatoria-2025"
STATE_FILE = Path("state.json")


def clean_text(value: str) -> str:
    return " ".join(value.split())


def fetch_items() -> dict[str, str]:
    response = requests.get(
        PAGE_URL,
        timeout=40,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; INAP-change-monitor/1.0; +https://github.com/)"
        },
    )
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

    items: dict[str, str] = {}
    for link in content.select("a[href]"):
        text = clean_text(link.get_text(" ", strip=True))
        href = urljoin(PAGE_URL, link.get("href", "").strip())
        if not text or not href.startswith(("http://", "https://")):
            continue
        # Evita enlaces estructurales que no son publicaciones del proceso.
        if text.lower() in {"inicio", "selección", "volver a procesos selectivos de cuerpos y escalas generales"}:
            continue
        items[href] = text

    if len(items) < 5:
        raise RuntimeError(f"Solo se detectaron {len(items)} enlaces; se cancela para evitar falsos avisos.")
    return items


def send_telegram(message: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en GitHub Secrets.")

    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        timeout=30,
        json={
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": True,
        },
    )
    response.raise_for_status()


def load_state() -> dict[str, str] | None:
    if not STATE_FILE.exists():
        return None
    with STATE_FILE.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data.get("items", {})


def save_state(items: dict[str, str]) -> None:
    payload = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "page": PAGE_URL,
        "items": items,
    }
    with STATE_FILE.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def main() -> int:
    current = fetch_items()
    previous = load_state()

    if previous is None:
        save_state(current)
        send_telegram(
            "✅ Monitor INAP activado\n\n"
            f"Se han guardado {len(current)} publicaciones como punto inicial. "
            "A partir de ahora te avisaré cuando aparezca algo nuevo o cambie el título de un enlace."
        )
        print(f"Estado inicial creado con {len(current)} enlaces.")
        return 0

    new_urls = [url for url in current if url not in previous]
    changed_urls = [url for url in current if url in previous and current[url] != previous[url]]

    if new_urls or changed_urls:
        lines = ["🚨 NOVEDAD EN INAP · ADMINISTRATIVO AGE 2025", ""]
        for url in new_urls:
            lines.extend([f"🆕 {current[url]}", url, ""])
        for url in changed_urls:
            lines.extend([
                f"✏️ Enlace actualizado: {current[url]}",
                f"Antes: {previous[url]}",
                url,
                "",
            ])
        lines.extend(["Página vigilada:", PAGE_URL])
        send_telegram("\n".join(lines)[:4096])
        print(f"Aviso enviado: {len(new_urls)} nuevos, {len(changed_urls)} modificados.")
    else:
        print("Sin novedades.")

    save_state(current)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise

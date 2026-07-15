# Monitor INAP — Administrativo AGE 2025

Vigila la página oficial del proceso selectivo y avisa por Telegram cuando aparece una publicación relevante nueva o cambia el título de una existente.

## Funciones

- Revisión automática cada 5 minutos (GitHub puede demorarse puntualmente).
- Filtrado de resoluciones, notas, listados, plantillas, cuestionarios, fechas y PDFs.
- Botón directo para abrir cada publicación.
- Adjunta automáticamente los PDFs en Telegram cuando la API lo permite; si falla, envía el enlace.
- Guarda un historial en `history.json`.
- Usa `ETag` y `Last-Modified` cuando el servidor los ofrece, evitando procesar una página sin cambios.
- Ignora menús, redes sociales y cambios de navegación.

## Secretos necesarios

En **Settings → Secrets and variables → Actions**:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Ejecución manual

Ve a **Actions → Vigilar novedades INAP → Run workflow**.

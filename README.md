# Monitor INAP — Administrativo AGE 2025

Monitor automático de la página oficial del INAP mediante GitHub Actions y Telegram.

## Funciones

- Revisión aproximada cada 5 minutos.
- Doble comprobación antes de avisar.
- Avisos diferenciados: nueva publicación, título actualizado, PDF añadido, PDF modificado y publicación retirada.
- Mensajes con tipo, título, fecha de detección y prioridad para términos importantes.
- PDF adjunto cuando Telegram puede descargarlo.
- Botones «Ver en INAP» y «Abrir PDF».
- Comparación SHA-256 para detectar sustituciones de PDFs con la misma URL.
- Historial en `history.json` y copias en `pdfs/`.
- Prevención de avisos duplicados.
- Prueba manual de Telegram desde Actions.
- Resumen semanal los domingos.

## Secretos

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID` o `TELEGRAM_CHAT_IDS`

Para varios destinos, `TELEGRAM_CHAT_IDS` admite IDs separados por comas.

## Prueba manual

Actions → **Vigilar novedades INAP** → **Run workflow** → marcar **Enviar mensaje de prueba a Telegram**.

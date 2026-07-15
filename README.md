# Monitor INAP — Administrativo AGE 2025

Vigila la página oficial de la convocatoria y avisa por Telegram.

## Funciones

- Revisión automática mediante GitHub Actions.
- Clasificación del aviso: resolución, nota, plantilla, listado, cuestionario, etc.
- Botón **🌐 Ver en INAP**.
- Envío del PDF directamente cuando Telegram puede descargarlo.
- Detección de PDFs sustituidos aunque mantengan la misma URL, mediante SHA-256.
- Segunda comprobación 30 segundos después para evitar avisos por publicaciones incompletas.
- Protección frente a avisos duplicados.
- Historial en `history.json` y estado en `state.json`.

## Secretos requeridos

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Nota sobre GitHub Actions

El texto `Vigilar novedades INAP #3` indica el número de ejecución del workflow. No significa que haya tres monitores funcionando a la vez.

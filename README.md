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
- Historial en `history.json`, estado persistente en `state.json` y copia de los PDFs nuevos en `pdfs/`.
- No repite el mensaje de activación al actualizar el código.
- Puede enviar a un chat, a un grupo o a varios destinos.

## Secretos

Usa una de estas opciones:

- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`: un único chat o grupo.
- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_IDS`: varios IDs separados por comas.

Para un grupo, añade el bot, envía un mensaje y guarda como `TELEGRAM_CHAT_ID` el identificador negativo del grupo.

## Nota

`Vigilar novedades INAP #3` es el número de ejecución del workflow; no indica tres monitores simultáneos.

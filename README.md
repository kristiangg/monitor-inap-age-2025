# Monitor INAP — Administrativo AGE 2025

Vigila la página oficial del proceso selectivo y envía un aviso por Telegram cuando aparece un enlace nuevo o cambia el texto de uno existente.

## Instalación rápida

1. **Revoca el token que compartiste en el chat**: abre `@BotFather`, envía `/revoke`, elige el bot y genera un token nuevo. No guardes el token dentro de ningún archivo.
2. Crea un repositorio **público** en GitHub. Por ejemplo: `monitor-inap-age-2025`.
3. Sube todo el contenido de esta carpeta, incluida la carpeta oculta `.github`.
4. En el repositorio abre: **Settings → Secrets and variables → Actions → New repository secret**.
5. Crea estos dos secretos:
   - `TELEGRAM_BOT_TOKEN`: el token nuevo facilitado por BotFather.
   - `TELEGRAM_CHAT_ID`: tu identificador numérico de chat.
6. Abre **Actions → Vigilar novedades INAP → Run workflow**.
7. El primer arranque guarda el contenido actual como referencia y envía a Telegram: **Monitor INAP activado**.

## Importante

- Antes del primer arranque, abre el chat de tu bot en Telegram y pulsa **Iniciar/Start**. Un bot no puede escribirte hasta que tú hayas iniciado la conversación.
- El repositorio debe ser público para que los ejecutores estándar de GitHub Actions sean gratuitos e ilimitados. Los secretos no aparecen públicamente.
- La programación pide una ejecución cada 5 minutos, pero GitHub no garantiza puntualidad exacta y puede haber retrasos.
- GitHub puede desactivar tareas programadas en repositorios públicos sin actividad durante 60 días. Los commits automáticos de `state.json` solo ocurren cuando cambia la página, así que revisa ocasionalmente que la tarea siga habilitada.
- Si cambia la estructura técnica de la web del INAP, la ejecución fallará de forma visible en la pestaña **Actions**, en vez de sobrescribir el estado o enviar un falso aviso.

## Página vigilada

https://sede.inap.gob.es/es/procedimientos-y-servicios/seleccion/procesos-selectivos-de-cuerpos-y-escalas-generales/cuerpo-general-administrativo-de-la-administracion-del-estado-ingreso-libre-convocatoria-2025

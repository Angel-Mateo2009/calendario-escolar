# Avisos push diarios sin Cron Job de Render

La app envía a cada estudiante que active los avisos una notificación por tarea pendiente que vence al día siguiente. El mensaje incluye la materia y el nombre de la tarea. GitHub Actions ejecuta el envío a las 8:17 a. m. de Ecuador (13:17 UTC); sus horarios pueden retrasarse cuando hay alta demanda. Las tareas completadas se omiten.

## 1. Generar las claves VAPID

1. En tu PC instala las dependencias del proyecto: `pip install -r requirements.txt`.
2. Ejecuta `python generate_vapid_keys.py` una sola vez.
3. Copia los valores `VAPID_PUBLIC_KEY` y `VAPID_PRIVATE_KEY` que aparecen. No los publiques ni subas el valor privado a GitHub como archivo. Conserva siempre este mismo par de claves.

## 2. Configurar Render

En el servicio web de Render añade `VAPID_PUBLIC_KEY` y `VAPID_PRIVATE_KEY` como variables de entorno y vuelve a desplegar. La clave pública permite que el navegador se suscriba; la privada sirve al proceso que envía los avisos.

## 3. Configurar GitHub Actions

1. Sube la carpeta `.github/workflows` junto con los otros archivos modificados al repositorio y a su rama principal. El archivo `send-reminders.yml` crea una ejecución diaria y también permite iniciarla manualmente desde la pestaña **Actions**.
2. Abre la página de la base PostgreSQL en Render y copia su **External Database URL** desde **Connect**. No uses la Internal URL, porque GitHub ejecutará el proceso fuera de Render.
3. En GitHub abre **Settings → Secrets and variables → Actions → New repository secret** y crea estos secretos:
   - `RENDER_DATABASE_URL`: External Database URL de Render.
   - `VAPID_PRIVATE_KEY`: la misma clave privada configurada en el servicio web de Render.
   - `VAPID_CLAIMS_EMAIL`: un correo de contacto válido.
4. Revisa que GitHub Actions esté habilitado en el repositorio. En **Actions**, ejecuta **Recordatorios push de tareas** manualmente una vez para revisar el resultado. La ejecución manual envía los avisos del día si hay tareas pendientes que vencen mañana.

GitHub Actions es gratis para repositorios públicos en runners estándar. En repositorios privados consume los minutos incluidos en tu plan; GitHub Free incluye 2.000 minutos mensuales según su documentación actual. Los minutos se comparten con los demás workflows de la cuenta. Los horarios programados pueden demorarse y solo corren desde la rama predeterminada.

Render admite conexiones externas a PostgreSQL mediante la External URL; revisa la sección Networking de la base si se restringió el acceso externo. La URL y credenciales deben guardarse como secreto, nunca en el código.

Después del despliegue, cada estudiante debe iniciar sesión, pulsar **Activar recordatorios** y aceptar las notificaciones del navegador. La web debe abrirse por HTTPS.

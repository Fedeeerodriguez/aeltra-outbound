# Deploy de Aeltra Outbound en EasyPanel (Docker Compose)

Server + worker de envío paceado + scheduler de rutinas corren en **un solo contenedor**.
La base SQLite persiste en un volumen (`/data`), así que sobrevive reinicios y re-deploys.

---

## 1. Antes de empezar (tener a mano)

- Repo de Aeltra Outbound accesible desde EasyPanel (GitHub) **o** subís el código al servicio.
- Credenciales de Gmail OAuth2 (`GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`).
  Si no las tenés, corré una vez en tu compu: `python gmail_oauth_setup.py` y copiá los valores que imprime.
- `APIFY_TOKEN` (para prospección real).
- El **dominio público** que le vas a dar a la app (para el link de baja y el auth).

---

## 2. Crear el servicio en EasyPanel

1. En tu proyecto de EasyPanel → **+ Create Service** → **Compose**.
2. Fuente: conectá el repositorio de GitHub (branch `master`) o subí el código.
3. EasyPanel detecta el `docker-compose.yml` de la raíz. No hace falta tocarlo.
4. En **Domains**, agregá tu dominio y apuntalo al puerto **8000**. Activá HTTPS.

---

## 3. Variables de entorno (pestaña **Environment** del servicio)

Pegá esto y completá los valores. **No subas el `.env`** — estas van en EasyPanel.

```
# --- Envío por SMTP (Zoho, dominio propio autenticado SPF/DKIM/DMARC) ---
SENDER_BACKEND=smtp
SMTP_HOST=smtppro.zoho.com
SMTP_PORT=465
SMTP_USER=contacto@aeltra.company
SMTP_PASS=<app password de Zoho>
FROM_NAME=Aeltra
FROM_EMAIL=contacto@aeltra.company
PLAIN_TEXT_ONLY=true

# --- Lectura de respuestas por IMAP (mismo buzón Zoho) ---
IMAP_HOST=imappro.zoho.com
IMAP_PORT=993
IMAP_USER=contacto@aeltra.company
IMAP_PASS=<mismo app password de Zoho>

# --- Prospección ---
PROSPECTS_MOCK=false
APIFY_TOKEN=...

# --- Seguridad / compliance (CRÍTICO en producción) ---
BASIC_AUTH_USER=aeltra
BASIC_AUTH_PASS=<una-contraseña-fuerte>
UNSUB_BASE=https://TU-DOMINIO/api/baja      # <-- NO localhost. El dominio público del servicio.

# --- Ritmo de envío ---
DEFAULT_WINDOW_HOURS=6
DAILY_SEND_CAP=40
```

> Los valores de Zoho (SMTP/IMAP) los tenés en tu `.env` local. El **App Password** es el mismo para SMTP e IMAP.

> **`UNSUB_BASE`**: cada mail lleva el link de baja apuntando acá. Si queda en `localhost`,
> los destinatarios **no pueden desuscribirse** (problema legal y de reputación). Poné el dominio público.

> **`BASIC_AUTH_USER/PASS`**: sin esto, la app queda **abierta al público** en internet.
> La página de baja (`/api/baja`) queda accesible igual, sin auth (así los destinatarios pueden bajarse).

---

## 4. Deploy

- **Deploy** en EasyPanel. Construye la imagen con el `Dockerfile` y levanta el contenedor.
- El volumen `aeltra-data` guarda `aeltra.db` en `/data` → los contactos/campañas/pipeline persisten.
- Healthcheck automático contra `GET /api/health` (ya configurado en el compose).

Verificá que arrancó:
```
https://TU-DOMINIO/api/health
```
Debería devolver `"ok": true` y `"sender_ready": true`.

---

## 5. Qué corre en el contenedor (la máquina de outbound completa)

**Todo el outbound funciona 24/7 en el contenedor, sin Claude Max ni tokens de API:**
- Prospección real (Apify), pipeline, dashboard, historial, baja (opt-out).
- **Secuencia de 3 pasos** con follow-ups condicionales (24h/48h).
- **Detección de respuestas por IMAP** (Zoho) → frena follow-ups + marca "respondió".
- Envío por SMTP (Zoho) con tope diario y texto plano.
- Métricas de entrega/respuesta.

Los copys ya van escritos (se cargan en el lanzador de Secuencia), así que **no hace falta
que las agentes "piensen" con IA** para mandar. En `/api/health` vas a ver `"claude_max_cli": false`
y `"reply_backend": "imap"` — es lo esperado.

> Si en el futuro querés que Vera/Nico redacten copy con Claude Max, eso se hace desde tu
> Visual Studio Code local (tu sesión de Claude Max); el envío y el seguimiento igual corren en el server.

---

## 6. Actualizar (re-deploy)

Push a `master` → **Deploy** en EasyPanel. La base no se toca (está en el volumen).

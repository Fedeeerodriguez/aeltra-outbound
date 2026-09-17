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
SENDER_BACKEND=gmail_oauth
GMAIL_CLIENT_ID=...
GMAIL_CLIENT_SECRET=...
GMAIL_REFRESH_TOKEN=...
GMAIL_SENDER=contacto.aeltra@gmail.com
FROM_NAME=Aeltra
FROM_EMAIL=contacto.aeltra@gmail.com

PROSPECTS_MOCK=false
APIFY_TOKEN=...

# --- Seguridad / compliance (CRÍTICO en producción) ---
BASIC_AUTH_USER=aeltra
BASIC_AUTH_PASS=<una-contraseña-fuerte>
UNSUB_BASE=https://TU-DOMINIO/api/baja      # <-- NO localhost. Tiene que ser el dominio público.

# --- Ritmo de envío ---
DEFAULT_WINDOW_HOURS=6
DAILY_SEND_CAP=40
```

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

## 5. ⚠️ Límite importante: los agentes con Claude Max NO piensan en el contenedor

Los agentes de la oficina (Nico/Vera/Lupe/Tino con Claude Max) corren vía el CLI `claude -p`,
que **no está autenticado dentro del contenedor**. En `/api/health` vas a ver `"claude_max_cli": false`.

**Qué SÍ funciona en producción (sin tokens de API, sin Claude Max):**
- Prospección real (Apify), pipeline, dashboard, historial, y la baja (opt-out).
- Envío paceado con tope diario real.
- Crear campañas por el motor: endpoint `POST /api/campanias/crear_manual` (el copy va escrito).

**Qué NO funciona en el contenedor:** que Vera/Nico "piensen" el copy solos con Claude Max.
Para eso, por ahora, usás los agentes en tu Visual Studio Code local (tu sesión de Claude Max)
y las campañas se cargan por el motor. Resolver Claude Max 24/7 en el contenedor es un tema aparte
(requiere autenticar el CLI dentro del container) y lo encaramos después si lo querés.

---

## 6. Actualizar (re-deploy)

Push a `master` → **Deploy** en EasyPanel. La base no se toca (está en el volumen).

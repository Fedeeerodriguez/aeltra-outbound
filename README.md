# Aeltra Outbound

Motor de outbound + email marketing de **Aeltra**. Le hablás en lenguaje natural
("buscá 30 e-commerce en Argentina y mandales un mail en 3 horas") y el
**agente orquestador** (LangGraph) busca prospectos → escribe el copy B2B →
personaliza → **envía paceado** en la ventana que pediste → registra todo en el
pipeline → te reporta.

Ver el diseño completo en [`PLAN_DE_ACCION.md`](PLAN_DE_ACCION.md).

## Arranque rápido

```bash
cd C:\aeltra-outreach
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env        # y completá las claves (ver abajo)
.venv\Scripts\python db.py    # crea la base
.venv\Scripts\uvicorn app:app --port 8000
```

Abrí **http://localhost:8000** → dashboard.

> Funciona **sin claves** en modo demo: `PROSPECTS_MOCK=true` genera prospectos
> falsos y, sin `ANTHROPIC_API_KEY`, el copywriter usa una plantilla sólida de
> fallback. Así probás el flujo completo antes de conectar nada real.

## Configuración (`.env`)

| Variable | Para qué |
|---|---|
| `ANTHROPIC_API_KEY` | Agentes de copy / búsqueda / orquestador (Claude) |
| `SMTP_USER` / `SMTP_PASS` | Envío por Gmail (App Password) |
| `APIFY_TOKEN` | Scraping real de Google Maps (si vacío → mock) |
| `PROSPECTS_MOCK` | `true` = prospectos falsos para probar |
| `DAILY_SEND_CAP` | Tope de seguridad de envíos/día (default 40) |

### Gmail App Password (paso a paso)
1. Entrá a la cuenta **aeltra.contacto@gmail.com**.
2. Activá **Verificación en 2 pasos** (myaccount.google.com/security).
3. Generá una **contraseña de aplicación**: myaccount.google.com/apppasswords
   → "Correo" → copiá los 16 caracteres **sin espacios**.
4. Pegala en `SMTP_PASS` del `.env`. Listo.

## Cómo se usa

- **Lanzar campaña:** dashboard → escribís el objetivo → el orquestador hace todo.
- **Importar CSV:** columnas `nombre,email,empresa` (opcional `nicho,pais`).
- **Envío de prueba:** mandá un mail a tu casilla para validar el SMTP.
- **Baja:** cada mail lleva pie con link de baja → cae en la lista de supresión
  y nunca más se le escribe.

## Arquitectura

```
app.py            API FastAPI + sirve la dashboard (static/index.html)
worker.py         loop que envía la cola cuando cada mail vence (pacing)
db.py / pipeline  SQLite: contactos, campañas, plantillas, envíos, supresión
sender/           envío pluggable (Gmail SMTP; swappable a Resend/SES/Smartlead)
agents/
  orchestrator.py  supervisor LangGraph: intake→search→write→execute→resumen
  search_agent.py  busca y carga prospectos al pipeline
  copywriter.py    copy B2B con el playbook investigado
  prospect_sources Apify (Google Maps) + búsqueda web + mock
  tools.py         herramientas de agente — incl. envio_email
  emailing.py      merge de {{nombre}} + pie de baja + envío atómico
  playbook.py      técnicas de cold email B2B (2026)
```

## Automatización (rutinas) + disparo manual
- **Manual:** desde la dashboard (Lanzar campaña) o hablándole a un agente en la pestaña **Agentes**.
- **Automático:** panel **⏰ Automatización** → creás rutinas por horario (ej: "todos los días 09:00 buscá 100 prospectos, sin enviar" o "campaña completa"). El scheduler (`scheduler.py`) las dispara solo. Cada rutina también tiene ▶ para dispararla a mano.

## Deploy 24/7 (para que corra sin tu PC, como Optimizar)
El worker de envío y el scheduler de rutinas son tareas asyncio dentro del mismo
proceso: **si el server corre 24/7, todo se dispara solo.**
1. Subí `C:\aeltra-outreach` a un repo de GitHub.
2. En **Render** → New → Blueprint → apuntá a `render.yaml`.
3. Cargá las variables (`ANTHROPIC_API_KEY`, `SMTP_USER`, `SMTP_PASS`, `FROM_EMAIL`,
   `APIFY_TOKEN`, y `UNSUB_BASE` con tu URL pública).
4. Deploy. Queda en `https://<tu-app>.onrender.com` corriendo 24/7.

> Opcional (100% estilo Optimizar): además del deploy, se puede armar un
> *scheduled cloud agent* de Claude Code que le pegue a los endpoints para
> orquestar campañas en horarios — avisame y lo montamos.

## ⚠️ Deliverability y legal
Cold email a volumen con Gmail gratis **se satura/banea rápido**. Para arrancar y
probar (decenas/día) sirve; para cientos/día conviene **dominio propio + Google
Workspace + proveedor dedicado** (Resend/SES/Smartlead) con warmup. El sistema ya
incluye supresión (opt-out), identificación del remitente y pie de baja; el uso
responsable (Ley 25.326 AR, GDPR/CAN-SPAM si aplica) es del operador. Empezá tibio
(20–40/día) y subí de a poco.

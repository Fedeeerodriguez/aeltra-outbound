# Aeltra Outbound — Plan de Acción

> Motor de outbound + email marketing de **Aeltra** (la marca matriz).
> Software propio, simple para arrancar, con un **agente orquestador** que dirige a sub-agentes de búsqueda, copywriting y envío.
> Fecha: 2026-09-14 · Estado: **plan aprobado / build pendiente**

---

## 1. Objetivo

Tener una máquina bajo demanda a la que le decís en lenguaje natural:

> *"Buscá 300 dueños de e-commerce en Argentina y mandales un mail personalizado en las próximas 6 horas."*

…y ella sola: **busca los prospectos → escribe el copy → los personaliza → los envía paceados en el tiempo → registra todo en un pipeline → te reporta resultados.**

Publicitamos con la **marca grande (Aeltra)**, no con Fluvo. Aeltra = casa creativa de software & IA; el mail vende "te construimos el sistema que te recupera ventas".

---

## 2. Principios de diseño

- **Simple para arrancar** — SQLite + FastAPI + una dashboard HTML. Sin Kubernetes, sin colas externas.
- **Todo pluggable** — el proveedor de envío y la fuente de prospectos se pueden cambiar sin tocar el resto.
- **El costo de IA es bajo** — la IA escribe **una plantilla por campaña** (pocas llamadas caras); el envío de cada mail es **merge de variables `{{nombre}}`, sin IA**. Así 300 o 3000 mails cuestan casi lo mismo en tokens.
- **Cumplimiento desde el día 1** — lista de supresión (opt-out), pie con identificación del remitente y baja, y ritmo de envío que cuida la reputación del dominio.

---

## 3. Arquitectura (visión)

```
                    ┌──────────────────────────────────────────┐
   Vos (lenguaje    │        AGENTE ORQUESTADOR (supervisor)     │
   natural)  ─────► │  parsea objetivo → arma "brief de campaña" │
                    │  decide el próximo paso hasta cumplir meta │
                    └───┬─────────┬──────────┬──────────┬────────┘
                        │         │          │          │
              ┌─────────▼──┐  ┌───▼─────┐ ┌──▼──────┐ ┌─▼──────────┐
              │ AGENTE     │  │ AGENTE  │ │ QA /    │ │ EJECUTOR   │
              │ BÚSQUEDA   │  │ COPY    │ │ COMPLI- │ │ (pacer +   │
              │ (prospec-  │  │ (writer │ │ ANCE    │ │ worker)    │
              │  tos)      │  │  B2B)   │ │         │ │            │
              └─────┬──────┘  └────┬────┘ └────┬────┘ └─────┬──────┘
                    │              │           │            │
                    ▼              ▼           ▼            ▼
              buscar_prospectos  plantilla   supresión   herramienta
              (web / Apify /     + variantes  + spam-     envio_email
               CSV)              A/B          check       (merge+send)
                    │                                        │
                    └────────────────┬───────────────────────┘
                                     ▼
                          ┌────────────────────┐
                          │  PIPELINE (SQLite)  │
                          │ contactos, campañas,│
                          │ envíos, eventos     │
                          └────────────────────┘
```

### 3.1 El agente orquestador (mi lógica propuesta)

Patrón **supervisor** de LangGraph. Recibe un objetivo en texto y mantiene un **estado de campaña** (grafo con memoria). En cada ciclo decide la próxima acción y enruta al sub-agente correspondiente, hasta que la meta se cumple.

**Estado que lleva:** `objetivo`, `brief` (nicho, país, cantidad, ventana horaria, ángulo), `prospectos[]`, `plantilla`, `enviados`, `pendientes`, `errores`, `metricas`.

**Máquina de decisión (simplificada):**
1. **INTAKE** → convierte tu frase en un `brief` estructurado (cantidad=300, ventana=6h, nicho=e-commerce AR, objetivo=agendar llamada). Si falta algo crítico, pregunta.
2. **¿Tengo suficientes prospectos válidos?** → No: llama al **agente de búsqueda**. Sí: sigue.
3. **¿Tengo copy aprobado?** → No: llama al **agente de copy** (genera plantilla + 1-2 variantes A/B con placeholders `{{nombre}}`). Sí: sigue.
4. **QA/Compliance** → filtra supresión, valida emails, revisa palabras spam, agrega pie de baja.
5. **EJECUTOR** → calcula el ritmo (300 mails / 6h ≈ 1 cada 72s) y **encola** los envíos con `scheduled_at` escalonado. El worker en background dispara `envio_email` cuando cada uno vence.
6. **MONITOR** → mientras se envía, reporta progreso (enviados/pendientes/fallos) y actualiza el pipeline. Al terminar, resumen.

> Le doy libertad al orquestador para **replanificar**: si la búsqueda trae 220 en vez de 300, decide si busca más, o arranca con 220 y avisa. Si el SMTP empieza a rebotar, baja el ritmo solo.

### 3.2 Sub-agentes

| Agente | Rol | Herramientas |
|---|---|---|
| **Búsqueda** | Encontrar prospectos del nicho + email válido. Deduplica contra el pipeline. | `buscar_prospectos` (web search / Apify Google Maps / import CSV), `validar_email` |
| **Copywriter B2B** | Escribir asunto + cuerpo (50–125 palabras) con las técnicas del §5, con placeholders. Genera variantes A/B. | — (genera texto; guarda plantilla) |
| **QA/Compliance** | Supresión, validación, spam-check, pie legal. | `chequear_supresion`, `spam_score` |
| **Ejecutor** | Pacing + envío real. | **`envio_email`** (la herramienta estrella) |

### 3.3 La herramienta `envio_email` (spec)

Herramienta de agente. Firma:

```
envio_email(email: str, nombre: str, asunto: str, cuerpo: str,
            variables: dict = {}, campania_id: int = None) -> dict
```

Qué hace, en orden:
1. **Chequea supresión** → si el email está en opt-out, devuelve `{status: "skipped"}` sin enviar.
2. **Merge de variables** → reemplaza `{{nombre}}`, `{{email}}` y cualquier `variables` extra en asunto y cuerpo.
3. **Agrega pie** → identificación de Aeltra + link/mailto de baja.
4. **Envía** vía el `Sender` configurado (Gmail SMTP por defecto).
5. **Registra** en la tabla `envios` (sent / failed / skipped) y avanza el estado del contacto en el pipeline.
6. Devuelve `{status, message_id, error?}`.

La usan **el worker** (para el lote paceado) y **vos** (para un envío de prueba desde la dashboard).

---

## 4. Modelo de datos (pipeline)

- **contactos** — `id, nombre, email, empresa, nicho, pais, fuente, estado, notas, created_at`
  - estados: `prospecto → contactado → abrió → respondió → llamada_agendada → cliente → descartado`
- **campanias** — `id, nombre, objetivo, brief_json, plantilla_id, estado, cantidad_objetivo, ventana_horas, created_at`
- **plantillas** — `id, campania_id, variante, asunto, cuerpo, created_at`
- **envios** — `id, contacto_id, campania_id, plantilla_id, status, scheduled_at, sent_at, message_id, error`
- **supresion** — `email, motivo (baja/rebote/queja), created_at`
- **eventos** — `id, contacto_id, tipo (envio/apertura/respuesta/baja), payload, created_at`

---

## 5. Playbook de copywriting B2B (investigado)

Reglas que van **baked** en el prompt del agente de copy (fuentes al final):

- **Personalización manda** — aperturas personalizadas: hasta **+142%** de respuestas. Nunca abrir con "Espero que estés bien" ni "Mi nombre es…". La 1ª línea es sobre **ellos**, no sobre nosotros.
- **Corto** — **50–125 palabras** (idealmente < 75). Un solo mensaje, un solo CTA.
- **Estructura ganadora (5 partes):** contexto específico → evidencia del problema del lector → costo de no actuar → prueba social → **CTA de baja fricción**.
- **Problema primero, no features** — los mails "pain-led" rinden **2–3x** más que los "feature-led" cuando el dolor es específico y real.
- **Asunto** — **3–7 palabras / 21–40 caracteres**. Números → **+113%** de aperturas; preguntas → **+21%**. Personalizado y con un beneficio o curiosidad.
- **3 niveles de personalización:** T1 merge fields (nombre/empresa/rol) · T2 trigger event (ronda, nuevo puesto, contenido publicado) · T3 research profundo (dolor puntual, conexión mutua, noticia reciente).
- **CTA único y fácil** — "¿te muestro en 15 min cómo lo haría con tu tienda?" en vez de "agendá una demo de 1 hora".
- **Benchmarks 2026:** apertura 15–25%, respuesta 2–5% (top 10–25%), conversión 0,5–1%. Meta nuestra: respuesta ≥ 5%.

---

## 6. Stack técnico

| Capa | Tecnología |
|---|---|
| Orquestación de agentes | **LangGraph** (supervisor + estado) |
| Agentes / LLM | **LangChain** + `langchain-anthropic` → `claude-opus-5` (pocas llamadas caras; envío sin IA) |
| Backend / API | **FastAPI** + Uvicorn |
| Base de datos | **SQLite** (→ PostgreSQL cuando escale) |
| Envío | `Sender` pluggable → **Gmail SMTP (App Password)** por defecto; migrable a Resend/SES/Smartlead |
| Pacing | worker asyncio en background (cola con `scheduled_at`) |
| Fuente prospectos | pluggable: web search · Apify (Google Maps) modo mock · import CSV |
| Frontend | 1 dashboard HTML (vanilla) contra la API |

**Ubicación:** `C:\aeltra-outreach` (ruta corta — evita el problema de Long Path de Windows al instalar LangChain, como nos pasó con el agente de Fluvo).

---

## 7. Roadmap por fases

- **Fase 0 — Cuenta de envío (vos + yo)**
  - Crear el Gmail de Aeltra (te doy los pasos; la cuenta la creás vos por el captcha/teléfono).
  - Activar verificación en 2 pasos + generar **App Password** para SMTP.
  - *Nota:* para volumen real conviene dominio propio (aeltra.com) + Google Workspace; SMTP de Gmail gratis se satura/banea rápido en cold email.

- **Fase 1 — Núcleo (backend + pipeline)**
  - Modelo de datos + FastAPI CRUD de contactos/campañas.
  - `Sender` SMTP + herramienta **`envio_email`** + tabla de supresión + pie de baja.
  - Import de contactos por CSV.

- **Fase 2 — Agentes**
  - Agente de copy B2B (playbook §5) → genera plantilla + variantes.
  - Agente de búsqueda (mock + web) → llena el pipeline.
  - **Orquestador** (LangGraph supervisor) que los coordina.

- **Fase 3 — Ejecución paceada**
  - Worker en background + cola `scheduled_at` → "300 en 6h".
  - Monitor/reportes en la dashboard (enviados/pendientes/fallos, tasa de respuesta).

- **Fase 4 — Dashboard**
  - Vista pipeline (kanban simple), lanzar campaña, ver copy, ver métricas.

- **Fase 5 — Escala y deliverability** *(cuando haya tracción)*
  - Dominio propio + warmup + proveedor pro (Resend/SES/Smartlead), seguimiento (follow-ups), tracking de apertura/respuesta.

---

## 8. Deliverability y legal (honesto)

- **Cold email a volumen con Gmail gratis = riesgo de baneo.** Sirve para probar (decenas/día); para cientos/día hace falta dominio propio + warmup + proveedor dedicado.
- **Legal** — identificar al remitente, incluir baja real, respetar opt-outs (lo hace la supresión). En Argentina aplica la Ley 25.326 de Protección de Datos; en envíos a UE/EE.UU., GDPR / CAN-SPAM. El software incluye los mecanismos; el uso responsable es tuyo.
- **Empezá tibio** — 20–40 mails/día la 1ª semana e ir subiendo, para no quemar el dominio.

---

## 9. Decisiones abiertas (para vos)

1. **Nombre del Gmail** — `hola@` / `contacto@` / `federico@` … ¿cuál? (con dominio propio queda más pro que `@gmail.com`).
2. **¿Arrancamos con Gmail SMTP** (rápido, gratis, limitado) **o vas directo a dominio + proveedor** (más setup, escala)?
3. **Fuente de prospectos inicial** — ¿tenés listas/CSV, querés que el agente scrapee Google Maps (Apify), o búsqueda web?

---

## Fuentes (copywriting B2B)
- Instantly — Cold Email Ultimate Guide 2026 · https://instantly.ai/blog/cold-email/
- Autobound — Cold Email Guide 2026 (benchmarks) · https://www.autobound.ai/blog/cold-email-guide-2026
- Clay — B2B Cold Email Copywriting 2026 · https://www.clay.com/blog/b2b-cold-email-copywriting
- Attaché — B2B Cold Email Frameworks 2026 · https://attacheai.io/blog/b2b-cold-email-copywriting-and-frameworks
- ZoomInfo — How to Write a Cold Email That Gets Replies 2026 · https://pipeline.zoominfo.com/sales/how-to-write-one-great-cold-email
- Leadfeeder — B2B Subject Lines + Framework · https://www.leadfeeder.com/blog/conversion-optimization/b2b-email-subject-lines/

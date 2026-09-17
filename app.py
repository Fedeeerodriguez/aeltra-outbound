# -*- coding: utf-8 -*-
"""Aeltra Outbound · API FastAPI + dashboard."""
import os
import csv
import io
import asyncio
from urllib.parse import unquote

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

import config
import activity
import pipeline
import worker
import scheduler
import claude_bridge
from db import init_db, get_conn
from worker import run_loop
from agents.orchestrator import lanzar_campania, parse_brief
from agents import search_agent, copywriter
from agents.emailing import enviar_core

app = FastAPI(title="Aeltra Outbound")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def _basic_auth(request, call_next):
    """Si BASIC_AUTH_USER/PASS están seteados, exige auth en todo menos la baja."""
    if config.BASIC_AUTH_USER and config.BASIC_AUTH_PASS and not request.url.path.startswith("/api/baja"):
        import base64
        import secrets
        from starlette.responses import Response
        hdr = request.headers.get("authorization", "")
        ok = False
        if hdr.startswith("Basic "):
            try:
                u, _, p = base64.b64decode(hdr[6:]).decode().partition(":")
                ok = (secrets.compare_digest(u, config.BASIC_AUTH_USER)
                      and secrets.compare_digest(p, config.BASIC_AUTH_PASS))
            except Exception:
                ok = False
        if not ok:
            return Response(status_code=401, content="Auth requerida",
                            headers={"WWW-Authenticate": 'Basic realm="Aeltra"'})
    return await call_next(request)

INDEX = os.path.join(config.BASE_DIR, "static", "index.html")


@app.on_event("startup")
async def _startup():
    init_db()
    asyncio.create_task(run_loop())            # worker de envío paceado
    asyncio.create_task(scheduler.run_loop())  # motor de rutinas automáticas


# ── Modelos de request ──
class LanzarReq(BaseModel):
    objetivo: str

class TestReq(BaseModel):
    email: str
    nombre: str = ""
    asunto: str = "Prueba Aeltra {{nombre}}"
    cuerpo: str = "Hola {{nombre}}, esto es un envío de prueba de Aeltra."

class ChatReq(BaseModel):
    mensaje: str

class RutinaReq(BaseModel):
    nombre: str
    tipo: str = "busqueda"        # busqueda | campania
    instruccion: str
    hora: str = "09:00"
    frecuencia: str = "diaria"
    motor: str = "engine"         # engine (Python) | claude (agentes .md)

class ClaudeRunReq(BaseModel):
    agente: str = "aeltra-orquestador"
    objetivo: str

class CrearManualReq(BaseModel):
    objetivo: str = ""
    nicho: str
    pais: str = "Argentina"
    cantidad: int = 25
    ventana_horas: float = 6.0
    asunto: str
    cuerpo: str
    fuentes: list = ["apify", "web"]


# ── UI ──
@app.get("/", response_class=HTMLResponse)
def home():
    return FileResponse(INDEX)


# ── Pipeline ──
@app.get("/api/stats")
def api_stats():
    return pipeline.stats()

@app.get("/api/contactos")
def api_contactos(estado: str = None):
    return pipeline.list_contacts(estado)

@app.get("/api/campanias")
def api_campanias():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM campanias ORDER BY id DESC LIMIT 50").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/envios")
def api_envios(status: str = None, limit: int = 100):
    conn = get_conn()
    if status:
        rows = conn.execute("SELECT * FROM envios WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM envios ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/contactos/import")
async def api_import(file: UploadFile = File(...)):
    raw = (await file.read()).decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(raw))
    n = 0
    for row in reader:
        low = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        email = low.get("email") or low.get("correo") or low.get("mail")
        if not email:
            continue
        cid = pipeline.add_contact(
            low.get("nombre") or low.get("name"), email,
            low.get("empresa") or low.get("company"),
            low.get("nicho"), low.get("pais") or low.get("país"), "csv",
        )
        if cid:
            n += 1
    return {"importados": n}


# ── Campañas ──
# NOTA: /api/campanias/lanzar fue ELIMINADO. Usaba el LLM del motor (API con tokens).
# Las campañas ahora las arma el orquestador .md con Claude Max y llaman a crear_manual.

@app.post("/api/campanias/crear_manual")
async def api_crear_manual(req: CrearManualReq):
    """Crea una campaña SIN usar la API/LLM del motor: el copy ya viene escrito por un
    agente de Claude Code (Claude Max). El motor solo busca prospectos (Apify), guarda la
    plantilla con ese copy y encola los envíos paceados. Cero tokens de API."""
    def _run():
        from datetime import datetime, timedelta
        brief = {"objetivo": req.objetivo or req.nicho, "nicho": req.nicho, "pais": req.pais,
                 "cantidad": int(req.cantidad), "ventana_horas": float(req.ventana_horas),
                 "fuentes": list(req.fuentes) or ["apify", "web"]}
        activity.update("orquestador", "trabajando", f"Creando campaña «{req.nicho}» (Claude Max, sin API)…", 15)
        cid = pipeline.create_campania(
            nombre=f"Campaña {datetime.now():%Y-%m-%d %H:%M}",
            objetivo=brief["objetivo"], brief=brief,
            cantidad_objetivo=brief["cantidad"], ventana_horas=brief["ventana_horas"])
        prospectos = search_agent.buscar(brief)
        pid = pipeline.create_plantilla(cid, req.asunto, req.cuerpo, "A")
        n = len(prospectos); ventana_h = brief["ventana_horas"]
        intervalo = (ventana_h * 3600.0 / n) if n else 0
        ahora = datetime.utcnow(); encolados = 0
        for i, p in enumerate(prospectos):
            sched = (ahora + timedelta(seconds=i * intervalo)).isoformat(timespec="seconds")
            pipeline.enqueue_envio(p["contacto_id"], cid, pid, p["email"], sched)
            encolados += 1
        try:
            ids = [p.get("contacto_id") for p in prospectos if p.get("contacto_id")]
            if ids:
                conn = get_conn()
                conn.executemany("UPDATE contactos SET campania_id=? WHERE id=?", [(cid, i) for i in ids])
                conn.commit(); conn.close()
        except Exception:
            pass
        pipeline.log_agente("orquestador", f"Campaña: {req.objetivo or req.nicho}",
                            f"Encolados {encolados}. Asunto: {req.asunto}")
        activity.update("orquestador", "listo",
                        f"Campaña #{cid} lista ✅ {encolados} encolados (1 cada {round(intervalo)}s).", 100,
                        resultado=(f"Campaña #{cid}\nObjetivo: {brief['objetivo']}\n"
                                   f"Nicho: {req.nicho} · {req.pais}\n"
                                   f"Encolados: {encolados} de {brief['cantidad']} "
                                   f"(1 cada {round(intervalo)}s · ventana {ventana_h}h)\n\n"
                                   f"Asunto: {req.asunto}\n\n{req.cuerpo}"),
                        titulo=f"Campaña #{cid} armada")
        return {"campania_id": cid, "encolados": encolados, "objetivo": brief["cantidad"],
                "asunto": req.asunto, "intervalo_seg": round(intervalo, 1)}
    return await run_in_threadpool(_run)


@app.get("/api/campanias/{cid}")
def api_campania_detalle(cid: int):
    conn = get_conn()
    try:
        c = conn.execute("SELECT * FROM campanias WHERE id=?", (cid,)).fetchone()
        if not c:
            return JSONResponse({"error": "no existe"}, status_code=404)
        pl = conn.execute("SELECT asunto,cuerpo,variante FROM plantillas "
                          "WHERE campania_id=? ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
        counts = {}
        for row in conn.execute("SELECT status, COUNT(*) n FROM envios "
                                "WHERE campania_id=? GROUP BY status", (cid,)):
            counts[row["status"]] = row["n"]
        d = dict(c)
        d["plantilla"] = dict(pl) if pl else None
        d["envios"] = counts
        d["total"] = sum(counts.values())
        return d
    finally:
        conn.close()


# ── Pipeline (estados de cliente) ──
class MoverReq(BaseModel):
    id: int
    estado: str

@app.get("/api/pipeline")
def api_pipeline():
    return {"estados": pipeline.PIPELINE_ESTADOS, "contactos": pipeline.contactos_pipeline()}

@app.post("/api/pipeline/mover")
def api_pipeline_mover(req: MoverReq):
    pipeline.mover_contacto(req.id, req.estado)
    return {"ok": True}

@app.post("/api/pipeline/auto")
def api_pipeline_auto():
    return {"movidos": pipeline.auto_no_respondio()}


# ── Dashboard (métricas) ──
@app.get("/api/dashboard")
def api_dashboard():
    return pipeline.metricas()


# ── Historial por agente ──
@app.get("/api/agentes/{slot}/historial")
def api_historial(slot: str):
    return pipeline.historial_agente(slot)


@app.post("/api/test-envio")
async def api_test(req: TestReq):
    return await run_in_threadpool(
        enviar_core, req.email, req.nombre, req.asunto, req.cuerpo, None, None
    )


# ── Baja (opt-out) ──
@app.get("/api/baja", response_class=HTMLResponse)
def api_baja(email: str = ""):
    email = unquote(email)
    if email:
        pipeline.add_supresion(email, "baja")
    return HTMLResponse(
        "<div style='font:16px/1.6 Arial;max-width:520px;margin:80px auto;text-align:center'>"
        "<h2>Listo ✅</h2><p>Diste de baja <b>%s</b>. No vas a recibir más correos nuestros.</p>"
        "<p style='color:#889'>Aeltra · Software &amp; IA</p></div>" % (email or "tu correo")
    )


# ── Agentes (estado en vivo + chat directo) ──
@app.get("/api/agentes")
def api_agentes():
    return activity.snapshot()


async def _bg(agente, fn, *args):
    try:
        await run_in_threadpool(fn, *args)
    except Exception as e:
        activity.update(agente, "error", f"Error: {e}")


@app.post("/api/agentes/{agente}/chat")
async def api_agente_chat(agente: str, req: ChatReq):
    msg = (req.mensaje or "").strip()
    if not msg:
        return {"respuesta": "Escribime algo 🙂"}

    if agente == "busqueda":
        brief = parse_brief(msg)
        asyncio.create_task(_bg("busqueda", search_agent.buscar, brief))
        return {"respuesta": f"Dale — busco {brief['cantidad']} de «{brief['nicho']}» en "
                             f"{brief['pais']} y los guardo en la base. NO envío nada. "
                             f"Seguí el progreso acá en la tarjeta."}

    if agente in ("copywriter", "orquestador"):
        # ELIMINADO: estas ramas usaban el LLM del motor (API con tokens).
        # El copy y la orquestación ahora los hace Claude Max vía /api/claude/run.
        return {"respuesta": "Este agente ahora trabaja con Claude Max. "
                             "Usá /api/claude/run (el front ya lo hace)."}

    if agente == "ejecutor":
        low = msg.lower()
        if any(k in low for k in ["pausa", "pausá", "para", "pará", "frena", "frená", "deten", "stop"]):
            worker.pause()
            return {"respuesta": "⏸ Envío pausado. Los correos quedan en cola."}
        if any(k in low for k in ["reanud", "segu", "continu", "resume", "arranc", "play", "dale"]):
            worker.resume()
            return {"respuesta": "▶ Envío reanudado."}
        st = pipeline.stats()
        return {"respuesta": f"Estado: {st['enviados']} enviados · {st['en_cola']} en cola · "
                             f"{st['fallidos']} fallidos. Decime «pausá» o «reanudá» para controlarme."}

    return {"respuesta": "No conozco ese agente."}


# ── Rutinas automáticas (scheduler) ──
@app.get("/api/rutinas")
def api_rutinas():
    return scheduler.list_rutinas()

@app.post("/api/rutinas")
def api_rutina_add(req: RutinaReq):
    rid = scheduler.add_rutina(req.nombre, req.tipo, req.instruccion, req.hora, req.frecuencia, req.motor)
    return {"id": rid}

@app.post("/api/rutinas/{rid}/toggle")
def api_rutina_toggle(rid: int):
    scheduler.toggle_rutina(rid)
    return {"ok": True}

@app.post("/api/rutinas/{rid}/run")
async def api_rutina_run(rid: int):
    return {"ok": scheduler.disparar_ya(rid)}

@app.delete("/api/rutinas/{rid}")
def api_rutina_del(rid: int):
    scheduler.delete_rutina(rid)
    return {"ok": True}


# ── Puente a los agentes .md de Claude Code ──
@app.get("/api/claude/agentes")
def api_claude_agentes():
    return ["aeltra-orquestador", "aeltra-buscador", "aeltra-copywriter", "aeltra-ejecutor"]

@app.post("/api/claude/run")
async def api_claude_run(req: ClaudeRunReq):
    asyncio.create_task(_bg(claude_bridge.act_slot(req.agente),
                            claude_bridge.run_agent, req.agente, req.objetivo))
    return {"respuesta": f"Disparé el agente Claude Code «{req.agente}». "
                         f"Mirá el progreso en la pestaña Agentes (tarda ~1-2 min)."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)

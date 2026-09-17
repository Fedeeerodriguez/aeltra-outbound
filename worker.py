# -*- coding: utf-8 -*-
"""Worker de envío paceado: procesa la cola `envios` cuando cada uno vence."""
import asyncio
from datetime import datetime

import activity
import pipeline
from db import get_conn
from agents.emailing import enviar_core

# pausa global del envío (la controla el agente Ejecutor desde la pestaña Agentes)
PAUSED = False

def pause():
    global PAUSED
    PAUSED = True
    activity.update("ejecutor", "idle", "⏸ Envío en pausa (los correos siguen en cola).")

def resume():
    global PAUSED
    PAUSED = False
    activity.update("ejecutor", "trabajando", "▶ Envío reanudado.")


def _load_plantilla(pid):
    conn = get_conn()
    r = conn.execute("SELECT asunto,cuerpo FROM plantillas WHERE id=?", (pid,)).fetchone()
    conn.close()
    return dict(r) if r else None


def _load_contacto(cid):
    conn = get_conn()
    r = conn.execute("SELECT * FROM contactos WHERE id=?", (cid,)).fetchone()
    conn.close()
    return dict(r) if r else None


def process_once(limit=10) -> int:
    """Envía los correos vencidos. Devuelve cuántos procesó."""
    if PAUSED:
        return 0
    now = datetime.utcnow().isoformat(timespec="seconds")
    due = pipeline.due_envios(now, limit)
    for e in due:
        pl = _load_plantilla(e["plantilla_id"])
        c = _load_contacto(e["contacto_id"])
        if not pl or not c:
            pipeline.mark_envio(e["id"], "failed", error="falta plantilla/contacto")
            continue
        activity.update("ejecutor", "trabajando", f"Enviando a {c['email']}…")
        res = enviar_core(
            c["email"], c.get("nombre"), pl["asunto"], pl["cuerpo"],
            variables={"empresa": c.get("empresa")}, contacto_id=c["id"],
        )
        pipeline.mark_envio(e["id"], res["status"], res.get("message_id"), res.get("error"))
        if res["status"] == "sent":
            pipeline.marcar_enviado(c["id"])           # pasa al estado 'enviado' del pipeline
            pipeline.log_agente("ejecutor", f"Envío a {c['email']}", f"Asunto: {pl['asunto']}", True)
            activity.update("ejecutor", "trabajando", f"✅ Enviado a {c['email']}")
        elif res["status"] == "failed":
            activity.update("ejecutor", "error", f"❌ Falló {c['email']}: {res.get('error','')}")
    if due:
        st = pipeline.stats()
        activity.update("ejecutor", "trabajando",
                        f"{st['enviados']} enviados · {st['en_cola']} en cola · {st['fallidos']} fallidos")
    return len(due)


async def run_loop(poll_seconds=5):
    while True:
        try:
            process_once()
        except Exception as ex:  # el worker nunca debe morir
            print("[worker] error:", ex)
        await asyncio.sleep(poll_seconds)


if __name__ == "__main__":
    # modo standalone: procesa en loop sin la API
    from db import init_db
    init_db()
    print("[worker] corriendo… Ctrl+C para salir")
    asyncio.run(run_loop())

# -*- coding: utf-8 -*-
"""Motor de automatización: dispara rutinas (búsqueda o campaña) por horario.
Corre como tarea asyncio dentro de la app; también sirve para disparo manual."""
import asyncio
from datetime import datetime

import activity
from db import get_conn
from agents.orchestrator import parse_brief, lanzar_campania
from agents import search_agent


def _hoy():
    return datetime.now().strftime("%Y-%m-%d")

def _ahora_hm():
    return datetime.now().strftime("%H:%M")


# ── CRUD de rutinas ──
def list_rutinas(solo_activas=False):
    conn = get_conn()
    q = "SELECT * FROM rutinas" + (" WHERE activa=1" if solo_activas else "") + " ORDER BY hora"
    rows = conn.execute(q).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_rutina(rid):
    conn = get_conn()
    r = conn.execute("SELECT * FROM rutinas WHERE id=?", (rid,)).fetchone()
    conn.close()
    return dict(r) if r else None

def add_rutina(nombre, tipo, instruccion, hora, frecuencia="diaria", motor="engine"):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO rutinas (nombre,tipo,instruccion,hora,frecuencia,motor) VALUES (?,?,?,?,?,?)",
        (nombre, tipo, instruccion, hora, frecuencia, motor),
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid

def toggle_rutina(rid):
    conn = get_conn()
    conn.execute("UPDATE rutinas SET activa = 1-activa WHERE id=?", (rid,))
    conn.commit()
    conn.close()

def delete_rutina(rid):
    conn = get_conn()
    conn.execute("DELETE FROM rutinas WHERE id=?", (rid,))
    conn.commit()
    conn.close()

def _set_ultimo(rid, fecha):
    conn = get_conn()
    conn.execute("UPDATE rutinas SET ultimo_run=? WHERE id=?", (fecha, rid))
    conn.commit()
    conn.close()


# ── Disparo ──
def _fire_safe(r):
    """Ejecuta una rutina (en un thread aparte). No debe romper el scheduler."""
    try:
        instr = r["instruccion"]
        if r.get("motor") == "claude":
            # dispara los agentes .md de Claude Code (headless)
            import claude_bridge
            agente = "aeltra-buscador" if r["tipo"] == "busqueda" else "aeltra-orquestador"
            claude_bridge.run_agent(agente, instr)
        elif r["tipo"] == "busqueda":
            search_agent.buscar(parse_brief(instr))
        elif r["tipo"] == "secuencia":
            # Rutina autónoma: prospecta N nuevos del nicho + encola secuencia 3 pasos
            # con el copy guardado (JSON en instruccion). Sin tokens de API.
            import json as _json
            import campaigns
            cfg = _json.loads(instr or "{}")
            campaigns.lanzar_secuencia_rutina(
                cfg.get("nicho", "constructoras"), cfg.get("pais", "Argentina"),
                int(cfg.get("cantidad", 7)), float(cfg.get("ventana_horas", 4)),
                cfg.get("pasos") or [], float(cfg.get("delay2", 24)), float(cfg.get("delay3", 48)))
        else:
            lanzar_campania(instr)
    except Exception as e:
        agente = "busqueda" if r["tipo"] == "busqueda" else "orquestador"
        activity.update(agente, "error", f"Rutina «{r['nombre']}» falló: {e}")


def disparar_ya(rid):
    r = get_rutina(rid)
    if not r:
        return False
    _set_ultimo(rid, _hoy())
    asyncio.create_task(asyncio.to_thread(_fire_safe, r))
    return True


_last_auto = None
_loops = 0

async def run_loop(poll_seconds=30):
    global _last_auto, _loops
    while True:
        try:
            now, hoy = _ahora_hm(), _hoy()
            for r in list_rutinas(solo_activas=True):
                if r.get("frecuencia", "diaria") == "diaria" and r.get("ultimo_run") != hoy and now >= (r.get("hora") or "99:99"):
                    _set_ultimo(r["id"], hoy)
                    asyncio.create_task(asyncio.to_thread(_fire_safe, r))

            # motor de secuencia (drip): encola follow-ups condicionales — cada ciclo
            try:
                import secuencia
                enc = await asyncio.to_thread(secuencia.avanzar)
                if enc:
                    print(f"[secuencia] {enc} follow-ups encolados")
            except Exception as e:
                print("[secuencia] error:", e)

            # lectura de respuestas por IMAP — cada ~3 min (6 ciclos de 30s)
            if _loops % 6 == 0:
                try:
                    import inbox as _inbox
                    res = await asyncio.to_thread(_inbox.revisar)
                    if res.get("ok") and (res.get("respondieron") or res.get("rebotes")):
                        print(f"[inbox] respuestas={res.get('respondieron')} rebotes={res.get('rebotes')}")
                except Exception as e:
                    print("[inbox] error:", e)

            # regla automática: 'enviado' sin respuesta → 'no_respondio' a los 3 días hábiles (1 vez por día)
            if _last_auto != hoy:
                _last_auto = hoy
                try:
                    import pipeline
                    n = pipeline.auto_no_respondio()
                    if n:
                        print(f"[pipeline] {n} contactos -> no_respondio (3 dias habiles)")
                except Exception as e:
                    print("[pipeline auto] error:", e)
        except Exception as e:
            print("[scheduler] error:", e)
        _loops += 1
        await asyncio.sleep(poll_seconds)

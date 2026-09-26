# -*- coding: utf-8 -*-
"""Lanzamiento de secuencias para RUTINAS autónomas.

Cada nicho tiene UNA campaña persistente ("Auto · <nicho>"): la rutina prospecta
N contactos NUEVOS por día (deduplicados, nunca re-emaila a alguien ya contactado)
y encola el paso 1 paceado. Los follow-ups (paso 2/3) los dispara secuencia.avanzar.
Sin tokens de API: el copy viene pre-escrito en la rutina.
"""
from datetime import datetime, timedelta

import pipeline
from db import get_conn
from agents import search_agent


def _find_or_create(nicho, pasos, delay2, delay3, ventana):
    """Devuelve (campania_id, {paso: plantilla_id}). Crea la campaña una sola vez por nicho."""
    nombre = f"Auto · {nicho}"
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM campanias WHERE nombre=? AND tipo='secuencia' ORDER BY id LIMIT 1",
        (nombre,)).fetchone()
    if row:
        cid = row["id"]
        pids = {r["paso"]: r["id"] for r in
                conn.execute("SELECT id,paso FROM plantillas WHERE campania_id=?", (cid,))}
        conn.close()
        return cid, pids
    conn.close()
    brief = {"objetivo": f"Auto {nicho}", "nicho": nicho, "pais": "Argentina",
             "cantidad": 0, "ventana_horas": ventana, "auto": True}
    cid = pipeline.create_campania(
        nombre=nombre, objetivo=brief["objetivo"], brief=brief,
        cantidad_objetivo=0, ventana_horas=ventana,
        tipo="secuencia", pasos_json={"delays_horas": {"2": float(delay2), "3": float(delay3)}})
    pids = {}
    for i, p in enumerate(pasos, start=1):
        asunto = p.get("asunto", "") if isinstance(p, dict) else p[0]
        cuerpo = p.get("cuerpo", "") if isinstance(p, dict) else p[1]
        pids[i] = pipeline.create_plantilla(cid, asunto, cuerpo, variante="A", paso=i)
    return cid, pids


def lanzar_secuencia_rutina(nicho, pais, cantidad, ventana_horas, pasos, delay2, delay3):
    """Prospecta hasta `cantidad` contactos NUEVOS del nicho y encola el paso 1 paceado.
    Reusa la campaña persistente del nicho. Devuelve {'campania_id','encolados'}."""
    pasos = [p for p in (pasos or []) if p][:3]
    if not pasos:
        return {"error": "faltan los copys de los pasos"}
    cid, pids = _find_or_create(nicho, pasos, delay2, delay3, ventana_horas)

    # Pedimos de más porque el dedupe descarta a los ya conocidos.
    brief = {"nicho": nicho, "pais": pais, "cantidad": max(int(cantidad) * 3, int(cantidad) + 15),
             "ventana_horas": ventana_horas, "fuentes": ["apify", "web"]}
    prospectos = search_agent.buscar(brief)

    conn = get_conn()
    nuevos = []
    for pr in prospectos:
        cont_id = pr.get("contacto_id")
        if not cont_id:
            continue
        # Nunca re-emailar: si el contacto ya tiene CUALQUIER envío, se saltea.
        ya = conn.execute("SELECT 1 FROM envios WHERE contacto_id=? LIMIT 1", (cont_id,)).fetchone()
        if ya:
            continue
        nuevos.append(pr)
        if len(nuevos) >= int(cantidad):
            break

    n = len(nuevos)
    intervalo = (float(ventana_horas) * 3600.0 / n) if n else 0
    ahora = datetime.utcnow()
    encolados = 0
    for i, pr in enumerate(nuevos):
        sched = (ahora + timedelta(seconds=i * intervalo)).isoformat(timespec="seconds")
        pipeline.enqueue_envio(pr["contacto_id"], cid, pids[1], pr["email"], sched, paso=1)
        conn.execute("UPDATE contactos SET campania_id=? WHERE id=?", (cid, pr["contacto_id"]))
        encolados += 1
    conn.commit()
    conn.close()

    pipeline.log_agente("orquestador", f"Rutina «{nicho}»",
                        f"{encolados} nuevos encolados (paso 1) en campaña #{cid}")
    return {"campania_id": cid, "encolados": encolados}

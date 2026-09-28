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

# Rotación geográfica: Argentina (varias provincias) + países de habla hispana.
# Cada corrida toma las próximas K zonas → Apify trae negocios frescos cada día.
LOCACIONES = [
    "Buenos Aires Argentina", "Santiago Chile", "Montevideo Uruguay", "Ciudad de México México",
    "Córdoba Argentina", "Lima Perú", "Asunción Paraguay", "Guadalajara México",
    "Rosario Argentina", "Valparaíso Chile", "Monterrey México", "Mendoza Argentina",
    "Arequipa Perú", "Punta del Este Uruguay", "Puebla México", "La Plata Argentina",
    "Concepción Chile", "Ciudad del Este Paraguay", "Querétaro México", "Mar del Plata Argentina",
    "Trujillo Perú", "Salto Uruguay", "Tijuana México", "San Miguel de Tucumán Argentina",
    "Antofagasta Chile", "Mérida México", "Salta Argentina", "Neuquén Argentina",
    "Santa Fe Argentina", "Bahía Blanca Argentina",
]
ZONAS_POR_CORRIDA = 4


def _next_locs(nicho, k=ZONAS_POR_CORRIDA):
    """Devuelve las próximas k zonas para el nicho y avanza el puntero (persistido en kv)."""
    key = f"rot::{nicho}"
    try:
        start = int(pipeline.kv_get(key) or 0)
    except Exception:
        start = 0
    n = len(LOCACIONES)
    locs = [LOCACIONES[(start + i) % n] for i in range(k)]
    try:
        pipeline.kv_set(key, str((start + k) % n))
    except Exception:
        pass
    return locs


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
    cantidad = int(cantidad)

    conn = get_conn()

    def _sin_envio_ni_supresion(cont_id, email):
        if conn.execute("SELECT 1 FROM envios WHERE contacto_id=? LIMIT 1", (cont_id,)).fetchone():
            return False   # ya fue contactado alguna vez
        if conn.execute("SELECT 1 FROM supresion WHERE email=? LIMIT 1", (email,)).fetchone():
            return False   # opt-out
        return True

    nuevos = []
    vistos = set()

    # 1) BACKLOG: primero usamos leads del nicho que YA tenemos y nunca enviamos.
    for r in conn.execute(
            "SELECT id, email, empresa FROM contactos WHERE nicho=? AND estado='prospecto' ORDER BY id",
            (nicho,)):
        row = dict(r)
        if len(nuevos) >= cantidad:
            break
        if row["email"] in vistos or not _sin_envio_ni_supresion(row["id"], row["email"]):
            continue
        vistos.add(row["email"])
        nuevos.append({"contacto_id": row["id"], "email": row["email"], "empresa": row["empresa"]})

    # 2) Si el backlog no alcanza, recién ahí scrapeamos NUEVOS (rotación de zonas).
    if len(nuevos) < cantidad:
        zonas = _next_locs(nicho)
        terms = [f"{nicho} {z}" for z in zonas]
        brief = {"nicho": nicho, "pais": pais, "cantidad": max(cantidad * 6, 45),
                 "ventana_horas": ventana_horas, "fuentes": ["apify"], "search_terms": terms}
        for pr in search_agent.buscar(brief):
            cont_id = pr.get("contacto_id")
            if len(nuevos) >= cantidad:
                break
            if not cont_id or pr["email"] in vistos or not _sin_envio_ni_supresion(cont_id, pr["email"]):
                continue
            vistos.add(pr["email"])
            nuevos.append(pr)

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

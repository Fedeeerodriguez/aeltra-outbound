# -*- coding: utf-8 -*-
"""Autoanálisis y mejora: mira los RESULTADOS y refina a quién apuntar.

Qué hace (sin tokens de API):
  - Mide por nicho: enviados, respuestas, rebotes, "contactables" (dejaron teléfono),
    y negocios auditados por nivel.
  - Cruza la auditoría de los que RESPONDIERON vs. los que no → aprende qué score de
    falla convierte mejor y recomienda un umbral de promoción.
  - Recomienda: qué nichos priorizar, cuáles pausar (mucho rebote y cero respuesta),
    y el umbral de score para promover a email.
  - Persiste el informe en kv ('autoanalisis') para el panel y lo loguea.

Es el volante de la máquina: arranca global y, con estos números, se afina.
"""
import json
from datetime import datetime

import pipeline
from db import get_conn

ESTADOS_EXITO = ("respondio", "reunion", "cerrado")


def _por_nicho():
    conn = get_conn()
    filas = conn.execute(
        "SELECT nicho, estado, COUNT(*) n FROM contactos "
        "WHERE nicho IS NOT NULL AND nicho<>'' GROUP BY nicho, estado").fetchall()
    conn.close()
    agg = {}
    for r in filas:
        d = dict(r)
        nk = d["nicho"]
        a = agg.setdefault(nk, {"nicho": nk, "contactados": 0, "respuestas": 0,
                                "rebotes": 0, "auditados": 0, "otros": 0})
        est, n = d["estado"], d["n"]
        if est in ESTADOS_EXITO:
            a["respuestas"] += n
        elif est == "rebote":
            a["rebotes"] += n
        elif est == "auditado":
            a["auditados"] += n
        if est in ("enviado", "no_respondio", "seguimiento") + ESTADOS_EXITO or est == "rebote":
            a["contactados"] += n
    return agg


def _score_responders():
    """Score promedio de auditoría de los que respondieron vs. los que no (si hay data)."""
    negocios = pipeline.negocios_auditados(limit=5000)
    resp, noresp = [], []
    for n in negocios:
        sc = n["auditoria"].get("score")
        if sc is None:
            continue
        (resp if n.get("estado") in ESTADOS_EXITO else noresp).append(sc)
    prom = lambda xs: round(sum(xs) / len(xs), 1) if xs else None
    return {"respondieron": prom(resp), "no_respondieron": prom(noresp),
            "n_respondieron": len(resp), "n_no": len(noresp)}


def analizar(persistir=True):
    por_nicho = _por_nicho()
    ranking = []
    for a in por_nicho.values():
        cont = max(a["contactados"], 1)
        tasa_resp = round(100 * a["respuestas"] / cont, 1)
        tasa_rebote = round(100 * a["rebotes"] / cont, 1)
        # Señal de calidad: respuestas pesan; rebotes penalizan.
        a["tasa_respuesta"] = tasa_resp
        a["tasa_rebote"] = tasa_rebote
        a["senal"] = round(tasa_resp - tasa_rebote * 0.5, 1)
        ranking.append(a)
    ranking.sort(key=lambda x: (x["senal"], x["respuestas"]), reverse=True)

    priorizar = [a["nicho"] for a in ranking if a["respuestas"] > 0][:3]
    pausar = [a["nicho"] for a in ranking
              if a["contactados"] >= 20 and a["respuestas"] == 0 and a["tasa_rebote"] > 15]

    sc = _score_responders()
    if sc["respondieron"] is not None and sc["n_respondieron"] >= 3:
        min_score_reco = max(40, int(sc["respondieron"]) - 10)
    else:
        min_score_reco = 60  # default hasta tener señal

    recomendaciones = []
    if priorizar:
        recomendaciones.append("Priorizar (subir volumen): " + ", ".join(priorizar))
    if pausar:
        recomendaciones.append("Pausar o revisar copy (mucho rebote, cero respuesta): "
                               + ", ".join(pausar))
    if sc["n_respondieron"] >= 3:
        recomendaciones.append(
            f"Los que responden tienen score de falla ~{sc['respondieron']} vs "
            f"~{sc['no_respondieron']} los que no → promover a email desde score "
            f"{min_score_reco}.")
    else:
        recomendaciones.append(
            "Todavía no hay suficientes respuestas para afinar el umbral; seguir global "
            f"y promover desde score {min_score_reco}.")

    informe = {
        "fecha": datetime.utcnow().isoformat(timespec="seconds"),
        "ranking_nichos": ranking,
        "priorizar": priorizar,
        "pausar": pausar,
        "score_responders": sc,
        "min_score_promocion": min_score_reco,
        "recomendaciones": recomendaciones,
        "auditoria": pipeline.resumen_auditoria(),
    }
    if persistir:
        try:
            pipeline.kv_set("autoanalisis", json.dumps(informe, ensure_ascii=False))
            pipeline.kv_set("audit_min_score", str(min_score_reco))
            pipeline.log_agente("autoanalisis", "Análisis de resultados",
                                " · ".join(recomendaciones)[:3900])
        except Exception:
            pass
    return informe


def ultimo_informe():
    raw = pipeline.kv_get("autoanalisis")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None

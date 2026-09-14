# -*- coding: utf-8 -*-
"""Agente orquestador (supervisor) en LangGraph.

Recibe un objetivo en lenguaje natural, lo convierte en un brief, y coordina:
  intake → búsqueda → copy → ejecución (encolado paceado) → resumen.
Con lógica de replanificación básica (si faltan prospectos, avisa; si el pedido
supera el tope diario seguro, lo marca en el resumen)."""
import json
import re
from datetime import datetime, timedelta
from typing import TypedDict, List, Optional

from langgraph.graph import StateGraph, END

import activity
import config
import pipeline
from . import search_agent, copywriter


class CampaignState(TypedDict, total=False):
    objetivo: str
    brief: dict
    campania_id: Optional[int]
    prospectos: List[dict]
    plantilla: dict
    plantilla_id: Optional[int]
    resumen: dict
    avisos: List[str]


# ── INTAKE: objetivo (texto) → brief estructurado ──
_HEUR_NUM = re.compile(r"(\d+)\s*(mails?|correos?|emails?|prospectos?|contactos?)", re.I)
_HEUR_H = re.compile(r"(\d+)\s*(h|hora|horas)", re.I)


_VERBOS = ["buscame", "buscá", "busca", "buscar", "conseguime", "conseguí", "consegui",
           "encontrame", "encontrá", "encontra", "juntame", "juntá", "junta", "recopilá",
           "recopila", "recopilame", "necesito", "quiero", "dame", "traeme", "sacame",
           "sacá", "saca", "mandales", "mandá", "manda", "escribiles", "escribí", "escribi"]


def _extract_nicho(low: str, pais: str) -> str:
    n = low
    for v in _VERBOS:
        n = n.replace(v, " ")
    n = _HEUR_H.sub(" ", n)                       # sacar "3 horas"
    n = re.sub(r"\b\d{1,6}\b", " ", n)            # sacar números
    n = re.split(r"\b(y|para|en las|dentro|luego|despu[eé]s)\b", n)[0]
    n = re.sub(r"\ben\s+" + re.escape(pais.lower()) + r"\b", " ", n)
    n = re.sub(r"\b(mails?|correos?|emails?|prospectos?|contactos?|negocios?|due[ñn]os? de)\b", " ", n)
    n = re.sub(r"\s+", " ", n).strip(" .,-")
    return n if len(n) > 2 else "tiendas online / e-commerce"


def _heuristic_brief(objetivo: str) -> dict:
    low = objetivo.lower()
    pais = "Argentina"
    for p in ["Argentina", "México", "Mexico", "Chile", "Colombia", "España", "Uruguay", "Perú"]:
        if p.lower() in low:
            pais = p
            break
    h = _HEUR_H.search(low)
    sin_horas = _HEUR_H.sub(" ", low)             # que "3 horas" no se lea como cantidad
    mnum = re.search(r"\b(\d{1,6})\b", sin_horas)
    return {
        "objetivo": objetivo,
        "nicho": _extract_nicho(low, pais),
        "pais": pais,
        "cantidad": int(mnum.group(1)) if mnum else 25,
        "ventana_horas": float(h.group(1)) if h else config.DEFAULT_WINDOW_HOURS,
        "angulo": "respuesta lenta por WhatsApp, ventas perdidas fuera de horario",
        "fuentes": ["apify", "web"],
    }


def _llm_brief(objetivo: str):
    if not config.llm_ready():
        return None
    try:
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(model=config.LLM_MODEL, max_tokens=600, timeout=45)
        sys = ("Sos el orquestador de campañas de Aeltra. Convertí el objetivo del usuario "
               "en un JSON con: nicho, pais, cantidad (int), ventana_horas (float), "
               "angulo (dolor a atacar), fuentes (lista: apify/web). Devolvé SOLO el JSON.")
        resp = llm.invoke([("system", sys), ("human", objetivo)])
        m = re.search(r"\{.*\}", resp.content, re.S)
        if m:
            d = json.loads(m.group(0))
            d["objetivo"] = objetivo
            d.setdefault("fuentes", ["apify", "web"])
            d.setdefault("cantidad", 25)
            d.setdefault("ventana_horas", config.DEFAULT_WINDOW_HOURS)
            d.setdefault("pais", "Argentina")
            return d
    except Exception:
        return None
    return None


def parse_brief(objetivo: str) -> dict:
    """Convierte un objetivo en texto a un brief estructurado (LLM o heurística)."""
    return _llm_brief(objetivo) or _heuristic_brief(objetivo)


def node_intake(state: CampaignState) -> CampaignState:
    objetivo = state["objetivo"]
    activity.update("orquestador", "trabajando", f"Interpretando objetivo: «{objetivo[:60]}»…", 10)
    brief = _llm_brief(objetivo) or _heuristic_brief(objetivo)
    avisos = []
    if brief["cantidad"] > config.DAILY_SEND_CAP:
        avisos.append(
            f"Pediste {brief['cantidad']} envíos, por encima del tope seguro de "
            f"{config.DAILY_SEND_CAP}/día para Gmail. Se encolan igual, pero cuidá la "
            f"reputación (idealmente dominio propio + proveedor)."
        )
    cid = pipeline.create_campania(
        nombre=f"Campaña {datetime.now():%Y-%m-%d %H:%M}",
        objetivo=objetivo, brief=brief,
        cantidad_objetivo=brief["cantidad"], ventana_horas=brief["ventana_horas"],
    )
    return {"brief": brief, "campania_id": cid, "avisos": avisos}


def node_search(state: CampaignState) -> CampaignState:
    activity.update("orquestador", "trabajando", "Derivando al agente de búsqueda…", 30)
    prospectos = search_agent.buscar(state["brief"])
    return {"prospectos": prospectos}


def node_write(state: CampaignState) -> CampaignState:
    activity.update("orquestador", "trabajando", "Derivando al copywriter…", 60)
    plantilla = copywriter.escribir_email(state["brief"])
    pid = pipeline.create_plantilla(
        state["campania_id"], plantilla["asunto"], plantilla["cuerpo"], plantilla.get("variante", "A"),
    )
    return {"plantilla": plantilla, "plantilla_id": pid}


def node_execute(state: CampaignState) -> CampaignState:
    activity.update("orquestador", "trabajando", "Encolando envíos paceados…", 85)
    prospectos = state.get("prospectos", [])
    ventana_h = float(state["brief"]["ventana_horas"])
    n = len(prospectos)
    intervalo = (ventana_h * 3600.0 / n) if n else 0
    ahora = datetime.utcnow()
    encolados = 0
    for i, p in enumerate(prospectos):
        sched = (ahora + timedelta(seconds=i * intervalo)).isoformat(timespec="seconds")
        pipeline.enqueue_envio(
            p["contacto_id"], state["campania_id"], state["plantilla_id"], p["email"], sched,
        )
        encolados += 1

    avisos = list(state.get("avisos", []))
    objetivo_n = int(state["brief"]["cantidad"])
    if encolados < objetivo_n:
        avisos.append(f"Se encontraron {encolados} de {objetivo_n} pedidos. "
                      f"Arranco con esos; podés relanzar para buscar más.")
    resumen = {
        "campania_id": state["campania_id"],
        "encolados": encolados,
        "objetivo": objetivo_n,
        "ventana_horas": ventana_h,
        "intervalo_seg": round(intervalo, 1),
        "asunto": state["plantilla"]["asunto"],
        "avisos": avisos,
    }
    activity.update("orquestador", "listo",
                    f"Campaña #{state['campania_id']} lista ✅ {encolados} envíos encolados "
                    f"(1 cada {round(intervalo)}s).", 100)
    return {"resumen": resumen, "avisos": avisos}


def _route_after_search(state: CampaignState):
    return "write" if state.get("prospectos") else "sin_prospectos"


def node_sin_prospectos(state: CampaignState) -> CampaignState:
    activity.update("orquestador", "error",
                    "No se encontraron prospectos con esos criterios.", 100)
    return {"resumen": {
        "campania_id": state["campania_id"], "encolados": 0,
        "objetivo": int(state["brief"]["cantidad"]),
        "avisos": ["No se encontraron prospectos con esos criterios. "
                   "Probá otro nicho/país, activá Apify (APIFY_TOKEN) o importá un CSV."],
    }}


def build_graph():
    g = StateGraph(CampaignState)
    g.add_node("intake", node_intake)
    g.add_node("search", node_search)
    g.add_node("write", node_write)
    g.add_node("execute", node_execute)
    g.add_node("sin_prospectos", node_sin_prospectos)
    g.set_entry_point("intake")
    g.add_edge("intake", "search")
    g.add_conditional_edges("search", _route_after_search,
                            {"write": "write", "sin_prospectos": "sin_prospectos"})
    g.add_edge("write", "execute")
    g.add_edge("execute", END)
    g.add_edge("sin_prospectos", END)
    return g.compile()


_GRAPH = None

def lanzar_campania(objetivo: str) -> dict:
    """Punto de entrada: corre el grafo del orquestador y devuelve el resumen."""
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    final = _GRAPH.invoke({"objetivo": objetivo})
    return final.get("resumen", {"avisos": ["Sin resumen."]})

# -*- coding: utf-8 -*-
"""Agente copywriter B2B: genera asunto + cuerpo con placeholders {{nombre}}."""
import json
import re

import activity
import config
from .playbook import writer_system_prompt

_FALLBACK = {
    "asunto": "{{nombre}}, una pregunta sobre tu tienda",
    "cuerpo": (
        "Hola {{nombre}}, vi tu tienda y me quedó una duda.\n"
        "Cuando un cliente escribe por WhatsApp fuera de horario, ¿alguien responde? "
        "La mayoría de las ventas se caen ahí: el que no recibe respuesta en minutos, compra en otro lado.\n"
        "En Aeltra armamos un sistema de IA que responde 24/7 y recupera esas ventas por vos. "
        "A un par de tiendas les recuperó ventas que estaban perdiendo sin darse cuenta.\n"
        "¿Te muestro en 15 minutos cómo lo haría con la tuya?"
    ),
    "variante": "A",
}


def _extract_json(s: str):
    m = re.search(r"\{.*\}", s, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def escribir_email(brief: dict) -> dict:
    """Devuelve {asunto, cuerpo, variante}. Si no hay LLM configurado, usa un fallback sólido."""
    activity.update("copywriter", "trabajando",
                    f"Escribiendo copy B2B para «{brief.get('nicho','')}»…", 40)
    if not config.llm_ready():
        activity.update("copywriter", "listo", "Copy listo (plantilla base, sin IA configurada).", 100)
        return dict(_FALLBACK)
    try:
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(model=config.LLM_MODEL, max_tokens=1200, timeout=60)
        sys = writer_system_prompt(config.COMPANY_NAME, config.COMPANY_TAGLINE)
        human = (
            f"Nicho: {brief.get('nicho','')}\n"
            f"País: {brief.get('pais','')}\n"
            f"Objetivo de la campaña: {brief.get('objetivo','')}\n"
            f"Dolor/ángulo a atacar: {brief.get('angulo','respuesta lenta por WhatsApp, ventas perdidas')}\n\n"
            "Escribí UN cold email siguiendo el playbook. Devolvé solo el JSON."
        )
        resp = llm.invoke([("system", sys), ("human", human)])
        data = _extract_json(resp.content if hasattr(resp, "content") else str(resp))
        if data and data.get("asunto") and data.get("cuerpo"):
            data.setdefault("variante", "A")
            activity.update("copywriter", "listo", f"Copy listo ✅ Asunto: «{data['asunto']}»", 100)
            return data
    except Exception:
        pass
    activity.update("copywriter", "listo", "Copy listo (fallback).", 100)
    return dict(_FALLBACK)

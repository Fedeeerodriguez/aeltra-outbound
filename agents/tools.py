# -*- coding: utf-8 -*-
"""Herramientas de agente (LangChain). La estrella: envio_email."""
from langchain_core.tools import tool

import pipeline
from .emailing import enviar_core
from . import prospect_sources


@tool
def envio_email(email: str, nombre: str, asunto: str, cuerpo: str,
                variables: dict = None, contacto_id: int = None) -> dict:
    """Envía un email personalizado a un contacto.
    Toma `email` y `nombre` como campos variables, reemplaza {{nombre}}/{{email}}
    (y cualquier clave de `variables`) en asunto y cuerpo, agrega el pie de baja
    y lo envía. Antes chequea la lista de supresión (si está en baja, NO envía).
    Devuelve {status: sent|skipped|failed, message_id?, error?}."""
    return enviar_core(email, nombre, asunto, cuerpo, variables, contacto_id)


@tool
def buscar_prospectos(nicho: str, pais: str, cantidad: int = 25, fuentes: list = None) -> list:
    """Busca prospectos de un nicho y país usando Apify (Google Maps) y/o búsqueda web.
    Devuelve una lista de dicts {nombre, email, empresa, nicho, pais, fuente}."""
    return prospect_sources.search_prospects(nicho, pais, cantidad, tuple(fuentes or ["apify", "web"]))


@tool
def chequear_supresion(email: str) -> bool:
    """Devuelve True si el email está en la lista de baja (opt-out)."""
    return pipeline.is_suppressed(email)


@tool
def validar_email(email: str) -> bool:
    """Valida el formato de un email. True si es válido."""
    try:
        from .prospect_sources import es_email_plausible
        if not es_email_plausible(email):   # descarta assets tipo logo@2x.png
            return False
        from email_validator import validate_email, EmailNotValidError
        validate_email(email, check_deliverability=False)
        return True
    except Exception:
        return False


ALL_TOOLS = [envio_email, buscar_prospectos, chequear_supresion, validar_email]

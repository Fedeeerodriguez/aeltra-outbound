# -*- coding: utf-8 -*-
"""Agente de búsqueda: encuentra prospectos, los valida y los carga al pipeline.
NO envía nada — solo recopila en la base para usarlos cuando quieras."""
import activity
import pipeline
from . import prospect_sources
from .tools import validar_email


def buscar(brief: dict) -> list:
    """Busca según el brief, deduplica contra el pipeline y guarda los contactos nuevos.
    Devuelve la lista de prospectos guardados (con contacto_id). No dispara emails."""
    nicho = brief.get("nicho", "e-commerce")
    pais = brief.get("pais", "Argentina")
    cantidad = int(brief.get("cantidad", 25))
    fuentes = tuple(brief.get("fuentes", ["apify", "web"]))

    activity.update("busqueda", "trabajando",
                    f"Buscando {cantidad} de «{nicho}» en {pais} (fuentes: {', '.join(fuentes)})…", 5)
    prospectos = prospect_sources.search_prospects(nicho, pais, cantidad, fuentes)
    total = len(prospectos)
    activity.update("busqueda", "trabajando",
                    f"Encontrados {total}. Validando y guardando en la base…", 30)

    guardados = []
    nuevos, repetidos, invalidos = 0, 0, 0
    for i, p in enumerate(prospectos):
        email = (p.get("email") or "").strip().lower()
        if not email or not validar_email.invoke({"email": email}):
            invalidos += 1
            continue
        if pipeline.is_suppressed(email):
            continue
        existente = pipeline.find_contact_by_email(email)
        cid = pipeline.add_contact(
            p.get("nombre"), email, p.get("empresa"), nicho, pais, p.get("fuente"),
        )
        if cid:
            if existente:
                repetidos += 1
            else:
                nuevos += 1
            p["contacto_id"] = cid
            p["email"] = email
            guardados.append(p)
        if total and i % 10 == 0:
            activity.update("busqueda", progreso=30 + int((i + 1) / total * 65))

    activity.update("busqueda", "listo",
                    f"Listo ✅ {nuevos} nuevos guardados ({repetidos} ya estaban, {invalidos} inválidos). "
                    f"Total en base: quedan disponibles para campañas.", 100)
    return guardados

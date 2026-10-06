# -*- coding: utf-8 -*-
"""Máquina de prospección con evidencia (mystery shopper automático).

Flujo 100% automático y SIN envío de mails:
  1. Busca negocios del nicho en Google Maps (rico: reseñas, rating, web, teléfono).
  2. Audita cada uno (auditor.py): score de falla + evidencia pública.
  3. Los guarda como contactos 'auditado' + evento 'auditoria'.

El envío NO ocurre acá (seguridad): los negocios quedan en estado 'auditado', que los
envíos automáticos ignoran. `promover_a_campania()` es el puente opcional que pasa los
de score alto (y con email entregable) a la secuencia de mails del nicho.

Rotación geográfica global (reusa las zonas de campaigns): arranca global y la rutina
va recorriendo zonas en cada corrida. El refinamiento lo hace autoanalisis.py.
"""
import pipeline
import nichos
import auditor
from agents import prospect_sources
from campaigns import LOCACIONES, ZONAS_POR_CORRIDA


def _next_zonas(nicho_key, k):
    """Próximas k zonas para el nicho; avanza el puntero persistido en kv."""
    key = f"audit_rot::{nicho_key}"
    try:
        start = int(pipeline.kv_get(key) or 0)
    except Exception:
        start = 0
    n = len(LOCACIONES)
    zonas = [LOCACIONES[(start + i) % n] for i in range(k)]
    try:
        pipeline.kv_set(key, str((start + k) % n))
    except Exception:
        pass
    return zonas


def correr_auditoria(nicho_key, zonas=None, cantidad=30, zonas_por_corrida=ZONAS_POR_CORRIDA,
                     chequear_web=True):
    """Audita hasta `cantidad` negocios del nicho (sin enviar nada).
    Devuelve {'nicho','auditados','alto','medio','bajo','zonas'}."""
    nd = nichos.get(nicho_key)
    if not nd:
        return {"error": f"nicho desconocido: {nicho_key}",
                "nichos": [n["key"] for n in nichos.listar()]}
    if not zonas:
        zonas = _next_zonas(nicho_key, zonas_por_corrida)
    # Un término por zona (usa la query principal del nicho).
    query = nd["queries"][0]
    search_terms = [f"{query} {z}" for z in zonas]

    negocios = prospect_sources.buscar_negocios_rich(nicho_key, search_terms, cantidad)
    conteo = {"alto": 0, "medio": 0, "bajo": 0}
    guardados = 0
    for neg in negocios:
        audit = auditor.auditar_negocio(neg, extra_keywords=nd.get("quejas_clave"),
                                        chequear_web=chequear_web)
        zona = neg.get("pais") or (zonas[0] if zonas else "")
        cid = pipeline.guardar_auditoria(neg, audit, nicho_key, zona)
        if cid:
            guardados += 1
            conteo[audit["nivel"]] = conteo.get(audit["nivel"], 0) + 1

    res = {"nicho": nicho_key, "auditados": guardados,
           "alto": conteo["alto"], "medio": conteo["medio"], "bajo": conteo["bajo"],
           "zonas": zonas}
    try:
        pipeline.log_agente("auditor", f"Auditoría «{nicho_key}»",
                            f"{guardados} auditados · alto={conteo['alto']} "
                            f"medio={conteo['medio']} bajo={conteo['bajo']} · zonas={', '.join(zonas)}")
    except Exception:
        pass
    return res


def promover_a_campania(nicho_key, min_score=60, cantidad=20,
                        ventana_horas=6.0, delay2=24.0, delay3=48.0):
    """Puente audit → email: pasa los negocios de score >= min_score (con email real y
    entregable) a estado 'prospecto' y lanza la secuencia de mails del nicho.
    Los sintéticos (@sin-email) y los no entregables se descartan solos (email_valido)."""
    nd = nichos.get(nicho_key)
    if not nd:
        return {"error": f"nicho desconocido: {nicho_key}"}
    from agents.prospect_sources import email_valido
    candidatos = [n for n in pipeline.negocios_auditados(nicho=nicho_key)
                  if n["auditoria"].get("score", 0) >= min_score
                  and not n["auditoria"].get("sintetico")
                  and email_valido(n.get("email") or "")]
    promovidos = 0
    for n in candidatos[:cantidad]:
        pipeline.set_estado(n["id"], "prospecto")
        promovidos += 1
    if not promovidos:
        return {"nicho": nicho_key, "promovidos": 0,
                "nota": "no hay auditados con email entregable y score suficiente todavía"}
    import campaigns
    r = campaigns.lanzar_secuencia_rutina(
        nicho_key, "Argentina", promovidos, ventana_horas, nd["pasos"], delay2, delay3)
    r.update({"nicho": nicho_key, "promovidos": promovidos})
    try:
        pipeline.log_agente("auditor", f"Promoción «{nicho_key}»",
                            f"{promovidos} promovidos a secuencia (score>={min_score})")
    except Exception:
        pass
    return r

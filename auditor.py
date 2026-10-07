# -*- coding: utf-8 -*-
"""Auditor de negocios (mystery shopper automático, sin contacto, sin tokens de API).

Para cada negocio de Google Maps mide la FALLA a partir de señales PÚBLICAS:
  1. Reseñas que se quejan de la respuesta/atención ("no responden", "no atienden"…).
  2. Ausencia de canal de respuesta instantánea en la web (WhatsApp / chat en vivo).
  3. Rating bajo / sin reseñas.
  4. Sin sitio web (vive solo en Maps) → oportunidad grande.

Devuelve un score 0-100, un nivel (alto/medio/bajo), una frase de EVIDENCIA legítima
(sale de sus propios clientes, no inventamos nada) y un bloque listo para el mail.

No le escribe ni llama a nadie: solo lee lo que ya es público. El "test real" de
contacto (escribir como cliente y medir cuánto tardan) queda para los finalistas y a
bajo volumen — eso lo decide Federico, no se automatiza en masa.
"""
import re
import unicodedata
import httpx


def _norm(s):
    """minúsculas sin acentos, para matchear quejas escritas de cualquier forma."""
    s = (s or "").lower()
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# Quejas GLOBALES sobre respuesta/atención (ya normalizadas, sin acentos).
_QUEJAS_RESPUESTA = [
    "no responden", "no contestan", "no atienden", "nunca me respondieron",
    "nunca me contestaron", "nunca me llamaron", "no me respondieron", "no me contestaron",
    "no me atendieron", "mala atencion", "pesima atencion", "nunca atienden",
    "no atienden el telefono", "no contestan el telefono", "no atienden el telefono",
    "tardan en responder", "tarde en responder", "demoran en responder", "nadie responde",
    "nadie atiende", "sin respuesta", "no responden los mensajes", "no responden whatsapp",
    "no responden el whatsapp", "dejan en visto", "imposible comunicarse", "no se puede contactar",
    "no volvieron a llamar", "no dan respuesta", "no responde nadie", "nunca contestan",
]

# Marcas de canal instantáneo en el HTML de la web (si está → NO es falla por ese lado).
_MARCAS_WHATSAPP = ["wa.me/", "api.whatsapp.com", "whatsapp://", "web.whatsapp.com",
                    "floating-whatsapp", "whatsapp-button", "clicktochat", "click-to-chat"]
_MARCAS_CHAT = ["tawk.to", "crisp.chat", "intercom", "zendesk", "zdassets", "livechatinc",
                "drift.com", "tidio", "hubspot-messages", "manychat", "cliengo", "whistle.me",
                "chatwoot", "freshchat", "landbot"]


def _citas_queja(reviews, extra_keywords=None):
    """Devuelve (lista de reseñas que se quejan de respuesta/atención, total de coincidencias)."""
    claves = list(_QUEJAS_RESPUESTA) + [_norm(k) for k in (extra_keywords or [])]
    citas = []
    for rv in reviews or []:
        texto = rv.get("text") if isinstance(rv, dict) else str(rv)
        if not texto:
            continue
        n = _norm(texto)
        for k in claves:
            if k in n:
                limpio = re.sub(r"\s+", " ", texto).strip()
                citas.append(limpio[:220])
                break
    return citas


def _analizar_web(website, timeout=8.0):
    """¿La web tiene canal instantáneo (WhatsApp / chat)? Best-effort. Si no hay web o
    falla la descarga, devuelve (None, None) = desconocido (no penaliza de más)."""
    if not website:
        return None, None
    url = website if website.startswith("http") else "https://" + website
    try:
        r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout,
                      follow_redirects=True)
        html = (r.text or "").lower()
        tiene_wa = any(m in html for m in _MARCAS_WHATSAPP)
        tiene_chat = any(m in html for m in _MARCAS_CHAT)
        return tiene_wa, tiene_chat
    except Exception:
        return None, None


def auditar_negocio(negocio: dict, extra_keywords=None, chequear_web=True) -> dict:
    """Audita un negocio (dict con empresa/website/telefono/rating/reviews_count/reviews).
    Devuelve el resultado de auditoría (score, nivel, evidencia, bloque_evidencia, señales)."""
    reviews = negocio.get("reviews") or []
    rating = negocio.get("rating")
    reviews_count = negocio.get("reviews_count") or 0
    website = (negocio.get("website") or "").strip()

    citas = _citas_queja(reviews, extra_keywords)
    tiene_wa, tiene_chat = (_analizar_web(website) if (chequear_web and website) else (None, None))

    score = 0
    senales = []

    # 1) Quejas de respuesta/atención en reseñas (la evidencia más fuerte cuando aparece).
    #    OJO: Google devuelve solo ~5 reseñas "más relevantes" (sesgadas a positivo), así
    #    que esta señal dispara poco; el rating y la ausencia de canal pesan más abajo.
    if citas:
        score += min(48, 28 + 9 * len(citas))
        senales.append(f"{len(citas)} reseña(s) mencionan demoras o falta de respuesta")

    # 2) Sin canal instantáneo detectable (para estos rubros, el dolor central).
    if not website:
        score += 25
        senales.append("no tiene sitio web (vive en WhatsApp/teléfono)")
    elif tiene_wa is False and tiene_chat is False:
        score += 30
        senales.append("la web no tiene WhatsApp ni chat para responder al instante")
    elif tiene_wa or tiene_chat:
        senales.append("ya tiene un canal instantáneo en la web")

    # 3) Rating: una reputación mala es una oportunidad enorme (y un lead caliente).
    try:
        r = float(rating) if rating is not None else None
    except Exception:
        r = None
    if r is not None:
        if r < 2.5:
            score += 38
            senales.append(f"rating MUY bajo en Google ({r})")
        elif r < 3.5:
            score += 26
            senales.append(f"rating bajo en Google ({r})")
        elif r < 4.0:
            score += 18
            senales.append(f"rating flojo en Google ({r})")
        elif r < 4.5:
            score += 8
            senales.append(f"rating mejorable ({r})")

    # 4) Poca o nula reputación online.
    if reviews_count == 0:
        score += 8
        senales.append("sin reseñas en Google")

    score = max(0, min(100, score))
    nivel = "alto" if score >= 55 else ("medio" if score >= 30 else "bajo")

    # Evidencia legítima (frase corta) + bloque opcional para el mail.
    if citas:
        evidencia = f'En Google, un cliente dejó: "{citas[0]}"'
        bloque = ("Mirando su ficha en Google vi algún comentario sobre demoras para recibir "
                  "respuesta — y justamente eso es lo que resolvemos.\n\n")
    elif not website:
        evidencia = "No encontré sitio web: hoy toda la consulta cae en el teléfono/WhatsApp."
        bloque = ("Vi que trabajan sobre todo por teléfono/WhatsApp, sin una web que filtre y "
                  "responda las consultas — ahí se suele escapar trabajo.\n\n")
    elif tiene_wa is False and tiene_chat is False:
        evidencia = "La web no tiene WhatsApp ni chat: las consultas fuera de hora quedan sin respuesta."
        bloque = ("Entré a su web y no vi un canal para responder al instante las consultas que "
                  "llegan fuera de hora — ahí se enfrían ventas.\n\n")
    else:
        evidencia = "Sin señales públicas de falla fuerte; candidato de menor prioridad."
        bloque = ""

    return {
        "score": score,
        "nivel": nivel,
        "evidencia": evidencia,
        "bloque_evidencia": bloque,
        "senales": senales,
        "citas": citas[:3],
        "rating": r,
        "reviews_count": reviews_count,
        "tiene_whatsapp": tiene_wa,
        "tiene_chat": tiene_chat,
        "website": website,
        "telefono": negocio.get("telefono") or "",
        "maps_url": negocio.get("maps_url") or "",
        "direccion": negocio.get("direccion") or "",
    }

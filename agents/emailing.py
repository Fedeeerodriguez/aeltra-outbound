# -*- coding: utf-8 -*-
"""Render (merge de variables + pie de baja) y envío atómico de un mail."""
import re
from urllib.parse import quote

import config
import pipeline
from sender import get_sender


def _merge(texto: str, variables: dict) -> str:
    if not texto:
        return ""
    out = texto
    for k, v in variables.items():
        v = "" if v is None else str(v)
        out = out.replace("{{" + k + "}}", v).replace("{" + k + "}", v)
    return out


def _footer_html(email: str) -> str:
    # Pie liviano y humano (ayuda a caer en Principal en vez de Promociones).
    unsub = f"{config.UNSUB_BASE}?email={quote(email)}"
    return (
        '<br>--<br>'
        f'<span style="color:#777;font-size:13px">{config.COMPANY_NAME}. '
        f'Si preferís que no te escriba más, respondé BAJA o '
        f'<a href="{unsub}" style="color:#777">hacé click acá</a>.</span>'
    )


def _footer_text(email: str) -> str:
    # Pie mínimo y humano para texto plano (opt-out por respuesta; el header
    # List-Unsubscribe cubre la baja técnica).
    return f"\n\n--\n{config.COMPANY_NAME}\nSi preferís que no te escriba más, respondé BAJA."


def render(asunto: str, cuerpo: str, nombre: str, email: str, variables: dict = None):
    base = {"nombre": nombre or "", "email": email or ""}
    if variables:
        base.update(variables)
    subject = _merge(asunto, base).strip()
    body = _merge(cuerpo, base).strip()

    text = body + _footer_text(email)
    if config.PLAIN_TEXT_ONLY:
        return subject, "", text        # sin HTML → mail de texto plano puro

    paras = [p.strip() for p in re.split(r"\n{1,}", body) if p.strip()]
    # HTML mínimo y sobrio (parece un mail 1-a-1, no una newsletter).
    html_body = "".join(f"<p>{p}</p>" for p in paras)
    html = (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;'
        'line-height:1.5;color:#222">' + html_body + _footer_html(email) + "</div>"
    )
    return subject, html, text


def enviar_core(email, nombre, asunto, cuerpo, variables=None, contacto_id=None):
    """Chequea supresión → merge → envía. Devuelve {status, message_id?, error?}."""
    email = (email or "").strip().lower()
    if not email:
        return {"status": "failed", "error": "email vacío"}
    if pipeline.is_suppressed(email):
        return {"status": "skipped", "error": "en lista de supresión"}
    try:
        subject, html, text = render(asunto, cuerpo, nombre, email, variables)
        msg_id = get_sender().send(email, nombre, subject, html, text)
        if contacto_id:
            pipeline.add_evento(contacto_id, "envio", {"asunto": subject})
        return {"status": "sent", "message_id": msg_id}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

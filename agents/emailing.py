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
    unsub = f"{config.UNSUB_BASE}?email={quote(email)}"
    return (
        '<hr style="border:none;border-top:1px solid #e3e8f0;margin:22px 0 12px">'
        f'<p style="font:12px/1.5 Arial,sans-serif;color:#8a94a6">'
        f'{config.COMPANY_NAME} · {config.COMPANY_TAGLINE}<br>'
        f'Si no querés recibir más correos, <a href="{unsub}" style="color:#8a94a6">hacé click acá</a> '
        f'o respondé <b>BAJA</b>.</p>'
    )


def _footer_text(email: str) -> str:
    unsub = f"{config.UNSUB_BASE}?email={quote(email)}"
    return (
        f"\n\n--\n{config.COMPANY_NAME} · {config.COMPANY_TAGLINE}\n"
        f"Para dejar de recibir correos: {unsub} (o respondé BAJA)."
    )


def render(asunto: str, cuerpo: str, nombre: str, email: str, variables: dict = None):
    base = {"nombre": nombre or "", "email": email or ""}
    if variables:
        base.update(variables)
    subject = _merge(asunto, base).strip()
    body = _merge(cuerpo, base).strip()

    paras = [p.strip() for p in re.split(r"\n{1,}", body) if p.strip()]
    html_body = "".join(
        f'<p style="font:15px/1.6 Arial,sans-serif;color:#1c2432;margin:0 0 14px">{p}</p>'
        for p in paras
    )
    html = (
        '<div style="max-width:560px;margin:0 auto">'
        + html_body + _footer_html(email) + "</div>"
    )
    text = body + _footer_text(email)
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

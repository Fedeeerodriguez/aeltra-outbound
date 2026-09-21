# -*- coding: utf-8 -*-
"""Lectura de la casilla (IMAP) para detectar RESPUESTAS y REBOTES.

- Respuesta: un mail entrante cuyo remitente coincide con un contacto contactado
  → el contacto pasa a 'respondio', se cancelan sus follow-ups en cola y se registra.
- Rebote: un mail de mailer-daemon/postmaster con una dirección que rebotó
  → el contacto pasa a 'rebote' y va a supresión (no se reintenta).

Requiere IMAP_USER / IMAP_PASS en la config (con Gmail: App Password + IMAP activado).
Si no está configurado, revisar() es un no-op y no rompe nada.
"""
import re
import email
import imaplib
from email.utils import parseaddr

import config
import pipeline

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
# estados desde los que una respuesta es relevante (ya los contactamos, aún no cerraron)
_ESTADOS_ABIERTOS = ("enviado", "no_respondio", "seguimiento", "prospecto", "contactado")


def _norm(addr):
    return (parseaddr(addr or "")[1] or "").strip().lower()


def _cuerpo_texto(msg):
    partes = []
    if msg.is_multipart():
        for p in msg.walk():
            if p.get_content_type() == "text/plain":
                try:
                    partes.append(p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", "replace"))
                except Exception:
                    pass
    else:
        try:
            partes.append(msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", "replace"))
        except Exception:
            pass
    return "\n".join(partes)


def _es_rebote(frm, subj):
    f = frm.lower()
    s = (subj or "").lower()
    return (f.startswith("mailer-daemon@") or f.startswith("postmaster@")
            or "delivery status notification" in s or "undelivered mail" in s
            or "mail delivery failed" in s or "returned mail" in s)


def _direccion_rebotada(msg):
    """Busca la dirección que rebotó dentro del cuerpo del DSN."""
    texto = _cuerpo_texto(msg)
    m = re.search(r"[Ff]inal-[Rr]ecipient:.*?([\w.%+\-]+@[\w.\-]+\.\w+)", texto)
    if m:
        return m.group(1).lower()
    # fallback: primer email del cuerpo que exista como contacto contactado
    for cand in _EMAIL_RE.findall(texto):
        c = pipeline.find_contact_by_email(cand)
        if c and c.get("estado") in _ESTADOS_ABIERTOS + ("rebote",):
            return cand.lower()
    return None


def revisar(max_msgs=80):
    """Lee mails NO leídos de la casilla y actualiza respuestas/rebotes.
    Devuelve un dict con el resultado. No marca los mails como leídos (usa BODY.PEEK)."""
    if not config.imap_ready():
        return {"ok": False, "motivo": "IMAP no configurado (falta IMAP_USER / IMAP_PASS)"}
    respondieron, rebotes, revisados = 0, 0, 0
    try:
        M = imaplib.IMAP4_SSL(config.IMAP_HOST, config.IMAP_PORT)
        M.login(config.IMAP_USER, config.IMAP_PASS)
        M.select("INBOX")
        typ, data = M.search(None, "UNSEEN")
        if typ != "OK":
            M.logout()
            return {"ok": False, "error": "IMAP search falló"}
        ids = (data[0] or b"").split()[-max_msgs:]
        for num in ids:
            typ, md = M.fetch(num, "(BODY.PEEK[])")   # PEEK = no marca como leído
            if typ != "OK" or not md or not md[0]:
                continue
            revisados += 1
            msg = email.message_from_bytes(md[0][1])
            frm = _norm(msg.get("From", ""))
            subj = msg.get("Subject", "") or ""

            if _es_rebote(frm, subj):
                bad = _direccion_rebotada(msg)
                if bad:
                    c = pipeline.find_contact_by_email(bad)
                    if c:
                        pipeline.marcar_rebote(c["id"], bad)
                        pipeline.add_evento(c["id"], "rebote", {"asunto": subj[:200]})
                        rebotes += 1
                continue

            c = pipeline.find_contact_by_email(frm)
            if c and c.get("estado") in _ESTADOS_ABIERTOS:
                pipeline.marcar_respondio(c["id"])
                pipeline.cancel_pending_envios(c["id"])   # frena los follow-ups
                pipeline.add_evento(c["id"], "respuesta", {"asunto": subj[:200]})
                pipeline.log_agente("ejecutor", f"Respuesta de {frm}", subj[:200], True)
                respondieron += 1
        M.logout()
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "revisados": revisados, "respondieron": respondieron, "rebotes": rebotes}

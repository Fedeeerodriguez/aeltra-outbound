# -*- coding: utf-8 -*-
"""Lectura de la casilla para detectar RESPUESTAS y REBOTES.

Dos backends (elige solo):
  - Gmail API (OAuth)  → si hay GMAIL_CLIENT_ID/SECRET/REFRESH_TOKEN (preferido).
                         El refresh token debe incluir el scope gmail.readonly
                         (correr gmail_oauth_setup.py de nuevo si hace falta).
  - IMAP               → si hay IMAP_USER/IMAP_PASS (App Password).

- Respuesta: remitente coincide con un contacto contactado → 'respondio',
  se cancelan sus follow-ups en cola y se registra.
- Rebote: mail de mailer-daemon/postmaster → el contacto rebotado pasa a 'rebote'
  y a supresión (no se reintenta).

Si no hay ningún backend configurado, revisar() es un no-op y no rompe nada.
"""
import re
import email
import base64
import imaplib
from email.utils import parseaddr

import config
import pipeline

GMAIL_READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_ESTADOS_ABIERTOS = ("enviado", "no_respondio", "seguimiento", "prospecto", "contactado")


def _norm(addr):
    return (parseaddr(addr or "")[1] or "").strip().lower()


def _cuerpo_texto(msg):
    partes = []
    for p in (msg.walk() if msg.is_multipart() else [msg]):
        if p.get_content_type() in ("text/plain", "message/delivery-status"):
            try:
                partes.append(p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", "replace"))
            except Exception:
                pass
    return "\n".join(partes)


def _es_rebote(frm, subj):
    f = (frm or "").lower(); s = (subj or "").lower()
    return (f.startswith("mailer-daemon@") or f.startswith("postmaster@")
            or "delivery status notification" in s or "undelivered mail" in s
            or "mail delivery failed" in s or "returned mail" in s or "delivery incomplete" in s)


def _direccion_rebotada(msg):
    texto = _cuerpo_texto(msg)
    m = re.search(r"[Ff]inal-[Rr]ecipient:.*?([\w.%+\-]+@[\w.\-]+\.\w+)", texto)
    if m:
        return m.group(1).lower()
    for cand in _EMAIL_RE.findall(texto):
        c = pipeline.find_contact_by_email(cand)
        if c and c.get("estado") in _ESTADOS_ABIERTOS + ("rebote",):
            return cand.lower()
    return None


def _aplicar(frm, subj, get_raw):
    """Aplica la lógica de respuesta/rebote a un mensaje. get_raw() devuelve los bytes
    crudos del mail (solo se llama para rebotes). Devuelve 'respuesta' | 'rebote' | None."""
    if _es_rebote(frm, subj):
        try:
            msg = email.message_from_bytes(get_raw())
            bad = _direccion_rebotada(msg)
        except Exception:
            bad = None
        if bad:
            c = pipeline.find_contact_by_email(bad)
            if c:
                pipeline.marcar_rebote(c["id"], bad)
                pipeline.add_evento(c["id"], "rebote", {"asunto": (subj or "")[:200]})
                return "rebote"
        return None
    c = pipeline.find_contact_by_email(frm)
    if c and c.get("estado") in _ESTADOS_ABIERTOS:
        pipeline.marcar_respondio(c["id"])
        pipeline.cancel_pending_envios(c["id"])
        pipeline.add_evento(c["id"], "respuesta", {"asunto": (subj or "")[:200]})
        pipeline.log_agente("ejecutor", f"Respuesta de {frm}", (subj or "")[:200], True)
        return "respuesta"
    return None


# ── Backend Gmail API (OAuth) ──
def _gmail_service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(
        token=None, refresh_token=config.GMAIL_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.GMAIL_CLIENT_ID, client_secret=config.GMAIL_CLIENT_SECRET,
        scopes=[GMAIL_READ_SCOPE],
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _revisar_gmail(max_msgs=100):
    svc = _gmail_service()
    last = int(pipeline.kv_get("inbox_last_ts", "0") or 0)
    lst = svc.users().messages().list(userId="me", q="in:inbox newer_than:3d",
                                      maxResults=max_msgs).execute()
    respondieron = rebotes = revisados = 0
    nuevo_max = last
    for m in lst.get("messages", []):
        meta = svc.users().messages().get(
            userId="me", id=m["id"], format="metadata",
            metadataHeaders=["From", "Subject"]).execute()
        internal = int(meta.get("internalDate", "0"))
        if internal <= last:
            continue
        nuevo_max = max(nuevo_max, internal)
        revisados += 1
        hdrs = {h["name"].lower(): h["value"] for h in meta.get("payload", {}).get("headers", [])}
        frm = _norm(hdrs.get("from", "")); subj = hdrs.get("subject", "") or ""

        def _raw():
            full = svc.users().messages().get(userId="me", id=m["id"], format="raw").execute()
            return base64.urlsafe_b64decode(full["raw"].encode())

        r = _aplicar(frm, subj, _raw)
        if r == "respuesta":
            respondieron += 1
        elif r == "rebote":
            rebotes += 1
    if nuevo_max > last:
        pipeline.kv_set("inbox_last_ts", nuevo_max)
    return {"ok": True, "backend": "gmail", "revisados": revisados,
            "respondieron": respondieron, "rebotes": rebotes}


# ── Backend IMAP ──
def _revisar_imap(max_msgs=80):
    respondieron = rebotes = revisados = 0
    M = imaplib.IMAP4_SSL(config.IMAP_HOST, config.IMAP_PORT)
    M.login(config.IMAP_USER, config.IMAP_PASS)
    M.select("INBOX")
    typ, data = M.search(None, "UNSEEN")
    if typ != "OK":
        M.logout()
        return {"ok": False, "error": "IMAP search falló"}
    for num in (data[0] or b"").split()[-max_msgs:]:
        typ, md = M.fetch(num, "(BODY.PEEK[])")   # PEEK = no marca leído
        if typ != "OK" or not md or not md[0]:
            continue
        revisados += 1
        msg = email.message_from_bytes(md[0][1])
        frm = _norm(msg.get("From", "")); subj = msg.get("Subject", "") or ""
        r = _aplicar(frm, subj, lambda: md[0][1])
        if r == "respuesta":
            respondieron += 1
        elif r == "rebote":
            rebotes += 1
    M.logout()
    return {"ok": True, "backend": "imap", "revisados": revisados,
            "respondieron": respondieron, "rebotes": rebotes}


def revisar(max_msgs=100):
    """Lee la casilla y actualiza respuestas/rebotes. Elige Gmail API si hay OAuth,
    si no IMAP, si no es no-op."""
    try:
        if config.gmail_oauth_ready():
            return _revisar_gmail(max_msgs)
        if config.imap_ready():
            return _revisar_imap(max_msgs)
        return {"ok": False, "motivo": "sin backend de lectura (ni OAuth Gmail ni IMAP)"}
    except Exception as e:
        msg = str(e)
        if "insufficient" in msg.lower() or "scope" in msg.lower() or "ACCESS_TOKEN_SCOPE" in msg:
            return {"ok": False, "error": "El token OAuth no tiene permiso de LECTURA. "
                                          "Corré gmail_oauth_setup.py de nuevo para re-autorizar con gmail.readonly."}
        return {"ok": False, "error": msg}

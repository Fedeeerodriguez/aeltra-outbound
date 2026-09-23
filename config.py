# -*- coding: utf-8 -*-
"""Configuración central de Aeltra Outbound (lee de .env)."""
import os
from dotenv import load_dotenv

load_dotenv()

def _b(v, default=False):
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "si", "sí", "on")

# LLM
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-opus-5")

# Backend de envío: 'smtp' (app password) | 'gmail_oauth' (Gmail API OAuth2)
SENDER_BACKEND = os.getenv("SENDER_BACKEND", "smtp")

# Gmail OAuth2
GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID", "")
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "")
GMAIL_REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN", "")
GMAIL_SENDER = os.getenv("GMAIL_SENDER", "")

# SMTP
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
FROM_NAME = os.getenv("FROM_NAME", "Aeltra")
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USER)

# Prospectos
PROSPECTS_MOCK = _b(os.getenv("PROSPECTS_MOCK"), True)
APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# IMAP (lectura de la casilla para detectar RESPUESTAS y rebotes)
# Con Gmail: activá IMAP en la cuenta y usá un App Password (16 caracteres) acá.
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER = os.getenv("IMAP_USER", "") or os.getenv("GMAIL_SENDER", "") or os.getenv("SMTP_USER", "")
IMAP_PASS = os.getenv("IMAP_PASS", "")

# Auth (protege la app cuando está deployada; vacío = sin auth para local)
BASIC_AUTH_USER = os.getenv("BASIC_AUTH_USER", "")
BASIC_AUTH_PASS = os.getenv("BASIC_AUTH_PASS", "")

# Identidad / compliance
COMPANY_NAME = os.getenv("COMPANY_NAME", "Aeltra")
COMPANY_TAGLINE = os.getenv("COMPANY_TAGLINE", "Software & IA")
UNSUB_BASE = os.getenv("UNSUB_BASE", "http://localhost:8000/api/baja")

# Secreto para firmar los links de baja (HMAC). Si no se setea, cae al pass de
# basic-auth; si tampoco existe, usa un default local (solo dev).
UNSUB_SECRET = os.getenv("UNSUB_SECRET", "") or BASIC_AUTH_PASS or "aeltra-unsub-dev"


def unsub_sign(email: str) -> str:
    """Token corto (HMAC-SHA256 truncado) que ata el link de baja a ese email."""
    import hmac, hashlib
    email = (email or "").strip().lower()
    return hmac.new(UNSUB_SECRET.encode("utf-8"), email.encode("utf-8"),
                    hashlib.sha256).hexdigest()[:24]


def unsub_verify(email: str, token: str) -> bool:
    import hmac
    if not token:
        return False
    return hmac.compare_digest(unsub_sign(email), (token or "").strip())

# Ritmo
DEFAULT_WINDOW_HOURS = float(os.getenv("DEFAULT_WINDOW_HOURS", "6"))
DAILY_SEND_CAP = int(os.getenv("DAILY_SEND_CAP", "40"))

# Formato del correo: texto plano puro (más "1-a-1", tiende a caer en Principal).
# Poné PLAIN_TEXT_ONLY=false si querés volver al HTML.
PLAIN_TEXT_ONLY = _b(os.getenv("PLAIN_TEXT_ONLY"), True)

# Rutas
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("DB_PATH", os.path.join(BASE_DIR, "aeltra.db"))

def llm_ready() -> bool:
    return bool(ANTHROPIC_API_KEY)

def smtp_ready() -> bool:
    return bool(SMTP_USER and SMTP_PASS)

def imap_ready() -> bool:
    return bool(IMAP_USER and IMAP_PASS)

def gmail_oauth_ready() -> bool:
    return bool(GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET and GMAIL_REFRESH_TOKEN)

def reply_backend():
    """Lee las respuestas del MISMO buzón desde el que se envía.
    Si enviás por SMTP (Zoho) → IMAP; si enviás por Gmail OAuth → Gmail API."""
    if SENDER_BACKEND == "smtp" and imap_ready():
        return "imap"
    if SENDER_BACKEND == "gmail_oauth" and gmail_oauth_ready():
        return "gmail"
    # fallbacks
    if imap_ready():
        return "imap"
    if gmail_oauth_ready():
        return "gmail"
    return None

def reply_read_ready() -> bool:
    return reply_backend() is not None

def sender_ready() -> bool:
    if SENDER_BACKEND == "gmail_oauth":
        return bool(GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET and GMAIL_REFRESH_TOKEN)
    return smtp_ready()

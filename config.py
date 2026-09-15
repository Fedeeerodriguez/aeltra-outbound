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

# Auth (protege la app cuando está deployada; vacío = sin auth para local)
BASIC_AUTH_USER = os.getenv("BASIC_AUTH_USER", "")
BASIC_AUTH_PASS = os.getenv("BASIC_AUTH_PASS", "")

# Identidad / compliance
COMPANY_NAME = os.getenv("COMPANY_NAME", "Aeltra")
COMPANY_TAGLINE = os.getenv("COMPANY_TAGLINE", "Software & IA")
UNSUB_BASE = os.getenv("UNSUB_BASE", "http://localhost:8000/api/baja")

# Ritmo
DEFAULT_WINDOW_HOURS = float(os.getenv("DEFAULT_WINDOW_HOURS", "6"))
DAILY_SEND_CAP = int(os.getenv("DAILY_SEND_CAP", "40"))

# Rutas
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("DB_PATH", os.path.join(BASE_DIR, "aeltra.db"))

def llm_ready() -> bool:
    return bool(ANTHROPIC_API_KEY)

def smtp_ready() -> bool:
    return bool(SMTP_USER and SMTP_PASS)

def sender_ready() -> bool:
    if SENDER_BACKEND == "gmail_oauth":
        return bool(GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET and GMAIL_REFRESH_TOKEN)
    return smtp_ready()

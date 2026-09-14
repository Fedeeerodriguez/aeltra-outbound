# -*- coding: utf-8 -*-
"""Fábrica de sender pluggable: SMTP (app password) o Gmail API (OAuth2)."""
import config
from .base import Sender
from .smtp_sender import SMTPSender

_sender = None

def get_sender() -> Sender:
    """Devuelve el sender según SENDER_BACKEND ('smtp' | 'gmail_oauth')."""
    global _sender
    if _sender is None:
        if config.SENDER_BACKEND == "gmail_oauth":
            from .gmail_oauth_sender import GmailOAuthSender
            _sender = GmailOAuthSender()
        else:
            _sender = SMTPSender()
    return _sender

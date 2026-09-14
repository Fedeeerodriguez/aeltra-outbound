# -*- coding: utf-8 -*-
"""Sender por Gmail API con OAuth2 (refresh token). Más robusto que SMTP app-password.
Funciona headless (server/Render) porque usa el refresh token, sin navegador."""
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import make_msgid, formataddr

import config
from .base import Sender

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


class GmailOAuthSender(Sender):
    def __init__(self):
        self.sender_email = config.GMAIL_SENDER or config.FROM_EMAIL
        self.from_name = config.FROM_NAME
        self._service = None

    def _svc(self):
        if self._service is None:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            if not (config.GMAIL_CLIENT_ID and config.GMAIL_CLIENT_SECRET and config.GMAIL_REFRESH_TOKEN):
                raise RuntimeError("Faltan credenciales OAuth: GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET / GMAIL_REFRESH_TOKEN")
            creds = Credentials(
                token=None,
                refresh_token=config.GMAIL_REFRESH_TOKEN,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=config.GMAIL_CLIENT_ID,
                client_secret=config.GMAIL_CLIENT_SECRET,
                scopes=[GMAIL_SEND_SCOPE],
            )
            self._service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        return self._service

    def send(self, to_email, to_name, subject, html, text) -> str:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = formataddr((self.from_name, self.sender_email))
        msg["To"] = formataddr((to_name or "", to_email))
        msg_id = make_msgid(domain=self.sender_email.split("@")[-1])
        msg["Message-ID"] = msg_id
        msg["List-Unsubscribe"] = f"<mailto:{self.sender_email}?subject=BAJA>"
        msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        self._svc().users().messages().send(userId="me", body={"raw": raw}).execute()
        return msg_id

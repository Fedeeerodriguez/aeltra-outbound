# -*- coding: utf-8 -*-
"""Sender por SMTP (Gmail App Password). Pluggable: swappable por Resend/SES/Smartlead."""
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.message import EmailMessage
from email.utils import make_msgid, formataddr

import config
from .base import Sender


class SMTPSender(Sender):
    def __init__(self):
        self.host = config.SMTP_HOST
        self.port = config.SMTP_PORT
        self.user = config.SMTP_USER
        self.password = config.SMTP_PASS
        self.from_name = config.FROM_NAME
        self.from_email = config.FROM_EMAIL

    def send(self, to_email, to_name, subject, html, text) -> str:
        if not (self.user and self.password):
            raise RuntimeError("SMTP no configurado: falta SMTP_USER / SMTP_PASS en .env")

        msg_id = make_msgid(domain=self.from_email.split("@")[-1])
        if html:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(text, "plain", "utf-8"))
            msg.attach(MIMEText(html, "html", "utf-8"))
        else:
            # texto plano puro → parece un mail 1-a-1
            msg = EmailMessage()
            msg.set_content(text)
        msg["Subject"] = subject
        msg["From"] = formataddr((self.from_name, self.from_email))
        msg["To"] = formataddr((to_name or "", to_email))
        msg["Message-ID"] = msg_id
        msg["List-Unsubscribe"] = f"<mailto:{self.from_email}?subject=BAJA>"

        ctx = ssl.create_default_context()
        if self.port == 465:
            with smtplib.SMTP_SSL(self.host, self.port, context=ctx, timeout=30) as s:
                s.login(self.user, self.password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=30) as s:
                s.starttls(context=ctx)
                s.login(self.user, self.password)
                s.send_message(msg)
        return msg_id


_sender = None

def get_sender() -> Sender:
    """Devuelve el sender configurado (singleton). Cambiá acá para otro proveedor."""
    global _sender
    if _sender is None:
        _sender = SMTPSender()
    return _sender

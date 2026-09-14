# -*- coding: utf-8 -*-
"""Setup único de OAuth para Gmail. Corré esto UNA vez.
Se abre el navegador, das consentimiento, y escribe las credenciales
DIRECTO en el .env (el refresh token no se imprime en pantalla)."""
import os
import re
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
BASE = os.path.dirname(os.path.abspath(__file__))
CLIENT_FILE = os.path.join(BASE, "client_secret.json")
ENV_FILE = os.path.join(BASE, ".env")


def set_env(vals: dict):
    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as f:
            lines = f.read().splitlines()
    out, seen = [], set()
    for ln in lines:
        m = re.match(r"\s*([A-Z_]+)\s*=", ln)
        if m and m.group(1) in vals:
            out.append(f"{m.group(1)}={vals[m.group(1)]}")
            seen.add(m.group(1))
        else:
            out.append(ln)
    for k, v in vals.items():
        if k not in seen:
            out.append(f"{k}={v}")
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


def main():
    if not os.path.exists(CLIENT_FILE):
        print("ERROR: falta client_secret.json en", BASE)
        return
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_FILE, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    set_env({
        "SENDER_BACKEND": "gmail_oauth",
        "GMAIL_CLIENT_ID": creds.client_id,
        "GMAIL_CLIENT_SECRET": creds.client_secret,
        "GMAIL_REFRESH_TOKEN": creds.refresh_token,
        "GMAIL_SENDER": "contacto.aeltra@gmail.com",
    })
    print("OK: credenciales OAuth escritas en .env (no se muestran acá).")


if __name__ == "__main__":
    main()

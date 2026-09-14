# -*- coding: utf-8 -*-
"""Setup único de OAuth para Gmail. Corré esto UNA vez para obtener el refresh token.

Requisitos previos (en Google Cloud Console, con la cuenta aeltra.contacto@gmail.com):
  1. Crear un proyecto.
  2. Habilitar la "Gmail API".
  3. Pantalla de consentimiento OAuth: tipo "External", en modo "Testing",
     agregar aeltra.contacto@gmail.com como usuario de prueba, scope gmail.send.
  4. Credenciales → Crear credenciales → ID de cliente OAuth → tipo "App de escritorio".
  5. Descargar el JSON y guardarlo acá como  client_secret.json

Después:  python gmail_oauth_setup.py
Se abre el navegador, das consentimiento, y te imprime las 3 variables para el .env.
"""
import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
CLIENT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "client_secret.json")


def main():
    if not os.path.exists(CLIENT_FILE):
        print("ERROR: falta client_secret.json en", os.path.dirname(CLIENT_FILE))
        print("Descargalo de Google Cloud (ID de cliente OAuth · App de escritorio).")
        return
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_FILE, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    print("\n================  PEGÁ ESTO EN TU .env  ================\n")
    print("SENDER_BACKEND=gmail_oauth")
    print(f"GMAIL_CLIENT_ID={creds.client_id}")
    print(f"GMAIL_CLIENT_SECRET={creds.client_secret}")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
    print("GMAIL_SENDER=aeltra.contacto@gmail.com")
    print("\n=======================================================\n")
    print("Listo. Borrá client_secret.json si querés (ya no hace falta).")


if __name__ == "__main__":
    main()

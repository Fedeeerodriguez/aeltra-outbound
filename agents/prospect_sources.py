# -*- coding: utf-8 -*-
"""Fuentes de prospectos: Apify (Google Maps) + búsqueda web. Con modo mock."""
import re
import time
import random
import httpx

import config

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def _mock(nicho, pais, cantidad):
    tipos = ["tienda", "shop", "store", "boutique", "market", "deco", "moda", "kids"]
    dominios = ["gmail.com", "hotmail.com", "outlook.com"]
    nombres = ["Martín", "Sofía", "Lucas", "Valentina", "Diego", "Carla", "Nicolás", "Julieta",
               "Federico", "Camila", "Tomás", "Agustina", "Matías", "Florencia"]
    out = []
    for i in range(cantidad):
        marca = f"{random.choice(tipos).capitalize()}{random.choice(tipos).capitalize()}{random.randint(1,99)}"
        nom = random.choice(nombres)
        email = f"{marca.lower()}.{i}{random.randint(100,999)}@{random.choice(dominios)}"
        out.append({
            "nombre": nom, "email": email, "empresa": marca,
            "nicho": nicho, "pais": pais, "fuente": "mock",
        })
    return out


def apify_google_maps(nicho, pais, cantidad):
    """Scrapea Google Maps con Apify. Best-effort: si falla o no hay token, cae a mock."""
    if config.PROSPECTS_MOCK or not config.APIFY_TOKEN:
        return _mock(nicho, pais, cantidad)
    try:
        actor = "compass~crawler-google-places"
        url = f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?token={config.APIFY_TOKEN}"
        payload = {"searchStringsArray": [f"{nicho} {pais}"], "maxCrawledPlaces": cantidad,
                   "language": "es"}
        r = httpx.post(url, json=payload, timeout=180)
        r.raise_for_status()
        items = r.json()
        out = []
        for it in items:
            email = None
            emails = it.get("emails") or []
            if emails:
                email = emails[0]
            elif it.get("website"):
                email = _scrape_email(it["website"])
            if not email:
                continue
            out.append({
                "nombre": "", "email": email, "empresa": it.get("title", ""),
                "nicho": nicho, "pais": pais, "fuente": "apify",
            })
        return out  # en modo real NO inyectamos mock (evita mails falsos que rebotan)
    except Exception:
        return []


def web_search(nicho, pais, cantidad):
    """Búsqueda web best-effort (DuckDuckGo HTML). Si falla, cae a mock."""
    if config.PROSPECTS_MOCK:
        return _mock(nicho, pais, cantidad)
    try:
        q = f"{nicho} {pais} contacto email"
        r = httpx.get("https://html.duckduckgo.com/html/", params={"q": q},
                      headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        sites = re.findall(r'href="(https?://[^"]+)"', r.text)[:cantidad]
        out = []
        for s in sites:
            email = _scrape_email(s)
            if email:
                out.append({"nombre": "", "email": email, "empresa": "",
                            "nicho": nicho, "pais": pais, "fuente": "web"})
            if len(out) >= cantidad:
                break
        return out  # en modo real NO inyectamos mock (evita mails falsos que rebotan)
    except Exception:
        return []


def _scrape_email(website):
    try:
        r = httpx.get(website, headers={"User-Agent": "Mozilla/5.0"}, timeout=15, follow_redirects=True)
        m = EMAIL_RE.search(r.text)
        return m.group(0).lower() if m else None
    except Exception:
        return None


def google_places(nicho, pais, cantidad):
    """Busca comercios con la Places API (Google Maps Platform) y saca el email de la web.
    Maps NO da email → se scrapea del sitio de cada comercio (por eso no todos rinden mail)."""
    if config.PROSPECTS_MOCK or not config.GOOGLE_MAPS_API_KEY:
        return _mock(nicho, pais, cantidad)
    try:
        url = "https://places.googleapis.com/v1/places:searchText"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": config.GOOGLE_MAPS_API_KEY,
            "X-Goog-FieldMask": "places.displayName,places.websiteUri,nextPageToken",
        }
        out, token = [], None
        for _ in range(max(1, (cantidad + 19) // 20)):
            body = {"textQuery": f"{nicho} en {pais}", "languageCode": "es"}
            if token:
                body["pageToken"] = token
            r = httpx.post(url, json=body, headers=headers, timeout=30)
            r.raise_for_status()
            data = r.json()
            for pl in data.get("places", []):
                site = pl.get("websiteUri")
                empresa = (pl.get("displayName") or {}).get("text", "")
                email = _scrape_email(site) if site else None
                if email:
                    out.append({"nombre": "", "email": email, "empresa": empresa,
                                "nicho": nicho, "pais": pais, "fuente": "google_places"})
                if len(out) >= cantidad:
                    break
            token = data.get("nextPageToken")
            if not token or len(out) >= cantidad:
                break
            time.sleep(2)  # el nextPageToken tarda ~2s en activarse
        return out
    except Exception:
        return []


def search_prospects(nicho, pais, cantidad, fuentes=("apify", "web")):
    """Combina fuentes, deduplica por email y devuelve hasta `cantidad`."""
    por_fuente = max(1, cantidad // max(1, len(fuentes)))
    juntos = []
    for f in fuentes:
        if f == "apify":
            juntos += apify_google_maps(nicho, pais, por_fuente + 5)
        elif f in ("google_places", "google_maps", "maps"):
            juntos += google_places(nicho, pais, por_fuente + 5)
        elif f == "web":
            juntos += web_search(nicho, pais, por_fuente + 5)
    vistos, unicos = set(), []
    for p in juntos:
        e = (p.get("email") or "").lower()
        if e and e not in vistos:
            vistos.add(e)
            unicos.append(p)
    return unicos[:cantidad]

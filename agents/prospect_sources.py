# -*- coding: utf-8 -*-
"""Fuentes de prospectos: Apify (Google Maps) + búsqueda web. Con modo mock."""
import re
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
        return out or _mock(nicho, pais, min(cantidad, 15))
    except Exception:
        return _mock(nicho, pais, min(cantidad, 15))


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
        return out or _mock(nicho, pais, min(cantidad, 15))
    except Exception:
        return _mock(nicho, pais, min(cantidad, 15))


def _scrape_email(website):
    try:
        r = httpx.get(website, headers={"User-Agent": "Mozilla/5.0"}, timeout=15, follow_redirects=True)
        m = EMAIL_RE.search(r.text)
        return m.group(0).lower() if m else None
    except Exception:
        return None


def search_prospects(nicho, pais, cantidad, fuentes=("apify", "web")):
    """Combina fuentes, deduplica por email y devuelve hasta `cantidad`."""
    por_fuente = max(1, cantidad // max(1, len(fuentes)))
    juntos = []
    for f in fuentes:
        if f == "apify":
            juntos += apify_google_maps(nicho, pais, por_fuente + 5)
        elif f == "web":
            juntos += web_search(nicho, pais, por_fuente + 5)
    vistos, unicos = set(), []
    for p in juntos:
        e = (p.get("email") or "").lower()
        if e and e not in vistos:
            vistos.add(e)
            unicos.append(p)
    return unicos[:cantidad]

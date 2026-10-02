# -*- coding: utf-8 -*-
"""Fuentes de prospectos: Apify (Google Maps) + búsqueda web. Con modo mock."""
import re
import time
import random
import httpx

import config

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# Extensiones de archivos/assets que NO son dominios de email. Los sitios usan
# nombres de imagen retina tipo "logo@2x.png" que matchean el patrón de email.
_ASSET_TLDS = ("png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "bmp",
               "css", "js", "mp4", "webm", "woff", "woff2", "ttf", "eot", "pdf")

# Dominios placeholder / de ejemplo que aparecen en plantillas de sitios web y
# siempre rebotan (Null MX o inexistentes). Son la causa #1 de rebotes basura.
_DOMINIOS_BLOQUEADOS = {
    "example.com", "example.org", "example.net", "ejemplo.com", "ejemplo.org",
    "mysite.com", "yoursite.com", "yourdomain.com", "domain.com", "dominio.com",
    "test.com", "tucorreo.com", "tuempresa.com", "email.com", "correo.com",
    "sitename.com", "website.com", "sentry.io", "wixpress.com", "localhost",
    "from.arch", "tv.gb",
}
# Usuarios obviamente de plantilla.
_USUARIOS_BLOQUEADOS = {"email", "youremail", "tuemail", "name", "nombre", "user",
                        "usuario", "ejemplo", "example", "sample", "test"}

def es_email_plausible(email: str) -> bool:
    """Descarta assets (logo@2x.png), retina (@2x/@3x), TLDs de archivo,
    dominios placeholder (example.com/ejemplo.com/…) y usuarios de plantilla."""
    e = (email or "").strip().lower()
    if "@" not in e:
        return False
    usuario, dominio = e.rsplit("@", 1)
    if "@2x" in e or "@3x" in e:
        return False
    if dominio.rsplit(".", 1)[-1] in _ASSET_TLDS:
        return False
    if dominio in _DOMINIOS_BLOQUEADOS:
        return False
    if usuario in _USUARIOS_BLOQUEADOS:
        return False
    if "." not in dominio or dominio.startswith(".") or dominio.endswith("."):
        return False
    return True


# Caché por dominio para no re-resolver DNS en cada lead del mismo dominio.
_MX_CACHE = {}

def dominio_entregable(dominio: str) -> bool:
    """¿El dominio puede recibir correo? Chequea MX; si no hay, cae a registro A.
    Descarta NXDOMAIN y Null MX (la basura típica: esqueleto.com.ar, from.arch…).
    Ante timeouts/errores de red NO descarta (le da el beneficio de la duda, para
    no perder leads válidos por una consulta lenta)."""
    dom = (dominio or "").strip().lower().rstrip(".")
    if not dom or "." not in dom:
        return False
    if dom in _MX_CACHE:
        return _MX_CACHE[dom]
    ok = True
    try:
        import dns.resolver
        res = dns.resolver.Resolver(configure=False)
        # Resolvers públicos (Google + Cloudflare): no dependemos del DNS del host,
        # que en algunas redes hace timeout en vez de devolver NXDOMAIN.
        res.nameservers = ["8.8.8.8", "1.1.1.1", "8.8.4.4"]
        res.lifetime = res.timeout = 6.0
        try:
            mx = res.resolve(dom, "MX")
            # Null MX (RFC 7505): un único MX con host "." = el dominio no recibe mail.
            hosts = [str(r.exchange).rstrip(".") for r in mx]
            ok = not (len(hosts) == 1 and hosts[0] in ("", "."))
        except dns.resolver.NoAnswer:
            # Sin MX → algunos dominios reciben en el registro A.
            try:
                res.resolve(dom, "A"); ok = True
            except Exception:
                ok = False
        except (dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
            ok = False   # dominio inexistente: basura típica de scraping
    except Exception:
        ok = True  # timeout / sin dnspython / red bloqueada: no descartar (no perder leads)
    _MX_CACHE[dom] = ok
    return ok


def email_valido(email: str, chequear_mx: bool = True) -> bool:
    """Plausibilidad (sintaxis/placeholder) + entregabilidad (MX/DNS)."""
    if not es_email_plausible(email):
        return False
    if not chequear_mx:
        return True
    return dominio_entregable((email or "").rsplit("@", 1)[-1])


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


def apify_google_maps(nicho, pais, cantidad, search_terms=None):
    """Scrapea Google Maps con Apify. Best-effort: si falla o no hay token, cae a mock.
    search_terms: lista de queries geográficas (rotación multi-ciudad/país). Si viene vacía
    usa el clásico "nicho pais"."""
    if config.PROSPECTS_MOCK or not config.APIFY_TOKEN:
        return _mock(nicho, pais, cantidad)
    try:
        actor = "compass~crawler-google-places"
        url = f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?token={config.APIFY_TOKEN}"
        terms = list(search_terms) if search_terms else [f"{nicho} {pais}"]
        payload = {"searchStringsArray": terms, "maxCrawledPlaces": cantidad,
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
        for m in EMAIL_RE.findall(r.text):        # 1er match plausible (no assets @2x.png)
            if es_email_plausible(m):
                return m.lower()
        return None
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


def search_prospects(nicho, pais, cantidad, fuentes=("apify", "web"), search_terms=None):
    """Combina fuentes, deduplica por email y devuelve hasta `cantidad`.
    search_terms: rotación geográfica (multi-ciudad/país) que se pasa a Apify."""
    por_fuente = max(1, cantidad // max(1, len(fuentes)))
    juntos = []
    for f in fuentes:
        if f == "apify":
            juntos += apify_google_maps(nicho, pais, por_fuente + 5, search_terms=search_terms)
        elif f in ("google_places", "google_maps", "maps"):
            juntos += google_places(nicho, pais, por_fuente + 5)
        elif f == "web":
            juntos += web_search(nicho, pais, por_fuente + 5)
    vistos, unicos = set(), []
    for p in juntos:
        e = (p.get("email") or "").lower()
        if not e or e in vistos:
            continue
        vistos.add(e)
        if not email_valido(e):      # placeholder/NXDOMAIN/Null MX → descartado antes de encolar
            continue
        unicos.append(p)
    return unicos[:cantidad]

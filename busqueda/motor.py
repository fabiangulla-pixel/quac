"""Motor de búsqueda en cascada → devuelve URLs de notas para los criterios.

Cascada (se intentan en orden y se acumulan resultados sin duplicar URL):
  1. ``buscadores`` por medio (cuando hay adaptador de búsqueda),
  2. Google News RSS (universal, gratis, sin API key),
  3. site-search en un buscador web (último recurso, best-effort).

Cada fuente devuelve ``Resultado``. El motor deduplica, filtra por rango de
fechas y por medios solicitados, y (si se pide) por entidades de interés.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from xml.etree import ElementTree as ET

import httpx

from .criterios import CriteriosBusqueda

logger = logging.getLogger(__name__)

_UA = (
    "QuacBot/0.1 (investigacion academica; prensa electoral colombiana; "
    "contacto: fabian.gulla@gmail.com)"
)


@dataclass
class Resultado:
    url: str
    titular: str = ""
    fecha: str = ""  # ISO-8601 si se conoce
    medio: str = ""
    fuente: str = ""  # "google_news" | "medio:<dominio>" | "site_search"

    def dominio(self) -> str:
        return urlparse(self.url).netloc.replace("www.", "").lower()


# ── Fuente 2: Google News RSS (universal) ───────────────────────────────────

_GNEWS = "https://news.google.com/rss/search"


def _gnews_query(criterios: CriteriosBusqueda) -> str:
    """Construye la query de Google News con términos, fechas y medios.

    Soporta operadores de Google News: ``when:``, ``after:``/``before:`` y
    ``site:`` para restringir a un medio.
    """
    q = criterios.query_principal() or " ".join(criterios.terminos_efectivos()[:3])
    partes = [q] if q else []
    if criterios.desde:
        partes.append(f"after:{criterios.desde.isoformat()}")
    if criterios.hasta:
        partes.append(f"before:{criterios.hasta.isoformat()}")
    # Restringir a medios concretos con site: (OR entre ellos)
    if criterios.medios:
        sites = " OR ".join(f"site:{m}" for m in criterios.medios)
        partes.append(f"({sites})")
    return " ".join(partes)


def _resolver_url_gnews(url: str) -> str:
    """Google News envuelve los enlaces; intenta extraer la URL real.

    Dos formatos:
      - ``...?url=<URL real>``  → trivial.
      - ``.../articles/CBMi...`` → la URL va en base64 dentro del path, en un
        blob protobuf. Se decodifica el base64 y se extrae la primera URL http(s)
        embebida. Si no se logra, se devuelve la URL de Google News tal cual (el
        scraper la seguirá: Google News redirige a la nota real).
    """
    if "news.google.com" not in url:
        return url
    qs = parse_qs(urlparse(url).query)
    if "url" in qs:
        return unquote(qs["url"][0])

    m = re.search(r"/articles/([A-Za-z0-9_\-]+)", url)
    if m:
        real = _decodificar_articulo_gnews(m.group(1))
        if real:
            return real
    return url  # se resolverá siguiendo el redirect al descargar


def _decodificar_articulo_gnews(token: str) -> str | None:
    """Extrae la URL real del token base64 de un enlace /articles/ de GNews."""
    import base64

    try:
        # padding a múltiplo de 4
        data = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    except Exception:
        return None
    # El blob protobuf contiene la URL como texto plano; buscarla.
    try:
        texto = data.decode("latin-1")
    except Exception:
        return None
    m = re.search(r"https?://[^\s\x00-\x1f\"'<>\\]+", texto)
    if not m:
        return None
    candidata = m.group(0)
    # cortar basura binaria final que a veces se cuela tras la URL
    candidata = re.split(r"[\x00-\x1f]", candidata)[0]
    return candidata if "." in urlparse(candidata).netloc else None


def buscar_google_news(
    criterios: CriteriosBusqueda, client: httpx.Client | None = None
) -> list[Resultado]:
    query = _gnews_query(criterios)
    if not query.strip():
        return []
    url = (
        f"{_GNEWS}?q={quote_plus(query)}"
        f"&hl={criterios.idioma}-{criterios.pais}"
        f"&gl={criterios.pais}&ceid={criterios.pais}:{criterios.idioma}"
    )
    cli = client or httpx.Client(headers={"User-Agent": _UA}, timeout=15.0, follow_redirects=True)
    try:
        resp = cli.get(url)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as exc:
        logger.warning("Google News RSS falló: %s", exc)
        return []
    finally:
        if client is None:
            cli.close()

    resultados = []
    for item in root.iterfind(".//item"):
        link = (item.findtext("link") or "").strip()
        titulo = (item.findtext("title") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        fecha_iso = _parse_pubdate(pub)
        # el título de GNews suele venir "Titular - Medio"
        medio = ""
        src = item.find("{http://news.google.com/}source") or item.find("source")
        if src is not None and src.text:
            medio = src.text.strip()
        elif " - " in titulo:
            titulo, medio = titulo.rsplit(" - ", 1)
        resultados.append(
            Resultado(
                url=_resolver_url_gnews(link),
                titular=titulo,
                fecha=fecha_iso,
                medio=medio,
                fuente="google_news",
            )
        )
    return resultados


def _parse_pubdate(pub: str) -> str:
    if not pub:
        return ""
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            dt = datetime.strptime(pub, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.date().isoformat()
        except ValueError:
            continue
    return ""


# ── Fuente 1: buscadores por medio (extensible) ─────────────────────────────
# Cada medio puede registrar aquí cómo buscar en su propio buscador interno.
# De momento vacío: la cascada cae a Google News, que cubre todos los medios.
# Para añadir uno: una función (criterios) -> list[Resultado] con fuente
# "medio:<dominio>", y registrarla en _BUSCADORES_MEDIO.
_BUSCADORES_MEDIO: dict[str, Callable[[CriteriosBusqueda], list]] = {}


def buscar_en_medios(criterios: CriteriosBusqueda) -> list[Resultado]:
    out: list[Resultado] = []
    medios = criterios.medios or list(_BUSCADORES_MEDIO)
    for dom in medios:
        fn = _BUSCADORES_MEDIO.get(dom)
        if fn:
            try:
                out.extend(fn(criterios))
            except Exception as exc:
                logger.warning("Buscador de %s falló: %s", dom, exc)
    return out


# ── Fuente 3: site-search (último recurso, best-effort) ─────────────────────


def buscar_site_search(
    criterios: CriteriosBusqueda, client: httpx.Client | None = None
) -> list[Resultado]:
    """Best-effort: usa el RSS de Bing News como alternativa a Google.

    No depende de API key. Si falla, devuelve []. Se mantiene simple a
    propósito: es el último eslabón de la cascada.
    """
    q = criterios.query_principal()
    if not q:
        return []
    url = f"https://www.bing.com/news/search?q={quote_plus(q)}&format=rss"
    cli = client or httpx.Client(headers={"User-Agent": _UA}, timeout=15.0, follow_redirects=True)
    try:
        resp = cli.get(url)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as exc:
        logger.info("Bing News RSS no disponible: %s", exc)
        return []
    finally:
        if client is None:
            cli.close()
    out = []
    for item in root.iterfind(".//item"):
        out.append(
            Resultado(
                url=_desenvolver_bing(item.findtext("link") or ""),
                titular=(item.findtext("title") or "").strip(),
                fecha=_parse_pubdate(item.findtext("pubDate") or ""),
                fuente="site_search",
            )
        )
    return out


def _desenvolver_bing(link: str) -> str:
    """Extrae la URL real de un enlace redirector de Bing News.

    Bing News RSS entrega enlaces tipo
    ``bing.com/news/apiclick.aspx?...&url=https%3a%2f%2fmedio.co%2f...`` que
    envuelven la URL del medio en el parámetro ``url``. Sin desenvolverlos, la
    nota se guarda con medio="bing.com" (ruido en el corpus). Devuelve la URL
    real cuando existe; si no, el enlace tal cual.
    """
    from urllib.parse import parse_qs, unquote, urlparse

    link = (link or "").strip()
    if "bing.com" not in link.lower():
        return link
    try:
        qs = parse_qs(urlparse(link).query)
        real = qs.get("url", [None])[0]
        if real:
            return unquote(real)
    except Exception:
        pass
    return link


# ── Orquestación ────────────────────────────────────────────────────────────


def buscar(
    criterios: CriteriosBusqueda,
    callback: Callable[[str], None] | None = None,
    aplicar_max: bool = True,
) -> list[Resultado]:
    """Ejecuta la cascada, deduplica y aplica filtros de fecha/medio/entidad.

    ``aplicar_max=False`` devuelve TODOS los resultados encontrados (para que la
    GUI muestre el total real y deje al usuario elegir cuántos/cuáles scrapear).
    """

    def log(m):
        if callback:
            callback(m)

    todos: list[Resultado] = []

    log("Buscando en buscadores de los medios…")
    todos += buscar_en_medios(criterios)

    log("Buscando en Google News…")
    todos += buscar_google_news(criterios)

    if len(todos) < criterios.max_resultados:
        log("Complementando con búsqueda web…")
        todos += buscar_site_search(criterios)

    # Deduplicar por URL y descartar SOLO buscadores directos (bing/google search).
    # OJO: news.google.com NO se excluye aquí — esos enlaces se RESUELVEN al medio
    # real al scrapear (vía Chrome/CDP). Excluirlos aquí vaciaba la búsqueda.
    _EXCLUIR = (
        "www.bing.com",
        "bing.com/search",
        "google.com/search",
        "duckduckgo.com",
        "search.yahoo.com",
    )
    vistos, dedup = set(), []
    for r in todos:
        u = r.url or ""
        if u and u not in vistos and not any(x in u for x in _EXCLUIR):
            vistos.add(u)
            dedup.append(r)

    # Filtro por medios solicitados (si se especificaron)
    if criterios.medios:
        doms = {m.replace("www.", "").lower() for m in criterios.medios}
        dedup = [r for r in dedup if any(d in r.dominio() for d in doms)]

    # Filtro por rango de fechas (cuando la fuente dio fecha)
    dedup = [r for r in dedup if criterios.en_rango(r.fecha)]

    # Filtro opcional por entidades de interés (sobre el titular conocido)
    if criterios.filtrar_por_entidades and criterios.entidades:
        dedup = [r for r in dedup if criterios.menciona_entidad(r.titular) or not r.titular]

    log(f"{len(dedup)} resultados tras deduplicar y filtrar.")
    if aplicar_max:
        return dedup[: criterios.max_resultados]
    return dedup


def medios_de(resultados: list[Resultado]) -> dict:
    """Cuenta resultados por medio (para el checklist de filtro de la GUI)."""
    from collections import Counter

    c = Counter((r.medio or r.dominio()) for r in resultados)
    return dict(c.most_common())


def _trocear_fechas(desde, hasta, dias=7):
    """Parte [desde, hasta] en ventanas de N días (para superar el límite ~100
    de Google News por consulta y traer muchas más notas)."""
    from datetime import timedelta

    if not (desde and hasta):
        return [(desde, hasta)]
    tramos, ini = [], desde
    while ini <= hasta:
        fin = min(ini + timedelta(days=dias - 1), hasta)
        tramos.append((ini, fin))
        ini = fin + timedelta(days=1)
    return tramos


def buscar_masivo(
    criterios: CriteriosBusqueda,
    callback=None,
    dias_tramo: int = 7,
    por_termino: bool = True,
    por_medio: bool = False,
) -> list[Resultado]:
    """Búsqueda EXHAUSTIVA: combina troceo por fechas × términos × (medios).

    Multiplica la cobertura frente a una sola consulta:
      - trocea el rango en ventanas de ``dias_tramo`` días,
      - lanza una búsqueda por cada término/entidad (si por_termino),
      - opcionalmente una por cada medio del perfil (site:),
    y deduplica todo el agregado. Ideal para pasar de cientos a miles de notas.
    """
    import copy

    def log(m):
        if callback:
            callback(m)

    base_terms = criterios.terminos_efectivos() if por_termino else [criterios.query_principal()]
    base_terms = [t for t in base_terms if t] or [criterios.query_principal()]
    tramos = _trocear_fechas(criterios.desde, criterios.hasta, dias_tramo)

    vistos, todos = set(), []
    total_consultas = len(base_terms) * max(1, len(tramos))
    n = 0
    for termino in base_terms:
        for d, h in tramos:
            n += 1
            c = copy.copy(criterios)
            c.terminos = [termino]
            c.entidades = []  # ya expandido en base_terms
            c.desde, c.hasta = d, h
            c.expandir_busqueda = False
            log(f"[{n}/{total_consultas}] «{termino}» {d or ''}…{h or ''}")
            try:
                for r in buscar(c, aplicar_max=False):
                    if r.url and r.url not in vistos:
                        vistos.add(r.url)
                        todos.append(r)
            except Exception as exc:
                log(f"   (consulta falló: {exc})")
    log(f"Búsqueda masiva: {len(todos)} notas únicas de {total_consultas} consultas.")
    return todos

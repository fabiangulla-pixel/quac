"""Adaptadores por medio.

Cada clase ajusta selectores al HTML de su portal y hereda de ``ScraperBase``
el fallback automático a ``trafilatura``. Por eso, aunque un portal cambie su
maquetado, la extracción sigue funcionando (degradada pero útil).

Selectores: se priorizan metadatos estructurados (JSON-LD / Open Graph /
``<meta>``) que son más estables que las clases CSS. La extracción CSS por
clase es la primera opción cuando existe y es estable; si no, trafilatura.
"""

from __future__ import annotations

import json

from bs4 import BeautifulSoup

from .base import Nota, ScraperBase


def _sopa(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def _meta(soup: BeautifulSoup, prop: str) -> str:
    tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
    return (tag.get("content") or "").strip() if tag else ""


def _json_ld(soup: BeautifulSoup) -> dict:
    """Devuelve el primer bloque JSON-LD tipo NewsArticle/Article."""
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        candidatos = data if isinstance(data, list) else [data]
        if isinstance(data, dict) and "@graph" in data:
            candidatos = data["@graph"]
        for c in candidatos:
            if not isinstance(c, dict):
                continue
            tipo = c.get("@type", "")
            tipos = tipo if isinstance(tipo, list) else [tipo]
            if any(t in ("NewsArticle", "Article", "ReportageNewsArticle") for t in tipos):
                return c
    return {}


def _autor_de_jsonld(ld: dict) -> str:
    autor = ld.get("author")
    if isinstance(autor, dict):
        return autor.get("name", "")
    if isinstance(autor, list) and autor:
        nombres = [a.get("name", "") if isinstance(a, dict) else str(a) for a in autor]
        return ", ".join(n for n in nombres if n)
    if isinstance(autor, str):
        return autor
    return ""


class _ScraperEstructurado(ScraperBase):
    """Base para medios que exponen JSON-LD / Open Graph (la mayoría).

    Extrae titular/autor/fecha de los metadatos estructurados y el cuerpo de
    un contenedor de artículo. Si el cuerpo sale corto, ScraperBase cae a
    trafilatura automáticamente.
    """

    # Selectores CSS candidatos para el contenedor del cuerpo, en orden.
    SELECTORES_CUERPO: tuple[str, ...] = (
        "article",
        "div.article-body",
        "div.paywall",
        "div.content",
    )

    def _extraer_con_selectores(self, html: str, url: str) -> Nota | None:
        soup = _sopa(html)
        ld = _json_ld(soup)

        titular = (
            ld.get("headline")
            or _meta(soup, "og:title")
            or (soup.title.string if soup.title else "")
        ).strip()
        autor = _autor_de_jsonld(ld) or _meta(soup, "author")
        fecha = (
            ld.get("datePublished")
            or _meta(soup, "article:published_time")
            or _meta(soup, "og:updated_time")
        ).strip()
        seccion = ld.get("articleSection") or _meta(soup, "article:section")
        if isinstance(seccion, list):
            seccion = seccion[0] if seccion else ""

        cuerpo = self._extraer_cuerpo(soup)

        if not cuerpo:
            return None

        return Nota(
            url=url,
            medio=self.MEDIO,
            titular=titular,
            cuerpo=cuerpo,
            autor=autor.strip(),
            fecha_publicacion=fecha,
            seccion=str(seccion).strip(),
        )

    def _extraer_cuerpo(self, soup: BeautifulSoup) -> str:
        for sel in self.SELECTORES_CUERPO:
            cont = soup.select_one(sel)
            if not cont:
                continue
            parrafos = [p.get_text(" ", strip=True) for p in cont.find_all("p")]
            parrafos = [p for p in parrafos if len(p) > 30]
            texto = "\n\n".join(parrafos)
            if len(texto.split()) >= self.MIN_PALABRAS_CUERPO:
                return texto
        return ""


# --- adaptadores concretos -------------------------------------------------
# Todos heredan el contrato estructurado + fallback trafilatura. Los selectores
# de cuerpo se ajustan donde se conoce el maquetado; el resto usa los genéricos.


class ElTiempo(_ScraperEstructurado):
    MEDIO = "El Tiempo"
    DOMINIOS = ("eltiempo.com",)
    SELECTORES_CUERPO = ("div.c-detail__body", "article", "div.articulo-contenido")


class ElEspectador(_ScraperEstructurado):
    MEDIO = "El Espectador"
    DOMINIOS = ("elespectador.com",)
    SELECTORES_CUERPO = ("div.Article-Content", "article", "div.font--secondary")


class Semana(_ScraperEstructurado):
    MEDIO = "Semana"
    DOMINIOS = ("semana.com",)
    SELECTORES_CUERPO = ("div.paywall", "article", "div.article-body")


class ElColombiano(_ScraperEstructurado):
    MEDIO = "El Colombiano"
    DOMINIOS = ("elcolombiano.com",)
    SELECTORES_CUERPO = ("div.block-content", "article", "div.priva")


class Cambio(_ScraperEstructurado):
    MEDIO = "Cambio"
    DOMINIOS = ("cambiocolombia.com",)


class Volcanicas(_ScraperEstructurado):
    MEDIO = "Volcánicas"
    DOMINIOS = ("volcanicas.com",)


class LaSillaVacia(_ScraperEstructurado):
    MEDIO = "La Silla Vacía"
    DOMINIOS = ("lasillavacia.com",)
    SELECTORES_CUERPO = ("div.field--name-body", "article", "div.content")


class RazonPublica(_ScraperEstructurado):
    MEDIO = "Razón Pública"
    DOMINIOS = ("razonpublica.com",)


class ElPaisCali(_ScraperEstructurado):
    MEDIO = "El País (Cali)"
    DOMINIOS = ("elpais.com.co",)


class Pulzo(_ScraperEstructurado):
    MEDIO = "Pulzo"
    DOMINIOS = ("pulzo.com",)


class LaFM(_ScraperEstructurado):
    MEDIO = "La FM"
    DOMINIOS = ("lafm.com.co",)


class BluRadio(_ScraperEstructurado):
    MEDIO = "Blu Radio"
    DOMINIOS = ("bluradio.com",)


class Caracol(_ScraperEstructurado):
    MEDIO = "Caracol Radio"
    DOMINIOS = ("caracol.com.co",)


class NoticiasRCN(_ScraperEstructurado):
    MEDIO = "Noticias RCN"
    DOMINIOS = ("noticiasrcn.com", "canalrcn.com")


class Voragine(_ScraperEstructurado):
    MEDIO = "Vorágine"
    DOMINIOS = ("voragine.co",)


class CuestionPublica(_ScraperEstructurado):
    MEDIO = "Cuestión Pública"
    DOMINIOS = ("cuestionpublica.com",)


# Lista de todas las clases de adaptadores registradas.
ADAPTADORES = [
    ElTiempo,
    ElEspectador,
    Semana,
    ElColombiano,
    Cambio,
    Volcanicas,
    LaSillaVacia,
    RazonPublica,
    ElPaisCali,
    Pulzo,
    LaFM,
    BluRadio,
    Caracol,
    NoticiasRCN,
    Voragine,
    CuestionPublica,
]

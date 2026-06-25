"""Tests de la capa de búsqueda (criterios + parsing RSS, sin red real)."""

import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from busqueda import motor
from busqueda.criterios import CriteriosBusqueda, EntidadInteres


def test_entidad_todas_las_formas_sin_duplicados():
    e = EntidadInteres(
        "De la Espriella", "persona", ["Abelardo de la Espriella", "de la espriella", "Espriella"]
    )
    formas = e.todas_las_formas
    assert "De la Espriella" in formas
    assert "Espriella" in formas
    # "de la espriella" es duplicado case-insensitive del canónico
    assert sum(f.lower() == "de la espriella" for f in formas) == 1


def test_terminos_efectivos_expande_entidades():
    c = CriteriosBusqueda(
        terminos=["camiseta selección"],
        entidades=[EntidadInteres("De la Espriella", variantes=["Espriella"])],
    )
    terms = c.terminos_efectivos()
    assert "camiseta selección" in terms
    assert "De la Espriella" in terms
    assert "Espriella" in terms


def test_rango_de_fechas():
    c = CriteriosBusqueda(desde="2026-06-01", hasta="2026-06-15")
    assert c.desde == date(2026, 6, 1)
    assert c.en_rango("2026-06-10T08:00:00") is True
    assert c.en_rango("2026-05-30") is False
    assert c.en_rango("2026-06-20") is False
    assert c.en_rango("") is True  # sin fecha no se descarta


def test_fecha_invertida_lanza_error():
    with pytest.raises(ValueError):
        CriteriosBusqueda(desde="2026-06-15", hasta="2026-06-01")


def test_query_google_news_incluye_fechas_y_site():
    c = CriteriosBusqueda(
        terminos=["De la Espriella camiseta"],
        desde="2026-06-01",
        hasta="2026-06-12",
        medios=["eltiempo.com"],
    )
    q = motor._gnews_query(c)
    assert "De la Espriella camiseta" in q
    assert "after:2026-06-01" in q
    assert "before:2026-06-12" in q
    assert "site:eltiempo.com" in q


def test_parse_rss_google_news(monkeypatch):
    rss = """<?xml version="1.0"?>
    <rss><channel>
      <item>
        <title>De la Espriella y la camiseta - El Tiempo</title>
        <link>https://news.google.com/rss/articles/XYZ?url=https://www.eltiempo.com/nota-1</link>
        <pubDate>Wed, 11 Jun 2026 10:00:00 GMT</pubDate>
      </item>
      <item>
        <title>Cepeda cuestiona el uso de la camiseta - Semana</title>
        <link>https://www.semana.com/nota-2</link>
        <pubDate>Thu, 12 Jun 2026 09:00:00 GMT</pubDate>
      </item>
    </channel></rss>"""

    class _Resp:
        content = rss.encode("utf-8")

        def raise_for_status(self):
            pass

    class _Client:
        def get(self, url):
            return _Resp()

        def close(self):
            pass

    c = CriteriosBusqueda(terminos=["De la Espriella camiseta"])
    res = motor.buscar_google_news(c, client=_Client())
    assert len(res) == 2
    # se resolvió la URL real envuelta por Google News
    assert res[0].url == "https://www.eltiempo.com/nota-1"
    assert res[0].medio == "El Tiempo"
    assert res[0].fecha == "2026-06-11"
    assert res[1].url == "https://www.semana.com/nota-2"


def test_no_excluye_enlaces_google_news(monkeypatch):
    # Regresión: el filtro anti-buscador NO debe eliminar enlaces news.google.com
    # (se resuelven al medio real al scrapear). Antes vaciaba la búsqueda.
    from busqueda.motor import Resultado

    gnews = [
        Resultado(
            url="https://news.google.com/rss/articles/CBMiABC",
            titular="Petro hoy",
            medio="Infobae",
            fuente="google_news",
        )
    ]
    monkeypatch.setattr(motor, "buscar_en_medios", lambda c: [])
    monkeypatch.setattr(motor, "buscar_google_news", lambda c, **k: gnews)
    monkeypatch.setattr(motor, "buscar_site_search", lambda c, **k: [])
    c = CriteriosBusqueda(terminos=["Petro"])
    res = motor.buscar(c)
    assert len(res) == 1  # el enlace de Google News se conserva
    # pero una búsqueda directa de Bing sí se excluye
    bing = [Resultado(url="https://www.bing.com/search?q=Petro", titular="x")]
    monkeypatch.setattr(motor, "buscar_google_news", lambda c, **k: bing)
    res2 = motor.buscar(c)
    assert len(res2) == 0


def test_serializacion_criterios(tmp_path):
    c = CriteriosBusqueda(
        terminos=["camiseta"],
        desde="2026-06-01",
        entidades=[EntidadInteres("De la Espriella", "persona", ["Espriella"])],
    )
    ruta = tmp_path / "crit.json"
    c.guardar(ruta)
    c2 = CriteriosBusqueda.cargar(ruta)
    assert c2.terminos == ["camiseta"]
    assert c2.desde == date(2026, 6, 1)
    assert c2.entidades[0].nombre == "De la Espriella"
    assert "Espriella" in c2.entidades[0].variantes

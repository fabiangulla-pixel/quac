"""Tests de la capa de scraping con HTML fixture (sin red)."""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from scrapers.base import Nota, ScraperGenerico
from scrapers.medios import ElEspectador
from scrapers.registro import scraper_para_url

FIXTURES = Path(__file__).parent / "fixtures"


def _html(nombre):
    return (FIXTURES / nombre).read_text(encoding="utf-8")


def test_registro_resuelve_dominio_conocido():
    s = scraper_para_url("https://www.elespectador.com/politica/nota")
    assert isinstance(s, ElEspectador)
    assert s.MEDIO == "El Espectador"


def test_registro_cae_a_generico_para_dominio_desconocido():
    s = scraper_para_url("https://un-medio-cualquiera.co/nota")
    assert isinstance(s, ScraperGenerico)


def test_extraccion_con_selectores_elespectador():
    html = _html("elespectador_ejemplo.html")
    s = ElEspectador()
    nota = s.extraer_nota("https://www.elespectador.com/politica/nota", html=html)
    assert nota is not None
    assert nota.medio == "El Espectador"
    assert "Petro" in nota.titular
    assert nota.metodo_extraccion == "selectores"
    assert nota.autor == "Redacción Política"
    assert nota.fecha_publicacion.startswith("2022-06-01")
    assert nota.seccion == "Política"
    assert nota.n_palabras >= 40
    # No debe colarse el menú/footer
    assert "Pie de página" not in nota.cuerpo


def test_hash_contenido_detecta_republicacion():
    n1 = Nota(url="https://a.co/1", medio="A", cuerpo="Petro y Hernández en campaña.")
    n2 = Nota(url="https://b.co/2", medio="B", cuerpo="Petro y Hernández en campaña.")
    assert n1.hash_contenido == n2.hash_contenido


def test_html_provisto_no_dispara_navegador(monkeypatch):
    # Con html provisto y selectores que fallan, NO debe intentar CDP.
    llamado = {"v": False}

    def _no_debe_llamarse(*a, **k):
        llamado["v"] = True
        return None

    import scrapers.captura_navegador as cn

    monkeypatch.setattr(cn, "capturar_con_sesion", _no_debe_llamarse)
    s = ElEspectador()
    s.extraer_nota("https://www.elespectador.com/x", html="<html></html>")
    assert llamado["v"] is False


def test_captura_navegador_produce_nota(monkeypatch):
    # Simula la captura CDP y verifica que se mapea a una Nota con método "navegador".
    import scrapers.captura_navegador as cn
    from scrapers.captura_navegador import CapturaResultado

    cuerpo = "Petro y Hernández disputan la presidencia de Colombia. " * 10
    monkeypatch.setattr(
        cn,
        "capturar_con_sesion",
        lambda url, **k: CapturaResultado(
            html="<html>...</html>", texto=cuerpo, titulo="Nota electoral", screenshot_png=None
        ),
    )
    s = ElEspectador(usar_navegador=True)
    # descargar() devuelve None (sin red) → cae a navegador
    monkeypatch.setattr(s, "descargar", lambda url, **k: None)
    nota = s.extraer_nota("https://www.elespectador.com/nota-js")
    assert nota is not None
    assert nota.metodo_extraccion == "navegador"
    assert "Petro" in nota.cuerpo


def test_fallback_trafilatura_si_no_hay_selectores():
    # HTML sin contenedor reconocible → debe caer a trafilatura
    html = """<html><head><title>Nota X</title></head><body>
        <main><p>%s</p></main></body></html>""" % ("Texto electoral. " * 60)
    s = ElEspectador()
    nota = s.extraer_nota("https://www.elespectador.com/x", html=html)
    assert nota is not None
    assert nota.cuerpo  # algo se extrajo

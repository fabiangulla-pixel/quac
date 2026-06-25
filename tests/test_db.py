"""Tests de persistencia y deduplicación."""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from db import BaseDatos
from scrapers.base import Nota


def _nota(url, cuerpo="Petro y Hernández en la segunda vuelta presidencial."):
    return Nota(
        url=url, medio="El Espectador", titular="t", cuerpo=cuerpo, fecha_publicacion="2022-06-01"
    )


def test_guardar_y_contar(tmp_path):
    db = BaseDatos(tmp_path / "x.db")
    assert db.guardar_nota(_nota("https://a.co/1")) is True
    assert db.contar() == 1
    db.close()


def test_dedupe_por_url(tmp_path):
    db = BaseDatos(tmp_path / "x.db")
    assert db.guardar_nota(_nota("https://a.co/1")) is True
    assert db.guardar_nota(_nota("https://a.co/1")) is False  # misma URL
    assert db.contar() == 1
    db.close()


def test_dedupe_por_contenido(tmp_path):
    db = BaseDatos(tmp_path / "x.db")
    assert db.guardar_nota(_nota("https://a.co/1")) is True
    # misma nota republicada en otra URL → mismo hash → duplicada
    assert db.guardar_nota(_nota("https://b.co/2")) is False
    assert db.contar() == 1
    db.close()


def test_guardar_analisis(tmp_path):
    db = BaseDatos(tmp_path / "x.db")
    db.guardar_nota(_nota("https://a.co/1"))
    db.guardar_analisis("https://a.co/1", sentimiento={"emocion_dominante": "ira"})
    notas = db.todas_las_notas()
    assert '"emocion_dominante": "ira"' in notas[0]["sentimiento"]
    db.close()

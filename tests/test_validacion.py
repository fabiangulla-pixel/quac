"""Tests de la validación metodológica (muestra + concordancia/Kappa)."""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import validacion


def _notas(n=50):
    return [
        {"url": f"http://m/{i}", "medio": "M", "titular": f"t{i}", "cuerpo": f"cuerpo {i} " * 30}
        for i in range(n)
    ]


def test_exportar_muestra_reproducible(tmp_path):
    notas = _notas(50)
    a = validacion.exportar_muestra(notas, tmp_path / "a.csv", n=10, semilla=42)
    b = validacion.exportar_muestra(notas, tmp_path / "b.csv", n=10, semilla=42)
    assert a.read_text(encoding="utf-8-sig") == b.read_text(encoding="utf-8-sig")


def test_exportar_incluye_polaridad_auto(tmp_path):
    notas = _notas(5)
    analisis = {"http://m/0": {"emociones": {"polaridad": "positivo"}}}
    ruta = validacion.exportar_muestra(notas, tmp_path / "m.csv", n=5, analisis_por_url=analisis)
    txt = ruta.read_text(encoding="utf-8-sig")
    assert "positivo" in txt
    assert "polaridad_manual" in txt  # columna para codificar


def test_concordancia_perfecta(tmp_path):
    ruta = tmp_path / "cod.csv"
    ruta.write_text(
        "polaridad_auto,polaridad_manual\n"
        "positivo,positivo\nnegativo,negativo\nneutro,neutro\npositivo,positivo\n",
        encoding="utf-8-sig",
    )
    r = validacion.calcular_concordancia(ruta)
    assert r["n"] == 4
    assert r["acuerdo"] == 1.0
    assert r["kappa"] == 1.0


def test_concordancia_parcial(tmp_path):
    ruta = tmp_path / "cod.csv"
    ruta.write_text(
        "polaridad_auto,polaridad_manual\n"
        "positivo,positivo\npositivo,negativo\nnegativo,negativo\nneutro,positivo\n",
        encoding="utf-8-sig",
    )
    r = validacion.calcular_concordancia(ruta)
    assert r["n"] == 4
    assert 0.0 < r["acuerdo"] < 1.0
    assert "kappa" in r


def test_concordancia_sin_codificar(tmp_path):
    ruta = tmp_path / "cod.csv"
    ruta.write_text("polaridad_auto,polaridad_manual\npositivo,\nnegativo,\n", encoding="utf-8-sig")
    r = validacion.calcular_concordancia(ruta)
    assert r["n"] == 0
    assert "error" in r


def test_filtrar_relevantes_como_estricto():
    """La muestra Kappa usa el MISMO filtro de relevancia del modo estricto."""
    from pipeline import filtrar_relevantes

    notas = [
        {"url": "a", "titular": "Iván Cepeda gana terreno", "cuerpo": "elecciones"},
        {"url": "b", "titular": "Keiko Fujimori en Perú", "cuerpo": "elecciones"},
        {"url": "c", "titular": "De la Espriella responde", "cuerpo": "campaña"},
        {"url": "d", "titular": "Peso colombiano sube", "cuerpo": "mercados"},
    ]
    res = filtrar_relevantes(notas, ["Cepeda", "Espriella"], ["Fujimori"])
    assert [n["url"] for n in res] == ["a", "c"]
    # plegado de acentos: "Ivan" (sin tilde) también matchea
    res2 = filtrar_relevantes(notas, ["ivan cepeda"], None)
    assert [n["url"] for n in res2] == ["a"]
    # sin filtros = pasa todo
    assert filtrar_relevantes(notas) == notas

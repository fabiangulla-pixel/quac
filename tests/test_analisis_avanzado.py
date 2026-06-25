"""Tests de framing (frame_engine) y análisis avanzado (series, polarización)."""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import analisis_avanzado
from core import frame_engine


def test_frame_legalidad():
    texto = (
        "El juzgado revocó la medida mediante un fallo. La tutela y el "
        "recurso de apelación fueron resueltos por la corte según la ley."
    )
    r = frame_engine.analizar_frame(texto)
    assert r["frame_dominante"] == "legalidad"
    assert r["total_marcadores"] >= 3


def test_frame_identidad():
    texto = (
        "La camiseta de la selección Colombia es un símbolo nacional de "
        "identidad y orgullo patrio para el pueblo colombiano."
    )
    r = frame_engine.analizar_frame(texto)
    assert r["frame_dominante"] == "identidad"


def test_frame_texto_vacio():
    r = frame_engine.analizar_frame("")
    assert r["frame_dominante"] is None
    assert r["distribucion"] == []


def test_series_temporales_agrupa_por_mes():
    por_nota = {
        "u1": {
            "medio": "A",
            "fecha": "2026-05-10",
            "emociones": {"emocion_dominante": "ira"},
            "frame": {"frame_dominante": "seguridad"},
        },
        "u2": {
            "medio": "B",
            "fecha": "2026-05-22",
            "emociones": {"emocion_dominante": "ira"},
            "frame": {"frame_dominante": "legalidad"},
        },
        "u3": {
            "medio": "A",
            "fecha": "2026-06-01",
            "emociones": {"emocion_dominante": "confianza"},
            "frame": {"frame_dominante": "seguridad"},
        },
    }
    s = analisis_avanzado.series_temporales(por_nota)
    assert s["meses"] == ["2026-05", "2026-06"]
    assert s["volumen"]["2026-05"] == 2
    assert s["volumen"]["2026-06"] == 1
    assert s["emociones"]["2026-05"]["ira"] == 2
    assert s["frames"]["2026-05"]["seguridad"] == 1


def test_comparar_medios_matriz():
    por_nota = {
        "u1": {"medio": "El Tiempo", "emociones": {"emocion_dominante": "alegria"}},
        "u2": {"medio": "Semana", "emociones": {"emocion_dominante": "ira"}},
    }
    indice = {"personas": {"Iván Cepeda": ["u1", "u2"], "De la Espriella": ["u1"]}}
    c = analisis_avanzado.comparar_medios(por_nota, indice)
    assert "Iván Cepeda" in c["actores"]
    assert c["matriz"]["El Tiempo"]["Iván Cepeda"] == 1
    assert c["matriz"]["Semana"]["Iván Cepeda"] == 1
    assert c["matriz"]["El Tiempo"]["De la Espriella"] == 1
    assert c["emocion_por_medio"]["Semana"] == "ira"


def test_resumen_frames():
    por_nota = {
        "u1": {"frame": {"frame_dominante": "seguridad", "etiqueta": "Seguridad"}},
        "u2": {"frame": {"frame_dominante": "seguridad", "etiqueta": "Seguridad"}},
        "u3": {"frame": {"frame_dominante": "legalidad", "etiqueta": "Legalidad"}},
    }
    r = analisis_avanzado.resumen_frames(por_nota)
    assert r["distribucion"][0]["frame"] == "seguridad"
    assert r["distribucion"][0]["n"] == 2

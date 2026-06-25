"""Tests de prominencia.py — quién aparece primero y con qué adjetivos.

Los tests de POSICIÓN/orden no requieren spaCy (van por regex sobre el texto).
Los de ADJETIVOS por dependencia requieren el modelo spaCy es; se marcan para
saltarse con gracia si el modelo no está instalado.
"""

import pytest

import prominencia as P

# ── Posición / orden (sin spaCy) ─────────────────────────────────────────────


def test_lider_es_quien_aparece_primero():
    texto = (
        "Iván Cepeda lideró el acto en Bogotá. Más tarde, "
        "Abelardo de la Espriella respondió a las críticas."
    )
    res = P.analizar_prominencia(texto, ["Iván Cepeda", "Abelardo de la Espriella"])
    assert res["lider"] == "Iván Cepeda"
    assert res["orden"] == ["Iván Cepeda", "Abelardo de la Espriella"]
    assert res["por_actor"]["Iván Cepeda"]["rango"] == 1
    assert res["por_actor"]["Abelardo de la Espriella"]["rango"] == 2


def test_posicion_relativa_lead_vs_cola():
    # Espriella al inicio (cerca de 0), Cepeda al final (cerca de 1).
    texto = "Abelardo de la Espriella " + ("texto relleno " * 30) + "Iván Cepeda"
    res = P.analizar_prominencia(texto, ["Iván Cepeda", "Abelardo de la Espriella"])
    pe = res["por_actor"]["Abelardo de la Espriella"]["posicion_relativa"]
    pc = res["por_actor"]["Iván Cepeda"]["posicion_relativa"]
    assert pe < 0.2
    assert pc > 0.8


def test_apellido_suelto_cuenta_como_mencion():
    texto = "Cepeda habló hoy. El senador Cepeda insistió en su propuesta."
    res = P.analizar_prominencia(texto, ["Iván Cepeda"])
    assert res["por_actor"]["Iván Cepeda"]["n_menciones"] == 2


def test_actor_ausente_no_tiene_rango():
    texto = "Solo se menciona a Cepeda en esta nota."
    res = P.analizar_prominencia(texto, ["Iván Cepeda", "Abelardo de la Espriella"])
    aus = res["por_actor"]["Abelardo de la Espriella"]
    assert aus["primera_mencion"] is None
    assert aus["rango"] is None
    assert "Abelardo de la Espriella" not in res["orden"]


def test_variantes_del_perfil_se_casan():
    texto = "De la Espriella encabezó la marcha."
    semillas = {"Abelardo de la Espriella": ["De la Espriella", "Abelardo"]}
    res = P.analizar_prominencia(texto, ["Abelardo de la Espriella"], semillas=semillas)
    assert res["por_actor"]["Abelardo de la Espriella"]["n_menciones"] == 1
    assert res["lider"] == "Abelardo de la Espriella"


# ── Carga léxica de adjetivos (sin spaCy) ────────────────────────────────────


def test_carga_lexica_conocida():
    assert P._carga_lexica("honesto") == "positivo"
    assert P._carga_lexica("corrupto") == "negativo"
    assert P._carga_lexica("azul") == "neutro"


# ── Resumen de corpus ────────────────────────────────────────────────────────


def test_resumen_agrega_veces_primero_y_adjetivos():
    por_nota = {
        "u1": {
            "prominencia": {
                "por_actor": {
                    "Cepeda": {
                        "primera_mencion": 0,
                        "posicion_relativa": 0.0,
                        "rango": 1,
                        "n_menciones": 1,
                        "adjetivos": [{"texto": "honesto", "carga": "positivo"}],
                    },
                    "Espriella": {
                        "primera_mencion": 50,
                        "posicion_relativa": 0.5,
                        "rango": 2,
                        "n_menciones": 1,
                        "adjetivos": [],
                    },
                }
            }
        },
        "u2": {
            "prominencia": {
                "por_actor": {
                    "Cepeda": {
                        "primera_mencion": 10,
                        "posicion_relativa": 0.1,
                        "rango": 1,
                        "n_menciones": 1,
                        "adjetivos": [{"texto": "honesto", "carga": "positivo"}],
                    },
                }
            }
        },
    }
    res = P.resumen_prominencia(por_nota)
    assert res["Cepeda"]["veces_primero"] == 2
    assert res["Cepeda"]["balance_adjetivos"]["positivo"] == 2
    # "honesto" aparece 2 veces para Cepeda, etiquetado positivo
    top0 = res["Cepeda"]["adjetivos_top"][0]
    assert top0["texto"] == "honesto" and top0["n"] == 2 and top0["carga"] == "positivo"
    # El primero del resumen es quien encabeza más notas.
    assert list(res.keys())[0] == "Cepeda"


# ── Adjetivos por dependencia/ventana (requiere spaCy) ───────────────────────


@pytest.fixture(scope="module")
def nlp():
    try:
        from spacy_loader import cargar_modelo_es

        return cargar_modelo_es()
    except Exception:
        pytest.skip("modelo spaCy es no disponible")


def test_adjetivo_directo_amod(nlp):
    texto = "El polémico Cepeda defendió su postura ayer."
    res = P.analizar_prominencia(texto, ["Cepeda"], nlp=nlp)
    adj = [a["texto"].lower() for a in res["por_actor"]["Cepeda"]["adjetivos"]]
    assert any("polémic" in a for a in adj)


def test_adjetivo_por_copula(nlp):
    texto = "Cepeda es honesto y trabajador."
    res = P.analizar_prominencia(texto, ["Cepeda"], nlp=nlp)
    adj = [a["texto"].lower() for a in res["por_actor"]["Cepeda"]["adjetivos"]]
    assert "honesto" in adj
    cargas = {a["texto"].lower(): a["carga"] for a in res["por_actor"]["Cepeda"]["adjetivos"]}
    assert cargas.get("honesto") == "positivo"

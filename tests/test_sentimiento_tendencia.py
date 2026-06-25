"""Tests del sentimiento político, marco intergrupal y tendencia de medios."""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import analisis_avanzado as aa
import sentimiento_politico as sp


def test_polaridad_positiva_negativa():
    pos = sp.analizar_polaridad("Un gran logro y avance, con apoyo y respaldo histórico.")
    neg = sp.analizar_polaridad("Escándalo de corrupción, fraude y ataques; grave crisis.")
    assert pos["polaridad"] == "positivo" and pos["score"] > 0
    assert neg["polaridad"] == "negativo" and neg["score"] < 0


def test_negacion_invierte():
    r = sp.analizar_polaridad("No hubo ningún logro ni avance.")
    # "logro/avance" negados → no debe salir positivo
    assert r["polaridad"] != "positivo"


def test_polaridad_hacia_entidad():
    texto = (
        "Cepeda presentó una propuesta de paz con gran respaldo. "
        "En otro tema económico sin relación se habló de impuestos."
    )
    r = sp.polaridad_hacia(texto, ["Iván Cepeda", "Cepeda"])
    assert r["n_menciones"] >= 1
    assert r["score"] > 0  # el entorno de Cepeda es positivo


def test_indice_polarizacion_afectiva():
    # mucha división pos/neg → alto; todo neutro → 0
    alto = sp.indice_polarizacion_afectiva({"positivo": 10, "negativo": 10, "neutro": 0})
    bajo = sp.indice_polarizacion_afectiva({"positivo": 0, "negativo": 0, "neutro": 20})
    unlado = sp.indice_polarizacion_afectiva({"positivo": 20, "negativo": 0, "neutro": 0})
    assert alto > 0.8
    assert bajo == 0.0
    assert unlado < 0.2


def test_intergrupal_nosotros_ellos():
    r = sp.analizar_intergrupal(
        "Nosotros unidos defendemos la patria; ellos son corruptos y traidores enemigos del pueblo."
    )
    assert r["endogrupo"] >= 1
    assert r["deslegitimacion"] >= 1
    assert r["indice_intergrupal"] > 0


def test_tendencia_medios_detecta_sesgo():
    perfil = {
        "entidades": [
            {"nombre": "Cepeda", "tipo": "candidato", "variantes": []},
            {"nombre": "Espriella", "tipo": "candidato", "variantes": []},
        ]
    }
    notas = [
        {"medio": "Medio A", "cuerpo": "Cepeda logró un gran avance con respaldo y éxito."},
        {"medio": "Medio A", "cuerpo": "Espriella enfrenta un escándalo de corrupción y fraude."},
        {"medio": "Medio B", "cuerpo": "Espriella presentó una propuesta con apoyo y esperanza."},
    ]
    t = aa.tendencia_medios(notas, perfil)
    assert "Cepeda" in t["candidatos"] and "Espriella" in t["candidatos"]
    a = t["medios"]["Medio A"]
    # Medio A: positivo con Cepeda, negativo con Espriella → favorece Cepeda
    assert a["favorece"] == "Cepeda"
    assert a["sesgo"] > 0


def test_tendencia_excluye_buscadores():
    perfil = {"entidades": [{"nombre": "Cepeda", "tipo": "candidato", "variantes": []}]}
    notas = [{"medio": "bing.com", "cuerpo": "Cepeda y su campaña con apoyo."}]
    t = aa.tendencia_medios(notas, perfil)
    assert "bing.com" not in t["medios"]

"""Tests de la revisión human-in-the-loop y de correferencia."""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import revision
from core import coref_engine
from db import BaseDatos


def _indice():
    return {
        "personas": {
            "Iván Cepeda": ["u1", "u2", "u3", "u4", "u5", "u6"],  # muchas notas → confiable
            "Fulanito": ["u1"],  # 1 nota → dudosa
            "Mengano": ["u2"],  # 1 nota → dudosa
        },
        "organizaciones": {"FARC": ["u1", "u2", "u3", "u4", "u5"]},
        "lugares": {},
    }


def test_cola_solo_dudosas():
    cola = revision.construir_cola(_indice())
    nombres = {c["nombre"] for c in cola}
    # Iván Cepeda (6 notas) y FARC (5) son confiables → no entran
    assert "Iván Cepeda" not in nombres
    assert "Fulanito" in nombres
    assert "Mengano" in nombres


def test_semilla_sube_confianza():
    # Si "Fulanito" fuera entidad de interés declarada, no debería ser dudosa
    cola = revision.construir_cola(_indice(), semillas={"Fulanito": ["Fulanito", "Don Fulano"]})
    nombres = {c["nombre"] for c in cola}
    assert "Fulanito" not in nombres  # ahora cuenta como en KB


def test_decidir_y_aplicar_descartar(tmp_path):
    db = BaseDatos(tmp_path / "r.db")
    cola = revision.construir_cola(_indice())
    revision.guardar_cola(db, cola)
    assert revision.decidir(db, "Fulanito", "personas", revision.DESCARTADA)

    indice = _indice()
    decisiones = revision.cargar_decisiones(db)
    revision.aplicar_revisiones(indice, decisiones)
    assert "Fulanito" not in indice["personas"]
    assert "Iván Cepeda" in indice["personas"]  # intacto
    db.close()


def test_decidir_y_aplicar_renombrar(tmp_path):
    db = BaseDatos(tmp_path / "r.db")
    revision.guardar_cola(db, revision.construir_cola(_indice()))
    revision.decidir(db, "Mengano", "personas", revision.RENOMBRADA, nombre_nuevo="Iván Cepeda")
    indice = _indice()
    revision.aplicar_revisiones(indice, revision.cargar_decisiones(db))
    assert "Mengano" not in indice["personas"]
    # sus artículos se fusionaron en Iván Cepeda
    assert "u2" in indice["personas"]["Iván Cepeda"]
    db.close()


def test_guardar_cola_no_pisa_decisiones(tmp_path):
    db = BaseDatos(tmp_path / "r.db")
    revision.guardar_cola(db, revision.construir_cola(_indice()))
    revision.decidir(db, "Fulanito", "personas", revision.VERIFICADA)
    # re-guardar la cola no debe revertir la decisión
    revision.guardar_cola(db, revision.construir_cola(_indice()))
    dec = revision.cargar_decisiones(db)
    assert dec[("Fulanito", "personas")]["decision"] == revision.VERIFICADA
    db.close()


def test_coref_cuenta_pronombres():
    texto = (
        "Iván Cepeda lideró el acto. Él habló de paz. Luego, el político insistió en su mensaje."
    )
    cadenas = coref_engine.resolver_correferencias(texto, usar_coreferee=False)
    assert cadenas
    principal = cadenas[0]
    assert "Cepeda" in principal["entidad_principal"]
    assert principal["n_menciones"] >= 2  # entidad + al menos un pronombre

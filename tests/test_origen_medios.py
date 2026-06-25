"""Tests de origen_medios.py — país de origen del medio (colombiano vs extranjero)."""

import origen_medios as O


def test_dominios_colombianos_sin_tld_nacional():
    # eltiempo.com es colombiano aunque sea .com (caso que el TLD no resuelve).
    o = O.clasificar_origen("https://www.eltiempo.com/politica/nota-123")
    assert o["es_colombiano"] and o["pais"] == "Colombia" and o["fuente"] == "tabla"


def test_elpais_es_distingue_de_elpais_com_co():
    espana = O.clasificar_origen("https://elpais.com/internacional/x")
    colomb = O.clasificar_origen("https://elpais.com.co/x")
    assert espana["es_extranjero"] and espana["pais"] == "España"
    assert colomb["es_colombiano"] and colomb["pais"] == "Colombia"


def test_infobae_es_argentino():
    o = O.clasificar_origen("infobae.com")
    assert o["es_extranjero"] and o["pais"] == "Argentina"


def test_tld_co_es_colombia_por_respaldo():
    # Dominio .co no listado en la tabla → cae a la regla de TLD.
    o = O.clasificar_origen("https://undominioraro123.co/nota")
    assert o["pais"] == "Colombia" and o["fuente"] == "tld"


def test_tld_es_es_espana():
    o = O.clasificar_origen("https://periodicodesconocido.es/x")
    assert o["pais"] == "España" and o["es_extranjero"]


def test_com_co_por_tld():
    o = O.clasificar_origen("https://otromedio.com.co/x")
    assert o["pais"] == "Colombia" and o["es_colombiano"]


def test_desconocido_no_revienta():
    o = O.clasificar_origen("https://algo.xyz/x")
    assert o["pais"] is None and o["fuente"] == "desconocido"
    assert not o["es_colombiano"] and not o["es_extranjero"]


def test_perfil_internacional_refuerza():
    perfil = {"medios": {"internacional": ["mediofantasma.net"], "prensa": ["otrocolombiano.com"]}}
    ext = O.clasificar_origen("mediofantasma.net", perfil=perfil)
    col = O.clasificar_origen("otrocolombiano.com", perfil=perfil)
    assert ext["es_extranjero"] and ext["fuente"] == "perfil"
    assert col["es_colombiano"] and col["fuente"] == "perfil"


def test_resumen_agrega_origen():
    por_nota = {
        "u1": {
            "medio": "eltiempo.com",
            "origen": {"pais": "Colombia", "es_colombiano": True, "es_extranjero": False},
        },
        "u2": {
            "medio": "infobae.com",
            "origen": {"pais": "Argentina", "es_colombiano": False, "es_extranjero": True},
        },
        "u3": {
            "medio": "infobae.com",
            "origen": {"pais": "Argentina", "es_colombiano": False, "es_extranjero": True},
        },
        "u4": {
            "medio": "raro.xyz",
            "origen": {"pais": None, "es_colombiano": False, "es_extranjero": False},
        },
    }
    r = O.resumen_origen(por_nota)
    assert r["n_colombianos"] == 1
    assert r["n_extranjeros"] == 2
    assert r["n_desconocidos"] == 1
    assert r["por_pais"]["Argentina"] == 2
    assert r["medios_extranjeros"]["infobae.com"] == 2

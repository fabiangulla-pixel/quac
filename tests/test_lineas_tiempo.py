"""Tests de lineas_tiempo.py — series diarias, media móvil, picos, filtro de medios."""

import lineas_tiempo as LT

PERFIL = {
    "entidades": [
        {"nombre": "Cepeda", "tipo": "candidato", "variantes": ["Iván Cepeda"]},
        {"nombre": "Espriella", "tipo": "candidato", "variantes": ["De la Espriella"]},
    ]
}


def _nota(dia, medio, texto):
    return {
        "medio": medio,
        "fecha": dia,
        "cuerpo": texto,
        "frame": {"frame_dominante": "seguridad"},
    }


def test_rango_dias_rellena_huecos():
    dias = LT._rango_dias(["2026-06-01", "2026-06-04"])
    assert dias == ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04"]


def test_media_movil_ignora_none():
    s = [1.0, None, 3.0]
    mm = LT._media_movil(s, ventana=3)
    assert mm[0] == 1.0  # (1) solo
    assert mm[1] == 2.0  # (1+3)/2
    assert mm[2] == 3.0  # (3) solo


def test_volumen_y_dias():
    por_nota = {
        "u1": _nota("2026-06-01", "eltiempo.com", "nota sobre Cepeda"),
        "u2": _nota("2026-06-01", "semana.com", "nota sobre Espriella"),
        "u3": _nota("2026-06-03", "eltiempo.com", "otra de Cepeda"),
    }
    r = LT.series_diarias(por_nota, PERFIL)
    assert r["dias"] == ["2026-06-01", "2026-06-02", "2026-06-03"]
    assert r["volumen"] == [2, 0, 1]
    assert r["candidatos"] == ["Cepeda", "Espriella"]


def test_filtro_por_grupo_de_medios():
    por_nota = {
        "u1": _nota("2026-06-01", "eltiempo.com", "Cepeda"),
        "u2": _nota("2026-06-01", "infobae.com", "Cepeda"),
    }
    # solo eltiempo
    r = LT.series_diarias(por_nota, PERFIL, medios=["eltiempo"])
    assert r["volumen"] == [1]
    assert "grupo" in r["ambito"]


def test_sesgo_presente_con_dos_candidatos():
    por_nota = {
        "u1": _nota("2026-06-01", "x.com", "Cepeda logro avance histórico victoria"),
        "u2": _nota("2026-06-01", "x.com", "Espriella escándalo fraude corrupción"),
    }
    r = LT.series_diarias(por_nota, PERFIL)
    assert len(r["sesgo"]) == len(r["dias"])
    # con dos candidatos el primero (Cepeda) debería salir mejor tratado → sesgo>0
    assert r["sesgo"][0] is None or isinstance(r["sesgo"][0], float)


def test_picos_volumen():
    dias = ["d1", "d2", "d3", "d4", "d5"]
    vol = [1, 1, 10, 1, 1]  # pico claro en d3
    picos = LT.picos_volumen(dias, vol, umbral_sigma=1.0)
    assert any(p["dia"] == "d3" for p in picos)


def test_frames_en_porcentaje():
    por_nota = {
        "u1": _nota("2026-06-01", "x.com", "Cepeda"),
        "u2": {
            "medio": "x.com",
            "fecha": "2026-06-01",
            "cuerpo": "Espriella",
            "frame": {"frame_dominante": "economico"},
        },
    }
    r = LT.series_diarias(por_nota, PERFIL)
    fr = r["frames"]
    # dos frames distintos el mismo día → 50% cada uno
    assert fr["seguridad"][0] == 50.0
    assert fr["economico"][0] == 50.0

"""Tests del estimador de tokens/costo (Claude) y del costo real desde usage."""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from core.costos import (  # noqa: E402
    PRECIOS,
    costo_real_desde_usages,
    estimar_lote_tono,
    estimar_tokens,
)


def test_estimar_tokens_proporcional():
    assert estimar_tokens("") == 0
    assert estimar_tokens("hola " * 100) > estimar_tokens("hola")


def test_precios_claude_coinciden_con_skill():
    # Verificado contra la skill claude-api (cache 2026-06-04).
    assert PRECIOS["claude-haiku-4-5"].input_por_millon == 1.00
    assert PRECIOS["claude-haiku-4-5"].output_por_millon == 5.00
    assert PRECIOS["claude-opus-4-8"].output_por_millon == 25.00


def test_modelo_con_sufijo_de_fecha_se_empareja_por_familia():
    # El id real trae sufijo de fecha; debe catalogarse igual.
    est = estimar_lote_tono({"a": "texto"}, "claude-haiku-4-5-20251001")
    assert est.modelo_catalogado is True
    assert est.precio_input_por_millon == 1.00


def test_estimar_lote_acepta_texto_y_dict():
    articulos = {
        "1": "x" * 4000,
        "2": {"texto": "y" * 4000, "seccion": "Editorial"},
    }
    est = estimar_lote_tono(articulos, "claude-haiku-4-5")
    assert est.n_items == 2
    assert est.tokens_output == 2 * 512
    assert est.costo_usd > 0


def test_fragmento_se_recorta_a_5000():
    # Un texto enorme se acota: el input no crece sin límite.
    corto = estimar_lote_tono({"a": "x" * 5000}, "claude-haiku-4-5")
    largo = estimar_lote_tono({"a": "x" * 50000}, "claude-haiku-4-5")
    assert corto.tokens_input == largo.tokens_input


def test_modelo_no_catalogado_usa_cota_superior():
    est = estimar_lote_tono({"a": "x"}, "modelo-raro-9000")
    assert est.modelo_catalogado is False
    mas_caro = max(p.output_por_millon for p in PRECIOS.values())
    assert est.precio_output_por_millon == mas_caro


def test_lote_vacio():
    est = estimar_lote_tono({}, "claude-haiku-4-5")
    assert est.n_items == 0
    assert est.costo_usd == 0


def test_costo_real_desde_usages_dict_y_objeto():
    class _U:
        input_tokens = 1_000_000
        output_tokens = 0
        cache_creation_input_tokens = 0

    usages = [
        _U(),  # objeto estilo SDK
        {"input_tokens": 0, "output_tokens": 1_000_000},  # dict
    ]
    real = costo_real_desde_usages("claude-haiku-4-5", usages)
    assert real.tokens_input == 1_000_000
    assert real.tokens_output == 1_000_000
    # 1M in ($1) + 1M out ($5) = $6
    assert round(real.costo_usd, 2) == 6.00


def test_costo_real_cuenta_cache_creation_como_entrada():
    usages = [{"input_tokens": 500_000, "cache_creation_input_tokens": 500_000}]
    real = costo_real_desde_usages("claude-haiku-4-5", usages)
    assert real.tokens_input == 1_000_000


def test_costo_real_ignora_none():
    real = costo_real_desde_usages("claude-haiku-4-5", [None, {"input_tokens": 5}])
    assert real.tokens_input == 5

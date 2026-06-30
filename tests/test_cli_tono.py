"""Tests del comando CLI `tono`: estima el costo y respeta la confirmación.

No llaman a Claude: verifican que el flujo de costo (estándar: estimar →
confirmar → no gastar si se cancela) funciona sin red ni API key real.
"""

import builtins
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import cli  # noqa: E402
from db import BaseDatos  # noqa: E402
from scrapers.base import Nota  # noqa: E402


class _Args:
    def __init__(self, **kw):
        self.db = kw.get("db")
        self.api_key = kw.get("api_key", "sk-dummy")
        self.modelo = kw.get("modelo", "claude-haiku-4-5-20251001")
        self.limite = kw.get("limite", 0)
        self.workers = kw.get("workers", 4)
        self.salida = kw.get("salida")
        self.si = kw.get("si", False)


def _db_con_notas(tmp_path, n=3):
    db = BaseDatos(tmp_path / "x.db")
    for i in range(n):
        db.guardar_nota(
            Nota(
                url=f"https://a.co/{i}",
                medio="El Espectador",
                titular=f"Titular {i}",
                cuerpo="Cepeda y De la Espriella en la segunda vuelta. " * 20,
                fecha_publicacion="2026-06-15",
            )
        )
    db.close()
    return tmp_path / "x.db"


def test_tono_cancela_no_gasta(tmp_path, monkeypatch, capsys):
    ruta = _db_con_notas(tmp_path)
    # El usuario responde "n": no debe llamar a Claude.
    monkeypatch.setattr(builtins, "input", lambda *_: "n")

    def _no_llamar(*a, **k):
        raise AssertionError("No debe llamar a Claude si se cancela")

    monkeypatch.setattr(cli.sentiment_engine, "analizar_corpus_tono", _no_llamar, raising=False)

    rc = cli.cmd_tono(_Args(db=str(ruta)))
    out = capsys.readouterr().out
    assert rc == 0
    assert "COSTO ESTIMADO" in out
    assert "Cancelado" in out


def test_tono_sin_api_key_falla(tmp_path, monkeypatch):
    ruta = _db_con_notas(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rc = cli.cmd_tono(_Args(db=str(ruta), api_key=None))
    assert rc == 1


def test_combinar_semillas_perfil_manda():
    # La BD trae basura: "Petro" e "Iván Cepeda" como canónicos propios, y
    # "Iván Cepeda Castro" sin variantes. El perfil debe imponerse y fundir todo.
    db_sem = {
        "Gustavo Petro": ["Gustavo Petro", "Gustavo"],
        "Petro": ["Petro"],
        "Iván Cepeda": ["Iván Cepeda"],
        "Iván Cepeda Castro": ["Iván Cepeda Castro"],
    }
    perfil_sem = {
        "Gustavo Petro": ["Gustavo Petro", "Petro"],
        "Iván Cepeda Castro": ["Iván Cepeda Castro", "Iván Cepeda", "Cepeda"],
    }
    out = cli._combinar_semillas(db_sem, perfil_sem)
    # Los canónicos-basura de la BD desaparecen (son variantes del perfil).
    assert "Petro" not in out
    assert "Iván Cepeda" not in out
    # El perfil conserva y une variantes.
    assert "Petro" in out["Gustavo Petro"]
    assert "Cepeda" in out["Iván Cepeda Castro"]
    assert "Iván Cepeda" in out["Iván Cepeda Castro"]


def test_tono_estima_y_ejecuta_con_si(tmp_path, monkeypatch, capsys):
    ruta = _db_con_notas(tmp_path, n=2)

    from core.costos import CostoReal

    def _fake_corpus(articulos, **kw):
        resultados = {aid: {"tono_principal": "neutro"} for aid in articulos}
        real = CostoReal(
            modelo=kw["modelo"],
            tokens_input=1000,
            tokens_output=500,
            costo_usd=0.0035,
            modelo_catalogado=True,
        )
        return resultados, real

    monkeypatch.setattr(cli.sentiment_engine, "analizar_corpus_tono", _fake_corpus, raising=False)

    rc = cli.cmd_tono(_Args(db=str(ruta), si=True))
    out = capsys.readouterr().out
    assert rc == 0
    assert "COSTO ESTIMADO" in out
    assert "COSTO REAL" in out

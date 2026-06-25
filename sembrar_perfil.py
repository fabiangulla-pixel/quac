#!/usr/bin/env python
"""Siembra las entidades del perfil en la tabla entidades_interes de una BD.

El comando `corpus` ya lo hace al arrancar, pero esto permite sembrar una BD
existente (p. ej. un corpus scrapeado antes de añadir esa siembra) para que el
`analizar` canonicalice las variantes (Cepeda / Iván Cepeda / …) y cargue los
marcos del perfil.

Uso:  python sembrar_perfil.py datos/corpus_grande.db
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config
from db import BaseDatos


def sembrar(ruta_db: str) -> int:
    db = BaseDatos(ruta_db)
    db.con.execute(
        "CREATE TABLE IF NOT EXISTS entidades_interes "
        "(nombre TEXT PRIMARY KEY, tipo TEXT, formas TEXT)"
    )
    n = 0
    for e in config.cargar().get("entidades", []):
        formas = [e["nombre"]] + e.get("variantes", [])
        db.con.execute(
            "INSERT OR REPLACE INTO entidades_interes VALUES (?,?,?)",
            (e["nombre"], e.get("tipo", "persona"), json.dumps(formas, ensure_ascii=False)),
        )
        n += 1
    db.con.commit()
    db.close()
    return n


if __name__ == "__main__":
    ruta = sys.argv[1] if len(sys.argv) > 1 else "datos/quac.db"
    n = sembrar(ruta)
    print(f"{n} entidades del perfil sembradas en {ruta}")

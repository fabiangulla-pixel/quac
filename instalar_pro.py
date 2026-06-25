#!/usr/bin/env python
"""Instalador de ¡Quac! PRO (con transformers: pysentimiento + BERTopic).

IMPORTANTE: la versión PRO requiere **Python 3.12** (no 3.13/3.14: torch y
transformers segfaultean en versiones muy nuevas de Python). Ejecuta este script
CON un Python 3.12:

    py -3.12 instalar_pro.py        (Windows, con el py launcher)

Crea/usa el entorno actual e instala torch (CPU) + pysentimiento + bertopic +
las dependencias base + el modelo spaCy. Pesado (~2-3 GB de descarga).
"""

from __future__ import annotations

import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

BASE = [
    "spacy>=3.8",
    "click>=8.0",
    "networkx>=3.6",
    "requests>=2.32",
    "beautifulsoup4>=4.13",
    "lxml>=5.0",
    "trafilatura>=2.0",
    "pyvis>=0.3",
    "httpx>=0.27",
    "websocket-client>=1.7",
    "openpyxl>=3.1",
    "scikit-learn>=1.4",
]
PRO = ["pysentimiento", "bertopic"]


def _run(cmd):
    print("  $", " ".join(cmd))
    return subprocess.call(cmd)


def main():
    print("Instalador de ¡Quac! PRO 🦆 (transformers)\n")
    if sys.version_info[:2] != (3, 12):
        print(
            f"  ⚠ Estás usando Python {sys.version.split()[0]}. La versión PRO "
            "se diseñó para Python 3.12.\n  En 3.13/3.14 torch puede fallar "
            "(segfault). Recomendado: py -3.12 instalar_pro.py"
        )
        if input("  ¿Continuar igual? [s/N]: ").strip().lower() != "s":
            return 1

    print("\n=== 1. Dependencias base ===")
    if _run([sys.executable, "-m", "pip", "install", "--upgrade", *BASE]):
        return 1

    print("\n=== 2. torch (CPU) ===")
    _run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "torch",
            "--index-url",
            "https://download.pytorch.org/whl/cpu",
        ]
    )

    print("\n=== 3. pysentimiento + bertopic (transformers) ===")
    if _run([sys.executable, "-m", "pip", "install", *PRO]):
        return 1

    print("\n=== 4. Modelo spaCy español ===")
    import spacy

    try:
        spacy.load("es_core_news_sm")
        print("  ✓ ya instalado")
    except OSError:
        _run([sys.executable, "-m", "spacy", "download", "es_core_news_sm"])

    print("\n=== 5. Verificación ===")
    fallos = []
    for m in ("torch", "pysentimiento", "bertopic", "spacy", "openpyxl"):
        try:
            __import__(m)
        except Exception as e:
            fallos.append(f"{m}: {e}")
    if fallos:
        print("  ✗", fallos)
        return 1
    print("  ✓ Pila PRO completa")
    print("\nLanza la versión PRO con:  python gui.py")
    print("(activa las casillas de transformer/BERTopic en la pestaña Análisis)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""Instalador de ¡Quac! para una PC limpia.

Verifica Python, instala dependencias, descarga el modelo spaCy español y
comprueba que todo carga. Pensado para ejecutarse desde el código fuente (no
desde el .exe, que ya trae todo empaquetado).

Uso:  python instalar.py
"""

from __future__ import annotations

import subprocess
import sys

# La consola de Windows usa cp1252 y no codifica emojis/símbolos Unicode.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

MIN_PY = (3, 10)

DEPENDENCIAS = [
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
# Opcionales (sentimiento transformer): pesados, se ofrecen aparte.
OPCIONALES = ["transformers>=4.40", "torch>=2.0"]

MODELO_SPACY = "es_core_news_sm"


def _run(cmd):
    print("  $", " ".join(cmd))
    return subprocess.call(cmd)


def paso(msg):
    print(f"\n=== {msg} ===")


def main():
    print("Instalador de ¡Quac! 🦆\n")

    paso("1. Verificando Python")
    if sys.version_info < MIN_PY:
        print(f"  ✗ Se requiere Python {MIN_PY[0]}.{MIN_PY[1]}+. Tienes {sys.version.split()[0]}")
        return 1
    print(f"  ✓ Python {sys.version.split()[0]}")

    paso("2. Instalando dependencias")
    if _run([sys.executable, "-m", "pip", "install", "--upgrade", *DEPENDENCIAS]):
        print("  ✗ Falló la instalación de dependencias.")
        return 1
    print("  ✓ Dependencias instaladas")

    paso("3. Descargando modelo lingüístico español (spaCy)")
    try:
        import spacy
    except ImportError as e:
        print(f"  ✗ spaCy no se importa: {e}")
        return 1
    try:
        spacy.load(MODELO_SPACY)
        print(f"  ✓ {MODELO_SPACY} ya está instalado")
    except OSError:
        if _run([sys.executable, "-m", "spacy", "download", MODELO_SPACY]):
            print("  ✗ No se pudo descargar el modelo (¿sin internet?).")
            return 1
        print(f"  ✓ {MODELO_SPACY} descargado")

    paso("4. Verificación final (importando todo)")
    fallos = []
    for mod in (
        "spacy",
        "networkx",
        "requests",
        "bs4",
        "lxml",
        "trafilatura",
        "pyvis",
        "httpx",
        "websocket",
        "openpyxl",
        "sklearn",
    ):
        try:
            __import__(mod)
        except ImportError as e:
            fallos.append(f"{mod}: {e}")
    # módulos propios
    sys.path.insert(0, ".")
    for mod in (
        "config",
        "pipeline",
        "dashboard",
        "exportar_excel",
        "sentimiento_politico",
        "validacion",
        "calidad",
    ):
        try:
            __import__(mod)
        except Exception as e:
            fallos.append(f"{mod}: {e}")
    try:
        from spacy_loader import cargar_modelo_es

        cargar_modelo_es()
    except Exception as e:
        fallos.append(f"modelo spaCy no carga: {e}")

    if fallos:
        print("  ✗ Problemas detectados:")
        for f in fallos:
            print("    -", f)
        return 1
    print("  ✓ Todo carga correctamente")

    paso("Listo")
    print("Ejecuta la interfaz con:  python gui.py")
    print("O la línea de comandos:   python cli.py --help")
    print("\nOpcional (sentimiento transformer, ~1.5GB):")
    print(f"  pip install {' '.join(OPCIONALES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Instala el hook de pre-commit de ¡Quac!.

El hook corre lint + formato + tests antes de cada commit y aborta si algo
falla. Sin caracteres unicode en la salida (compatibilidad con consola cp1252).

Uso:  C:/quac_pro_env/Scripts/python.exe scripts/install_hooks.py
"""

import stat
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
HOOK = RAIZ / ".git" / "hooks" / "pre-commit"

CONTENIDO = r"""#!/bin/sh
# Hook de pre-commit de Quac: lint + formato + tests. Aborta si algo falla.
PY="C:/quac_pro_env/Scripts/python.exe"
RUFF="C:/quac_pro_env/Scripts/ruff.exe"

echo "[pre-commit] ruff check..."
"$RUFF" check . || { echo "[pre-commit] FALLO: lint"; exit 1; }

echo "[pre-commit] ruff format --check..."
"$RUFF" format --check . || { echo "[pre-commit] FALLO: formato (corre: ruff format .)"; exit 1; }

echo "[pre-commit] pytest..."
"$PY" -m pytest tests/ -q || { echo "[pre-commit] FALLO: tests"; exit 1; }

echo "[pre-commit] OK"
exit 0
"""


def main():
    if not (RAIZ / ".git").is_dir():
        print("[FALLO] No hay repositorio git en", RAIZ)
        return 1
    HOOK.parent.mkdir(parents=True, exist_ok=True)
    HOOK.write_text(CONTENIDO, encoding="utf-8", newline="\n")
    HOOK.chmod(HOOK.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    print("[OK] Hook de pre-commit instalado en", HOOK)
    return 0


if __name__ == "__main__":
    sys.exit(main())

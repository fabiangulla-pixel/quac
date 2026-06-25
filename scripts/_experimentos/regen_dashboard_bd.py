"""Regenera el dashboard desde la BD existente (sin re-buscar ni re-scrapear).

Corre el pipeline de análisis con limpieza estricta sobre `datos/quac.db` y
regenera `datos/quac.dashboard.html` + red + Excel, reutilizando
`automatico.analizar_y_dashboard`. Útil para ver cambios de dashboard.py /
studyInfo.js sin esperar un scraping completo.

Uso:  C:/quac_pro_env/Scripts/python.exe -u scripts/_experimentos/regen_dashboard_bd.py
"""

import sys
import time
from pathlib import Path

# El script vive en scripts/_experimentos/; la raíz del proyecto está dos niveles
# arriba. Se añade al path para importar los módulos de la app.
RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

import automatico  # noqa: E402
import config  # noqa: E402
from db import BaseDatos  # noqa: E402

t0 = time.time()


def log(m):
    print(f"[{time.time() - t0:5.1f}s] {m}", flush=True)


def main():
    log("arrancando: cargando perfil y BD")
    perfil = config.cargar()
    db = BaseDatos(str(RAIZ / "datos" / "quac.db"))
    log(f"Corpus: {db.contar()} notas. Perfil: {len(perfil.get('entidades', []))} entidades.")
    automatico.analizar_y_dashboard(db, perfil, log)
    log("LISTO")


if __name__ == "__main__":
    main()

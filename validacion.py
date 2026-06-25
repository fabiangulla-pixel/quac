"""Validación metodológica de la clasificación automática (para publicar).

El análisis de contenido automatizado debe validarse contra codificación humana
para ser defendible en un paper. Este módulo implementa el flujo estándar:

  1. exportar_muestra(): toma una muestra ALEATORIA (semilla fija → reproducible)
     de notas y genera un CSV con la clasificación automática + columnas vacías
     para que el investigador (y un segundo codificador) anoten a mano.
  2. calcular_concordancia(): tras codificar, compara manual vs. automático y
     reporta % de acuerdo y **Kappa de Cohen** (acuerdo corregido por azar),
     la métrica que piden las revistas para fiabilidad inter-codificador.

100% local, sin dependencias nuevas (csv + math).
"""

from __future__ import annotations

import csv
import random
from pathlib import Path


def exportar_muestra(
    notas: list[dict],
    ruta_csv: str | Path,
    *,
    n: int = 30,
    semilla: int = 42,
    analisis_por_url: dict | None = None,
) -> Path:
    """Exporta una muestra aleatoria para codificación manual.

    ``notas``: filas de la BD (con url, medio, titular, cuerpo).
    ``analisis_por_url``: {url: {"emociones": {...}}} del pipeline, para incluir
    la polaridad AUTOMÁTICA en el CSV (columna a comparar).
    El CSV trae columnas vacías ``polaridad_manual`` y ``codificador`` para llenar.
    """
    ruta = Path(ruta_csv)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    analisis_por_url = analisis_por_url or {}

    rng = random.Random(semilla)  # reproducible
    muestra = notas[:] if len(notas) <= n else rng.sample(notas, n)

    # Para no depender de análisis guardados (que pueden ser de versiones viejas),
    # se calcula la polaridad automática al vuelo desde el cuerpo.
    try:
        import sentimiento_politico as _sp
    except Exception:
        _sp = None

    campos = [
        "url",
        "medio",
        "titular",
        "fragmento",
        "polaridad_auto",
        "polaridad_manual",
        "codificador",
        "notas_codificacion",
    ]
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        for nt in muestra:
            url = nt.get("url", "")
            auto = ((analisis_por_url.get(url) or {}).get("emociones") or {}).get("polaridad", "")
            if not auto and _sp:
                auto = _sp.analizar_polaridad(nt.get("cuerpo") or "")["polaridad"]
            cuerpo = (nt.get("cuerpo") or "").replace("\n", " ")
            w.writerow(
                {
                    "url": url,
                    "medio": nt.get("medio", ""),
                    "titular": (nt.get("titular") or "")[:120],
                    "fragmento": cuerpo[:300],
                    "polaridad_auto": auto,
                    "polaridad_manual": "",  # ← llenar: positivo/negativo/neutro
                    "codificador": "",
                    "notas_codificacion": "",
                }
            )
    return ruta


def _kappa_cohen(pares: list[tuple[str, str]]) -> float:
    """Kappa de Cohen entre dos series de etiquetas (manual vs. auto)."""
    if not pares:
        return 0.0
    etiquetas = sorted({x for p in pares for x in p})
    n = len(pares)
    # acuerdo observado
    po = sum(1 for a, b in pares if a == b) / n
    # acuerdo esperado por azar
    pe = 0.0
    for e in etiquetas:
        pa = sum(1 for a, _ in pares if a == e) / n
        pb = sum(1 for _, b in pares if b == e) / n
        pe += pa * pb
    if pe >= 1.0:
        return 1.0
    return round((po - pe) / (1 - pe), 3)


def _interpreta_kappa(k: float) -> str:
    if k < 0:
        return "pobre (peor que el azar)"
    if k < 0.20:
        return "leve"
    if k < 0.40:
        return "aceptable"
    if k < 0.60:
        return "moderado"
    if k < 0.80:
        return "sustancial"
    return "casi perfecto"


def calcular_concordancia(
    ruta_csv: str | Path, col_manual: str = "polaridad_manual", col_auto: str = "polaridad_auto"
) -> dict:
    """Lee el CSV ya codificado y calcula acuerdo % + Kappa de Cohen.

    Solo considera filas con codificación manual no vacía.
    """
    ruta = Path(ruta_csv)
    pares = []
    with open(ruta, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            man = (row.get(col_manual) or "").strip().lower()
            aut = (row.get(col_auto) or "").strip().lower()
            if man and aut:
                pares.append((man, aut))
    if not pares:
        return {"error": "No hay filas con 'polaridad_manual' codificada.", "n": 0}
    acuerdo = sum(1 for a, b in pares if a == b) / len(pares)
    k = _kappa_cohen(pares)
    # matriz de confusión simple
    matriz: dict = {}
    for man, aut in pares:
        matriz.setdefault(man, {}).setdefault(aut, 0)
        matriz[man][aut] += 1
    return {
        "n": len(pares),
        "acuerdo": round(acuerdo, 3),
        "kappa": k,
        "interpretacion": _interpreta_kappa(k),
        "matriz_confusion": matriz,
    }

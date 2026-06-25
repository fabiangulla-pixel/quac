"""Análisis SOCIAL con transformer (pysentimiento) por BLOQUES, persistente y
reanudable. Pensado para equipos con poca RAM (8 GB): procesa el corpus en
bloques de N notas, guarda cada resultado en la BD (columna social_transformer),
libera memoria entre bloques, y al final compila/pondera todos los resultados.

Si el proceso se corta, al re-lanzarlo RETOMA donde quedó (solo analiza las notas
que aún no tienen análisis transformer).

Uso programático:
    from transformer_lotes import analizar_por_bloques, compilar
    analizar_por_bloques("datos/quac.db", tam_bloque=250, callback=print)
    resumen = compilar("datos/quac.db")

CLI:
    python transformer_lotes.py datos/quac.db --bloque 250
    python transformer_lotes.py datos/quac.db --compilar
"""

from __future__ import annotations

import gc
import time
from collections import Counter
from collections.abc import Callable

from db import BaseDatos
from scrapers.limpieza import limpiar_cuerpo


def transformer_disponible() -> bool:
    import sentimiento_politico as sp

    return sp.transformer_disponible()


def _es_relevante(nota: dict, oblig: list, excl: list) -> bool:
    """True si la nota menciona ≥1 término obligatorio y ninguno excluido."""
    import unicodedata

    txt = unicodedata.normalize(
        "NFKD", ((nota.get("titular") or "") + " " + (nota.get("cuerpo") or "")).lower()
    )
    txt = "".join(c for c in txt if not unicodedata.combining(c))

    def norm(s):
        s = unicodedata.normalize("NFKD", str(s).lower())
        return "".join(c for c in s if not unicodedata.combining(c))

    if oblig and not any(norm(t) in txt for t in oblig):
        return False
    if excl and any(norm(t) in txt for t in excl):
        return False
    return True


def analizar_por_bloques(
    ruta_db: str,
    tam_bloque: int = 250,
    max_chars: int = 2000,
    entidades_obligatorias: list | None = None,
    excluir_terminos: list | None = None,
    callback: Callable[[str], None] | None = None,
) -> dict:
    """Analiza con transformer todas las notas pendientes, en bloques.

    - tam_bloque: nº de notas por bloque (250 cabe holgado en 8 GB).
    - max_chars: recorte del cuerpo (robertuito procesa ~512 tokens; recortar
      acelera y evita problemas de memoria sin perder el tono general).
    - entidades_obligatorias / excluir_terminos: si se pasan, analiza SOLO las
      notas relevantes (mismo criterio que el pipeline), saltando el ruido.
    - Tras cada bloque: commit a la BD + gc.collect() para liberar RAM.
    - Reanudable: solo procesa notas con social_transformer NULL.
    """

    def log(m):
        if callback:
            callback(m)

    import sentimiento_politico as sp

    if not sp.transformer_disponible():
        return {"ok": False, "error": "transformer no disponible en este entorno"}

    db = BaseDatos(ruta_db)
    prog = db.progreso_transformer()
    log(
        f"Progreso previo: {prog['hechas']}/{prog['total']} ya analizadas. Faltan {prog['faltan']}."
    )
    pendientes = db.notas_sin_transformer()
    if entidades_obligatorias or excluir_terminos:
        antes = len(pendientes)
        pendientes = [
            n
            for n in pendientes
            if _es_relevante(n, entidades_obligatorias or [], excluir_terminos or [])
        ]
        log(
            f"Filtro de relevancia: {len(pendientes)}/{antes} notas pendientes "
            f"son relevantes (se analizan solo esas)."
        )
    if not pendientes:
        db.close()
        return {
            "ok": True,
            "analizadas": 0,
            "mensaje": "Todo el corpus ya tiene análisis transformer.",
            **prog,
        }

    t0 = time.time()
    n_ok = 0
    total = len(pendientes)
    for ini in range(0, total, tam_bloque):
        bloque = pendientes[ini : ini + tam_bloque]
        for nota in bloque:
            texto = limpiar_cuerpo(nota.get("cuerpo") or "")[:max_chars]
            if not texto.strip():
                # marcar como hecha (vacía) para no reintentarla siempre
                db.guardar_social_transformer(nota["url"], {"fuente": "vacia"})
                continue
            social = sp.analisis_social_completo(texto)
            if social is None:
                social = {"fuente": "sin_transformer"}
            db.guardar_social_transformer(nota["url"], social)
            n_ok += 1
        # liberar memoria entre bloques (clave en 8 GB)
        gc.collect()
        hechas = ini + len(bloque)
        veloc = hechas / max(1, time.time() - t0)
        eta = (total - hechas) / max(0.1, veloc)
        log(
            f"Bloque {ini // tam_bloque + 1}: {hechas}/{total} notas "
            f"({veloc:.1f} notas/s · ETA {eta / 60:.0f} min)"
        )

    db.close()
    return {
        "ok": True,
        "analizadas": n_ok,
        "total_pendiente": total,
        "segundos": round(time.time() - t0),
    }


def compilar(ruta_db: str) -> dict:
    """Compila y PONDERA los resultados transformer de TODOS los bloques.

    Devuelve un resumen agregado del corpus: distribución de polaridad, emoción
    dominante, % de odio/ironía/agresividad, listo para el paper.
    """
    db = BaseDatos(ruta_db)
    social = db.social_transformer_todas()
    db.close()

    pol = Counter()
    emo = Counter()
    n_odio = n_iro = n_agr = 0
    n = 0
    for url, s in social.items():
        if not isinstance(s, dict) or s.get("fuente") in ("vacia", "sin_transformer"):
            continue
        n += 1
        pol[s.get("polaridad", "neutro")] += 1
        if s.get("emocion"):
            emo[s["emocion"]] += 1
        if s.get("odio"):
            n_odio += 1
        if s.get("ironia"):
            n_iro += 1
        if s.get("agresivo"):
            n_agr += 1

    def pct(x):
        return round(100 * x / n, 1) if n else 0.0

    return {
        "n_analizadas": n,
        "polaridad": dict(pol),
        "polaridad_pct": {k: pct(v) for k, v in pol.items()},
        "emocion_dominante": dict(emo.most_common()),
        "odio": {"n": n_odio, "pct": pct(n_odio)},
        "ironia": {"n": n_iro, "pct": pct(n_iro)},
        "agresividad": {"n": n_agr, "pct": pct(n_agr)},
    }


if __name__ == "__main__":
    import argparse
    import io
    import json
    import sys

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="Análisis transformer por bloques")
    ap.add_argument("db", help="ruta a la base de datos .db")
    ap.add_argument("--bloque", type=int, default=250, help="notas por bloque")
    ap.add_argument(
        "--compilar", action="store_true", help="solo compilar/ponderar resultados ya guardados"
    )
    args = ap.parse_args()

    if args.compilar:
        print(json.dumps(compilar(args.db), ensure_ascii=False, indent=2))
    else:
        res = analizar_por_bloques(args.db, tam_bloque=args.bloque, callback=print)
        print("\n--- RESULTADO ---")
        print(json.dumps(res, ensure_ascii=False, indent=2))
        print("\n--- COMPILACIÓN ---")
        print(json.dumps(compilar(args.db), ensure_ascii=False, indent=2))

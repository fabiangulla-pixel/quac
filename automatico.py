"""Proceso AUTÓNOMO de ¡Quac! para correr sin supervisión (ej. tarea de las 6am
del día de elecciones). Hace todo el pipeline de punta a punta:

  1. BUSCA notas nuevas (términos del perfil + ventana de fechas reciente).
  2. SCRAPEA solo las URLs nuevas (la BD dedupe por URL → reanudable).
  3. ANALIZA todo el corpus con la limpieza estricta (perfil, sin ruido).
  4. GENERA el dashboard + red + Excel.
  5. Deja un LOG con todo lo ocurrido y un resumen al final.

Diseñado para no requerir intervención: si la búsqueda falla (sin internet,
GNews caído), continúa con el análisis de lo que ya hay en la BD. Nunca borra
nada. Pensado para 8 GB de RAM (modo léxico; el transformer va aparte por
bloques con transformer_lotes.py).

Uso:
    python automatico.py                      # usa datos/quac.db
    python automatico.py --db otra.db --dias 2 --sin-buscar
"""

from __future__ import annotations

import argparse
import io
import sys
import time
import traceback
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
LOG_DIR = RAIZ / "datos" / "logs_auto"


def _log(msg, archivo=None):
    linea = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(linea, flush=True)
    if archivo:
        archivo.write(linea + "\n")
        archivo.flush()


def buscar_nuevas(perfil, desde, hasta, log):
    """Busca notas de los candidatos en la ventana de fechas. Devuelve lista de
    resultados (vacía si falla la búsqueda, sin tumbar el proceso)."""
    try:
        from busqueda import buscar_masivo
        from busqueda.criterios import CriteriosBusqueda, EntidadInteres

        # Términos: nombres de los candidatos del perfil (los más relevantes).
        terminos = []
        for e in perfil.get("entidades", []):
            if e.get("tipo") in ("candidato", "formula_vp"):
                terminos.append(e["nombre"])
        if not terminos:
            terminos = ["Iván Cepeda", "Abelardo de la Espriella"]
        ents = [
            EntidadInteres(e["nombre"], e.get("tipo", "persona"), e.get("variantes", []))
            for e in perfil.get("entidades", [])
        ]
        criterios = CriteriosBusqueda(
            terminos=terminos,
            desde=desde,
            hasta=hasta,
            entidades=ents,
            max_resultados=0,
            filtrar_por_entidades=False,
        )
        log(f"Buscando notas {desde}→{hasta} para: {', '.join(terminos)}")
        res = buscar_masivo(criterios, callback=lambda m: None, dias_tramo=3)
        log(f"Búsqueda: {len(res)} resultados encontrados.")
        return res
    except Exception as e:
        log(f"⚠ Búsqueda falló ({e}); se continúa con el corpus existente.")
        return []


def scrapear_nuevas(db, resultados, log, max_scrapeos=150, tope_duplicados=40):
    """Scrapea las URLs que no están en la BD. Devuelve nº de notas nuevas.

    max_scrapeos: tope de URLs a intentar (evita tardar horas con Google News).
    tope_duplicados: si vienen tantos duplicados seguidos, para (corpus al día).
    """
    if not resultados:
        return 0
    try:
        from cli import _scrapear_urls

        ya = {r[0] for r in db.con.execute("SELECT url FROM notas").fetchall()}
        fechas = {r.url: (r.fecha or "") for r in resultados if r.url}
        pendientes = [r.url for r in resultados if r.url and r.url not in ya]
        # IMPORTANTE: las URLs de Google News son OPACAS (cambian cada vez aunque
        # apunten a la misma nota), así que muchas "pendientes" son en realidad
        # duplicados que solo se detectan al resolverlas con Chrome (lento). Para
        # no tardar horas re-scrapeando duplicados, limitamos el nº de intentos y
        # PARAMOS pronto si vienen muchos duplicados seguidos (señal de que el
        # grueso ya está en la BD). Las notas nuevas reales suelen estar al inicio.
        max_intentos = min(len(pendientes), max_scrapeos)
        log(
            f"Scraping: hasta {max_intentos} URLs (de {len(pendientes)} candidatas; "
            f"se corta tras {tope_duplicados} duplicados seguidos)."
        )
        ins = dup_seguidos = 0
        for i, url in enumerate(pendientes[:max_intentos], 1):
            r = _scrapear_urls(db, [url], fechas=fechas, ignorar_robots=False, sin_navegador=False)
            if r["insertadas"]:
                ins += r["insertadas"]
                dup_seguidos = 0
            else:
                dup_seguidos += 1
            if dup_seguidos >= tope_duplicados:
                log(
                    f"  ⏹ {tope_duplicados} duplicados seguidos → el corpus ya "
                    f"está al día. Paro el scraping ({ins} nuevas)."
                )
                break
            if i % 25 == 0:
                log(f"  ▸ {i}/{max_intentos} · {ins} nuevas guardadas")
        log(f"Scraping terminado: {ins} notas nuevas en la BD.")
        return ins
    except Exception as e:
        log(f"⚠ Scraping falló ({e}); se analiza lo que ya hay.")
        return 0


def analizar_y_dashboard(db, perfil, log):
    """Corre el pipeline limpio sobre toda la BD y genera dashboard + red + Excel."""
    import config
    import dashboard
    import revision
    from busqueda.criterios import EntidadInteres
    from core import network_engine
    from pipeline import analizar_corpus

    notas = db.todas_las_notas()
    log(f"Analizando {len(notas)} notas (limpieza estricta)…")
    ents = [
        EntidadInteres(e["nombre"], e.get("tipo", "persona"), e.get("variantes", []))
        for e in perfil.get("entidades", [])
    ]
    sem = dict(config.semillas_normalizacion(perfil))
    sem.update({e.nombre: e.todas_las_formas for e in ents})
    dec = revision.cargar_decisiones(db)
    OBLIG = ["Cepeda", "Espriella", "De la Espriella", "Quilcué", "Restrepo"]
    EXCL = ["Fujimori", "Keiko", "Boluarte", "Perú", "Dina", "Pedro Castillo"]

    res = analizar_corpus(
        notas,
        semillas_entidades=sem,
        usar_coref=True,
        decisiones_revision=dec,
        usar_transformer=False,
        n_topicos=int(perfil.get("n_topicos", 8) or 8),
        entidades_obligatorias=OBLIG,
        excluir_terminos=EXCL,
        solo_actores_relevantes=True,
        callback=lambda m: None,
    )

    # Compilar transformer si la BD ya tiene análisis por bloques.
    try:
        import transformer_lotes

        st = transformer_lotes.compilar(str(db.ruta))
        if st.get("n_analizadas"):
            res["social_transformer"] = st
            log(f"Transformer: {st['n_analizadas']} notas (odio {st['odio']['pct']}%).")
    except Exception:
        pass

    for url, rr in res["por_nota"].items():
        db.guardar_analisis(
            url, sentimiento=rr["emociones"], ner=rr["ner"], confianza=rr["confianza"]
        )
    revision.guardar_cola(db, revision.construir_cola(res["indice_global"], semillas=sem))

    nf = [n for n in notas if n["url"] in res["por_nota"]]
    G = network_engine.dict_a_grafo(res["grafo"])
    network_engine.exportar_pyvis(
        G, Path(db.ruta).with_suffix(".red.html"), titulo="¡Quac! — Red de actores"
    )
    dash = Path(db.ruta).with_suffix(".dashboard.html")
    dashboard.generar_dashboard(res, nf, dash, titulo="¡Quac! — Cepeda vs De la Espriella")
    try:
        import exportar_excel

        exportar_excel.exportar(res, nf, Path(db.ruta).with_suffix(".xlsx"))
    except Exception:
        pass

    ig = res["indice_global"]
    top = sorted(ig.get("personas", {}).items(), key=lambda x: -len(x[1]))[:5]
    log(f"Análisis OK: {len(res['por_nota'])} notas relevantes.")
    log(f"  Top actores: {[(k, len(v)) for k, v in top]}")
    log(f"Dashboard: {dash}")
    return dash


def main():
    # UTF-8 en la salida solo al ejecutar como script (no al importar el módulo).
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="¡Quac! autónomo")
    ap.add_argument("--db", default="datos/quac.db")
    ap.add_argument("--dias", type=int, default=2, help="ventana de búsqueda hacia atrás (días)")
    ap.add_argument(
        "--sin-buscar", action="store_true", help="saltar búsqueda/scraping, solo analizar la BD"
    )
    args = ap.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"auto_{time.strftime('%Y%m%d_%H%M%S')}.log"
    f = open(log_path, "w", encoding="utf-8")
    log = lambda m: _log(m, f)
    t0 = time.time()

    log("=" * 60)
    log("¡Quac! AUTÓNOMO — inicio")
    log(f"BD: {args.db}")
    try:
        import config
        from db import BaseDatos

        perfil = config.cargar()
        db = BaseDatos(args.db)
        log(
            f"Corpus inicial: {db.contar()} notas. Perfil: "
            f"{len(perfil.get('entidades', []))} entidades."
        )

        nuevas = 0
        if not args.sin_buscar:
            hoy = date.today()
            desde = (hoy - timedelta(days=args.dias)).isoformat()
            hasta = hoy.isoformat()
            resultados = buscar_nuevas(perfil, desde, hasta, log)
            nuevas = scrapear_nuevas(db, resultados, log)
        else:
            log("Modo --sin-buscar: se omite búsqueda/scraping.")

        dash = analizar_y_dashboard(db, perfil, log)
        db.close()

        log("=" * 60)
        log(f"COMPLETADO en {(time.time() - t0) / 60:.1f} min. Notas nuevas hoy: {nuevas}.")
        log(f"Abre el dashboard:  {dash}")
        log(f"Log guardado en: {log_path}")
    except Exception:
        log("✖ ERROR FATAL:")
        log(traceback.format_exc())
    finally:
        f.close()


if __name__ == "__main__":
    main()

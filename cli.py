#!/usr/bin/env python
"""¡Quac! — CLI de análisis de prensa electoral colombiana contemporánea.

Subcomandos:
  medios                      Lista los medios con adaptador dedicado.
  scrape URL [URL ...]        Scrapea notas y las guarda en la BD del proyecto.
  scrape --archivo urls.txt   Scrapea las URLs de un archivo (una por línea).
  listar                      Muestra cuántas notas hay por medio.
  analizar                    Corre sentimiento + NER + red sobre las notas.

Uso:
  python cli.py --db datos/elecciones.db scrape https://...
  python cli.py --db datos/elecciones.db analizar --salida datos/red.html
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Permite ejecutar desde la raíz del proyecto.
sys.path.insert(0, str(Path(__file__).parent))

# La consola de Windows usa cp1252 por defecto y no codifica símbolos Unicode
# (→, ✓, 📸…). Forzar UTF-8 en stdout/stderr evita UnicodeEncodeError.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from core import costos, sentiment_engine
from db import BaseDatos
from scrapers.registro import listar_medios, scraper_para_url


def _log(msg):
    print(msg, flush=True)


def cmd_medios(args):
    print("Medios con adaptador dedicado (los demás usan extracción genérica):\n")
    for m in listar_medios():
        print(f"  • {m['medio']:<20} {', '.join(m['dominios'])}")


def _scrapear_urls(db, urls, *, ignorar_robots=False, sin_navegador=False, fechas=None):
    """Scrapea una lista de URLs a la BD. Devuelve {insertadas, duplicadas, fallidas}.

    ``fechas``: {url: fecha_iso} opcional (p. ej. de la búsqueda). Se usa como
    respaldo cuando la extracción de la nota no obtuvo fecha de publicación.
    """
    fechas = fechas or {}
    screenshots_dir = str(Path(db.ruta).parent / "screenshots")
    ins = dup = err = 0
    for url in urls:
        scraper = scraper_para_url(
            url,
            respetar_robots=not ignorar_robots,
            usar_navegador=not sin_navegador,
            screenshots_dir=screenshots_dir,
        )
        _log(f"→ {url}")
        nota = scraper.extraer_nota(url)
        if not nota or not nota.cuerpo:
            _log("   ✗ no se pudo extraer (robots.txt, red, o sin contenido)")
            err += 1
            continue
        # Respaldo de fecha: la búsqueda (Google News) suele traerla aunque la
        # extracción de la página no la haya capturado.
        if not nota.fecha_publicacion:
            nota.fecha_publicacion = fechas.get(url) or fechas.get(nota.url) or ""
        if db.guardar_nota(nota):
            extra = f" · 📸 {Path(nota.screenshot_path).name}" if nota.screenshot_path else ""
            _log(
                f"   ✓ {nota.medio} · {nota.n_palabras} palabras · {nota.metodo_extraccion}{extra}"
            )
            ins += 1
        else:
            _log("   ↺ duplicada (URL o contenido ya en BD)")
            dup += 1
    return {"insertadas": ins, "duplicadas": dup, "fallidas": err}


def cmd_scrape(args):
    urls = list(args.urls)
    if args.archivo:
        urls += [
            l.strip()
            for l in Path(args.archivo).read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")
        ]
    if not urls:
        print("No hay URLs. Pasa URLs o --archivo.", file=sys.stderr)
        return 1

    db = BaseDatos(args.db)
    r = _scrapear_urls(
        db, urls, ignorar_robots=args.ignorar_robots, sin_navegador=args.sin_navegador
    )
    db.close()
    print(
        f"\nResumen: {r['insertadas']} insertadas, {r['duplicadas']} "
        f"duplicadas, {r['fallidas']} fallidas."
    )
    return 0


def cmd_corpus(args):
    """Scrapea un corpus masivo (JSON de buscar --masivo) a la BD del proyecto.

    El JSON es una lista de {url, fecha, medio, titular}. Reanudable: la BD
    dedupe por URL, así que volver a correrlo salta lo ya guardado. Muestra
    progreso cada ``--cada`` notas y un resumen al final.
    """
    items = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    if args.limite:
        items = items[: args.limite]
    total = len(items)
    print(f"Corpus: {total} URLs desde {args.corpus}")

    db = BaseDatos(args.db)

    # Sembrar la canonicalización con el perfil (Cepeda/De la Espriella, etc.).
    # El corpus no pasa por 'buscar', así que sin esto el análisis no uniría las
    # variantes ni cargaría los marcos del perfil. Igual que hace la GUI.
    import config

    db.con.execute(
        "CREATE TABLE IF NOT EXISTS entidades_interes "
        "(nombre TEXT PRIMARY KEY, tipo TEXT, formas TEXT)"
    )
    sembradas = 0
    for e in config.cargar().get("entidades", []):
        formas = [e["nombre"]] + e.get("variantes", [])
        db.con.execute(
            "INSERT OR REPLACE INTO entidades_interes VALUES (?,?,?)",
            (e["nombre"], e.get("tipo", "persona"), json.dumps(formas, ensure_ascii=False)),
        )
        sembradas += 1
    db.con.commit()
    if sembradas:
        print(f"  perfil sembrado: {sembradas} entidades para canonicalización")

    fechas = {it["url"]: it.get("fecha", "") for it in items if it.get("url")}
    urls = [it["url"] for it in items if it.get("url")]

    # Saltar las URLs ya presentes en la BD (reanudable sin reabrir Chrome).
    try:
        ya = {r[0] for r in db.con.execute("SELECT url FROM notas").fetchall()}
    except Exception:
        ya = set()
    pendientes = [u for u in urls if u not in ya]
    if ya:
        print(f"  {len(ya)} ya en BD · {len(pendientes)} pendientes")

    ins = dup = err = 0
    hechas = 0
    for url in pendientes:
        r = _scrapear_urls(
            db,
            [url],
            fechas=fechas,
            ignorar_robots=args.ignorar_robots,
            sin_navegador=args.sin_navegador,
        )
        ins += r["insertadas"]
        dup += r["duplicadas"]
        err += r["fallidas"]
        hechas += 1
        if hechas % args.cada == 0:
            print(
                f"  ▸ progreso {hechas}/{len(pendientes)} · {ins} ok · {dup} dup · {err} fallidas",
                flush=True,
            )
    db.close()
    print(
        f"\nResumen corpus: {ins} insertadas, {dup} duplicadas, "
        f"{err} fallidas (de {len(pendientes)} pendientes)."
    )
    print(f"Total en BD ahora: {BaseDatos(args.db).contar()}")
    print(
        f"\nAhora corre:  python cli.py --db {args.db} analizar "
        f"--transformer --excel datos/estudio_grande.xlsx "
        f"--salida datos/estudio_grande.red.html"
    )
    return 0


def cmd_buscar(args):
    """Descubre notas por términos + rango de fechas, las scrapea y guarda."""
    from busqueda import buscar
    from busqueda.criterios import CriteriosBusqueda, EntidadInteres

    if args.criterios:
        criterios = CriteriosBusqueda.cargar(args.criterios)
    else:
        entidades = []
        for spec in args.entidad or []:
            # formato: "Nombre|tipo|variante1,variante2"
            partes = spec.split("|")
            nombre = partes[0].strip()
            tipo = partes[1].strip() if len(partes) > 1 and partes[1].strip() else "persona"
            variantes = [v.strip() for v in partes[2].split(",")] if len(partes) > 2 else []
            entidades.append(EntidadInteres(nombre, tipo, variantes))
        criterios = CriteriosBusqueda(
            terminos=args.termino or [],
            desde=args.desde,
            hasta=args.hasta,
            medios=args.medio or [],
            entidades=entidades,
            max_resultados=args.max,
            filtrar_por_entidades=args.filtrar,
        )

    print(
        f"Buscando: «{criterios.query_principal()}»"
        + (
            f" · {criterios.desde}→{criterios.hasta}"
            if (criterios.desde or criterios.hasta)
            else ""
        )
    )
    if getattr(args, "masivo", False):
        from busqueda import buscar_masivo

        resultados = buscar_masivo(
            criterios, callback=_log, dias_tramo=getattr(args, "dias_tramo", 7)
        )
    else:
        resultados = buscar(criterios, callback=_log)
    if not resultados:
        print("Sin resultados. Prueba otros términos o amplía el rango de fechas.")
        return 0

    print(f"\n{len(resultados)} notas encontradas:")
    for r in resultados:
        print(f"  • [{r.fecha or '?'}] {r.medio or r.dominio()} — {r.titular[:70]}")

    if args.solo_listar:
        return 0

    db = BaseDatos(args.db)
    # Sembrar canonicalización con las variantes declaradas por el usuario
    _guardar_variantes_entidades(db, criterios)
    fechas = {r.url: r.fecha for r in resultados if r.fecha}
    res = _scrapear_urls(
        db,
        [r.url for r in resultados],
        fechas=fechas,
        ignorar_robots=args.ignorar_robots,
        sin_navegador=args.sin_navegador,
    )
    db.close()
    print(
        f"\nResumen: {res['insertadas']} insertadas, {res['duplicadas']} "
        f"duplicadas, {res['fallidas']} fallidas."
    )
    print(f"Ahora corre:  python cli.py --db {args.db} analizar --peso-minimo 1")
    return 0


def _guardar_variantes_entidades(db, criterios):
    """Persiste las variantes declaradas para sembrar la canonicalización."""
    import json

    mapa = {e.nombre: e.todas_las_formas for e in criterios.entidades}
    if not mapa:
        return
    db.con.execute(
        "CREATE TABLE IF NOT EXISTS entidades_interes "
        "(nombre TEXT PRIMARY KEY, tipo TEXT, formas TEXT)"
    )
    for e in criterios.entidades:
        db.con.execute(
            "INSERT OR REPLACE INTO entidades_interes VALUES (?,?,?)",
            (e.nombre, e.tipo, json.dumps(e.todas_las_formas, ensure_ascii=False)),
        )
    db.con.commit()


def cmd_listar(args):
    db = BaseDatos(args.db)
    total = db.contar()
    print(f"Notas en {args.db}: {total}\n")
    for medio, n in db.notas_por_medio().items():
        print(f"  {n:>4}  {medio}")
    db.close()


def _leer_semillas_entidades(db) -> dict:
    """Lee {canónico: [formas]} de la tabla entidades_interes, si existe."""
    import json

    try:
        cur = db.con.execute("SELECT nombre, formas FROM entidades_interes")
    except Exception:
        return {}
    return {r["nombre"]: json.loads(r["formas"]) for r in cur.fetchall()}


def _combinar_semillas(db_sem: dict, perfil_sem: dict) -> dict:
    """Combina las semillas de la BD con las del perfil — el PERFIL manda.

    La tabla entidades_interes de la BD puede traer entradas incompletas o
    duplicadas (p. ej. "Petro" registrado como canónico propio, o "Iván Cepeda
    Castro" sin variantes). Si pisaran al perfil, partirían un mismo actor en
    varios nodos del grafo. Por eso: (1) se descartan los canónicos de la BD que
    en realidad son una variante reclamada por el perfil, y (2) se sobreescribe
    con el perfil uniendo variantes, para no perder ninguna forma.
    """
    from scrapers.limpieza import _norm_rel

    semillas = dict(db_sem)
    reclamadas = {_norm_rel(v) for formas in perfil_sem.values() for v in formas}
    for canon in list(semillas):
        if _norm_rel(canon) in reclamadas and canon not in perfil_sem:
            del semillas[canon]
    for canon, formas in perfil_sem.items():
        semillas[canon] = sorted(set(semillas.get(canon, [])) | set(formas))
    return semillas


def cmd_analizar(args):
    from core import network_engine
    from pipeline import analizar_corpus

    db = BaseDatos(args.db)
    notas = db.todas_las_notas()
    if not notas:
        print("No hay notas que analizar. Usa 'scrape' primero.", file=sys.stderr)
        return 1

    import config
    import revision

    perfil_sem = config.semillas_normalizacion(config.cargar())
    semillas = _combinar_semillas(_leer_semillas_entidades(db), perfil_sem)
    decisiones = revision.cargar_decisiones(db)

    oblig = [t.strip() for t in (args.oblig or "").split(",") if t.strip()]
    excl = [t.strip() for t in (args.excluir or "").split(",") if t.strip()]
    if args.estricto:
        _log(
            "Modo ESTRICTO: red/índice solo con actores del perfil"
            + (f" · obligatorias: {oblig}" if oblig else "")
            + (f" · excluir: {excl}" if excl else "")
        )

    res = analizar_corpus(
        notas,
        api_key=args.api_key,
        usar_roberta=args.roberta,
        peso_minimo_red=args.peso_minimo,
        semillas_entidades=semillas,
        usar_coref=not args.sin_coref,
        decisiones_revision=decisiones,
        entidades_obligatorias=oblig,
        excluir_terminos=excl,
        solo_actores_relevantes=args.estricto,
        usar_transformer=args.transformer,
        usar_bertopic=args.bertopic,
        callback=_log,
    )

    # Construir/actualizar la cola de revisión de entidades dudosas
    cola = revision.construir_cola(res["indice_global"], semillas=semillas)
    revision.guardar_cola(db, cola)

    # Persistir análisis por nota (la BD se cierra al final, tras la cola)
    for url, r in res["por_nota"].items():
        db.guardar_analisis(url, sentimiento=r["emociones"], ner=r["ner"], confianza=r["confianza"])

    # Resumen en consola
    print("\n=== AGREGADOS POR MEDIO ===")
    for medio, d in res["agregados"].items():
        emo = max(d["emociones"], key=d["emociones"].get) if d["emociones"] else "—"
        print(f"  {medio:<20} {d['n']:>3} notas · emoción dominante: {emo}")

    print("\n=== ACTORES MÁS MENCIONADOS (por nº de notas) ===")
    personas = res["indice_global"].get("personas", {})
    top_actores = sorted(personas.items(), key=lambda kv: -len(kv[1]))[:8]
    for nombre, arts in top_actores:
        print(f"  {len(arts):>2} notas · {nombre}")

    menc = res.get("menciones_coref", [])
    if menc:
        print("\n=== PRESENCIA REAL (menciones + correferencia) ===")
        for x in menc[:8]:
            print(f"  {x['menciones']:>3} menciones · {x['actor']}")

    print("\n=== RED DE ACTORES ===")
    m = res["metricas_red"]
    if m.get("error") or not m.get("nodos"):
        print(
            "  (red vacía: se necesitan ≥2 notas que compartan actores; "
            "baja --peso-minimo a 1 para corpus pequeños)"
        )
    else:
        print(
            f"  nodos: {m['nodos']} · aristas: {m['aristas']} · densidad: {m.get('densidad', '?')}"
        )
        top_c = m.get("top_centralidad", [])[:5]
        if top_c:
            print("  centralidad: " + ", ".join(f"{n} ({v})" for n, v in top_c))

    col = res.get("colocaciones", {})
    if col.get("collocates"):
        print(f"\n=== PALABRAS ASOCIADAS A «{col.get('clave', '')}» (PMI) ===")
        for c in col["collocates"][:8]:
            print(f"  {c['palabra']:<18} pmi={c['pmi']:.2f}  (f={c['frecuencia']})")

    print("\n=== TÉRMINOS MÁS FRECUENTES ===")
    frec = res.get("frecuencias", [])
    if isinstance(frec, list):
        linea = ", ".join(f"{f['palabra']}({f['freq']})" for f in frec[:12])
        print("  " + linea)

    # Encuadre / framing del corpus
    frames = res.get("frames", {}).get("distribucion", [])
    if frames:
        print("\n=== ENCUADRE (FRAMING) DEL CORPUS ===")
        for f in frames[:6]:
            print(f"  {f['n']:>2} notas · {f['etiqueta']}")

    # Comparación medio × actor (polarización / sesgo de selección)
    comp = res.get("comparacion_medios", {})
    if comp.get("actores") and comp.get("medios"):
        print("\n=== COBERTURA MEDIO × ACTOR (top) ===")
        actores = comp["actores"][:5]
        emo = comp.get("emocion_por_medio", {})
        print("  medio".ljust(24) + " · ".join(a[:14] for a in actores))
        for medio in comp["medios"]:
            fila = comp["matriz"].get(medio, {})
            celdas = "  ".join(str(fila.get(a, 0)).center(min(14, len(a)) or 1) for a in actores)
            etq = f" [{emo[medio]}]" if emo.get(medio) else ""
            print(f"  {medio[:22]:<22} {celdas}{etq}")

    # Series temporales (volumen por mes)
    series = res.get("series_temporales", {})
    if series.get("meses"):
        print("\n=== VOLUMEN POR MES ===")
        vol = series["volumen"]
        maxv = max(vol.values()) if vol else 1
        for mes in series["meses"]:
            barra = "█" * max(1, round(10 * vol[mes] / maxv))
            print(f"  {mes}  {barra} {vol[mes]}")

    # Exportar red interactiva si se pidió
    if args.salida:
        salida = Path(args.salida)
        G = network_engine.dict_a_grafo(res["grafo"])
        network_engine.exportar_pyvis(G, salida, titulo="¡Quac! — Red de actores electorales")
        print(f"\nRed exportada a: {salida}")
        if args.gephi:
            ruta_gephi = salida.with_suffix(".gexf")
            network_engine.exportar_gephi(G, ruta_gephi)
            print(f"Grafo Gephi (.gexf) exportado a: {ruta_gephi}")

    # Dashboard HTML interactivo (lo mismo que genera la GUI)
    if args.dashboard:
        import dashboard

        ruta_dash = Path(args.dashboard)
        dashboard.generar_dashboard(res, notas, ruta_dash, titulo=f"¡Quac! — {ruta_dash.stem}")
        print(f"\nDashboard interactivo: {ruta_dash}")

    # Volcado JSON opcional
    if args.json:
        Path(args.json).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Resultados JSON: {args.json}")

    # Exportar a Excel para el paper
    if args.excel:
        import exportar_excel

        ruta = exportar_excel.exportar(res, notas, args.excel)
        print(f"Excel para el paper: {ruta}")

    # Aviso de cola de revisión human-in-the-loop
    n_pend = len(revision.pendientes(db))
    if n_pend:
        print(
            f"\n⚑ {n_pend} entidades dudosas en cola de revisión. "
            f"Revísalas con:  python cli.py --db {args.db} revisar"
        )
    db.close()
    return 0


def cmd_revisar(args):
    """Revisión human-in-the-loop de entidades dudosas (validar/descartar/renombrar)."""
    import revision

    db = BaseDatos(args.db)
    pend = revision.pendientes(db)

    if args.stats:
        st = revision.estadisticas(db)
        print(
            f"Revisión: {st['total']} entidades · {st['pendientes']} pendientes · "
            f"{st['verificadas']} verificadas · {st['descartadas']} descartadas · "
            f"{st['renombradas']} renombradas"
        )
        db.close()
        return 0

    if not pend:
        print("No hay entidades pendientes. Corre 'analizar' primero.")
        db.close()
        return 0

    print(f"{len(pend)} entidades dudosas a revisar.")
    print("Para cada una: [v]erificar  [d]escartar  [r]enombrar  [s]altar  [q]salir\n")
    for item in pend:
        print(
            f"  «{item['nombre']}» ({item['categoria']}) · "
            f"{item['n_articulos']} notas · {item['nivel']}"
        )
        try:
            op = input("    decisión [v/d/r/s/q]: ").strip().lower()
        except EOFError:
            break
        if op == "q":
            break
        elif op == "v":
            revision.decidir(db, item["nombre"], item["categoria"], revision.VERIFICADA)
        elif op == "d":
            revision.decidir(db, item["nombre"], item["categoria"], revision.DESCARTADA)
        elif op == "r":
            nuevo = input("    nombre correcto: ").strip()
            if nuevo:
                revision.decidir(
                    db, item["nombre"], item["categoria"], revision.RENOMBRADA, nombre_nuevo=nuevo
                )
        # 's' o cualquier otra cosa = saltar (queda pendiente)

    st = revision.estadisticas(db)
    print(
        f"\nListo. Pendientes: {st['pendientes']}. Vuelve a correr 'analizar' "
        "para aplicar las decisiones al corpus."
    )
    db.close()
    return 0


def cmd_validar(args):
    """Validación metodológica: exporta muestra para codificar o calcula concordancia."""
    import validacion

    if args.concordancia:
        res = validacion.calcular_concordancia(args.concordancia)
        if res.get("error"):
            print(res["error"])
            return 1
        print(f"Validación sobre {res['n']} notas codificadas:")
        print(f"  Acuerdo: {res['acuerdo'] * 100:.1f}%")
        print(f"  Kappa de Cohen: {res['kappa']} ({res['interpretacion']})")
        print("  Matriz (manual → auto):")
        for man, fila in res["matriz_confusion"].items():
            print(f"    {man}: " + ", ".join(f"{a}={n}" for a, n in fila.items()))
        return 0
    # exportar muestra
    db = BaseDatos(args.db)
    notas = db.todas_las_notas()
    if not notas:
        print("No hay notas. Analiza un corpus primero.", file=sys.stderr)
        return 1
    # Mismo filtro de relevancia del modo estricto: la muestra Kappa debe salir
    # del MISMO corpus del estudio (sin ruido de Perú/Florentino), o el
    # inter-codificador validaría notas que el paper ni siquiera usa.
    oblig = [t.strip() for t in (getattr(args, "oblig", "") or "").split(",") if t.strip()]
    excl = [t.strip() for t in (getattr(args, "excluir", "") or "").split(",") if t.strip()]
    if oblig or excl:
        from pipeline import filtrar_relevantes

        antes = len(notas)
        notas = filtrar_relevantes(notas, oblig, excl)
        print(f"Filtro de relevancia: {len(notas)}/{antes} notas del corpus del estudio.")
    # incluir polaridad automática: leer del JSON de sentimiento guardado
    import json

    analisis = {}
    for n in notas:
        if n.get("sentimiento"):
            try:
                analisis[n["url"]] = {"emociones": json.loads(n["sentimiento"])}
            except Exception:
                pass
    ruta = validacion.exportar_muestra(
        notas, args.salida or "datos/muestra_validacion.csv", n=args.n, analisis_por_url=analisis
    )
    db.close()
    print(f"Muestra de {min(args.n, len(notas))} notas exportada a: {ruta}")
    print("Codifica a mano la columna 'polaridad_manual' (positivo/negativo/neutro)")
    print(f"y luego:  python cli.py validar --concordancia {ruta}")
    return 0


def cmd_tono(args):
    """Análisis de tono editorial con Claude — con estimación y registro de costo.

    Implementa el estándar de costo IA: estima volumen→tokens→USD, pide
    confirmación ANTES de gastar, ejecuta el lote y reporta el costo REAL leído
    del usage de Claude.
    """
    import os

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "Falta la API key de Anthropic. Pásala con --api-key o en la variable "
            "de entorno ANTHROPIC_API_KEY.",
            file=sys.stderr,
        )
        return 1

    db = BaseDatos(args.db)
    notas = db.todas_las_notas()
    if not notas:
        print("No hay notas. Analiza o scrapea un corpus primero.", file=sys.stderr)
        db.close()
        return 1

    # Construir {id: texto} a partir de titular + cuerpo (lo que ve el motor de tono).
    articulos = {}
    for n in notas:
        texto = ((n.get("titular") or "") + "\n\n" + (n.get("cuerpo") or "")).strip()
        if texto:
            articulos[str(n["id"])] = texto
    if args.limite:
        articulos = dict(list(articulos.items())[: args.limite])

    # 1) Estimar y mostrar el costo ANTES de ejecutar.
    est = costos.estimar_lote_tono(articulos, args.modelo)
    print(est.resumen())
    print()

    # 2) Confirmar (salvo --si para flujos automáticos).
    if not args.si:
        try:
            resp = input("¿Ejecutar el análisis de tono con este costo? [s/N] ").strip().lower()
        except EOFError:
            resp = ""
        if resp not in ("s", "si", "sí", "y", "yes"):
            print("Cancelado. No se gastó nada.")
            db.close()
            return 0

    # 3) Ejecutar el lote y medir el costo real.
    print(f"\nAnalizando el tono de {len(articulos)} notas con {args.modelo}...")

    def _progreso(hechos, total, _id):
        if hechos % 25 == 0 or hechos == total:
            print(f"  {hechos}/{total}", end="\r", flush=True)

    resultados, real = sentiment_engine.analizar_corpus_tono(
        articulos,
        api_key=api_key,
        modelo=args.modelo,
        callback=_progreso,
        workers=args.workers,
        devolver_costo=True,
    )
    print()

    errores = sum(1 for r in resultados.values() if r.get("error"))
    print(f"Listo: {len(resultados)} notas analizadas ({errores} con error).")
    print("\n--- COSTO REAL DEL LOTE ---")
    print(f"  Modelo: {real.modelo}")
    print(f"  Tokens entrada: {real.tokens_input:,}")
    print(f"  Tokens salida:  {real.tokens_output:,}")
    print(f"  COSTO REAL: ${real.costo_usd:,.4f} USD")
    print(f"  (estimado previo: ${est.costo_usd:,.4f} USD)")

    if args.salida:
        import json

        salida = {
            aid: {k: v for k, v in r.items() if k != "_usage"} for aid, r in resultados.items()
        }
        with open(args.salida, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "modelo": real.modelo,
                    "costo_usd": round(real.costo_usd, 4),
                    "tokens_input": real.tokens_input,
                    "tokens_output": real.tokens_output,
                    "resultados": salida,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        print(f"\nResultados guardados en: {args.salida}")

    db.close()
    return 0


def cmd_social(args):
    """Busca en redes sociales (YouTube/TikTok/X), filtra por audiencia y guarda."""
    from social import buscar_social, filtrar_por_audiencia, fuentes_disponibles, publicacion_a_nota

    claves = {}
    if args.youtube_key:
        claves["youtube"] = args.youtube_key
    if args.tiktok_token:
        claves["tiktok"] = args.tiktok_token
    plataformas = args.plataforma or ["youtube", "tiktok", "x"]
    disp = fuentes_disponibles(claves)
    print(f"Fuentes disponibles ahora: {disp or '(ninguna — falta API key o Chrome)'}")

    if getattr(args, "estado", False):
        print("\nCómo activar cada fuente:")
        print("  • YouTube  → API key gratis en https://console.cloud.google.com")
        print("               (habilita 'YouTube Data API v3' → crea API key).")
        print("               Luego:")
        print(
            f"               python cli.py --db {args.db} social "
            "--plataforma youtube --youtube-key TU_KEY \\"
        )
        print('                 --query "Cepeda Espriella" --min-vistas 1000 --top 100')
        print("  • TikTok   → requiere afiliación académica (Research API).")
        print("  • X        → usa la sesión de Chrome en :9222 (frágil, zona gris).")
        return 0
    plataformas = [p for p in plataformas if p in disp]
    if not plataformas:
        print("Sin fuentes usables. Para YouTube: --youtube-key TU_KEY")
        print("  (consíguela gratis en https://console.cloud.google.com → YouTube Data API v3)")
        return 1

    query = args.query or "Iván Cepeda Abelardo de la Espriella"
    pubs = buscar_social(
        plataformas,
        query,
        claves=claves,
        desde=args.desde,
        hasta=args.hasta,
        max_por_fuente=args.max,
        callback=_log,
    )
    print(f"\n{len(pubs)} publicaciones recolectadas.")
    if args.min_vistas or args.min_interacciones or args.top:
        pubs = filtrar_por_audiencia(
            pubs,
            min_vistas=args.min_vistas,
            min_interacciones=args.min_interacciones,
            top_n=args.top,
        )
        print(f"{len(pubs)} tras filtrar por audiencia.")
    # guardar como notas en la BD (para analizar con el mismo pipeline)
    db = BaseDatos(args.db)
    ins = 0
    for p in pubs:
        from scrapers.base import Nota

        d = publicacion_a_nota(p)
        nota = Nota(
            url=d["url"],
            medio=d["medio"],
            titular=d["titular"],
            cuerpo=d["cuerpo"],
            autor=d["autor"],
            fecha_publicacion=d["fecha_publicacion"],
            seccion=d["seccion"],
            metodo_extraccion=d["metodo_extraccion"],
        )
        if db.guardar_nota(nota):
            ins += 1
    db.close()
    print(
        f"{ins} publicaciones guardadas en {args.db}. Analiza con: "
        f"python cli.py --db {args.db} analizar"
    )
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="quac", description="¡Quac! — análisis de prensa electoral colombiana"
    )
    p.add_argument(
        "--db",
        default="datos/quac.db",
        help="Ruta de la base SQLite del proyecto (default: datos/quac.db)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("medios", help="Listar medios con adaptador").set_defaults(func=cmd_medios)

    ss = sub.add_parser("social", help="Buscar en redes sociales (YouTube/TikTok/X)")
    ss.add_argument("--query", help="Términos a buscar en redes")
    ss.add_argument(
        "--plataforma",
        action="append",
        choices=["youtube", "tiktok", "x"],
        help="Plataforma (repetible)",
    )
    ss.add_argument("--youtube-key", dest="youtube_key", help="API key de YouTube Data API v3")
    ss.add_argument("--tiktok-token", dest="tiktok_token", help="Token de TikTok Research API")
    ss.add_argument("--desde", help="AAAA-MM-DD")
    ss.add_argument("--hasta", help="AAAA-MM-DD")
    ss.add_argument("--max", type=int, default=50, help="Máx. por fuente")
    ss.add_argument("--min-vistas", type=int, default=0, dest="min_vistas")
    ss.add_argument("--min-interacciones", type=int, default=0, dest="min_interacciones")
    ss.add_argument("--top", type=int, help="Conservar solo las top-N por impacto")
    ss.add_argument(
        "--estado",
        action="store_true",
        help="Solo mostrar qué fuentes están activas y cómo activarlas",
    )
    ss.set_defaults(func=cmd_social)

    sv = sub.add_parser("validar", help="Validar la clasificación automática vs. manual")
    sv.add_argument("--salida", help="Ruta CSV de la muestra a exportar")
    sv.add_argument("--n", type=int, default=30, help="Tamaño de la muestra (default 30)")
    sv.add_argument("--concordancia", help="CSV ya codificado: calcula acuerdo + Kappa")
    sv.add_argument(
        "--oblig", help="La nota debe mencionar ≥1 (coma-separado); igual que en analizar"
    )
    sv.add_argument("--excluir", help="Descartar notas que mencionen alguno (coma-separado)")
    sv.set_defaults(func=cmd_validar)

    sp = sub.add_parser("scrape", help="Scrapear y guardar notas")
    sp.add_argument("urls", nargs="*", help="URLs de notas a scrapear")
    sp.add_argument("--archivo", help="Archivo con una URL por línea")
    sp.add_argument(
        "--ignorar-robots", action="store_true", help="(no recomendado) no consultar robots.txt"
    )
    sp.add_argument(
        "--sin-navegador",
        action="store_true",
        help="No usar el fallback de captura vía la sesión de Chrome",
    )
    sp.set_defaults(func=cmd_scrape)

    sb = sub.add_parser("buscar", help="Buscar notas por términos + fechas y scrapearlas")
    sb.add_argument("--termino", action="append", help="Término o frase a buscar (repetible)")
    sb.add_argument("--desde", help="Fecha de inicio AAAA-MM-DD (ida)")
    sb.add_argument("--hasta", help="Fecha final AAAA-MM-DD (regreso)")
    sb.add_argument(
        "--medio", action="append", help="Restringir a un dominio (repetible), ej. eltiempo.com"
    )
    sb.add_argument(
        "--entidad", action="append", help="Entidad de interés 'Nombre|tipo|var1,var2' (repetible)"
    )
    sb.add_argument("--criterios", help="Cargar criterios desde un JSON")
    sb.add_argument("--max", type=int, default=50, help="Máximo de resultados")
    sb.add_argument(
        "--masivo",
        action="store_true",
        help="Búsqueda EXHAUSTIVA: trocea fechas × términos para traer muchas más notas",
    )
    sb.add_argument(
        "--dias-tramo",
        type=int,
        default=7,
        dest="dias_tramo",
        help="Días por ventana en búsqueda masiva (default 7)",
    )
    sb.add_argument(
        "--filtrar",
        action="store_true",
        help="Conservar solo notas que mencionan una entidad de interés",
    )
    sb.add_argument(
        "--solo-listar", action="store_true", help="Solo mostrar resultados, sin scrapear"
    )
    sb.add_argument("--ignorar-robots", action="store_true")
    sb.add_argument("--sin-navegador", action="store_true")
    sb.set_defaults(func=cmd_buscar)

    sc = sub.add_parser("corpus", help="Scrapear un corpus masivo (JSON de buscar --masivo)")
    sc.add_argument("corpus", help="Ruta al JSON [{url,fecha,medio,titular}]")
    sc.add_argument(
        "--limite", type=int, default=0, help="Scrapear solo las primeras N URLs (0 = todas)"
    )
    sc.add_argument(
        "--cada", type=int, default=25, help="Imprimir progreso cada N notas (default 25)"
    )
    sc.add_argument("--ignorar-robots", action="store_true")
    sc.add_argument("--sin-navegador", action="store_true")
    sc.set_defaults(func=cmd_corpus)

    sub.add_parser("listar", help="Conteo de notas por medio").set_defaults(func=cmd_listar)

    sa = sub.add_parser("analizar", help="Sentimiento + NER + red")
    sa.add_argument("--salida", help="Ruta .html para la red interactiva")
    sa.add_argument("--json", help="Volcar resultados completos a JSON")
    sa.add_argument("--api-key", help="API key de Anthropic (enriquece NER/tono)")
    sa.add_argument(
        "--roberta", action="store_true", help="Usar RoBERTa-BNE para NER (si está instalado)"
    )
    sa.add_argument(
        "--peso-minimo",
        type=int,
        default=2,
        help="Mínimo de notas compartidas para una arista (default 2)",
    )
    sa.add_argument(
        "--gephi", action="store_true", help="Exportar también el grafo en formato Gephi (.gexf)"
    )
    sa.add_argument("--excel", help="Exportar tablas a un .xlsx para el paper")
    sa.add_argument(
        "--transformer",
        action="store_true",
        help="Sentimiento+emoción+odio con pysentimiento (solo versión PRO)",
    )
    sa.add_argument(
        "--bertopic", action="store_true", help="Tópicos con BERTopic/embeddings (solo versión PRO)"
    )
    sa.add_argument(
        "--sin-coref", action="store_true", help="No resolver correferencias (más rápido)"
    )
    sa.add_argument(
        "--estricto",
        action="store_true",
        help="Modo publicable: red/índice SOLO con actores del perfil (descarta ruido)",
    )
    sa.add_argument(
        "--oblig",
        default="",
        help="La nota DEBE mencionar ≥1 de estos términos (coma-separados)",
    )
    sa.add_argument(
        "--excluir",
        default="",
        help="Descartar la nota si menciona ≥1 de estos términos (coma-separados)",
    )
    sa.add_argument("--dashboard", help="Generar el dashboard HTML interactivo en esta ruta")
    sa.set_defaults(func=cmd_analizar)

    sr = sub.add_parser("revisar", help="Revisión human-in-the-loop de entidades dudosas")
    sr.add_argument("--stats", action="store_true", help="Solo mostrar estadísticas")
    sr.set_defaults(func=cmd_revisar)

    st = sub.add_parser(
        "tono", help="Análisis de tono editorial con Claude (estima y registra el costo IA)"
    )
    st.add_argument("--db", default="datos/quac.db", help="Base de datos del corpus")
    st.add_argument("--api-key", help="API key de Anthropic (o variable ANTHROPIC_API_KEY)")
    st.add_argument(
        "--modelo",
        default="claude-haiku-4-5-20251001",
        help="Modelo Claude (por defecto haiku-4-5, el más barato para tono)",
    )
    st.add_argument("--limite", type=int, default=0, help="Analizar solo las primeras N notas")
    st.add_argument("--workers", type=int, default=4, help="Llamadas en paralelo")
    st.add_argument("--salida", help="Guardar resultados+costo en este JSON")
    st.add_argument("--si", action="store_true", help="No preguntar; ejecutar (flujos automáticos)")
    st.set_defaults(func=cmd_tono)

    args = p.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())

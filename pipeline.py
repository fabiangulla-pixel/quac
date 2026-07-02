"""Pipeline de análisis de ¡Quac! — orquesta los motores reutilizados de Bashkar.

Sobre un conjunto de notas (de la BD) corre:
  - NER (spaCy es_core_news_sm; RoBERTa/Claude opcionales) → índice global.
  - Sentimiento/emociones OFFLINE (léxico; sin API key por defecto).
  - Red de co-ocurrencia de actores (network_engine).
  - Confianza por nota (semáforo: cuerpo corto / sin fecha → dudoso).

Todo offline salvo que se active enriquecimiento con Claude vía API key.
"""

from __future__ import annotations

import gc
from collections.abc import Callable

import analisis_avanzado
from core import (
    collocation_engine,
    confianza_engine,
    coref_engine,
    frame_engine,
    ner_engine,
    network_engine,
    sentiment_engine,
    topic_engine,
)
from scrapers.limpieza import (
    canonicalizar_organizaciones,
    canonicalizar_personas,
    filtrar_entidades_ner,
    limpiar_cuerpo,
)


def _cargar_spacy():
    from spacy_loader import cargar_modelo_es

    return cargar_modelo_es()


def _score_confianza_nota(nota: dict) -> dict:
    """Semáforo de calidad de scraping (reutiliza la lógica de Bashkar)."""
    score = 1.0
    motivos = []
    n_palabras = len((nota.get("cuerpo") or "").split())
    if n_palabras < 40:
        score -= 0.5
        motivos.append("cuerpo muy corto")
    if not nota.get("fecha_publicacion"):
        score -= 0.2
        motivos.append("sin fecha de publicación")
    if not nota.get("titular"):
        score -= 0.2
        motivos.append("sin titular")
    if nota.get("metodo_extraccion") == "trafilatura":
        score -= 0.1
        motivos.append("extracción genérica (sin adaptador dedicado)")
    score = max(0.0, round(score, 2))
    return {
        "score": score,
        "nivel": confianza_engine.nivel_confianza(score),
        "etiqueta": confianza_engine.etiqueta_semaforo(score),
        "motivos": motivos,
    }


def filtrar_relevantes(
    notas: list[dict],
    entidades_obligatorias: list | None = None,
    excluir_terminos: list | None = None,
) -> list[dict]:
    """Filtro de relevancia temática sobre titular+cuerpo, sin acentos/mayúsculas.

    - entidades_obligatorias: la nota debe mencionar ≥1 de estos términos.
    - excluir_terminos: se descarta si menciona ≥1 de estos.
    Es EL MISMO filtro del modo estricto de analizar_corpus; también lo usa
    `cli.py validar` para que la muestra Kappa salga del corpus del estudio.
    """
    import unicodedata

    def _norm_txt(s):
        s = unicodedata.normalize("NFKD", str(s or "").lower())
        return "".join(c for c in s if not unicodedata.combining(c))

    oblig = [_norm_txt(t) for t in (entidades_obligatorias or []) if str(t).strip()]
    excl = [_norm_txt(t) for t in (excluir_terminos or []) if str(t).strip()]
    if not (oblig or excl):
        return notas
    filtradas = []
    for nt in notas:
        txt = _norm_txt((nt.get("titular") or "") + " " + (nt.get("cuerpo") or ""))
        if oblig and not any(t in txt for t in oblig):
            continue
        if excl and any(t in txt for t in excl):
            continue
        filtradas.append(nt)
    return filtradas


def analizar_corpus(
    notas: list[dict],
    *,
    api_key: str | None = None,
    usar_roberta: bool = False,
    peso_minimo_red: int = 2,
    semillas_entidades: dict | None = None,
    usar_coref: bool = True,
    decisiones_revision: dict | None = None,
    # --- parámetros afinables (metodología DH) ---
    n_topicos: int = 5,
    min_palabras_nota: int = 0,  # excluir notas más cortas que esto
    calidad_minima: float = 0.0,  # excluir notas con score de calidad <
    entidades_obligatorias: list | None = None,  # la nota DEBE mencionar ≥1
    excluir_terminos: list | None = None,  # descartar si menciona ≥1
    solo_actores_relevantes: bool = False,  # red/índice SOLO con actores del perfil
    stopwords_extra: list | None = None,  # términos a ignorar en frec/colloc
    ventana_colocaciones: int = 6,
    usar_transformer: bool = False,  # sentimiento con modelo (más preciso)
    usar_bertopic: bool = False,  # tópicos con embeddings BERT (mejores)
    callback: Callable[[str], None] | None = None,
) -> dict:
    """Analiza una lista de notas (dicts de la BD).

    Devuelve dict con: por_nota (sentimiento/ner/confianza por url),
    indice_global, grafo (dict serializable) y agregados.
    """

    def log(msg):
        if callback:
            callback(msg)

    # Cargar marcos del perfil del usuario en el motor de framing (tu recomendación:
    # incluir marcos/eventos, no solo nombres).
    _perfil = {}
    try:
        import config as _config

        _perfil = _config.cargar()
        frame_engine.registrar_marcos_personalizados(_perfil.get("marcos", {}))
    except Exception:
        _perfil = {}

    log("Cargando modelo lingüístico…")
    nlp = _cargar_spacy()

    # Actores canónicos para el análisis de PROMINENCIA: los del perfil del
    # usuario (con sus variantes como semillas), si lo hay. Así "quién aparece
    # primero" y "con qué adjetivos" se miden sobre entidades unificadas y no
    # sobre cada forma cruda que detecte spaCy. Si no hay perfil, se rellena más
    # abajo con las personas que el NER vaya encontrando (fallback).
    _semillas_perfil: dict[str, list] = {}
    for _ent in _perfil.get("entidades") or []:
        if isinstance(_ent, dict) and _ent.get("nombre"):
            _semillas_perfil[_ent["nombre"]] = _ent.get("variantes", []) or []
    _actores_prominencia = sorted((semillas_entidades or _semillas_perfil).keys())

    indice_global = ner_engine.indice_global_vacio()
    por_nota: dict[str, dict] = {}

    # Filtro de calidad/longitud: excluir notas que el investigador no quiere
    # en el análisis (basura, muros, demasiado cortas). Reproducible.
    import calidad as _cal

    if min_palabras_nota or calidad_minima:
        antes = len(notas)
        filtradas = []
        for nt in notas:
            if len((nt.get("cuerpo") or "").split()) < min_palabras_nota:
                continue
            if calidad_minima and _cal.evaluar_extraccion(nt)["score"] < calidad_minima:
                continue
            filtradas.append(nt)
        log(f"Filtro de calidad: {len(filtradas)}/{antes} notas pasan el umbral.")
        notas = filtradas

    # Filtro de RELEVANCIA temática (combate el ruido de la búsqueda masiva:
    # notas de Perú/Fujimori, Florentino Pérez, etc. que coinciden en vocabulario
    # pero no son sobre la elección de interés). Opt-in.
    if entidades_obligatorias or excluir_terminos:
        antes = len(notas)
        notas = filtrar_relevantes(notas, entidades_obligatorias, excluir_terminos)
        det = []
        if entidades_obligatorias:
            det.append("mencionan ≥1 actor de interés")
        if excluir_terminos:
            det.append("sin términos excluidos")
        log(f"Filtro de relevancia ({', '.join(det)}): {len(notas)}/{antes} notas.")

    total = len(notas)
    for i, nota in enumerate(notas, 1):
        url = nota["url"]
        # Limpieza propia de ¡Quac!: quita boilerplate de portal antes de analizar.
        texto = limpiar_cuerpo(nota.get("cuerpo") or "")
        log(f"[{i}/{total}] {nota.get('medio', '?')}: {nota.get('titular', '')[:60]}")

        # NER (+ filtro de entidades-ruido propio de ¡Quac!, sin tocar el motor)
        ner = ner_engine.pipeline_ner(texto, nlp=nlp, api_key=api_key, usar_roberta=usar_roberta)
        ner = filtrar_entidades_ner(ner)
        ner_engine.actualizar_indice_global(indice_global, url, ner)

        # Sentimiento/emociones offline (8 emociones) + polaridad política
        # discriminante (positivo/negativo/neutro) más útil para cobertura.
        emo = sentiment_engine.analizar_emociones(texto)
        import sentimiento_politico

        # Con transformer: pysentimiento da sentimiento+emoción+ODIO+ironía.
        social = sentimiento_politico.analisis_social_completo(texto) if usar_transformer else None
        if social:
            emo["polaridad"] = social.get("polaridad", "neutro")
            emo["score_polaridad"] = social.get("score_polaridad", 0.0)
            emo["odio"] = social.get("odio", False)
            emo["agresivo"] = social.get("agresivo", False)
            emo["ironia"] = social.get("ironia", False)
            if social.get("emocion"):
                emo["emocion_transformer"] = social["emocion"]
        else:
            pol = sentimiento_politico.analizar_polaridad(texto, usar_transformer=usar_transformer)
            emo["polaridad"] = pol["polaridad"]
            emo["score_polaridad"] = pol["score"]
        # Marco intergrupal nosotros/ellos (Garzón-Velandia 2024)
        emo["intergrupal"] = sentimiento_politico.analizar_intergrupal(texto)

        # Encuadre / framing (offline; multi-etiqueta: top frames, no solo 1)
        frame = frame_engine.analizar_frame(texto)
        if api_key and not frame.get("frame_dominante"):
            frame_llm = frame_engine.clasificar_frame_llm(texto, api_key)
            if frame_llm:
                frame = frame_llm

        # Correferencia: cuenta menciones reales (entidad + pronombres "él",
        # "el candidato"…) para ponderar mejor la presencia de cada actor.
        coref = {}
        if usar_coref:
            try:
                cadenas = coref_engine.resolver_correferencias(texto, nlp=nlp)
                coref = {c["entidad_principal"]: c["n_menciones"] for c in cadenas}
            except Exception:
                coref = {}

        # Confianza de scraping + calidad de extracción (¿texto o basura?)
        conf = _score_confianza_nota(nota)
        import calidad

        cal = calidad.evaluar_extraccion(nota)

        # Prominencia: quién aparece PRIMERO (posición/lead) y con qué ADJETIVOS
        # se le califica. Medida sobre los actores CANÓNICOS de interés (del
        # perfil si lo hay; si no, las personas detectadas por el NER), con sus
        # variantes como formas — así "Cepeda" y "Iván Cepeda" no se cuentan
        # aparte. Se evita disparar sobre cualquier PROPN suelto.
        import prominencia

        # Sin perfil ni semillas: caer a las personas detectadas en esta nota.
        _actores_nota = _actores_prominencia or sorted(set(ner.get("personas", [])))
        prom = (
            prominencia.analizar_prominencia(
                texto,
                _actores_nota,
                nlp=nlp,
                semillas=semillas_entidades or _semillas_perfil,
                ventana=4,
            )
            if _actores_nota
            else {}
        )

        # Origen del medio: ¿la nota es de un medio colombiano o extranjero?
        # (país de origen). Usa la URL real y refuerza con el perfil.
        import origen_medios

        origen = origen_medios.clasificar_origen(
            nota.get("url") or nota.get("medio") or "", perfil=_perfil
        )

        por_nota[url] = {
            "medio": nota.get("medio"),
            "titular": nota.get("titular"),
            "fecha": nota.get("fecha_publicacion"),
            "autor": nota.get("autor"),
            "ner": ner,
            "emociones": emo,
            "frame": frame,
            "coref": coref,
            "confianza": conf,
            "calidad": cal,
            "prominencia": prom,
            "origen": origen,
        }

    # Unificar variantes del mismo actor (De la Espriella / Espriella / …),
    # sembrando con las variantes declaradas por el investigador (si las hay).
    log("Canonicalizando nombres de actores…")
    canonicalizar_personas(indice_global, semillas=semillas_entidades)
    # Unificar también organizaciones por las variantes del perfil (siglas→
    # nombre: CNE→Consejo Nacional Electoral, Farc→FARC, Presidencia→…).
    canonicalizar_organizaciones(indice_global, _perfil)

    # Filtro de RELEVANCIA: tras unificar variantes, conservar en el índice SOLO
    # los actores/instituciones del perfil curado (modo ESTRICTO, ideal para el
    # paper: control total, todo limpio y defendible). Saca el ruido internacional
    # y los fragmentos que aparecen por estadística pero no son de la discusión
    # nacional. Se aplica DESPUÉS de canonicalizar para no perder variantes ya
    # fundidas en la forma del perfil. Si falta un actor relevante, se agrega al
    # perfil y se reanaliza. (El modo mixto queda como variante explorable.)
    if solo_actores_relevantes:
        from scrapers.limpieza import _norm_rel, construir_universo_relevante

        universo = construir_universo_relevante(_perfil)
        if universo:
            antes_tot = sum(len(v) for v in indice_global.values() if isinstance(v, dict))
            for cat, ents in list(indice_global.items()):
                if isinstance(ents, dict):
                    indice_global[cat] = {
                        nombre: arts
                        for nombre, arts in ents.items()
                        if _norm_rel(nombre) in universo
                    }
            despues_tot = sum(len(v) for v in indice_global.values() if isinstance(v, dict))
            log(
                f"Filtro de relevancia (estricto, solo perfil): "
                f"{despues_tot}/{antes_tot} entidades conservadas."
            )

    # Human-in-the-loop: aplicar decisiones previas del revisor (descartar/
    # renombrar entidades validadas manualmente en sesiones anteriores).
    if decisiones_revision:
        import revision

        log(f"Aplicando {len(decisiones_revision)} revisiones manuales…")
        revision.aplicar_revisiones(indice_global, decisiones_revision)

    # Liberar el modelo spaCy: ya no se usa tras el bucle de NER/coref. En
    # equipos con poca RAM (≈8 GB) y corpus grandes (miles de notas) el pico de
    # memoria se acumula aquí; soltar el modelo y forzar GC evita el OOM/cierre
    # silencioso al entrar en las fases de red, tópicos y dashboard.
    del nlp
    gc.collect()

    # Red de co-ocurrencia de actores
    log("Construyendo red de co-ocurrencia de actores…")
    G = network_engine.construir_grafo(
        indice_global,
        categorias=["personas", "organizaciones"],
        peso_minimo=peso_minimo_red,
        callback=callback,
    )
    grafo = network_engine.grafo_a_dict(G)
    metricas = network_engine.metricas_red(G)

    # Análisis léxico del corpus (herramientas de Bashkar)
    textos = [limpiar_cuerpo(n.get("cuerpo") or "") for n in notas]
    textos = [t for t in textos if t.strip()]

    # Stopwords extra del investigador: se eliminan de los textos para que no
    # contaminen frecuencias/colocaciones/tópicos.
    if stopwords_extra:
        import re as _re

        patron = _re.compile(
            r"\b(" + "|".join(_re.escape(w) for w in stopwords_extra if w.strip()) + r")\b",
            _re.IGNORECASE,
        )
        textos = [patron.sub(" ", t) for t in textos]

    topicos = _modelar_topicos_seguro(
        textos, callback=log, n_topicos=n_topicos, usar_bertopic=usar_bertopic
    )
    frec = collocation_engine.frecuencias(textos, top_n=25, stopwords=True)
    colocaciones = _colocaciones_actor_principal(
        textos, indice_global, ventana=ventana_colocaciones
    )
    # `textos` duplica todo el corpus limpio en RAM y ya no se reutiliza tras
    # tópicos/frecuencias/colocaciones: liberarlo antes de los agregados.
    del textos
    gc.collect()

    # Metodologías DH: series temporales, encuadre agregado y polarización medios
    log("Calculando series temporales, encuadre y comparación entre medios…")
    series = analisis_avanzado.series_temporales(por_nota)
    # Líneas del tiempo DIARIAS: tendencia/sesgo/volumen/encuadre día a día, con
    # media móvil y series por medio (para ver si un medio o grupo cambia de
    # tendencia). Global + por cada medio top (el dashboard combina grupos).
    import lineas_tiempo as _lt

    log("Calculando líneas del tiempo diarias (tendencia, picos)…")
    lineas_global = _lt.series_diarias(por_nota, _perfil)
    _medios_top = [
        m for m, _ in sorted(_agregados(por_nota).items(), key=lambda kv: -kv[1]["n"])[:20]
    ]
    lineas_por_medio = {m: _lt.series_diarias(por_nota, _perfil, medios=[m]) for m in _medios_top}
    lineas = {
        "global": lineas_global,
        "por_medio": lineas_por_medio,
        "picos_volumen": _lt.picos_volumen(lineas_global["dias"], lineas_global["volumen"]),
    }
    frames_corpus = analisis_avanzado.resumen_frames(por_nota)
    comparacion = analisis_avanzado.comparar_medios(por_nota, indice_global)
    menciones_coref = analisis_avanzado.menciones_por_coref(por_nota)

    # Tipos ricos del perfil: cobertura por tipo y comparativa de candidatos
    cobertura_tipo = analisis_avanzado.cobertura_por_tipo(indice_global, _perfil)
    comp_candidatos = analisis_avanzado.comparar_candidatos(por_nota, indice_global, _perfil)
    # Filiación/tendencia política de cada medio hacia los candidatos
    tendencia = analisis_avanzado.tendencia_medios(notas, _perfil)
    toxicidad = analisis_avanzado.resumen_toxicidad(por_nota)
    # Prominencia agregada: quién encabeza más notas y con qué adjetivos
    import prominencia as _prom

    prominencia_corpus = _prom.resumen_prominencia(por_nota)
    # Origen agregado: cobertura nacional vs. internacional, desglose por país
    import origen_medios as _orig

    origen_corpus = _orig.resumen_origen(por_nota)

    return {
        "por_nota": por_nota,
        "indice_global": indice_global,
        "grafo": grafo,
        "metricas_red": metricas,
        "agregados": _agregados(por_nota),
        "topicos": topicos,
        "frecuencias": frec,
        "colocaciones": colocaciones,
        "series_temporales": series,
        "frames": frames_corpus,
        "comparacion_medios": comparacion,
        "menciones_coref": menciones_coref,
        "calidad_corpus": __import__("calidad").resumen_calidad(notas),
        "cobertura_por_tipo": cobertura_tipo,
        "comparacion_candidatos": comp_candidatos,
        "tendencia_medios": tendencia,
        "toxicidad": toxicidad,
        "prominencia": prominencia_corpus,
        "origen": origen_corpus,
        "lineas_tiempo": lineas,
    }


def _modelar_topicos_seguro(textos, callback=None, n_topicos=5, usar_bertopic=False):
    """Tópicos: BERTopic (embeddings, mejor) si se pide y está; si no, NMF.
    Degrada con gracia si el corpus es chico o BERTopic falla."""
    if len(textos) < 3:
        return {"nota": "corpus demasiado pequeño para modelar tópicos (<3 notas)"}
    try:
        return topic_engine.modelar_topicos(
            textos,
            n_topicos=min(max(2, n_topicos), len(textos)),
            usar_bertopic=usar_bertopic,
            min_df=1,
            callback=callback,
        )
    except Exception as exc:
        # si BERTopic falló, reintentar con NMF
        if usar_bertopic:
            try:
                return topic_engine.modelar_topicos(
                    textos,
                    n_topicos=min(max(2, n_topicos), len(textos)),
                    usar_bertopic=False,
                    min_df=1,
                    callback=callback,
                )
            except Exception as exc2:
                return {"error": str(exc2)}
        return {"error": str(exc)}


def _colocaciones_actor_principal(textos, indice_global, ventana=6):
    """Collocates (PMI) del apellido del actor más mencionado."""
    personas = indice_global.get("personas", {})
    if not personas:
        return {}
    principal = max(personas, key=lambda p: len(personas[p]))
    # Elegir como clave el apellido más frecuente del actor EN el corpus, no la
    # última palabra de su nombre legal (que puede ser un segundo apellido raro).
    corpus_low = " ".join(textos).lower()
    candidatos = [
        w
        for w in principal.split()
        if len(w) > 3
        and w.lower() not in {"abelardo", "gabriel", "juan", "maría", "maria", "josé", "jose"}
    ]
    clave = max(candidatos, key=lambda w: corpus_low.count(w.lower())) if candidatos else principal
    try:
        cols = collocation_engine.collocates(textos, clave, ventana=ventana, top_n=15)
    except Exception:
        cols = []
    return {"actor": principal, "clave": clave, "collocates": cols}


def _agregados(por_nota: dict) -> dict:
    """Resúmenes por medio: emoción dominante y nº de notas."""
    por_medio: dict[str, dict] = {}
    for url, r in por_nota.items():
        medio = r.get("medio") or "?"
        d = por_medio.setdefault(medio, {"n": 0, "emociones": {}})
        d["n"] += 1
        dom = r["emociones"].get("emocion_dominante")
        if dom:
            d["emociones"][dom] = d["emociones"].get(dom, 0) + 1
    return por_medio

"""Análisis avanzado de ¡Quac! — series temporales y polarización entre medios.

Implementa metodologías de humanidades digitales (ver docs/METODOLOGIAS_DH.md):
  - **Series temporales** (distant reading): volumen, tono y frame por fecha.
    Aprovecha que la prensa web SÍ trae fecha real (a diferencia de la histórica).
  - **Comparación medio×actor** (selection bias / polarización): qué medios
    cubren a qué actores y con qué emoción dominante; índice de divergencia.

Funciones puras sobre ``por_nota`` (el dict que produce el pipeline), sin red.
"""

from __future__ import annotations

from collections import defaultdict


def _mes(fecha_iso: str) -> str:
    """Devuelve AAAA-MM de una fecha ISO; '' si no hay fecha."""
    if not fecha_iso or len(fecha_iso) < 7:
        return ""
    return fecha_iso[:7]


def series_temporales(por_nota: dict) -> dict:
    """Agrega por mes: volumen de notas, emoción dominante y frame dominante.

    Retorna:
      {"meses": [AAAA-MM,…],
       "volumen": {mes: n},
       "emociones": {mes: {emocion: n}},
       "frames": {mes: {frame: n}}}
    """
    volumen: dict[str, int] = defaultdict(int)
    emociones: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    frames: dict[str, dict] = defaultdict(lambda: defaultdict(int))

    for r in por_nota.values():
        mes = _mes(r.get("fecha") or "")
        if not mes:
            continue
        volumen[mes] += 1
        emo = (r.get("emociones") or {}).get("emocion_dominante")
        if emo:
            emociones[mes][emo] += 1
        frame = (r.get("frame") or {}).get("frame_dominante")
        if frame:
            frames[mes][frame] += 1

    meses = sorted(volumen)
    return {
        "meses": meses,
        "volumen": dict(volumen),
        "emociones": {m: dict(emociones[m]) for m in meses},
        "frames": {m: dict(frames[m]) for m in meses},
    }


def comparar_medios(por_nota: dict, indice_global: dict, top_actores: int = 8) -> dict:
    """Matriz medio × actor: cuántas notas de cada medio mencionan a cada actor.

    Revela sesgo de selección: qué actores destaca o silencia cada medio.
    Retorna {"actores": [...], "medios": [...], "matriz": {medio: {actor: n}},
             "emocion_por_medio": {medio: emocion_dominante}}.
    """
    personas = indice_global.get("personas", {})
    # actores más mencionados (por nº de notas)
    actores = [a for a, _ in sorted(personas.items(), key=lambda kv: -len(kv[1]))[:top_actores]]

    # url → medio
    url_medio = {url: (r.get("medio") or "?") for url, r in por_nota.items()}

    matriz: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    for actor in actores:
        for art_id in personas.get(actor, []):
            medio = url_medio.get(art_id, "?")
            matriz[medio][actor] += 1

    # emoción dominante agregada por medio
    emo_medio: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    for r in por_nota.values():
        medio = r.get("medio") or "?"
        emo = (r.get("emociones") or {}).get("emocion_dominante")
        if emo:
            emo_medio[medio][emo] += 1
    emocion_por_medio = {m: max(d, key=d.get) if d else None for m, d in emo_medio.items()}

    medios = sorted(matriz)
    return {
        "actores": actores,
        "medios": medios,
        "matriz": {m: dict(matriz[m]) for m in medios},
        "emocion_por_medio": emocion_por_medio,
    }


def _mapa_tipos(perfil: dict) -> dict:
    """{forma_lower: tipo_rico} a partir de las entidades del perfil.

    Permite reclasificar los actores detectados por NER (persona/org/lugar) en
    los tipos del diccionario del investigador: candidato, formula_vp,
    excandidato, encuestadora, autoridad_electoral, etc.
    """
    mapa = {}
    for e in (perfil or {}).get("entidades", []):
        tipo = e.get("tipo", "otro")
        for forma in [e["nombre"]] + e.get("variantes", []):
            mapa[forma.lower().strip()] = tipo
    return mapa


def tipo_de_actor(nombre: str, mapa_tipos: dict) -> str:
    """Devuelve el tipo rico del perfil para un actor, o 'otro' si no está.

    Coincidencia estricta para no clasificar mal: (1) forma exacta, o (2) el
    actor ES exactamente una forma del perfil tras quitar ruido. NO basta con
    "contener el apellido" — eso etiquetaba "Caso Manuel Cepeda Vargas" como
    candidato. Tras la canonicalización, los actores ya vienen en su forma
    canónica, así que la coincidencia exacta es lo correcto.
    """
    low = nombre.lower().strip()
    if low in mapa_tipos:
        return mapa_tipos[low]
    return "otro"


def cobertura_por_tipo(indice_global: dict, perfil: dict) -> dict:
    """Agrupa los actores por su TIPO del perfil y cuenta su cobertura.

    Ej.: {candidato: [{actor, n_notas}], excandidato: [...], encuestadora: [...]}.
    Habilita comparaciones como "cobertura de candidatos vs. excandidatos".
    """
    mapa = _mapa_tipos(perfil)
    personas = indice_global.get("personas", {})
    orgs = indice_global.get("organizaciones", {})
    todos = {**personas, **orgs}
    por_tipo: dict[str, list] = {}
    for actor, arts in todos.items():
        tipo = tipo_de_actor(actor, mapa)
        por_tipo.setdefault(tipo, []).append({"actor": actor, "n_notas": len(arts)})
    for tipo in por_tipo:
        por_tipo[tipo].sort(key=lambda d: -d["n_notas"])
    return por_tipo


def comparar_candidatos(por_nota: dict, indice_global: dict, perfil: dict) -> dict:
    """Comparativa de los CANDIDATOS: visibilidad, tono y encuadre de cada uno.

    Es la tabla central de un estudio de cobertura electoral: para cada
    candidato, nº de notas, emoción dominante de esas notas y encuadre dominante.
    """
    mapa = _mapa_tipos(perfil)
    personas = indice_global.get("personas", {})
    candidatos = [a for a in personas if tipo_de_actor(a, mapa) in ("candidato", "formula_vp")]
    res = {}
    for cand in candidatos:
        arts = set(personas.get(cand, []))
        notas = [r for u, r in por_nota.items() if u in arts]
        emo, fr, pol = {}, {}, {"positivo": 0, "negativo": 0, "neutro": 0}
        suma_score = 0.0
        for r in notas:
            e = (r.get("emociones") or {}).get("emocion_dominante")
            if e:
                emo[e] = emo.get(e, 0) + 1
            p = (r.get("emociones") or {}).get("polaridad")
            if p in pol:
                pol[p] += 1
            suma_score += (r.get("emociones") or {}).get("score_polaridad", 0) or 0
            f = (r.get("frame") or {}).get("etiqueta")
            if f:
                fr[f] = fr.get(f, 0) + 1
        n = len(notas)
        import sentimiento_politico

        res[cand] = {
            "n_notas": n,
            "emocion_dominante": max(emo, key=emo.get) if emo else None,
            "encuadre_dominante": max(fr, key=fr.get) if fr else None,
            "polaridad": pol,
            "polaridad_dominante": max(pol, key=pol.get) if n else None,
            "score_polaridad_medio": round(suma_score / n, 3) if n else 0.0,
            "polarizacion_afectiva": sentimiento_politico.indice_polarizacion_afectiva(pol),
            "emociones": emo,
            "encuadres": fr,
        }
    return res


def tendencia_medios(
    notas: list[dict], perfil: dict, candidatos_formas: dict | None = None
) -> dict:
    """Filiación/tendencia política de cada medio hacia los candidatos.

    Para cada medio y cada candidato, calcula el TONO MEDIO (polaridad) de los
    fragmentos de sus notas que hablan de ese candidato (polaridad_hacia). Un
    medio que trata positivo a A y negativo a B revela su tendencia. El "sesgo"
    es la diferencia de trato entre candidatos: >0 favorece al primer candidato.

    Retorna:
      {"candidatos": [c1, c2,...],
       "medios": {medio: {"tono": {cand: score}, "n": {cand: n_notas},
                          "sesgo": float, "favorece": cand|None}}}
    """
    import sentimiento_politico as sp

    # candidatos del perfil + sus formas
    if candidatos_formas is None:
        candidatos_formas = {}
        for e in perfil.get("entidades", []):
            if e.get("tipo") in ("candidato",):
                candidatos_formas[e["nombre"]] = [e["nombre"]] + e.get("variantes", [])
    candidatos = list(candidatos_formas)
    if len(candidatos) < 1:
        return {"candidatos": [], "medios": {}}

    _EXCLUIR = ("bing.com", "google.com", "duckduckgo", "yahoo.com", "msn.com")
    medios: dict[str, dict] = {}
    for nt in notas:
        medio = nt.get("medio") or "?"
        if any(x in medio.lower() for x in _EXCLUIR):
            continue
        cuerpo = nt.get("cuerpo") or ""
        d = medios.setdefault(
            medio, {"_acum": {c: [] for c in candidatos}, "n": dict.fromkeys(candidatos, 0)}
        )
        for cand, formas in candidatos_formas.items():
            ph = sp.polaridad_hacia(cuerpo, formas)
            if ph.get("n_menciones", 0) > 0:
                d["_acum"][cand].append(ph["score"])
                d["n"][cand] += 1

    salida = {}
    for medio, d in medios.items():
        tono = {}
        for cand in candidatos:
            vals = d["_acum"][cand]
            tono[cand] = round(sum(vals) / len(vals), 3) if vals else None
        # sesgo: diferencia de trato entre los dos primeros candidatos
        sesgo, favorece = 0.0, None
        if len(candidatos) >= 2:
            a, b = candidatos[0], candidatos[1]
            ta, tb = tono.get(a), tono.get(b)
            if ta is not None and tb is not None:
                sesgo = round(ta - tb, 3)
                if abs(sesgo) >= 0.1:
                    favorece = a if sesgo > 0 else b
        # solo incluir medios que mencionan a algún candidato
        if any(d["n"][c] for c in candidatos):
            salida[medio] = {"tono": tono, "n": d["n"], "sesgo": sesgo, "favorece": favorece}
    # ordenar por nº total de notas sobre candidatos
    salida = dict(sorted(salida.items(), key=lambda kv: -sum(kv[1]["n"].values())))
    return {"candidatos": candidatos, "medios": salida}


def menciones_por_coref(por_nota: dict, top_n: int = 15) -> list[dict]:
    """Suma las menciones (entidad + pronombres) de cada actor en todo el corpus.

    A diferencia del conteo por nº de notas, esto pondera la PRESENCIA real:
    un actor referido muchas veces dentro de una nota (por correferencia) pesa
    más. Complementa el ranking del índice global.
    """
    total: dict[str, int] = defaultdict(int)
    for r in por_nota.values():
        for actor, n in (r.get("coref") or {}).items():
            total[actor] += n
    ordenado = sorted(total.items(), key=lambda kv: -kv[1])
    return [{"actor": a, "menciones": n} for a, n in ordenado[:top_n]]


def resumen_toxicidad(por_nota: dict) -> dict:
    """Discurso de odio/agresividad/ironía en el corpus (requiere transformer).

    Cuenta notas con odio/agresividad y las desglosa por medio. Métrica de la
    calidad del debate público — clave en cobertura electoral polarizada.
    """
    total = odio = agresivo = ironia = 0
    por_medio: dict[str, dict] = {}
    for r in por_nota.values():
        e = r.get("emociones") or {}
        if "odio" not in e and "agresivo" not in e:
            continue  # no se corrió el transformer
        total += 1
        medio = r.get("medio") or "?"
        d = por_medio.setdefault(medio, {"odio": 0, "agresivo": 0, "n": 0})
        d["n"] += 1
        if e.get("odio"):
            odio += 1
            d["odio"] += 1
        if e.get("agresivo"):
            agresivo += 1
            d["agresivo"] += 1
        if e.get("ironia"):
            ironia += 1
    return {
        "disponible": total > 0,
        "n_analizadas": total,
        "odio": odio,
        "agresivo": agresivo,
        "ironia": ironia,
        "por_medio": por_medio,
    }


def resumen_frames(por_nota: dict) -> dict:
    """Distribución global de frames dominantes en el corpus."""
    dist: dict[str, int] = defaultdict(int)
    etiquetas: dict[str, str] = {}
    for r in por_nota.values():
        fr = r.get("frame") or {}
        f = fr.get("frame_dominante")
        if f:
            dist[f] += 1
            etiquetas[f] = fr.get("etiqueta", f)
    ordenado = sorted(dist.items(), key=lambda kv: -kv[1])
    return {"distribucion": [{"frame": f, "etiqueta": etiquetas[f], "n": n} for f, n in ordenado]}

"""Sentimiento orientado a cobertura política — más discriminante que el léxico
de 8 emociones (que sesga todo a "confianza" por palabras como paz/orden/nación).

Para un estudio de cobertura electoral interesa la POLARIDAD de la nota hacia su
tema (positiva / negativa / neutra) y su intensidad, no solo una etiqueta de
emoción. Combina:
  - léxico de polaridad política (positivo/negativo) en español,
  - negaciones ("no", "sin", "nunca") que invierten la polaridad,
  - normalización por longitud,
y deja el análisis de 8 emociones de Bashkar como complemento.

100% local. Si hay API key se puede sustituir por el tono de Claude (opcional).
"""

from __future__ import annotations

import re

_POS = {
    "logro",
    "logros",
    "avance",
    "avances",
    "mejora",
    "mejoras",
    "éxito",
    "exitoso",
    "respaldo",
    "apoyo",
    "favorable",
    "favorabilidad",
    "ganar",
    "ganó",
    "victoria",
    "lidera",
    "liderazgo",
    "fortaleza",
    "acuerdo",
    "consenso",
    "unidad",
    "esperanza",
    "propuesta",
    "compromiso",
    "transparencia",
    "honesto",
    "honestidad",
    "defiende",
    "reconocimiento",
    "elogio",
    "celebra",
    "histórico",
    "positivo",
    "crecimiento",
    "respeto",
    "diálogo",
    "paz",
    "garantía",
    "confianza",
    "credibilidad",
}
_NEG = {
    "crisis",
    "escándalo",
    "corrupción",
    "corrupto",
    "fraude",
    "polémica",
    "ataque",
    "ataques",
    "denuncia",
    "denuncias",
    "acusación",
    "acusaciones",
    "rechazo",
    "crítica",
    "críticas",
    "critican",
    "cuestionado",
    "cuestionamientos",
    "fracaso",
    "derrota",
    "pierde",
    "perdió",
    "caída",
    "amenaza",
    "amenazas",
    "riesgo",
    "violencia",
    "conflicto",
    "mentira",
    "mentiras",
    "falso",
    "engaño",
    "miedo",
    "temor",
    "irregularidades",
    "ilegal",
    "delito",
    "investigación",
    "sanción",
    "controversia",
    "tensión",
    "división",
    "guerra",
    "odio",
    "negativo",
    "grave",
    "preocupación",
    "alarma",
    "desinformación",
    "bots",
    "bodegas",
}
_NEGADORES = {"no", "ni", "sin", "nunca", "jamás", "tampoco", "nada"}


# ── Modelo transformer opcional (más preciso que el léxico) ─────────────────
# Carga perezosa: solo si el usuario activa "usar transformer". El modelo se
# descarga de HuggingFace la primera vez (requiere internet esa vez). Si algo
# falla (sin internet, sin transformers/torch), se cae al léxico sin romper.
_MODELO_HF = "pysentimiento/robertuito-sentiment-analysis"
_pipe_cache = {}


def _cargar_transformer():
    if "pipe" in _pipe_cache:
        return _pipe_cache["pipe"]
    try:
        from transformers import pipeline

        pipe = pipeline(
            "sentiment-analysis",
            model=_MODELO_HF,
            tokenizer=_MODELO_HF,
            truncation=True,
            max_length=512,
        )
        _pipe_cache["pipe"] = pipe
        return pipe
    except Exception:
        _pipe_cache["pipe"] = None
        return None


def analizar_polaridad_transformer(texto: str) -> dict | None:
    """Polaridad con modelo transformer en español. None si no está disponible."""
    if not texto or not texto.strip():
        return {"polaridad": "neutro", "score": 0.0, "fuente": "transformer"}
    pipe = _cargar_transformer()
    if pipe is None:
        return None
    try:
        r = pipe(texto[:1500])[0]
        # robertuito devuelve POS/NEG/NEU
        etq = r["label"].upper()
        mapa = {"POS": "positivo", "NEG": "negativo", "NEU": "neutro"}
        pol = mapa.get(etq, "neutro")
        signo = {"positivo": 1, "negativo": -1, "neutro": 0}[pol]
        return {
            "polaridad": pol,
            "score": round(signo * float(r["score"]), 3),
            "fuente": "transformer",
        }
    except Exception:
        return None


def analizar_polaridad(texto: str, usar_transformer: bool = False) -> dict:
    """Polaridad política: positivo / negativo / neutro + score ∈ [-1, 1].

    Por defecto usa el léxico (rápido, local). Si ``usar_transformer=True`` y el
    modelo está disponible, usa el transformer (más preciso) y cae al léxico si
    falla. Léxico: cuenta términos pos/neg, invierte por negación local, normaliza.
    """
    if usar_transformer:
        r = analizar_polaridad_transformer(texto)
        if r is not None:
            return r
    return _analizar_polaridad_lexico(texto)


def _analizar_polaridad_lexico(texto: str) -> dict:
    if not texto or not texto.strip():
        return {"polaridad": "neutro", "score": 0.0, "n_pos": 0, "n_neg": 0, "intensidad": 0.0}

    palabras = re.findall(r"\b[a-záéíóúüñ]+\b", texto.lower())
    n_pos = n_neg = 0
    for i, p in enumerate(palabras):
        es_pos = p in _POS
        es_neg = p in _NEG
        if not (es_pos or es_neg):
            continue
        # ¿negación en las 3 palabras previas? invierte
        ventana = palabras[max(0, i - 3) : i]
        if any(w in _NEGADORES for w in ventana):
            es_pos, es_neg = es_neg, es_pos
        if es_pos:
            n_pos += 1
        if es_neg:
            n_neg += 1

    total = n_pos + n_neg
    n_palabras = max(1, len(palabras))
    if total == 0:
        return {"polaridad": "neutro", "score": 0.0, "n_pos": 0, "n_neg": 0, "intensidad": 0.0}

    score = round((n_pos - n_neg) / total, 3)
    intensidad = round(total / n_palabras * 100, 2)  # densidad emocional %
    if score > 0.15:
        pol = "positivo"
    elif score < -0.15:
        pol = "negativo"
    else:
        pol = "neutro"
    return {
        "polaridad": pol,
        "score": score,
        "n_pos": n_pos,
        "n_neg": n_neg,
        "intensidad": intensidad,
    }


# ── pysentimiento: análisis social completo en español (opcional) ──────────
# Toolkit transformer (RoBERTuito) que da sentimiento + emoción (6 Ekman) +
# DISCURSO DE ODIO + ironía con un solo modelo. Carga perezosa; si no está
# instalado, las funciones devuelven None y el pipeline usa el léxico.
_ANALIZADORES = {}


def transformer_disponible() -> bool:
    """True si pysentimiento está instalado y el Python es compatible (no 3.14).

    NO importa pysentimiento/torch (eso es lento y puede bloquear la GUI): solo
    comprueba que los módulos EXISTEN con importlib.util.find_spec. La carga real
    ocurre perezosamente al primer análisis con transformer.
    """
    import sys

    if sys.version_info[:2] >= (3, 14):
        return False
    try:
        import importlib.util as u

        return u.find_spec("pysentimiento") is not None and u.find_spec("torch") is not None
    except Exception:
        return False


def _analizador(tarea: str):
    """Carga perezosa de un analyzer de pysentimiento. None si no disponible."""
    if tarea in _ANALIZADORES:
        return _ANALIZADORES[tarea]
    if not transformer_disponible():
        _ANALIZADORES[tarea] = None
        return None
    try:
        from pysentimiento import create_analyzer

        _ANALIZADORES[tarea] = create_analyzer(task=tarea, lang="es")
    except Exception:
        _ANALIZADORES[tarea] = None
    return _ANALIZADORES[tarea]


def analisis_social_completo(texto: str) -> dict | None:
    """Sentimiento + emoción + odio + ironía con pysentimiento (transformer).

    Devuelve None si pysentimiento no está instalado (→ el pipeline usa léxico).
    """
    if not texto or not texto.strip():
        return None
    senti = _analizador("sentiment")
    if senti is None:
        return None
    frag = texto[:1500]
    out = {"fuente": "pysentimiento"}
    try:
        s = senti.predict(frag)
        mapa = {"POS": "positivo", "NEG": "negativo", "NEU": "neutro"}
        out["polaridad"] = mapa.get(s.output, "neutro")
        signo = {"positivo": 1, "negativo": -1, "neutro": 0}[out["polaridad"]]
        out["score_polaridad"] = round(signo * float(s.probas.get(s.output, 0)), 3)
    except Exception:
        return None
    # emoción (6 Ekman + otros) — opcional
    emo = _analizador("emotion")
    if emo is not None:
        try:
            out["emocion"] = emo.predict(frag).output
        except Exception:
            pass
    # discurso de odio — opcional (clave para polarización electoral)
    hate = _analizador("hate_speech")
    if hate is not None:
        try:
            h = hate.predict(frag)
            etiquetas = h.output if isinstance(h.output, (list, tuple)) else [h.output]
            out["odio"] = "hateful" in etiquetas
            out["agresivo"] = "aggressive" in etiquetas
            out["dirigido"] = "targeted" in etiquetas
        except Exception:
            pass
    # ironía — opcional
    iro = _analizador("irony")
    if iro is not None:
        try:
            out["ironia"] = iro.predict(frag).output == "ironic"
        except Exception:
            pass
    return out


# ── Marco endogrupo/exogrupo (nosotros vs. ellos) ───────────────────────────
# Basado en Garzón-Velandia (USC 2024), "Polarización política en redes sociales:
# perspectiva intergrupal y emocional": la polarización afectiva se expresa como
# exaltación del endogrupo ("nosotros") y deslegitimación/ataque al exogrupo
# ("ellos"). Categorías léxicas tipo LIWC en español.

_NOSOTROS = {
    "nosotros",
    "nuestro",
    "nuestra",
    "nuestros",
    "nuestras",
    "nos",
    "unidos",
    "juntos",
    "nuestra gente",
    "los nuestros",
    "compatriotas",
}
_ELLOS = {"ellos", "esos", "esa gente", "los otros", "aquellos", "su gente"}
_DESLEGITIMACION = {
    "corrupto",
    "corruptos",
    "mentiroso",
    "mentirosos",
    "traidor",
    "traidores",
    "criminal",
    "criminales",
    "enemigo",
    "enemigos",
    "peligro",
    "amenaza",
    "fraude",
    "ilegítimo",
    "dictadura",
    "tirano",
    "populista",
    "demagogo",
    "radical",
    "extremista",
    "castrochavismo",
    "comunista",
    "fascista",
    "uribista",
    "petrista",
}
_EXALTACION = {
    "esperanza",
    "futuro",
    "cambio",
    "unidad",
    "dignidad",
    "patria",
    "pueblo",
    "victoria",
    "triunfo",
    "compromiso",
    "honesto",
    "trabajo",
    "progreso",
    "libertad",
    "justicia",
    "paz",
}


def analizar_intergrupal(texto: str) -> dict:
    """Mide el marco 'nosotros vs. ellos' (polarización afectiva intergrupal).

    Retorna conteos de exaltación del endogrupo y deslegitimación del exogrupo,
    y un 'índice intergrupal' (cuánto del discurso es de confrontación de grupos).
    """
    if not texto:
        return {
            "endogrupo": 0,
            "exogrupo": 0,
            "deslegitimacion": 0,
            "exaltacion": 0,
            "indice_intergrupal": 0.0,
        }
    palabras = re.findall(r"\b[a-záéíóúüñ]+\b", texto.lower())
    n = max(1, len(palabras))
    endo = sum(1 for p in palabras if p in _NOSOTROS)
    exo = sum(1 for p in palabras if p in _ELLOS)
    desleg = sum(1 for p in palabras if p in _DESLEGITIMACION)
    exalt = sum(1 for p in palabras if p in _EXALTACION)
    indice = round((endo + exo + desleg + exalt) / n * 100, 2)
    return {
        "endogrupo": endo,
        "exogrupo": exo,
        "deslegitimacion": desleg,
        "exaltacion": exalt,
        "indice_intergrupal": indice,
    }


def indice_polarizacion_afectiva(distrib_polaridad: dict) -> float:
    """Índice de polarización afectiva de la cobertura de un actor (0–1).

    Garzón-Velandia: la polarización combina valencia (pos/neg) con intensidad.
    Aquí: alta cuando la cobertura se reparte en EXTREMOS (mucho positivo Y mucho
    negativo) en vez de concentrarse o ser neutra. 0 = sin polarización (todo
    neutro/un solo signo); 1 = máxima división pos/neg.
    """
    pos = distrib_polaridad.get("positivo", 0)
    neg = distrib_polaridad.get("negativo", 0)
    neu = distrib_polaridad.get("neutro", 0)
    total = pos + neg + neu
    if total == 0 or (pos + neg) == 0:
        return 0.0
    # proporción no-neutra * balance entre pos y neg (máximo cuando pos≈neg)
    no_neutro = (pos + neg) / total
    balance = 1 - abs(pos - neg) / (pos + neg)
    return round(no_neutro * balance, 3)


def polaridad_hacia(texto: str, entidad_formas: list[str], ventana: int = 25) -> dict:
    """Polaridad del texto SOLO en el entorno de una entidad (X respecto a Y).

    Mide cómo se habla de una entidad concreta: toma ventanas de ±N palabras
    alrededor de cada mención de la entidad y calcula la polaridad ahí. Clave
    para "¿con qué tono trata cada medio a cada candidato?".
    """
    if not texto:
        return analizar_polaridad("")
    palabras = re.findall(r"\b[\wáéíóúüñ]+\b", texto.lower())
    formas = [f.lower() for f in entidad_formas]
    # índices de menciones (por última palabra significativa de cada forma)
    claves = set()
    for f in formas:
        toks = [t for t in f.split() if len(t) > 3]
        if toks:
            claves.add(toks[-1])
        else:
            claves.add(f)
    fragmentos = []
    for i, p in enumerate(palabras):
        if p in claves:
            ini = max(0, i - ventana)
            fin = min(len(palabras), i + ventana)
            fragmentos.append(" ".join(palabras[ini:fin]))
    if not fragmentos:
        return {"polaridad": "neutro", "score": 0.0, "n_menciones": 0}
    r = analizar_polaridad(" ".join(fragmentos))
    r["n_menciones"] = len(fragmentos)
    return r

"""core/coref_engine.py — Resolución de correferencia para corpus histórico.

Estrategia en dos capas:
  1. Ligera (sin dependencias extras): heurísticas basadas en spaCy NER + pronombres.
     Funciona 100% offline con es_core_news_sm.
  2. Pesada (opcional): coreferee o spacy-experimental si están instalados.

Funciones principales:
  resolver_correferencias()   — devuelve cadenas de menciones por texto
  cadena_referencial()        — todas las menciones de una entidad específica
  sustituir_referencias()     — reemplaza pronombres por su antecedente (útil para NER)
  estadisticas_coref()        — densidad referencial del corpus
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable

# ── Pronombres y expresiones referenciales del español (incluyendo formas históricas) ──

_PRONOMBRES_3P = {
    # singular
    "él",
    "ella",
    "ello",
    "lo",
    "la",
    "le",
    "se",
    "su",
    "sus",
    "suyo",
    "suya",
    "suyos",
    "suyas",
    "este",
    "esta",
    "estos",
    "estas",
    "ese",
    "esa",
    "esos",
    "esas",
    "aquel",
    "aquella",
    "aquellos",
    "aquellas",
    # plural
    "ellos",
    "ellas",
    "los",
    "las",
    "les",
    "nos",
    # formas históricas frecuentes en la prensa de los 30
    "dicho",
    "dicha",
    "dichos",
    "dichas",
    "mismo",
    "misma",
    "mismos",
    "mismas",
}

# Expresiones descriptivas que introducen correferencia
_RE_DESC = re.compile(
    r"\b(el\s+(?:señor|doctor|general|presidente|ministro|director|poeta|escritor|"
    r"ilustre|notable|eminente|conocido|distinguido))\b",
    re.IGNORECASE,
)


def _cargar_nlp():
    # ¡Quac!: usar el loader robusto (resuelve el modelo también en el .exe).
    try:
        import os
        import sys

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from spacy_loader import cargar_modelo_es

        return cargar_modelo_es()
    except Exception:
        pass
    import spacy

    for modelo in ("es_core_news_sm", "es_core_news_md", "es_core_news_lg"):
        try:
            return spacy.load(modelo)
        except OSError:
            continue
    raise ImportError("Ningún modelo spaCy español encontrado.")


# ── Estrategia heurística (sin coreferee) ─────────────────────────────────────


def _coref_heuristico(doc) -> list[dict]:
    """
    Cadenas de correferencia por heurísticas:
    - Una entidad PER aparece → los pronombres siguientes hasta la próxima entidad
      PER se asumen referentes a ella.
    - Distancia máxima de 3 oraciones.
    """
    sents = list(doc.sents)
    cadenas: list[dict] = []

    # Recopilar entidades PER con su posición de oración
    ents_per: list[dict] = []
    for i, sent in enumerate(sents):
        for ent in sent.ents:
            if ent.label_ in ("PER", "PERSON"):
                ents_per.append(
                    {
                        "texto": ent.text,
                        "sent_idx": i,
                        "start": ent.start,
                        "end": ent.end,
                        "menciones": [{"texto": ent.text, "tipo": "entidad", "sent_idx": i}],
                    }
                )

    # Para cada entidad, buscar pronombres en las siguientes 3 oraciones
    for ent_info in ents_per:
        i_sent = ent_info["sent_idx"]
        rango_sents = sents[i_sent + 1 : i_sent + 4]

        for j, sent in enumerate(rango_sents, start=1):
            for tok in sent:
                if tok.text.lower() in _PRONOMBRES_3P:
                    ent_info["menciones"].append(
                        {
                            "texto": tok.text,
                            "tipo": "pronombre",
                            "sent_idx": i_sent + j,
                            "oracion": sent.text.strip(),
                        }
                    )

        cadenas.append(
            {
                "entidad_principal": ent_info["texto"],
                "n_menciones": len(ent_info["menciones"]),
                "menciones": ent_info["menciones"],
            }
        )

    return cadenas


def _coref_coreferee(doc) -> list[dict]:
    """Usa coreferee si está disponible (mejor precisión)."""
    try:
        import coreferee  # noqa: F401
    except ImportError:
        return _coref_heuristico(doc)

    # coreferee agrega doc._.coref_chains
    cadenas = []
    try:
        for chain in doc._.coref_chains:
            menciones = []
            for mention in chain:
                toks = [doc[i] for i in mention]
                texto_m = " ".join(t.text for t in toks)
                menciones.append(
                    {
                        "texto": texto_m,
                        "tipo": "entidad" if any(t.ent_type_ for t in toks) else "pronombre",
                    }
                )
            if menciones:
                cadenas.append(
                    {
                        "entidad_principal": menciones[0]["texto"],
                        "n_menciones": len(menciones),
                        "menciones": menciones,
                    }
                )
    except Exception:
        return _coref_heuristico(doc)

    return cadenas


# ── API pública ───────────────────────────────────────────────────────────────


def resolver_correferencias(
    texto: str,
    nlp=None,
    usar_coreferee: bool = True,
) -> list[dict]:
    """
    Resuelve correferencias en un texto.

    Retorna lista de cadenas:
      [{entidad_principal, n_menciones,
        menciones: [{texto, tipo, sent_idx, oracion?}]}]

    usar_coreferee=True intenta usar el paquete coreferee si está instalado;
    si no, cae al método heurístico (siempre disponible).
    """
    if nlp is None:
        nlp = _cargar_nlp()

    if not texto or not texto.strip():
        return []

    doc = nlp(texto[:25000])

    if usar_coreferee:
        return _coref_coreferee(doc)
    return _coref_heuristico(doc)


def cadena_referencial(
    texto: str,
    entidad: str,
    nlp=None,
) -> dict:
    """
    Devuelve todas las menciones de una entidad específica en el texto.

    entidad: nombre o fragmento a buscar (búsqueda insensible a mayúsculas)

    Retorna:
      {entidad, menciones: [{texto, tipo, sent_idx, oracion}], n_menciones}
    """
    cadenas = resolver_correferencias(texto, nlp=nlp)
    entidad_lower = entidad.lower()

    for cadena in cadenas:
        if entidad_lower in cadena["entidad_principal"].lower():
            return cadena

    # Si no hay cadena por coref, buscar menciones directas
    if nlp is None:
        nlp = _cargar_nlp()
    doc = nlp(texto[:25000])

    menciones = []
    for i, sent in enumerate(doc.sents):
        if re.search(re.escape(entidad_lower), sent.text.lower()):
            # Encontrar la mención exacta
            for m in re.finditer(re.escape(entidad_lower), sent.text.lower()):
                menciones.append(
                    {
                        "texto": sent.text[m.start() : m.end()],
                        "tipo": "mención_directa",
                        "sent_idx": i,
                        "oracion": sent.text.strip(),
                    }
                )

    return {
        "entidad": entidad,
        "menciones": menciones,
        "n_menciones": len(menciones),
    }


def sustituir_referencias(
    texto: str,
    nlp=None,
) -> str:
    """
    Sustituye pronombres por el nombre de su antecedente cuando es posible.
    Útil para mejorar NER en textos con muchos pronombres.

    Estrategia: tras una entidad PER, sustituye 'él'/'ella' por el nombre.
    Retorna el texto modificado.
    """
    if nlp is None:
        nlp = _cargar_nlp()

    doc = nlp(texto[:25000])
    tokens_out = []
    ultimo_per = None

    for tok in doc:
        tok_lower = tok.text.lower()
        if tok.ent_type_ in ("PER", "PERSON"):
            ultimo_per = tok.text
            tokens_out.append(tok.text_with_ws)
        elif tok_lower in ("él", "ella") and ultimo_per:
            # Sustituir con el antecedente
            ws = tok.whitespace_
            tokens_out.append(ultimo_per + ws)
        else:
            tokens_out.append(tok.text_with_ws)

    return "".join(tokens_out)


def estadisticas_coref(
    corpus: list[str],
    nlp=None,
    callback: Callable[[int, int], None] | None = None,
) -> dict:
    """
    Calcula estadísticas de correferencia sobre el corpus.

    Retorna:
      {total_cadenas, promedio_menciones_por_cadena,
       entidades_mas_referidas: [{entidad, n_menciones}],
       densidad_referencial: pronombres/tokens}
    """
    if nlp is None:
        nlp = _cargar_nlp()

    total_cadenas = 0
    suma_menciones = 0
    conteo_entidades: dict[str, int] = defaultdict(int)
    total_tokens = 0
    total_pronombres = 0
    total = len(corpus)

    for i, texto in enumerate(corpus):
        if callback:
            callback(i + 1, total)
        if not texto:
            continue

        cadenas = resolver_correferencias(texto, nlp=nlp)
        total_cadenas += len(cadenas)
        for c in cadenas:
            n = c["n_menciones"]
            suma_menciones += n
            conteo_entidades[c["entidad_principal"]] += n

        doc = nlp(texto[:10000])
        for tok in doc:
            total_tokens += 1
            if tok.text.lower() in _PRONOMBRES_3P:
                total_pronombres += 1

    entidades_top = sorted(
        [{"entidad": e, "n_menciones": n} for e, n in conteo_entidades.items()],
        key=lambda x: -x["n_menciones"],
    )[:20]

    return {
        "total_cadenas": total_cadenas,
        "promedio_menciones": round(suma_menciones / total_cadenas, 2) if total_cadenas > 0 else 0,
        "entidades_mas_referidas": entidades_top,
        "densidad_referencial": round(total_pronombres / total_tokens, 4)
        if total_tokens > 0
        else 0,
        "total_pronombres": total_pronombres,
        "total_tokens": total_tokens,
    }

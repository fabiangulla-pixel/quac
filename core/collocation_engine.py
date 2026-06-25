"""core/collocation_engine.py — Collocates y redes léxicas tipo Voyant.

Funciones:
  collocates()       — palabras que co-ocurren con una palabra clave
  red_lexica()       — grafo de asociaciones léxicas (networkx)
  concordancias()    — KWIC (keyword in context)
  frecuencias()      — distribución de frecuencia de términos
  dispersion()       — dónde aparece un término en el corpus (gráfico de dispersión)
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

PARAMS_SCHEMA = {
    "ventana": {
        "type": "int",
        "min": 2,
        "max": 20,
        "step": 1,
        "default": 5,
        "label": "Ventana de collocación",
        "help": "Número de palabras a cada lado de la palabra clave",
    },
    "metrica": {
        "type": "choice",
        "options": ["pmi", "frecuencia", "t_score", "log_likelihood"],
        "default": "pmi",
        "label": "Métrica de asociación",
        "help": "PMI = Pointwise Mutual Information; t-score y log-likelihood son más robustos con corpus pequeños",
    },
    "top_n": {
        "type": "int",
        "min": 5,
        "max": 100,
        "step": 5,
        "default": 20,
        "label": "Top N collocates",
    },
    "min_freq": {
        "type": "int",
        "min": 1,
        "max": 50,
        "step": 1,
        "default": 3,
        "label": "Frecuencia mínima",
        "help": "Ignorar palabras que aparecen menos de N veces en el corpus",
    },
    "usar_stopwords": {
        "type": "bool",
        "default": True,
        "label": "Filtrar stopwords",
    },
    "kwic_contexto": {
        "type": "int",
        "min": 20,
        "max": 200,
        "step": 10,
        "default": 60,
        "label": "Contexto KWIC (chars)",
        "help": "Caracteres a cada lado de la palabra en las concordancias",
    },
}

_RE_TOKEN = re.compile(r"\b[a-záéíóúüñ]{3,}\b", re.IGNORECASE)

STOPWORDS_ES = {
    "que",
    "con",
    "una",
    "del",
    "los",
    "las",
    "por",
    "para",
    "este",
    "esta",
    "ese",
    "esa",
    "son",
    "fue",
    "ser",
    "han",
    "hay",
    "pero",
    "como",
    "más",
    "sus",
    "también",
    "cuando",
    "sobre",
    "entre",
    "desde",
    "hasta",
    "todo",
    "todos",
    "toda",
    "todas",
    "muy",
    "bien",
    "sin",
    "algo",
    "así",
    "mismo",
    "cada",
    "otros",
    "otras",
    "otro",
    "otra",
    "donde",
    "quien",
    "cual",
    "cuyo",
    "cuya",
    "siendo",
    "sido",
    "estar",
    "está",
    "están",
    "tiene",
    "tienen",
    "había",
    "era",
    "eran",
    "aquel",
    "aquella",
    "aquellos",
    "aquellas",
    "nuestro",
    "nuestra",
    "vuestro",
    "menos",
    "durante",
    "después",
    "antes",
    "siempre",
    "nunca",
    "solo",
    "sólo",
    "aunque",
    "porque",
    "pues",
    "aun",
    "mientras",
    "hacia",
    "según",
}


def _tokenizar(texto: str, stopwords: bool = True, lematizar: bool = False, nlp=None) -> list[str]:
    """
    Tokeniza texto. Si lematizar=True y nlp es un modelo spaCy, usa lemas.
    Si lematizar=False (corpus histórico), usa la forma original en minúscula.
    """
    if lematizar and nlp is not None:
        try:
            doc = nlp(texto[:50000])  # límite para velocidad
            tokens = [tok.lemma_.lower() for tok in doc if tok.is_alpha and len(tok) > 1]
        except Exception:
            tokens = _RE_TOKEN.findall(texto.lower())
    else:
        tokens = _RE_TOKEN.findall(texto.lower())
    if stopwords:
        tokens = [t for t in tokens if t not in STOPWORDS_ES]
    return tokens


def collocates(
    corpus: list[str] | str,
    palabra_clave: str,
    ventana: int = 5,
    top_n: int = 30,
    stopwords: bool = True,
) -> list[dict]:
    """
    Calcula collocates de palabra_clave en el corpus.

    corpus: lista de textos o un único texto
    ventana: número de tokens a cada lado de la palabra clave
    top_n: cuántos collocates devolver

    Retorna lista de {palabra, frecuencia, pmi} ordenada por PMI descendente.
    PMI = log2(P(w,k) / P(w)*P(k))  — mide asociación estadística.
    """
    import math

    if isinstance(corpus, str):
        corpus = [corpus]

    clave = palabra_clave.lower().strip()
    freq_coloc: Counter = Counter()
    freq_total: Counter = Counter()
    n_ventanas = 0

    for texto in corpus:
        tokens = _tokenizar(texto, stopwords=False)
        freq_total.update(t for t in tokens if t not in STOPWORDS_ES or not stopwords)
        for i, tok in enumerate(tokens):
            if tok == clave:
                inicio = max(0, i - ventana)
                fin = min(len(tokens), i + ventana + 1)
                vecinos = [tokens[j] for j in range(inicio, fin) if j != i]
                if stopwords:
                    vecinos = [v for v in vecinos if v not in STOPWORDS_ES]
                freq_coloc.update(vecinos)
                n_ventanas += 1

    if n_ventanas == 0:
        return []

    total_tokens = sum(freq_total.values()) or 1
    freq_clave = freq_total.get(clave, 1)

    resultados = []
    for palabra, freq in freq_coloc.most_common(top_n * 3):
        if palabra == clave:
            continue
        freq_w = freq_total.get(palabra, 1)
        p_coloc = freq / n_ventanas
        p_w = freq_w / total_tokens
        p_k = freq_clave / total_tokens
        pmi = math.log2(p_coloc / (p_w * p_k + 1e-10) + 1e-10)
        resultados.append(
            {
                "palabra": palabra,
                "frecuencia": freq,
                "pmi": round(pmi, 3),
            }
        )

    resultados.sort(key=lambda x: x["pmi"], reverse=True)
    return resultados[:top_n]


def red_lexica(
    corpus: list[str] | str,
    palabras_clave: list[str] | None = None,
    ventana: int = 5,
    top_n_nodos: int = 40,
    min_coocurrencias: int = 2,
    stopwords: bool = True,
) -> dict:
    """
    Construye una red léxica de co-ocurrencias.

    Si palabras_clave es None, usa las top_n_nodos palabras más frecuentes.
    Retorna dict con nodos y aristas compatible con networkx y pyvis.
    """
    if isinstance(corpus, str):
        corpus = [corpus]

    freq_total: Counter = Counter()
    cooc: dict[tuple, int] = defaultdict(int)

    for texto in corpus:
        tokens = _tokenizar(texto, stopwords)
        freq_total.update(tokens)
        for i, tok in enumerate(tokens):
            inicio = max(0, i - ventana)
            fin = min(len(tokens), i + ventana + 1)
            for j in range(inicio, fin):
                if j != i:
                    par = tuple(sorted([tok, tokens[j]]))
                    cooc[par] += 1

    # Nodos: palabras clave o las más frecuentes
    if palabras_clave:
        nodos_sel = set(p.lower() for p in palabras_clave)
    else:
        nodos_sel = set(w for w, _ in freq_total.most_common(top_n_nodos))

    nodos = [
        {"id": w, "label": w, "freq": freq_total[w], "size": min(40, 10 + freq_total[w] // 5)}
        for w in nodos_sel
        if w in freq_total
    ]

    aristas = [
        {"source": a, "target": b, "weight": c}
        for (a, b), c in cooc.items()
        if a in nodos_sel and b in nodos_sel and c >= min_coocurrencias
    ]

    return {
        "nodos": nodos,
        "aristas": aristas,
        "total_tokens": sum(freq_total.values()),
        "vocabulario": len(freq_total),
    }


def concordancias(
    corpus: list[str] | str,
    palabra_clave: str,
    ventana_chars: int = 60,
    max_resultados: int = 50,
) -> list[dict]:
    """
    KWIC — Keyword In Context.
    Retorna fragmentos de texto con la palabra clave en el centro.
    """
    if isinstance(corpus, str):
        corpus = [corpus]

    clave = re.escape(palabra_clave.lower())
    patron = re.compile(clave, re.IGNORECASE)
    resultados = []

    for i, texto in enumerate(corpus):
        for m in patron.finditer(texto):
            inicio = max(0, m.start() - ventana_chars)
            fin = min(len(texto), m.end() + ventana_chars)
            izq = texto[inicio : m.start()].replace("\n", " ").strip()
            centro = texto[m.start() : m.end()]
            der = texto[m.end() : fin].replace("\n", " ").strip()
            resultados.append(
                {
                    "doc_idx": i,
                    "izquierda": izq,
                    "kwic": centro,
                    "derecha": der,
                    "posicion": m.start(),
                }
            )
            if len(resultados) >= max_resultados:
                return resultados

    return resultados


def frecuencias(
    corpus: list[str] | str,
    top_n: int = 50,
    stopwords: bool = True,
    por_documento: bool = False,
) -> list[dict] | dict:
    """
    Distribución de frecuencia de términos.

    Si por_documento=True, retorna {doc_idx: [{palabra, freq}]}.
    Si por_documento=False, retorna lista global [{palabra, freq, df}].
    df = document frequency (en cuántos documentos aparece).
    """
    if isinstance(corpus, str):
        corpus = [corpus]

    if por_documento:
        return {
            i: [
                {"palabra": w, "freq": f}
                for w, f in Counter(_tokenizar(t, stopwords)).most_common(top_n)
            ]
            for i, t in enumerate(corpus)
        }

    freq_global: Counter = Counter()
    df: Counter = Counter()

    for texto in corpus:
        tokens = _tokenizar(texto, stopwords)
        freq_global.update(tokens)
        df.update(set(tokens))

    return [{"palabra": w, "freq": f, "df": df[w]} for w, f in freq_global.most_common(top_n)]


def dispersion(
    corpus: list[str],
    palabras: list[str],
) -> dict:
    """
    Calcula dónde aparece cada palabra en el corpus (gráfico de dispersión léxica).
    Útil para ver si un término es ubicuo o aparece solo en ciertos números/páginas.

    Retorna: {palabra: [posición_relativa_0.0-1.0, ...]}
    donde posición_relativa es la posición en el corpus concatenado.
    """
    texto_total = " ".join(corpus)
    total_chars = len(texto_total) or 1
    resultado = {}

    for palabra in palabras:
        patron = re.compile(re.escape(palabra.lower()), re.IGNORECASE)
        posiciones = [m.start() / total_chars for m in patron.finditer(texto_total)]
        resultado[palabra] = posiciones

    return resultado


def ngramas(
    corpus: list[str] | str,
    n: int = 2,
    top_n: int = 30,
    stopwords: bool = False,
    min_freq: int = 2,
) -> list[dict]:
    """
    Extrae los n-gramas más frecuentes del corpus.

    n=2 → bigramas, n=3 → trigramas.
    Por defecto NO filtra stopwords (los n-gramas más útiles suelen incluirlas).

    Retorna lista de {ngrama: str, frecuencia: int}.
    """
    if isinstance(corpus, str):
        corpus = [corpus]

    contador: Counter = Counter()
    for texto in corpus:
        tokens = _tokenizar(texto, stopwords=stopwords)
        for i in range(len(tokens) - n + 1):
            ngrama = " ".join(tokens[i : i + n])
            contador[ngrama] += 1

    return [
        {"ngrama": ng, "frecuencia": f} for ng, f in contador.most_common(top_n) if f >= min_freq
    ]


def stopwords_personalizadas(
    stopwords_extra: list[str],
) -> frozenset:
    """
    Combina STOPWORDS_ES con stopwords adicionales del investigador.
    Retorna un frozenset listo para pasar a _tokenizar().
    """
    return frozenset(STOPWORDS_ES | {w.lower() for w in stopwords_extra})

"""core/topic_engine.py — Topic modeling del corpus con BERTopic.

Detecta temas recurrentes en el corpus y su distribución temporal.
Dos backends:
  - BERTopic (requiere sentence-transformers): alta calidad semántica
  - sklearn NMF (fallback, siempre disponible): más rápido, sin GPU

Retorna tópicos etiquetados por Claude si hay API key disponible.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

PARAMS_SCHEMA = {
    "backend": {
        "type": "choice",
        "options": ["bertopic", "nmf", "lda"],
        "default": "nmf",
        "label": "Algoritmo",
        "help": "BERTopic = semántico (requiere sentence-transformers); NMF y LDA = matriciales, siempre disponibles",
    },
    "n_topics": {
        "type": "int",
        "min": 2,
        "max": 30,
        "step": 1,
        "default": 8,
        "label": "Número de tópicos",
        "help": "Para BERTopic usa -1 para detectar automáticamente",
    },
    "palabras_por_topic": {
        "type": "int",
        "min": 5,
        "max": 30,
        "step": 1,
        "default": 10,
        "label": "Palabras por tópico",
    },
    "etiquetar_ia": {
        "type": "bool",
        "default": False,
        "label": "Etiquetar tópicos con IA",
        "help": "Pide al modelo de IA un nombre descriptivo para cada tópico",
    },
    "min_df": {
        "type": "int",
        "min": 1,
        "max": 20,
        "step": 1,
        "default": 2,
        "label": "Min. documentos por término",
        "help": "Ignora términos que aparecen en menos de N documentos",
    },
    "max_df": {
        "type": "float",
        "min": 0.5,
        "max": 1.0,
        "step": 0.05,
        "default": 0.95,
        "label": "Max. proporción documentos",
        "help": "Ignora términos que aparecen en más del X% de documentos (demasiado genéricos)",
    },
}

# ── Constantes ────────────────────────────────────────────────────────────────
_STOPWORDS_ES = {
    "que",
    "de",
    "la",
    "el",
    "en",
    "y",
    "a",
    "los",
    "las",
    "un",
    "una",
    "es",
    "por",
    "con",
    "del",
    "se",
    "le",
    "su",
    "al",
    "no",
    "lo",
    "más",
    "pero",
    "este",
    "esta",
    "ha",
    "para",
    "como",
    "sus",
    "muy",
    "también",
    "fue",
    "ser",
    "está",
    "son",
    "si",
    "ya",
    "todo",
    "hay",
    "sin",
    "sobre",
    "entre",
    "cuando",
    "gran",
    "hasta",
    "donde",
    "bien",
    "así",
    "porque",
    "después",
    "mismo",
    "cada",
    "vez",
    "tan",
    "dos",
    "antes",
    "años",
    "año",
    "Colombia",
    "colombiano",
    "colombiana",
    "revista",
    "estampa",
}

_PROMPT_ETIQUETAR = """\
Eres un historiador especializado en cultura colombiana 1930-1940.

Los siguientes son tópicos extraídos automáticamente de la revista *Estampa*.
Cada tópico se define por sus palabras más representativas.

Para cada tópico, proporciona:
1. Un nombre corto (2-4 palabras) que capture la esencia temática
2. Una descripción de una oración

Responde ÚNICAMENTE con JSON válido:
{
  "topicos": [
    {"id": 0, "nombre": "...", "descripcion": "..."},
    ...
  ]
}

Tópicos:
{topicos}
"""


# ── Preprocesamiento ─────────────────────────────────────────────────────────


def _limpiar_texto(texto: str) -> str:
    texto = re.sub(r"[^\w\sáéíóúñüÁÉÍÓÚÑÜ]", " ", texto.lower())
    tokens = [t for t in texto.split() if len(t) > 3 and t not in _STOPWORDS_ES]
    return " ".join(tokens)


# ── Backend 1: BERTopic ──────────────────────────────────────────────────────


def _modelar_bertopic(
    textos: list[str],
    n_topicos: int = 10,
    callback: Callable[[str], None] | None = None,
) -> dict:
    def log(m):
        if callback:
            callback(m)

    try:
        from bertopic import BERTopic
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError(
            "BERTopic no disponible. "
            "Instala: pip install bertopic>=0.16.0 sentence-transformers>=2.7.0"
        )

    log("Cargando modelo de embeddings (paraphrase-multilingual-MiniLM-L12-v2)…")
    embed_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

    log(f"Entrenando BERTopic con {len(textos)} documentos…")
    topic_model = BERTopic(
        embedding_model=embed_model,
        nr_topics=n_topicos,
        language="multilingual",
        verbose=False,
    )
    topics, probs = topic_model.fit_transform(textos)

    topicos_info = topic_model.get_topic_info()
    topicos_dict = {}
    for _, row in topicos_info.iterrows():
        tid = int(row["Topic"])
        if tid == -1:
            continue
        palabras_raw = topic_model.get_topic(tid)
        palabras = [w for w, _ in palabras_raw[:10]] if palabras_raw else []
        topicos_dict[str(tid)] = {
            "palabras": palabras,
            "n_docs": int(row["Count"]),
            "nombre": f"Tópico {tid}",
        }

    distribucion = {str(i): int(t) for i, t in enumerate(topics)}
    log(f"BERTopic: {len(topicos_dict)} tópicos detectados")

    return {
        "backend": "bertopic",
        "topicos": topicos_dict,
        "distribucion": distribucion,
    }


# ── Backend 2: NMF sklearn (fallback) ────────────────────────────────────────


def _modelar_nmf(
    textos: list[str],
    n_topicos: int = 10,
    callback: Callable[[str], None] | None = None,
    min_df: int = 2,
    max_df: float = 0.95,
    n_palabras: int = 10,
) -> dict:
    def log(m):
        if callback:
            callback(m)

    from sklearn.decomposition import NMF
    from sklearn.feature_extraction.text import TfidfVectorizer

    log(f"Vectorizando {len(textos)} documentos…")
    textos_limpios = [_limpiar_texto(t) for t in textos]
    textos_limpios = [t if t.strip() else "sin texto" for t in textos_limpios]

    vec = TfidfVectorizer(max_features=5000, max_df=max_df, min_df=min_df)
    X = vec.fit_transform(textos_limpios)
    vocab = vec.get_feature_names_out()

    n_real = min(n_topicos, X.shape[0], X.shape[1])
    log(f"NMF con {n_real} tópicos…")
    nmf = NMF(n_components=n_real, random_state=42, max_iter=300)
    W = nmf.fit_transform(X)

    topicos_dict = {}
    for tid in range(n_real):
        indices = nmf.components_[tid].argsort()[-n_palabras:][::-1]
        palabras = [str(vocab[i]) for i in indices]
        topicos_dict[str(tid)] = {
            "palabras": palabras,
            "n_docs": int((W[:, tid] > 0.01).sum()),
            "nombre": f"Tópico {tid}",
        }

    doc_topicos = W.argmax(axis=1)
    distribucion = {str(i): int(t) for i, t in enumerate(doc_topicos)}
    log(f"NMF: {n_real} tópicos detectados")

    return {
        "backend": "nmf",
        "topicos": topicos_dict,
        "distribucion": distribucion,
    }


# ── Etiquetado con Claude ────────────────────────────────────────────────────


def etiquetar_topicos_llm(resultado: dict, api_key: str) -> dict:
    """
    Usa Claude para dar nombres descriptivos a los tópicos detectados.
    Modifica resultado["topicos"] en lugar y lo retorna.
    """
    try:
        import anthropic
    except ImportError:
        return resultado

    topicos = resultado.get("topicos", {})
    if not topicos:
        return resultado

    topicos_str = "\n".join(
        f"Tópico {tid}: {', '.join(info['palabras'][:8])}" for tid, info in topicos.items()
    )

    client = anthropic.Anthropic(api_key=api_key)
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            messages=[
                {"role": "user", "content": _PROMPT_ETIQUETAR.replace("{topicos}", topicos_str)}
            ],
        )
        raw = msg.content[0].text.strip()
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        etiquetas = json.loads(raw)
        for item in etiquetas.get("topicos", []):
            tid = str(item.get("id", ""))
            if tid in resultado["topicos"]:
                resultado["topicos"][tid]["nombre"] = item.get("nombre", f"Tópico {tid}")
                resultado["topicos"][tid]["descripcion"] = item.get("descripcion", "")
    except Exception:
        pass

    return resultado


# ── Función principal ────────────────────────────────────────────────────────


def modelar_topicos(
    textos: list[str],
    n_topicos: int = 10,
    api_key: str | None = None,
    usar_bertopic: bool = True,
    callback: Callable[[str], None] | None = None,
    min_df: int = 2,
    max_df: float = 0.95,
    n_palabras: int = 10,
) -> dict:
    """
    Detecta tópicos en el corpus.

    textos:         lista de textos de artículos
    n_topicos:      número de tópicos objetivo
    api_key:        si se provee, etiqueta los tópicos con Claude
    usar_bertopic:  intenta BERTopic primero; cae a NMF si no está instalado

    Retorna dict con: backend, topicos {id: {palabras, n_docs, nombre}},
                      distribucion {doc_idx: topico_id}
    """

    def log(m):
        if callback:
            callback(m)

    textos_validos = [t for t in textos if t and t.strip()]
    if not textos_validos:
        return {"backend": "vacio", "topicos": {}, "distribucion": {}}

    if usar_bertopic:
        try:
            resultado = _modelar_bertopic(textos_validos, n_topicos, callback)
        except ImportError as e:
            log(f"BERTopic no disponible ({e}), usando NMF…")
            resultado = _modelar_nmf(
                textos_validos,
                n_topicos,
                callback,
                min_df=min_df,
                max_df=max_df,
                n_palabras=n_palabras,
            )
    else:
        resultado = _modelar_nmf(
            textos_validos, n_topicos, callback, min_df=min_df, max_df=max_df, n_palabras=n_palabras
        )

    if api_key:
        log("Etiquetando tópicos con Claude…")
        resultado = etiquetar_topicos_llm(resultado, api_key)

    log(f"Topic modeling completado: {len(resultado['topicos'])} tópicos")
    return resultado


# ── Estadísticas de distribución ─────────────────────────────────────────────


def estadisticas_topicos(resultado: dict) -> dict:
    """
    Calcula estadísticas de distribución de tópicos.
    """
    from collections import Counter

    dist = resultado.get("distribucion", {})
    topicos = resultado.get("topicos", {})

    conteo = Counter(dist.values())
    total = len(dist)

    stats = {}
    for tid, info in topicos.items():
        n = conteo.get(int(tid), 0)
        stats[tid] = {
            "nombre": info.get("nombre", f"Tópico {tid}"),
            "n_docs": n,
            "porcentaje": round(100 * n / total, 1) if total > 0 else 0,
            "palabras_clave": info.get("palabras", [])[:5],
        }
    return {"total_docs": total, "topicos": stats}


def exportar_topicos_csv(resultado: dict, ruta: Path) -> int:
    """Exporta distribución de tópicos a CSV."""
    import csv

    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    topicos = resultado.get("topicos", {})
    distribucion = resultado.get("distribucion", {})

    filas = []
    for doc_idx, tid in distribucion.items():
        info = topicos.get(str(tid), {})
        filas.append(
            {
                "articulo_idx": doc_idx,
                "topico_id": tid,
                "topico_nombre": info.get("nombre", f"Tópico {tid}"),
                "palabras_clave": ", ".join(info.get("palabras", [])[:5]),
            }
        )

    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(
            f, fieldnames=["articulo_idx", "topico_id", "topico_nombre", "palabras_clave"]
        )
        w.writeheader()
        w.writerows(filas)
    return len(filas)

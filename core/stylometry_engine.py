"""core/stylometry_engine.py — Estilometría para atribución de autoría.

Usa TF-IDF de n-gramas de caracteres para crear perfiles estilísticos.
Permite detectar artículos de autoría anónima con estilo similar a artículos firmados.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


def _vectorizar(textos: list[str], ngram_range=(2, 4), max_features=3000):
    """Vectoriza textos con TF-IDF de n-gramas de caracteres."""
    from sklearn.feature_extraction.text import TfidfVectorizer

    vec = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=ngram_range,
        max_features=max_features,
        sublinear_tf=True,
    )
    X = vec.fit_transform(textos)
    return X, vec


def perfil_autor(textos_autor: list[str]) -> dict:
    """
    Crea un perfil estilométrico para un autor dado sus textos.
    Retorna dict con vectorizador y vector promedio.
    """
    import numpy as np

    if not textos_autor:
        return {}
    X, vec = _vectorizar(textos_autor)
    perfil = {
        "vector_medio": np.asarray(X.mean(axis=0)).flatten(),
        "vocabulario": vec.vocabulary_,
        "n_textos": len(textos_autor),
    }
    return perfil


def similitud_coseno(v1, v2) -> float:
    """Similitud coseno entre dos vectores numpy."""
    import numpy as np

    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (n1 * n2))


def atribuir_autoria(
    textos_firmados: dict[str, list[str]],
    textos_anonimos: dict[str, str],
    top_n: int = 3,
    callback: Callable[[str], None] | None = None,
) -> dict:
    """
    Atribuye textos anónimos a posibles autores por similitud estilométrica.

    textos_firmados: {nombre_autor: [texto1, texto2, ...]}
    textos_anonimos: {art_id: texto}
    top_n: número de candidatos a retornar por artículo

    Retorna: {art_id: [{"autor": ..., "similitud": ...}]}
    """
    import numpy as np

    if not textos_firmados or not textos_anonimos:
        return {}

    def log(m):
        if callback:
            callback(m)

    # Construir corpus global para vectorizador consistente
    all_textos = []
    autor_indices: dict[str, list[int]] = {}
    for autor, textos in textos_firmados.items():
        autor_indices[autor] = list(range(len(all_textos), len(all_textos) + len(textos)))
        all_textos.extend(textos)

    anon_start = len(all_textos)
    anon_ids = list(textos_anonimos.keys())
    all_textos.extend(textos_anonimos.values())

    log(f"Vectorizando {len(all_textos)} textos…")
    try:
        X, _ = _vectorizar(all_textos)
    except Exception as e:
        log(f"Error vectorizando: {e}")
        return {}

    # Perfiles por autor
    perfiles = {}
    for autor, indices in autor_indices.items():
        vecs = np.asarray(X[indices].mean(axis=0)).flatten()
        perfiles[autor] = vecs

    # Atribución
    resultados = {}
    for i, art_id in enumerate(anon_ids):
        # X es matriz sparse: convertir la fila a vector denso 1-D
        v_anon = X[anon_start + i].toarray().ravel()
        scores = []
        for autor, v_autor in perfiles.items():
            sim = similitud_coseno(v_anon, v_autor)
            scores.append({"autor": autor, "similitud": round(sim, 4)})
        scores.sort(key=lambda x: x["similitud"], reverse=True)
        resultados[art_id] = scores[:top_n]

    return resultados


def exportar_estilometria_csv(resultados: dict, ruta: Path) -> int:
    """Exporta resultados de atribución a CSV."""
    import csv

    ruta = Path(ruta)
    filas = []
    for art_id, candidatos in resultados.items():
        for rk, c in enumerate(candidatos, 1):
            filas.append(
                {
                    "articulo": art_id,
                    "rango": rk,
                    "autor_candidato": c["autor"],
                    "similitud": c["similitud"],
                }
            )
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["articulo", "rango", "autor_candidato", "similitud"])
        w.writeheader()
        w.writerows(filas)
    return len(filas)


def cluster_tematico(
    textos: dict[str, str],
    n_clusters: int = 5,
    callback: Callable[[str], None] | None = None,
) -> dict:
    """
    Agrupa artículos por similitud estilométrica usando K-Means.
    Útil para detectar secciones temáticas sin etiqueta.

    textos: {art_id: texto}
    Retorna: {art_id: cluster_id}
    """
    from sklearn.cluster import KMeans

    def log(m):
        if callback:
            callback(m)

    if len(textos) < n_clusters:
        n_clusters = max(2, len(textos))

    ids = list(textos.keys())
    corpus = list(textos.values())
    log(f"Vectorizando {len(corpus)} textos para clustering…")

    try:
        X, _ = _vectorizar(corpus)
    except Exception as e:
        log(f"Error: {e}")
        return {}

    log(f"K-Means con {n_clusters} clusters…")
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = km.fit_predict(X)
    return {art_id: int(label) for art_id, label in zip(ids, labels)}

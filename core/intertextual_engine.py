"""core/intertextual_engine.py — Detección de intertextualidad en el corpus Estampa.

Detecta:
  - Citas explícitas (frases entre comillas que se repiten en el corpus)
  - Similitud textual entre artículos (TF-IDF coseno)
  - Alusiones a textos canónicos (personajes históricos conocidos)
  - Clusters temáticos de artículos relacionados
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

# ── Extracción de citas ───────────────────────────────────────────────────────


def extraer_citas(texto: str, min_palabras: int = 5) -> list[str]:
    """Extrae fragmentos entre comillas (latinas o inglesas) de longitud mínima."""
    patrones = [
        r"«([^»]{20,500})»",
        r'"([^"]{20,500})"',
        r'"([^"]{20,500})"',
        r"'([^']{20,500})'",
    ]
    citas = []
    for pat in patrones:
        for m in re.finditer(pat, texto):
            cita = m.group(1).strip()
            if len(cita.split()) >= min_palabras:
                citas.append(cita)
    return citas


def detectar_citas_compartidas(
    articulos: dict[str, dict], min_citas: int = 2, callback: Callable | None = None
) -> dict:
    """
    Detecta citas que aparecen en múltiples artículos.
    articulos: {art_id: {"texto_limpio": str, ...}}
    Retorna: {cita: [art_ids]}
    """
    citas_por_articulo: dict[str, list[str]] = {}
    for art_id, art in articulos.items():
        texto = art.get("texto_limpio") or art.get("texto_ocr") or ""
        citas_por_articulo[art_id] = extraer_citas(texto)
        if callback:
            callback(f"Extrayendo citas: {art_id}")

    # Invertir: cita → artículos
    mapa: dict[str, list[str]] = defaultdict(list)
    for art_id, citas in citas_por_articulo.items():
        for cita in citas:
            mapa[cita].append(art_id)

    compartidas = {c: arts for c, arts in mapa.items() if len(arts) >= min_citas}
    return dict(sorted(compartidas.items(), key=lambda x: -len(x[1])))


# ── Similitud textual (TF-IDF coseno) ────────────────────────────────────────


def calcular_similitud_corpus(
    articulos: dict[str, dict],
    umbral: float = 0.25,
    max_pares: int = 50,
    callback: Callable | None = None,
) -> list[dict]:
    """
    Calcula similitud coseno TF-IDF entre todos los pares de artículos.
    Retorna lista de pares con similitud > umbral, ordenada desc.
    """
    try:
        import numpy as np
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:
        raise ImportError("Instala scikit-learn: pip install scikit-learn")

    ids = list(articulos.keys())
    textos = [articulos[a].get("texto_limpio") or articulos[a].get("texto_ocr") or " " for a in ids]

    if callback:
        callback("Calculando TF-IDF...")

    vec = TfidfVectorizer(
        max_features=5000,
        ngram_range=(1, 2),
        sublinear_tf=True,
        min_df=2,
    )
    try:
        matriz = vec.fit_transform(textos)
    except ValueError:
        return []

    if callback:
        callback("Calculando similitud coseno...")

    sim = cosine_similarity(matriz)
    np.fill_diagonal(sim, 0)

    pares = []
    n = len(ids)
    for i in range(n):
        for j in range(i + 1, n):
            s = float(sim[i, j])
            if s >= umbral:
                pares.append(
                    {
                        "art_a": ids[i],
                        "art_b": ids[j],
                        "similitud": round(s, 4),
                    }
                )

    pares.sort(key=lambda x: -x["similitud"])
    return pares[:max_pares]


# ── Detección con LLM ─────────────────────────────────────────────────────────


def detectar_intertextualidad_llm(
    texto_a: str,
    texto_b: str,
    titulo_a: str,
    titulo_b: str,
    api_key: str,
    modelo: str = "claude-haiku-4-5-20251001",
) -> dict:
    """
    Usa Claude para identificar conexiones intertextuales entre dos artículos.
    Retorna: {tipo, descripcion, fragmento_a, fragmento_b, confianza}
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError("Instala anthropic: pip install anthropic")

    cliente = anthropic.Anthropic(api_key=api_key)

    # Truncar a ~800 palabras cada uno
    def _truncar(t: str, n: int = 800) -> str:
        words = t.split()
        return " ".join(words[:n]) + ("..." if len(words) > n else "")

    prompt = f"""Analiza si existe intertextualidad entre estos dos artículos de la revista Estampa (Colombia, 1930-1940).

ARTÍCULO A — {titulo_a}:
{_truncar(texto_a)}

ARTÍCULO B — {titulo_b}:
{_truncar(texto_b)}

Identifica si hay:
1. Cita directa (uno cita al otro)
2. Alusión temática (tratan el mismo tema con léxico similar)
3. Respuesta/réplica (uno responde argumentativamente al otro)
4. Sin conexión intertextual significativa

Responde SOLO con JSON:
{{
  "tipo": "cita_directa|alusión_tematica|respuesta|sin_conexion",
  "descripcion": "explicación breve en español",
  "fragmento_a": "fragmento relevante de A (o vacío)",
  "fragmento_b": "fragmento relevante de B (o vacío)",
  "confianza": 0.0-1.0
}}"""

    try:
        rsp = cliente.messages.create(
            model=modelo,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        import json

        texto = rsp.content[0].text.strip()
        m = re.search(r"\{.*\}", texto, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception:
        pass

    return {
        "tipo": "sin_conexion",
        "descripcion": "Error al analizar",
        "fragmento_a": "",
        "fragmento_b": "",
        "confianza": 0.0,
    }


# ── Pipeline completo ─────────────────────────────────────────────────────────


def analizar_intertextualidad(
    articulos: dict[str, dict],
    api_key: str = "",
    umbral_similitud: float = 0.3,
    usar_llm: bool = True,
    max_pares_llm: int = 10,
    callback: Callable | None = None,
) -> dict:
    """
    Pipeline completo de detección intertextual.
    Retorna: {citas_compartidas, pares_similares, conexiones_llm}
    """

    def _log(msg: str):
        if callback:
            callback(msg)

    _log("Detectando citas compartidas...")
    citas = detectar_citas_compartidas(articulos, callback=callback)

    _log("Calculando similitud TF-IDF...")
    try:
        pares = calcular_similitud_corpus(articulos, umbral=umbral_similitud, callback=callback)
    except Exception as e:
        _log(f"  Error similitud: {e}")
        pares = []

    conexiones_llm = []
    if usar_llm and api_key and pares:
        _log(f"Analizando {min(max_pares_llm, len(pares))} pares con LLM...")
        for par in pares[:max_pares_llm]:
            art_a = articulos.get(par["art_a"], {})
            art_b = articulos.get(par["art_b"], {})
            texto_a = art_a.get("texto_limpio") or art_a.get("texto_ocr") or ""
            texto_b = art_b.get("texto_limpio") or art_b.get("texto_ocr") or ""
            titulo_a = art_a.get("titulo") or par["art_a"]
            titulo_b = art_b.get("titulo") or par["art_b"]

            _log(f"  LLM: {titulo_a[:30]} ↔ {titulo_b[:30]}")
            conn = detectar_intertextualidad_llm(texto_a, texto_b, titulo_a, titulo_b, api_key)
            if conn.get("tipo") != "sin_conexion":
                conexiones_llm.append({**par, **conn})

    _log(
        f"Listo. {len(citas)} citas compartidas, {len(pares)} pares similares, {len(conexiones_llm)} conexiones LLM."
    )
    return {
        "citas_compartidas": citas,
        "pares_similares": pares,
        "conexiones_llm": conexiones_llm,
    }


def exportar_grafo_intertextual(resultado: dict, ruta: Path) -> Path:
    """Genera HTML interactivo con red de intertextualidad (pyvis)."""
    try:
        from pyvis.network import Network
    except ImportError:
        raise ImportError("Instala pyvis: pip install pyvis")

    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    net = Network(height="600px", width="100%", bgcolor="#0f0f23", font_color="#e0e0e0")
    net.set_options("""
    {
      "physics": {"stabilization": {"iterations": 100}},
      "edges": {"smooth": {"type": "dynamic"}},
      "interaction": {"hover": true}
    }
    """)

    nodos_vistos = set()

    def _agregar_nodo(nid: str):
        if nid not in nodos_vistos:
            net.add_node(nid, label=nid[:30], title=nid, color="#7c3aed")
            nodos_vistos.add(nid)

    for par in resultado.get("pares_similares", []):
        _agregar_nodo(par["art_a"])
        _agregar_nodo(par["art_b"])
        net.add_edge(
            par["art_a"],
            par["art_b"],
            value=par["similitud"],
            title=f"Similitud: {par['similitud']:.2%}",
            color="#a78bfa",
        )

    for conn in resultado.get("conexiones_llm", []):
        _agregar_nodo(conn["art_a"])
        _agregar_nodo(conn["art_b"])
        colores = {
            "cita_directa": "#f59e0b",
            "alusión_tematica": "#10b981",
            "respuesta": "#ef4444",
        }
        color = colores.get(conn.get("tipo", ""), "#94a3b8")
        net.add_edge(
            conn["art_a"],
            conn["art_b"],
            title=conn.get("descripcion", ""),
            color=color,
        )

    net.save_graph(str(ruta))
    return ruta

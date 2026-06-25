"""core/network_engine.py — Redes de co-ocurrencia de entidades NER.

Construye grafos networkx a partir del índice NER global. Exporta:
  - HTML interactivo (pyvis) para visualización en navegador
  - GEXF (Gephi) para análisis avanzado
  - Métricas de red: densidad, centralidad, comunidades Louvain
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

# ── Categorías disponibles ──────────────────────────────────────────────────
CATEGORIAS_DISPONIBLES = (
    "personas",
    "lugares",
    "organizaciones",
    "fechas",
    "obras_publicaciones",
    "eventos_historicos",
)

_COLOR_CAT = {
    "personas": "#E74C3C",
    "lugares": "#27AE60",
    "organizaciones": "#2980B9",
    "fechas": "#F39C12",
    "obras_publicaciones": "#8E44AD",
    "eventos_historicos": "#16A085",
}


# ── Construcción del grafo ──────────────────────────────────────────────────


def construir_grafo(
    indice_global: dict,
    categorias: list | None = None,
    peso_minimo: int = 2,
    max_nodos: int = 300,
    callback: Callable[[str], None] | None = None,
):
    """
    Construye grafo de co-ocurrencia a partir del índice NER global.

    indice_global: {categoria: {entidad: [art_ids]}}
    categorias:    lista de categorías a incluir (None = todas)
    peso_minimo:   número mínimo de artículos compartidos para crear arista
    max_nodos:     limita nodos para grafos muy grandes

    Retorna: networkx.Graph con atributos de nodo (categoria, color, freq)
    """
    try:
        import networkx as nx
    except ImportError:
        raise ImportError("Instala networkx: pip install networkx>=3.2.0")

    def log(msg):
        if callback:
            callback(msg)

    if categorias is None:
        categorias = list(CATEGORIAS_DISPONIBLES)

    G = nx.Graph()

    # Paso 1: construir mapa artículo → entidades
    log("Indexando entidades por artículo…")
    art_entidades: dict[str, list[str]] = {}

    for cat in categorias:
        if cat not in indice_global:
            continue
        if not isinstance(indice_global[cat], dict):
            continue
        for ent, arts in indice_global[cat].items():
            for art in arts:
                if art not in art_entidades:
                    art_entidades[art] = []
                art_entidades[art].append(ent)
            # Agregar nodo con metadatos
            if not G.has_node(ent):
                G.add_node(ent, categoria=cat, color=_COLOR_CAT.get(cat, "#95A5A6"), freq=len(arts))

    log(f"Nodos candidatos: {G.number_of_nodes()}")

    # Paso 2: co-ocurrencia → aristas ponderadas
    log("Calculando co-ocurrencias…")
    from collections import Counter

    pesos: Counter = Counter()

    for art_id, ents in art_entidades.items():
        ents_unicas = list(set(ents))
        for i in range(len(ents_unicas)):
            for j in range(i + 1, len(ents_unicas)):
                a, b = sorted([ents_unicas[i], ents_unicas[j]])
                if G.has_node(a) and G.has_node(b):
                    pesos[(a, b)] += 1

    # Paso 3: agregar aristas con peso mínimo
    aristas_agregadas = 0
    for (a, b), peso in pesos.items():
        if peso >= peso_minimo:
            G.add_edge(a, b, weight=peso)
            aristas_agregadas += 1

    log(f"Aristas con peso >= {peso_minimo}: {aristas_agregadas}")

    # Paso 4: eliminar nodos aislados (sin aristas)
    nodos_aislados = [n for n in list(G.nodes) if G.degree(n) == 0]
    G.remove_nodes_from(nodos_aislados)

    # Paso 5: limitar tamaño por frecuencia si es muy grande
    if G.number_of_nodes() > max_nodos:
        log(f"Grafo muy grande ({G.number_of_nodes()} nodos), limitando a {max_nodos}…")
        nodos_ord = sorted(G.nodes(data=True), key=lambda x: x[1].get("freq", 0), reverse=True)
        conservar = {n for n, _ in nodos_ord[:max_nodos]}
        eliminar = [n for n in G.nodes if n not in conservar]
        G.remove_nodes_from(eliminar)

    log(f"Grafo final: {G.number_of_nodes()} nodos, {G.number_of_edges()} aristas")
    return G


# ── Métricas de red ─────────────────────────────────────────────────────────


def metricas_red(G) -> dict:
    """
    Calcula métricas de red sobre el grafo G.
    Retorna dict con: densidad, componentes, nodos, aristas,
                      top_centralidad, comunidades (si louvain disponible).
    """
    import networkx as nx

    if G.number_of_nodes() == 0:
        return {"error": "Grafo vacío"}

    metricas = {
        "nodos": G.number_of_nodes(),
        "aristas": G.number_of_edges(),
        "densidad": round(nx.density(G), 4),
        "componentes_conexas": nx.number_connected_components(G),
    }

    # Centralidad de grado (rápida, funciona en grafos grandes)
    try:
        centralidad = nx.degree_centrality(G)
        top10 = sorted(centralidad.items(), key=lambda x: x[1], reverse=True)[:10]
        metricas["top_centralidad"] = [(n, round(v, 4)) for n, v in top10]
    except Exception:
        metricas["top_centralidad"] = []

    # Comunidades Louvain (opcional)
    try:
        import community as community_louvain

        partition = community_louvain.best_partition(G)
        n_comunidades = len(set(partition.values()))
        metricas["comunidades_louvain"] = n_comunidades
        # Agregar comunidad como atributo de nodo
        nx.set_node_attributes(G, partition, "comunidad")
    except ImportError:
        metricas["comunidades_louvain"] = None

    # Modularidad si hay comunidades
    try:
        if metricas.get("comunidades_louvain"):
            import community as cl
            from networkx.algorithms.community import modularity

            partition = cl.best_partition(G)
            comunidades_nx = {}
            for node, com in partition.items():
                comunidades_nx.setdefault(com, set()).add(node)
            mod = modularity(G, list(comunidades_nx.values()))
            metricas["modularidad"] = round(mod, 4)
    except Exception:
        pass

    return metricas


def metricas_avanzadas(G) -> dict:
    """
    Calcula métricas de centralidad avanzadas: betweenness, PageRank, closeness.
    Más costosas computacionalmente — se calculan bajo demanda.

    Retorna dict con listas de (nodo, valor) ordenadas descendentemente.
    """
    import networkx as nx

    if G.number_of_nodes() == 0:
        return {}

    resultado = {}

    # Betweenness centrality — nodos "puente" entre grupos
    try:
        bc = nx.betweenness_centrality(G, weight="weight", normalized=True)
        resultado["betweenness"] = sorted(bc.items(), key=lambda x: -x[1])
        nx.set_node_attributes(G, bc, "betweenness")
    except Exception:
        resultado["betweenness"] = []

    # PageRank — nodos influyentes por sus conexiones con otros influyentes
    try:
        pr = nx.pagerank(G, weight="weight")
        resultado["pagerank"] = sorted(pr.items(), key=lambda x: -x[1])
        nx.set_node_attributes(G, pr, "pagerank")
    except Exception:
        resultado["pagerank"] = []

    # Closeness centrality — nodos más cercanos al resto de la red
    try:
        cc = nx.closeness_centrality(G)
        resultado["closeness"] = sorted(cc.items(), key=lambda x: -x[1])
        nx.set_node_attributes(G, cc, "closeness")
    except Exception:
        resultado["closeness"] = []

    # Tabla de comunidades: {comunidad_id: [nodos]}
    try:
        partition = nx.get_node_attributes(G, "comunidad")
        if partition:
            comunidades: dict = {}
            for nodo, com_id in partition.items():
                comunidades.setdefault(com_id, []).append(nodo)
            # Ordenar por tamaño descendente
            resultado["comunidades"] = sorted(comunidades.items(), key=lambda x: -len(x[1]))
        else:
            resultado["comunidades"] = []
    except Exception:
        resultado["comunidades"] = []

    return resultado


def evolucion_temporal(
    indice_por_numero: dict,
    categorias: list = None,
    peso_minimo: int = 1,
    callback=None,
) -> list[dict]:
    """
    Calcula métricas de red para cada número del corpus y retorna la serie temporal.

    indice_por_numero: {numero: {cat: {entidad: [art_ids]}}}
    Retorna lista de dicts: [{numero, nodos, aristas, densidad, top_nodo, top_cent}]
    """
    if categorias is None:
        categorias = list(CATEGORIAS_DISPONIBLES)

    serie = []
    numeros = sorted(indice_por_numero.keys())

    for i, numero in enumerate(numeros):
        if callback:
            callback(i + 1, len(numeros), numero)
        indice = indice_por_numero[numero]
        try:
            G = construir_grafo(indice, categorias=categorias, peso_minimo=peso_minimo)
            import networkx as nx

            met = {
                "numero": numero,
                "nodos": G.number_of_nodes(),
                "aristas": G.number_of_edges(),
                "densidad": round(nx.density(G), 4) if G.number_of_nodes() > 1 else 0,
            }
            # Nodo más central por grado
            if G.number_of_nodes() > 0:
                top = max(nx.degree_centrality(G).items(), key=lambda x: x[1])
                met["top_nodo"] = top[0]
                met["top_cent"] = round(top[1], 4)
            else:
                met["top_nodo"] = ""
                met["top_cent"] = 0.0
            serie.append(met)
        except Exception:
            serie.append(
                {
                    "numero": numero,
                    "nodos": 0,
                    "aristas": 0,
                    "densidad": 0,
                    "top_nodo": "",
                    "top_cent": 0,
                }
            )

    return serie


def exportar_metricas_csv(G, metricas_av: dict, ruta: Path) -> Path:
    """Exporta métricas de nodo (grado, betweenness, pagerank, closeness, comunidad) a CSV."""
    import csv

    import networkx as nx

    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    grado = dict(G.degree())
    bc = dict(metricas_av.get("betweenness", []))
    pr = dict(metricas_av.get("pagerank", []))
    cl = dict(metricas_av.get("closeness", []))
    com = nx.get_node_attributes(G, "comunidad")
    cat = nx.get_node_attributes(G, "categoria")
    frq = nx.get_node_attributes(G, "freq")

    filas = []
    for nodo in G.nodes():
        filas.append(
            {
                "entidad": nodo,
                "categoria": cat.get(nodo, ""),
                "n_articulos": frq.get(nodo, 0),
                "grado": grado.get(nodo, 0),
                "betweenness": round(bc.get(nodo, 0), 6),
                "pagerank": round(pr.get(nodo, 0), 6),
                "closeness": round(cl.get(nodo, 0), 6),
                "comunidad": com.get(nodo, ""),
            }
        )
    filas.sort(key=lambda r: -r["betweenness"])

    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()) if filas else [])
        w.writeheader()
        w.writerows(filas)

    return ruta


# ── Exportación pyvis (HTML interactivo) ────────────────────────────────────


def exportar_pyvis(G, ruta: Path, titulo: str = "Red de entidades — Estampa") -> Path:
    """
    Exporta el grafo como HTML interactivo con pyvis.
    Retorna la ruta del archivo generado.
    """
    try:
        from pyvis.network import Network
    except ImportError:
        raise ImportError("Instala pyvis: pip install pyvis>=0.3.2")

    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    net = Network(
        height="750px",
        width="100%",
        bgcolor="#1a1a2e",
        font_color="#e0e0e0",
        notebook=False,
    )
    net.heading = titulo

    # Escalar tamaño de nodos por frecuencia
    max_freq = max((d.get("freq", 1) for _, d in G.nodes(data=True)), default=1)

    for node, data in G.nodes(data=True):
        freq = data.get("freq", 1)
        size = 10 + 30 * (freq / max_freq)
        color = data.get("color", "#95A5A6")
        cat = data.get("categoria", "")
        com = data.get("comunidad", "")
        title = f"<b>{node}</b><br>Categoría: {cat}<br>Artículos: {freq}"
        if com != "":
            title += f"<br>Comunidad: {com}"
        net.add_node(node, label=node, color=color, size=size, title=title)

    max_peso = max((d.get("weight", 1) for _, _, d in G.edges(data=True)), default=1)
    for u, v, data in G.edges(data=True):
        peso = data.get("weight", 1)
        width = 1 + 5 * (peso / max_peso)
        net.add_edge(u, v, value=peso, width=width, title=f"Co-ocurrencias: {peso}")

    # Opciones de física para mejor layout
    net.set_options("""
    {
      "physics": {
        "forceAtlas2Based": {
          "gravitationalConstant": -50,
          "centralGravity": 0.01,
          "springLength": 100,
          "springConstant": 0.08
        },
        "solver": "forceAtlas2Based",
        "stabilization": {"iterations": 150}
      },
      "edges": {"smooth": {"type": "continuous"}},
      "interaction": {"hover": true, "tooltipDelay": 200}
    }
    """)

    net.save_graph(str(ruta))
    return ruta


# ── Exportación Gephi (GEXF) ────────────────────────────────────────────────


def exportar_gephi(G, ruta: Path) -> Path:
    """Exporta el grafo en formato GEXF para Gephi."""
    import networkx as nx

    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    nx.write_gexf(G, str(ruta))
    return ruta


# ── Serialización del grafo ─────────────────────────────────────────────────


def grafo_a_dict(G) -> dict:
    """Serializa el grafo a dict JSON-compatible para persistir en .bashkar."""
    import networkx as nx

    data = nx.node_link_data(G)
    return data


def dict_a_grafo(data: dict):
    """Restaura el grafo desde dict (node-link format)."""
    import networkx as nx

    return nx.node_link_graph(data)

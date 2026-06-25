"""core/viz_engine.py — Visualizaciones avanzadas del corpus Estampa.

Genera:
  - Nubes de palabras (simple y comparativa por período)
  - Heatmap temporal términos × artículos
  - Mapa geográfico de Colombia con lugares mencionados (folium)
  - Timeline HTML interactiva de eventos/personas
"""

from __future__ import annotations

from pathlib import Path


def _cargar_stopwords_historicas() -> set:
    """Carga stopwords desde datos/stopwords_historicas_es.txt si existe."""
    ruta = Path(__file__).parent.parent / "datos" / "stopwords_historicas_es.txt"
    stops = set()
    if ruta.exists():
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#"):
                stops.update(linea.split())
    return stops


_STOPWORDS_HISTORICAS = _cargar_stopwords_historicas()


# Stopwords funcionales frecuentes que la lista corta no cubría y aparecían
# como ruido dominante en la nube ("uno", "todos", "esto", "cómo"…).
_STOPWORDS_EXTRA = {
    "uno",
    "una",
    "unos",
    "unas",
    "todo",
    "todos",
    "toda",
    "todas",
    "esto",
    "esta",
    "este",
    "estos",
    "estas",
    "eso",
    "esa",
    "ese",
    "esos",
    "esas",
    "aquel",
    "aquello",
    "cómo",
    "como",
    "cuándo",
    "cuando",
    "dónde",
    "donde",
    "qué",
    "que",
    "quien",
    "quién",
    "cual",
    "cuál",
    "porque",
    "porqué",
    "sólo",
    "solo",
    "más",
    "menos",
    "muy",
    "tan",
    "tanto",
    "también",
    "tampoco",
    "él",
    "ella",
    "ellos",
    "ellas",
    "ser",
    "estar",
    "haber",
    "tener",
    "hacer",
    "decir",
    "ver",
    "dar",
    "ir",
    "poder",
    "deber",
    "era",
    "fue",
    "han",
    "hay",
    "puede",
    "dice",
    "está",
    "había",
    "sido",
    "siendo",
    "allí",
    "aquí",
    "ahí",
    "entonces",
    "ahora",
    "luego",
    "después",
    "antes",
    "siempre",
    "nunca",
    "mismo",
    "misma",
    "cada",
    "otro",
    "otra",
    "otros",
    "otras",
    "alguno",
    "alguna",
    "algún",
    "ningún",
    "primero",
    "primera",
    "último",
    "última",
    "gran",
    "grande",
    "mejor",
    "mayor",
    "menor",
    "nuevo",
    "nueva",
    "medio",
    "hombre",
    "vida",
    "casa",
    "día",
    "días",
    "año",
    "años",
    "vez",
    "veces",
    "momento",
    "tiempo",
    "hora",
    "parte",
    "punto",
    "manera",
    "modo",
    "cosa",
    "señor",
    "señora",
    "don",
    "doña",
    "usted",
    "ustedes",
    # marcadores del sistema / OCR — NO son del corpus
    "ilegible",
    "pág",
    "pag",
    "página",
    "pagina",
}

# Tokens de OCR roto frecuentes que no son palabras (fragmentos de una/dos
# letras o sílabas sueltas que el wordcloud agranda por frecuencia).
_RUIDO_OCR_FIJO = {
    "ns",
    "ro",
    "pa",
    "ol",
    "et",
    "fo",
    "ea",
    "ce",
    "des",
    "enel",
    "tre",
    "pre",
    "pro",
    "ton",
    "vo",
    "ve",
    "ma",
    "po",
    "mó",
    "na",
    "ho",
    "di",
    "ra",
    "cra",
    "coso",
    "caso",
    "tos",
    "ele",
    "fa",
    "ber",
    "ción",
    "mente",
    # errores OCR recurrentes en el corpus Estampa (no son palabras de contenido)
    "poro",
    "poo",
    "rir",
    "tir",
    "ica",
    "ene",
    "rca",
    "colomll",
    "beneiicencio",
    "merizald",
}

_VOCALES = set("aeiouáéíóúü")


def _es_token_valido(palabra: str) -> bool:
    """
    Heurística para descartar ruido de OCR sin tocar palabras legítimas:
      - longitud >= 3
      - contiene al menos una vocal y una consonante (un token todo-vocales
        o todo-consonantes casi siempre es basura de OCR)
      - no es un fragmento de ruido conocido
      - no mezcla cifras con letras (p. ej. "20dejulio", "5()()")
    """
    p = palabra.lower().strip()
    if len(p) < 4 or p in _RUIDO_OCR_FIJO:  # <4 letras: casi todo ruido OCR
        return False
    if any(c.isdigit() for c in p):
        return False
    tiene_vocal = any(c in _VOCALES for c in p)
    tiene_cons = any(c.isalpha() and c not in _VOCALES for c in p)
    if not (tiene_vocal and tiene_cons):
        return False
    # vocal repetida 3+ veces seguidas → OCR roto ("poo", "aaa")
    import re as _re

    if _re.search(r"([aeiouáéíóú])\1\1", p):
        return False
    # proporción de vocales fuera de rango normal del español (0.25–0.7)
    n_voc = sum(1 for c in p if c in _VOCALES)
    ratio_voc = n_voc / len(p)
    if ratio_voc < 0.25 or ratio_voc > 0.70:
        return False
    # demasiadas consonantes seguidas → OCR roto ("brdgst")
    max_cons = 0
    run = 0
    for c in p:
        if c.isalpha() and c not in _VOCALES:
            run += 1
            max_cons = max(max_cons, run)
        else:
            run = 0
    return max_cons <= 4


def _limpiar_vocabulario_nube(
    textos: list[str],
    usar_spacy: bool = True,
    usar_ia: bool = False,
    api_key: str = "",
) -> str:
    """
    Devuelve un texto depurado (cadena de lemas separados por espacio) listo
    para WordCloud, eliminando ruido OCR, stopwords y formas funcionales.

    Capas:
      1. spaCy: lematiza y conserva solo NOUN/PROPN/ADJ/VERB con sentido
         (si spaCy está disponible; si no, tokeniza con regex).
      2. Heurística `_es_token_valido` contra fragmentos de OCR.
      3. (opcional) IA: Claude marca términos sin valor en el top de frecuencia.

    Esta cadena ya viene filtrada, así que WordCloud no necesita re-filtrar.
    """
    import re as _re

    texto_completo = " ".join(textos)
    stops = set(_STOPWORDS_HISTORICAS) | _STOPWORDS_EXTRA

    lemas: list[str] = []

    if usar_spacy:
        try:
            import spacy

            nlp = None
            for m in ("es_core_news_lg", "es_core_news_md", "es_core_news_sm"):
                try:
                    nlp = spacy.load(m, disable=["parser", "ner"])
                    break
                except OSError:
                    continue
            if nlp is not None:
                nlp.max_length = max(nlp.max_length, len(texto_completo) + 100)
                POS_OK = {"NOUN", "PROPN", "ADJ", "VERB"}
                # ¿el modelo trae vectores? Si los hay, un token OOV (sin vector)
                # es casi siempre ruido de OCR: lo usamos como filtro extra.
                tiene_vectores = nlp.vocab.vectors_length > 0
                for doc in nlp.pipe([texto_completo], batch_size=1):
                    for tok in doc:
                        if tok.pos_ not in POS_OK or tok.is_stop:
                            continue
                        lema = tok.lemma_.lower().strip()
                        # nombres propios: conservar tal cual (entidades)
                        es_propn = tok.pos_ == "PROPN"
                        if lema in stops or not _es_token_valido(lema):
                            continue
                        # filtro de diccionario: descartar palabras desconocidas
                        # (ruido OCR como 'paro', 'rir', 'tir') salvo nombres propios
                        if not es_propn and len(lema) >= 4 and tiene_vectores:
                            if tok.is_oov and not tok.has_vector:
                                continue
                        elif not es_propn and len(lema) < 4:
                            continue  # palabras de contenido de <4 letras: casi todo ruido
                        lemas.append(lema)
        except Exception:
            pass

    # Fallback (o complemento) por regex si spaCy no produjo nada
    if not lemas:
        for tok in _re.findall(r"[a-záéíóúüñ]+", texto_completo.lower()):
            if tok not in stops and _es_token_valido(tok):
                lemas.append(tok)

    # Capa IA opcional: depura el top de frecuencia
    if usar_ia and api_key and lemas:
        lemas = _depurar_vocabulario_ia(lemas, api_key)

    return " ".join(lemas)


def _depurar_vocabulario_ia(lemas: list[str], api_key: str) -> list[str]:
    """
    Pasa el top de términos por Claude para que marque ruido OCR / términos sin
    valor semántico. Degrada al vocabulario original si la IA no está disponible.
    """
    from collections import Counter

    frec = Counter(lemas)
    top = [w for w, _ in frec.most_common(300)]
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        prompt = (
            "Esta es una lista de términos extraídos por OCR de prensa colombiana "
            'de 1939. Devuelve SOLO un JSON con la clave "ruido": una lista de '
            "los términos que son errores de OCR, fragmentos sin sentido o lexemas "
            "sin valor semántico (NO quites nombres propios ni palabras de contenido "
            "histórico). Lista:\n" + ", ".join(top)
        )
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        import json as _json
        import re as _re2

        raw = msg.content[0].text
        m = _re2.search(r"\{.*\}", raw, _re2.DOTALL)
        if m:
            ruido = set(w.lower() for w in _json.loads(m.group()).get("ruido", []))
            return [l for l in lemas if l not in ruido]
    except Exception:
        pass
    return lemas


# ── Nube de palabras ─────────────────────────────────────────────────────────


def nube_palabras(
    textos: list[str],
    ruta: Path,
    titulo: str = "Corpus",
    stopwords_extra: set | None = None,
    max_palabras: int = 150,
    ancho: int = 900,
    alto: int = 500,
    fondo: str = "white",
    limpiar: bool = True,
    usar_ia: bool = False,
    api_key: str = "",
) -> Path:
    """
    Genera una nube de palabras y la guarda como PNG.

    limpiar=True (por defecto): lematiza con spaCy y descarta ruido de OCR,
    stopwords y formas funcionales antes de construir la nube — evita que
    términos como 'ns', 'M', 'uno', 'todos' o 'ilegible' la dominen.
    usar_ia=True: además pasa el vocabulario por Claude (requiere api_key).

    Requiere: wordcloud, matplotlib.
    """
    try:
        from wordcloud import STOPWORDS, WordCloud
    except ImportError:
        raise ImportError("Instala wordcloud: pip install wordcloud>=1.9.3")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    if limpiar:
        texto_completo = _limpiar_vocabulario_nube(
            textos, usar_spacy=True, usar_ia=usar_ia, api_key=api_key
        )
    else:
        texto_completo = " ".join(textos)

    stops = set(STOPWORDS)
    stops.update(_STOPWORDS_HISTORICAS)
    stops.update(_STOPWORDS_EXTRA)
    stops.update(
        [
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
        ]
    )
    if stopwords_extra:
        stops.update(stopwords_extra)

    wc = WordCloud(
        width=ancho,
        height=alto,
        background_color=fondo,
        stopwords=stops,
        max_words=max_palabras,
        collocations=False,
        colormap="viridis",
        prefer_horizontal=0.8,
        min_word_length=3,
    ).generate(texto_completo)

    fig, ax = plt.subplots(figsize=(ancho / 100, alto / 100), dpi=100)
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    ax.set_title(titulo, fontsize=14, pad=10)
    fig.tight_layout(pad=0.5)
    fig.savefig(str(ruta), dpi=100, bbox_inches="tight")
    plt.close(fig)
    return ruta


def nubes_comparativas(
    grupos: dict[str, list[str]],
    ruta: Path,
    titulo: str = "Comparativo por período",
) -> Path:
    """
    Genera una figura con nubes de palabras lado a lado para varios grupos.
    grupos: {etiqueta: [textos]}
    """
    try:
        from wordcloud import STOPWORDS, WordCloud
    except ImportError:
        raise ImportError("Instala wordcloud: pip install wordcloud>=1.9.3")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    n = len(grupos)
    fig, axes = plt.subplots(1, n, figsize=(7 * n, 5))
    if n == 1:
        axes = [axes]

    stops = {
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
    }
    stops.update(STOPWORDS)

    for ax, (etiqueta, textos) in zip(axes, grupos.items()):
        texto = " ".join(textos)
        wc = WordCloud(
            width=600,
            height=400,
            background_color="white",
            stopwords=stops,
            max_words=100,
            collocations=False,
            colormap="plasma",
        ).generate(texto or "sin datos")
        ax.imshow(wc, interpolation="bilinear")
        ax.axis("off")
        ax.set_title(etiqueta, fontsize=12, pad=6)

    fig.suptitle(titulo, fontsize=14)
    fig.tight_layout()
    fig.savefig(str(ruta), dpi=100, bbox_inches="tight")
    plt.close(fig)
    return ruta


# ── Heatmap temporal ─────────────────────────────────────────────────────────


def heatmap_temporal(
    corpus_df,
    terminos: list[str],
    col_texto: str = "texto",
    col_fecha: str = "fecha",
    ruta: Path = None,
) -> Path:
    """
    Genera heatmap de frecuencia de términos × período temporal.
    corpus_df: DataFrame con columnas col_texto y col_fecha.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd

    df = corpus_df.copy()
    df[col_fecha] = pd.to_datetime(df[col_fecha], errors="coerce")
    df["periodo"] = df[col_fecha].dt.to_period("M").astype(str)
    periodos = sorted(df["periodo"].dropna().unique())

    matriz = np.zeros((len(terminos), len(periodos)))
    for j, periodo in enumerate(periodos):
        textos_p = " ".join(df[df["periodo"] == periodo][col_texto].fillna("").tolist()).lower()
        for i, term in enumerate(terminos):
            matriz[i, j] = textos_p.count(term.lower())

    ruta = Path(ruta or Path.home() / "Documents" / "BashkarStation" / "viz" / "heatmap.png")
    ruta.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(max(12, len(periodos) * 0.8), max(6, len(terminos) * 0.5)))
    im = ax.imshow(matriz, aspect="auto", cmap="YlOrRd")
    ax.set_xticks(range(len(periodos)))
    ax.set_xticklabels(periodos, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(terminos)))
    ax.set_yticklabels(terminos, fontsize=9)
    ax.set_title("Frecuencia de términos por período — Estampa 1930-1940", fontsize=12)
    plt.colorbar(im, ax=ax, label="Frecuencia")
    fig.tight_layout()
    fig.savefig(str(ruta), dpi=100, bbox_inches="tight")
    plt.close(fig)
    return ruta


# ── Mapa geográfico (folium) ─────────────────────────────────────────────────


def _cargar_coords() -> dict:
    """Carga coordenadas desde datos/coordenadas_colombia.json si existe, o usa fallback."""
    import json as _json

    ruta = Path(__file__).parent.parent / "datos" / "coordenadas_colombia.json"
    if ruta.exists():
        try:
            data = _json.loads(ruta.read_text(encoding="utf-8"))
            coords = {}
            for seccion in ("ciudades", "paises_vecinos", "regiones_historicas"):
                for nombre, info in data.get(seccion, {}).items():
                    coords[nombre] = (info["lat"], info["lon"])
            return coords
        except Exception:
            pass
    # Fallback mínimo
    return {
        "bogotá": (4.711, -74.0721),
        "bogota": (4.711, -74.0721),
        "medellín": (6.2518, -75.5636),
        "medellin": (6.2518, -75.5636),
        "cali": (3.4516, -76.5319),
        "barranquilla": (10.9639, -74.7964),
        "cartagena": (10.3910, -75.4794),
        "colombia": (4.5709, -74.2973),
    }


_COORDS_COLOMBIA = _cargar_coords()


def mapa_lugares(
    indice_global: dict,
    ruta: Path,
    titulo: str = "Lugares mencionados en Estampa 1930-1940",
) -> Path:
    """
    Genera mapa HTML interactivo con los lugares del índice NER.
    Requiere: folium.
    """
    try:
        import folium
    except ImportError:
        raise ImportError("Instala folium: pip install folium>=0.17.0")

    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    m = folium.Map(location=[4.5, -74.3], zoom_start=6, tiles="CartoDB positron")

    lugares = indice_global.get("lugares", {})
    sin_coords = []

    for lugar, arts in sorted(lugares.items(), key=lambda x: -len(x[1])):
        lugar_norm = lugar.lower().strip()
        coords = _COORDS_COLOMBIA.get(lugar_norm)
        if coords:
            n = len(arts)
            folium.CircleMarker(
                location=coords,
                radius=min(5 + n * 2, 30),
                popup=folium.Popup(
                    f"<b>{lugar}</b><br>Artículos: {n}<br>"
                    + "<br>".join(arts[:5])
                    + ("..." if n > 5 else ""),
                    max_width=200,
                ),
                tooltip=f"{lugar} ({n})",
                color="#E74C3C",
                fill=True,
                fill_opacity=0.7,
            ).add_to(m)
        else:
            sin_coords.append(lugar)

    # Leyenda con lugares sin coordenadas
    if sin_coords:
        legend = (
            "<div style='position:fixed;bottom:30px;right:30px;z-index:1000;"
            "background:white;padding:10px;border-radius:8px;font-size:12px;"
            "max-width:200px;max-height:200px;overflow-y:auto;'>"
            "<b>Sin coordenadas:</b><br>"
            + "<br>".join(sin_coords[:20])
            + ("..." if len(sin_coords) > 20 else "")
            + "</div>"
        )
        m.get_root().html.add_child(folium.Element(legend))

    m.save(str(ruta))
    return ruta


# ── Timeline HTML ─────────────────────────────────────────────────────────────


def timeline_html(
    eventos: list[dict],
    ruta: Path,
    titulo: str = "Línea de tiempo — Estampa 1930-1940",
) -> Path:
    """
    Genera timeline HTML interactiva.
    eventos: lista de dicts con: fecha (str), titulo, descripcion, categoria
    """
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    items_js = []
    for i, ev in enumerate(eventos):
        desc = ev.get("descripcion", "").replace("'", "\\'").replace("\n", " ")
        tit = ev.get("titulo", "").replace("'", "\\'")
        cat = ev.get("categoria", "evento")
        fecha = ev.get("fecha", "1935-01-01")
        items_js.append(
            f"{{id:{i}, content:'{tit}', start:'{fecha}', title:'{desc}', group:'{cat}'}}"
        )

    cats_unicas = list({ev.get("categoria", "evento") for ev in eventos})
    grupos_js = ", ".join(f"{{id:'{c}', content:'{c}'}}" for c in cats_unicas)
    items_str = ", ".join(items_js)

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>{titulo}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.css">
<style>
body {{ font-family: 'Segoe UI', sans-serif; background: #1a1a2e; color: #e0e0e0; margin: 0; padding: 10px; }}
h1 {{ text-align: center; color: #a78bfa; }}
#timeline {{ height: 600px; border: 1px solid #334155; border-radius: 8px; }}
</style>
</head>
<body>
<h1>{titulo}</h1>
<div id="timeline"></div>
<script>
var items = new vis.DataSet([{items_str}]);
var groups = new vis.DataSet([{grupos_js}]);
var options = {{
  groupOrder: 'id',
  zoomKey: 'ctrlKey',
  start: '1930-01-01',
  end: '1940-12-31',
}};
var tl = new vis.Timeline(document.getElementById('timeline'), items, groups, options);
</script>
</body>
</html>"""

    ruta.write_text(html, encoding="utf-8")
    return ruta


def eventos_desde_ner(indice_global: dict) -> list[dict]:
    """Convierte el índice NER en lista de eventos para la timeline."""
    eventos = []
    for cat, entidades in indice_global.items():
        if cat not in ("personas", "eventos_historicos", "organizaciones"):
            continue
        if not isinstance(entidades, dict):
            continue
        for ent, arts in entidades.items():
            eventos.append(
                {
                    "titulo": ent,
                    "fecha": "1935-01-01",
                    "descripcion": f"Artículos: {', '.join(arts[:3])}",
                    "categoria": cat,
                }
            )
    return eventos

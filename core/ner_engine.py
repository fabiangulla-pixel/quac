"""
core/ner_engine.py — Pipeline NER híbrido para prensa histórica.

Orden de motores (de mejor a peor para este corpus):
  1. RoBERTa-BNE (local, ~88% F1 español, sin API key)
  2. spaCy es_core_news_lg (local, ~75% F1, fallback)
  3. LLM opcional (enriquece entidades ambiguas):
       - Claude API (nube, alta precisión)
       - Ollama local — recomendado: latamgpt (español latinoamericano, sin costo)

El investigador no necesita configurar nada: el pipeline usa
automáticamente el mejor motor disponible.
"""

import gc
import json
import re
from collections.abc import Callable
from pathlib import Path

# ── Parámetros configurables (leídos por app.py para construir el panel lateral) ─
PARAMS_SCHEMA = {
    "motor": {
        "type": "choice",
        "options": ["auto", "roberta", "spacy", "fallback"],
        "default": "auto",
        "label": "Motor NER",
        "help": "auto = mejor disponible; roberta = RoBERTa-BNE local; spacy = spaCy es_core_news_lg; fallback = reglas",
    },
    "usar_ia": {
        "type": "bool",
        "default": False,
        "label": "Enriquecer con IA",
        "help": "Usa el modelo de IA seleccionado para resolver entidades ambiguas",
    },
    "proveedor_llm": {
        "type": "choice",
        "options": ["claude", "ollama"],
        "default": "claude",
        "label": "Proveedor IA",
        "help": "claude = API Anthropic (nube, de pago)\nollama = modelo local sin costo\n  → latamgpt: recomendado para corpus Estampa",
    },
    "modelo_ollama_ner": {
        "type": "str",
        "default": "latamgpt",
        "label": "Modelo Ollama",
        "help": "Nombre del modelo Ollama para NER (ej: latamgpt, llama3.1, mistral)",
    },
    "umbral_confianza": {
        "type": "float",
        "min": 0.0,
        "max": 1.0,
        "step": 0.05,
        "default": 0.7,
        "label": "Umbral de confianza",
        "help": "Entidades con score < umbral se descartan",
    },
    "categorias": {
        "type": "multicheck",
        "options": [
            "personas",
            "lugares",
            "organizaciones",
            "fechas",
            "obras_publicaciones",
            "eventos_historicos",
        ],
        "default": [
            "personas",
            "lugares",
            "organizaciones",
            "fechas",
            "obras_publicaciones",
            "eventos_historicos",
        ],
        "label": "Categorías a extraer",
    },
    "min_longitud_texto": {
        "type": "int",
        "min": 10,
        "max": 500,
        "step": 10,
        "default": 100,
        "label": "Mín. palabras por artículo",
        "help": "Artículos con menos palabras se omiten",
    },
}

# ── Categorías canónicas ────────────────────────────────────────────────────
CATEGORIAS = (
    "personas",
    "lugares",
    "organizaciones",
    "fechas",
    "obras_publicaciones",
    "eventos_historicos",
)

# spaCy labels → categoría
_SPACY_MAP = {
    "PER": "personas",
    "LOC": "lugares",
    "ORG": "organizaciones",
    "DATE": "fechas",
    "TIME": "fechas",
}

# Prompt para Claude
_PROMPT = """Eres un experto en historia colombiana del siglo XX especializado en \
publicaciones periódicas de los años 1930-1940.

Analiza el siguiente fragmento de texto, posiblemente con errores tipográficos por OCR \
(tildes faltantes, s/z intercambiadas, caracteres rotos).

Devuelve ÚNICAMENTE JSON válido (sin markdown, sin texto extra) con este esquema exacto:
{
  "personas": [],
  "lugares": [],
  "organizaciones": [],
  "fechas": [],
  "obras_publicaciones": [],
  "eventos_historicos": [],
  "notas_ocr": ""
}

Reglas:
- personas: nombres propios de personas (normaliza tildes y mayúsculas)
- lugares: topónimos, regiones, países (grafías históricas aceptadas)
- organizaciones: instituciones, partidos, academias, empresas
- fechas: fechas concretas o períodos ("12 de octubre de 1938", "los años treinta")
- obras_publicaciones: revistas, periódicos, libros, películas mencionadas
- eventos_historicos: guerras, revoluciones, eventos con nombre propio
- notas_ocr: observación breve si detectas texto muy corrupto (o "" si limpio)

Texto:
{texto}
"""

_CHUNK = 60_000  # caracteres por chunk de spaCy


# ── Funciones núcleo ────────────────────────────────────────────────────────


def _limpiar(texto: str) -> str:
    """Normalización mínima de OCR ruidoso sin perder contenido."""
    texto = re.sub(r"[ \t]{3,}", " ", texto)
    texto = re.sub(r"\n{4,}", "\n\n", texto)
    return texto.strip()


def _indice_vacio() -> dict:
    return {cat: set() for cat in CATEGORIAS}


def extraer_spacy(texto: str, nlp) -> dict:
    """Pase 1: spaCy, offline, sin costo. Devuelve dict de sets."""
    indice = _indice_vacio()
    for i in range(0, min(len(texto), 400_000), _CHUNK):
        doc = nlp(texto[i : i + _CHUNK])
        for ent in doc.ents:
            cat = _SPACY_MAP.get(ent.label_)
            if cat:
                tok = ent.text.strip()
                if len(tok) > 2:
                    indice[cat].add(tok)
        del doc
    gc.collect()
    return indice


def validar_con_llm(
    texto: str, api_key: str, modelo: str = None, proveedor: str = "claude"
) -> dict:
    """Pase 2 opcional: LLM valida y enriquece entidades ambiguas.
    Proveedores: claude (API Anthropic) | ollama (local, recomendado: latamgpt).
    Trabaja sobre los primeros 8000 caracteres para controlar costo y velocidad."""
    fragmento = texto[:8000]
    prompt_final = _PROMPT.replace("{texto}", fragmento)

    try:
        if proveedor == "claude":
            try:
                import anthropic
            except ImportError:
                return {}
            _modelo = modelo or "claude-sonnet-4-6"
            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model=_modelo,
                max_tokens=1500,
                system="Responde únicamente con JSON válido, sin markdown.",
                messages=[{"role": "user", "content": prompt_final}],
            )
            raw = msg.content[0].text.strip()

        elif proveedor == "ollama":
            import requests as _req

            _modelo = modelo or "latamgpt"
            url = api_key if api_key and api_key.startswith("http") else "http://localhost:11434"
            try:
                resp = _req.post(
                    f"{url}/api/generate",
                    json={"model": _modelo, "prompt": prompt_final, "stream": False},
                    timeout=180,
                )
                resp.raise_for_status()
            except _req.exceptions.ConnectionError:
                raise ConnectionError(
                    f"No se pudo conectar a Ollama en {url}.\n"
                    "Asegúrate de que Ollama esté corriendo: ollama serve"
                )
            raw = resp.json().get("response", "")

        else:
            return {}

        raw = re.sub(r"^```json\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)

    except (json.JSONDecodeError, ConnectionError):
        raise
    except Exception:
        return {}


def extraer_roberta(texto: str) -> dict:
    """Pase primario con RoBERTa-BNE (mejor F1 que spaCy). Retorna dict de sets."""
    try:
        from core.ner_roberta_local import ner_roberta

        entidades = ner_roberta(texto)
    except Exception:
        return _indice_vacio()

    indice = _indice_vacio()
    for ent in entidades:
        cat = ent.get("categoria")
        if cat in indice:
            indice[cat].add(ent["texto"])
    return indice


def pipeline_ner(
    texto: str,
    nlp=None,
    api_key: str | None = None,
    callback: Callable[[str], None] | None = None,
    usar_roberta: bool = True,
    umbral_confianza: float = 0.0,
    categorias: list | None = None,
    proveedor_llm: str = "claude",
    modelo_ollama: str = "latamgpt",
) -> dict:
    """
    Pipeline completo: RoBERTa-BNE (o spaCy) → (opcional) Claude.

    Args:
        texto:        Texto a analizar.
        nlp:          Modelo spaCy cargado (usado si RoBERTa no está disponible).
        api_key:      Clave API de Anthropic para enriquecimiento con Claude.
        callback:     callable(mensaje) para logging en UI.
        usar_roberta: Si False, fuerza spaCy aunque RoBERTa esté disponible.

    Returns:
        dict {categoria: [lista_ordenada]}
    """

    def log(msg):
        if callback:
            callback(msg)

    texto = _limpiar(texto)
    if not texto:
        return {cat: [] for cat in CATEGORIAS}

    # Motor primario: RoBERTa si está disponible
    indice = _indice_vacio()
    roberta_usada = False

    if usar_roberta:
        try:
            from core.ner_roberta_local import roberta_disponible

            if roberta_disponible():
                log("  RoBERTa-BNE: extrayendo entidades (mejor F1)…")
                indice = extraer_roberta(texto)
                n = sum(len(v) for v in indice.values())
                log(f"  RoBERTa-BNE: {n} entidades candidatas")
                roberta_usada = True
        except Exception:
            pass

    # Fallback: spaCy
    if not roberta_usada:
        if nlp is not None:
            log("  spaCy: extrayendo entidades…")
            indice = extraer_spacy(texto, nlp)
            log(f"  spaCy: {sum(len(v) for v in indice.values())} entidades candidatas")
        else:
            log("  ⚠ Sin motor NER local disponible (instala transformers o spaCy)")

    # Enriquecimiento opcional con LLM
    if api_key:
        _prov_label = "LatamGPT/Ollama" if proveedor_llm == "ollama" else "Claude"
        log(f"  {_prov_label}: validando y enriqueciendo con contexto histórico…")
        llm = validar_con_llm(
            texto,
            api_key,
            modelo=modelo_ollama if proveedor_llm == "ollama" else None,
            proveedor=proveedor_llm,
        )
        for cat in CATEGORIAS:
            if cat in llm and isinstance(llm[cat], list):
                for item in llm[cat]:
                    item = str(item).strip()
                    if len(item) > 2:
                        indice[cat].add(item)
        notas = llm.get("notas_ocr", "")
        if notas:
            log(f"  OCR: {notas}")
        log(
            f"  {_prov_label}: índice enriquecido → {sum(len(v) for v in indice.values())} entidades"
        )

    cats_activas = set(categorias) if categorias else set(CATEGORIAS)
    return {cat: sorted(indice[cat]) for cat in CATEGORIAS if cat in cats_activas}


# ── Gestión del índice global ───────────────────────────────────────────────


def actualizar_indice_global(indice_global: dict, art_id: str, ner_art: dict) -> dict:
    """Fusiona el NER de un artículo en el índice global.
    indice_global: {categoria: {entidad: [art_ids]}}
    Modifica en lugar y devuelve el mismo objeto.
    """
    for cat, entidades in ner_art.items():
        if cat not in indice_global:
            indice_global[cat] = {}
        for ent in entidades:
            if ent not in indice_global[cat]:
                indice_global[cat][ent] = []
            if art_id not in indice_global[cat][ent]:
                indice_global[cat][ent].append(art_id)
    return indice_global


def indice_global_vacio() -> dict:
    return {cat: {} for cat in CATEGORIAS}


def exportar_csv(indice_global: dict, ruta_csv: Path):
    """Exporta el índice global a CSV para la investigadora."""
    import csv

    filas = []
    for cat, entidades in indice_global.items():
        if not isinstance(entidades, dict):
            continue
        for ent, arts in entidades.items():
            filas.append(
                {
                    "categoria": cat,
                    "entidad": ent,
                    "n_articulos": len(arts),
                    "articulos": "; ".join(arts),
                }
            )
    filas.sort(key=lambda r: (r["categoria"], -r["n_articulos"], r["entidad"]))
    with open(ruta_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["categoria", "entidad", "n_articulos", "articulos"])
        w.writeheader()
        w.writerows(filas)
    return len(filas)

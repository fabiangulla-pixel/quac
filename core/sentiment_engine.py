"""core/sentiment_engine.py — Análisis de tono editorial con Claude.

Categorías de tono para prensa histórica colombiana 1930-1940:
  celebratorio | crítico | neutro | elegíaco | polémico | informativo

Funciones principales:
  analizar_tono()           — un artículo
  analizar_corpus_tono()    — lote en paralelo con ThreadPoolExecutor
  estadisticas_tono()       — distribución y confianza media
  evolucion_temporal()      — tono por número/período
  cruce_seccion_tono()      — tono por sección o autor
  comparar_numeros_tono()   — delta de distribución entre dos números
  tendencia_tono()          — ¿el tono X sube o baja en el tiempo?
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

PARAMS_SCHEMA = {
    "motor": {
        "type": "choice",
        "options": ["ia", "lexicon", "transformers"],
        "default": "lexicon",
        "label": "Motor de tono",
        "help": "ia = Claude/Ollama; lexicon = basado en léxico AFINN-ES; transformers = modelo local pysentimiento",
    },
    "tonos_activos": {
        "type": "multicheck",
        "options": ["celebratorio", "crítico", "neutro", "elegíaco", "polémico", "informativo"],
        "default": ["celebratorio", "crítico", "neutro", "elegíaco", "polémico", "informativo"],
        "label": "Tonos a detectar",
    },
    "workers": {
        "type": "int",
        "min": 1,
        "max": 16,
        "step": 1,
        "default": 4,
        "label": "Workers paralelos",
        "help": "Hilos simultáneos para procesar el corpus",
    },
    "evolucion_temporal": {
        "type": "bool",
        "default": True,
        "label": "Calcular evolución temporal",
        "help": "Grafica el tono promedio por número a lo largo del tiempo",
    },
    "min_palabras": {
        "type": "int",
        "min": 10,
        "max": 300,
        "step": 10,
        "default": 50,
        "label": "Mín. palabras por artículo",
    },
}

TONOS = ("celebratorio", "crítico", "neutro", "elegíaco", "polémico", "informativo")

COLORES_TONO = {
    "celebratorio": "#22C55E",
    "crítico": "#EF4444",
    "neutro": "#6B7280",
    "elegíaco": "#8B5CF6",
    "polémico": "#F59E0B",
    "informativo": "#3B82F6",
}

_PROMPT = """\
Eres un historiador especializado en periodismo colombiano de los años 1930-1940.

Analiza el tono editorial del siguiente fragmento de la revista *Estampa*.

Responde ÚNICAMENTE con JSON válido (sin markdown):
{
  "tono_principal": "celebratorio|crítico|neutro|elegíaco|polémico|informativo",
  "tono_secundario": "tono o null",
  "confianza": 0.0-1.0,
  "indicadores": ["lista de frases o palabras que indican el tono"],
  "resumen": "Una oración que describe el tono del fragmento",
  "intensidad": "alta|media|baja"
}

Definiciones:
- celebratorio: alaba o enaltece personas, eventos, logros nacionales o regionales
- crítico: cuestiona, denuncia, señala problemas sociales, políticos o morales
- neutro: reportaje factual sin posicionamiento evidente
- elegíaco: lamento por pérdidas, muertes, decadencias; tono nostálgico
- polémico: debate, controversia, contraposición de posiciones
- informativo: divulgación práctica (recetas, consejos, datos, ciencia)

intensidad: qué tan marcado es el tono (alta=muy evidente, baja=sutil).

Texto:
{texto}
"""


def analizar_tono(
    texto: str,
    api_key: str,
    modelo: str = "claude-haiku-4-5-20251001",
    callback: Callable[[str], None] | None = None,
) -> dict:
    """Analiza el tono editorial de un texto. Retorna dict con todos los campos."""
    if not texto or not texto.strip():
        return {"tono_principal": "neutro", "confianza": 0.0, "error": "texto vacío"}

    fragmento = texto[:5000]
    try:
        import anthropic
    except ImportError:
        raise ImportError("Instala anthropic: pip install anthropic>=0.25.0")

    client = anthropic.Anthropic(api_key=api_key)
    try:
        msg = client.messages.create(
            model=modelo,
            max_tokens=512,
            messages=[{"role": "user", "content": _PROMPT.replace("{texto}", fragmento)}],
        )
        raw = msg.content[0].text.strip()
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        resultado = json.loads(raw)
        # Normalizar campos opcionales
        resultado.setdefault("tono_secundario", None)
        resultado.setdefault("intensidad", "media")
        resultado.setdefault("indicadores", [])
        resultado.setdefault("resumen", "")
        # Adjuntar el usage real para medir el costo del lote (lo recoge y retira
        # analizar_corpus_tono). Clave interna con guion bajo: no es un campo de
        # tono y no debe filtrarse a estadísticas/export.
        resultado["_usage"] = getattr(msg, "usage", None)
        return resultado
    except Exception as e:
        return {
            "tono_principal": "neutro",
            "tono_secundario": None,
            "confianza": 0.0,
            "intensidad": "media",
            "indicadores": [],
            "resumen": "",
            "error": str(e),
        }


def analizar_corpus_tono(
    articulos: dict,
    api_key: str,
    modelo: str = "claude-haiku-4-5-20251001",
    callback: Callable[[int, int, str], None] | None = None,
    workers: int = 4,
    devolver_costo: bool = False,
):
    """
    Analiza el tono de todos los artículos en paralelo.

    articulos: {art_id: texto}  o  {art_id: {"texto": ..., "seccion": ..., "numero": ..., "autor": ...}}
    Retorna: {art_id: resultado_tono}  — cada resultado incluye los metadatos originales.

    Si `devolver_costo=True`, retorna `(resultados, CostoReal)` con el costo real
    del lote leído del `usage` de Claude (estándar de estimación/registro de costo).
    """
    total = len(articulos)
    resultados = {}
    completados = [0]
    _usages: list = []  # usage real de cada llamada, para el costo del lote

    def _analizar_uno(art_id, entrada):
        if isinstance(entrada, dict):
            texto = entrada.get("texto", "")
            meta = {k: v for k, v in entrada.items() if k != "texto"}
        else:
            texto = entrada
            meta = {}
        res = analizar_tono(texto, api_key, modelo)
        res.update(meta)
        return art_id, res

    with ThreadPoolExecutor(max_workers=min(workers, max(1, total))) as pool:
        futures = {
            pool.submit(_analizar_uno, aid, entrada): aid for aid, entrada in articulos.items()
        }
        for fut in as_completed(futures):
            art_id, res = fut.result()
            # Retirar el usage interno del resultado para no contaminar
            # estadísticas/export, y acumularlo para el costo real del lote.
            u = res.pop("_usage", None)
            if u is not None:
                _usages.append(u)
            resultados[art_id] = res
            completados[0] += 1
            if callback:
                callback(completados[0], total, art_id)

    if devolver_costo:
        from core.costos import costo_real_desde_usages

        return resultados, costo_real_desde_usages(modelo, _usages)
    return resultados


def estadisticas_tono(resultados: dict) -> dict:
    """
    Distribución de tonos y confianza media sobre el corpus.

    Retorna:
      total, distribucion {tono: {n, porcentaje, confianza_media}},
      tono_dominante, indice_polarizacion (% crítico + polémico)
    """
    conteo = Counter()
    confianzas: dict[str, list] = {t: [] for t in TONOS}

    for res in resultados.values():
        tono = res.get("tono_principal", "neutro")
        conf = res.get("confianza", 0.0)
        conteo[tono] += 1
        if tono in confianzas:
            confianzas[tono].append(conf)

    total = sum(conteo.values())
    distribucion = {}
    for tono in TONOS:
        n = conteo.get(tono, 0)
        conf_list = confianzas[tono]
        distribucion[tono] = {
            "n": n,
            "porcentaje": round(100 * n / total, 1) if total > 0 else 0.0,
            "confianza_media": round(sum(conf_list) / len(conf_list), 2) if conf_list else 0.0,
        }

    tono_dominante = conteo.most_common(1)[0][0] if conteo else "neutro"
    n_critico = conteo.get("crítico", 0)
    n_polemico = conteo.get("polémico", 0)
    indice_polarizacion = round(100 * (n_critico + n_polemico) / total, 1) if total > 0 else 0.0

    return {
        "total": total,
        "distribucion": distribucion,
        "tono_dominante": tono_dominante,
        "indice_polarizacion": indice_polarizacion,
    }


def evolucion_temporal(
    resultados: dict,
    campo_periodo: str = "numero",
) -> dict:
    """
    Evolución del tono a lo largo del tiempo.

    resultados: {art_id: {tono_principal, <campo_periodo>, ...}}
    campo_periodo: clave que identifica el período (ej. "numero", "fecha", "anio")

    Retorna: {periodo: {tono: porcentaje, "total": n}}  ordenado cronológicamente.
    """
    por_periodo: dict[str, Counter] = defaultdict(Counter)

    for res in resultados.values():
        periodo = str(res.get(campo_periodo, "sin_periodo"))
        tono = res.get("tono_principal", "neutro")
        por_periodo[periodo][tono] += 1

    evolucion = {}
    for periodo in sorted(por_periodo.keys()):
        conteo = por_periodo[periodo]
        total = sum(conteo.values())
        evolucion[periodo] = {tono: round(100 * conteo.get(tono, 0) / total, 1) for tono in TONOS}
        evolucion[periodo]["total"] = total

    return evolucion


def cruce_seccion_tono(
    resultados: dict,
    campo: str = "seccion",
) -> dict:
    """
    Distribución de tono cruzada con una variable categórica (sección, autor, tipo).

    Retorna: {valor_campo: {tono: porcentaje, "total": n}}
    """
    por_campo: dict[str, Counter] = defaultdict(Counter)

    for res in resultados.values():
        valor = str(res.get(campo, "desconocido"))
        tono = res.get("tono_principal", "neutro")
        por_campo[valor][tono] += 1

    cruce = {}
    for valor in sorted(por_campo.keys()):
        conteo = por_campo[valor]
        total = sum(conteo.values())
        cruce[valor] = {tono: round(100 * conteo.get(tono, 0) / total, 1) for tono in TONOS}
        cruce[valor]["total"] = total

    return cruce


def comparar_numeros_tono(
    resultados_a: dict,
    resultados_b: dict,
    etiqueta_a: str = "A",
    etiqueta_b: str = "B",
) -> dict:
    """
    Compara la distribución de tono entre dos números o corpus.

    Retorna: {tono: {etiqueta_a: %, etiqueta_b: %, delta: %B-%A}}
    """
    stats_a = estadisticas_tono(resultados_a)["distribucion"]
    stats_b = estadisticas_tono(resultados_b)["distribucion"]

    comparacion = {}
    for tono in TONOS:
        pct_a = stats_a.get(tono, {}).get("porcentaje", 0.0)
        pct_b = stats_b.get(tono, {}).get("porcentaje", 0.0)
        comparacion[tono] = {
            etiqueta_a: pct_a,
            etiqueta_b: pct_b,
            "delta": round(pct_b - pct_a, 1),
        }

    return comparacion


def tendencia_tono(
    evolucion: dict,
    tono: str,
) -> dict:
    """
    Calcula si un tono sube, baja o se mantiene a lo largo del tiempo.

    evolucion: resultado de evolucion_temporal()
    Retorna: {periodos, valores, pendiente, direccion: "sube"|"baja"|"estable"}
    """
    periodos = sorted(evolucion.keys())
    valores = [evolucion[p].get(tono, 0.0) for p in periodos]

    if len(valores) < 2:
        return {"periodos": periodos, "valores": valores, "pendiente": 0.0, "direccion": "estable"}

    # Regresión lineal simple (sin numpy)
    n = len(valores)
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(valores) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, valores))
    den = sum((x - mx) ** 2 for x in xs)
    pendiente = round(num / den, 4) if den != 0 else 0.0

    if pendiente > 0.5:
        direccion = "sube"
    elif pendiente < -0.5:
        direccion = "baja"
    else:
        direccion = "estable"

    return {
        "periodos": periodos,
        "valores": valores,
        "pendiente": pendiente,
        "direccion": direccion,
    }


def resumen_narrativo(
    stats: dict,
    evolucion: dict,
    api_key: str,
    modelo: str = "claude-haiku-4-5-20251001",
    nombre_corpus: str = "el corpus",
) -> str:
    """
    Genera un párrafo de síntesis interpretativa del análisis de tono.
    Útil para el reporte automático del paper.
    """
    try:
        import anthropic
    except ImportError:
        return ""

    dist = stats.get("distribucion", {})
    dominante = stats.get("tono_dominante", "neutro")
    polarizacion = stats.get("indice_polarizacion", 0.0)

    # Construir tendencias
    tendencias = []
    for tono in ("celebratorio", "crítico", "polémico"):
        t = tendencia_tono(evolucion, tono)
        if t["direccion"] != "estable":
            tendencias.append(f"{tono}: {t['direccion']}")

    prompt = f"""Eres un historiador del periodismo colombiano.
Con base en estos datos de tono editorial de {nombre_corpus}:

- Tono dominante: {dominante} ({dist.get(dominante, {}).get("porcentaje", 0)}%)
- Índice de polarización (crítico+polémico): {polarizacion}%
- Distribución completa: {json.dumps({t: dist.get(t, {}).get("porcentaje", 0) for t in TONOS}, ensure_ascii=False)}
- Tendencias a lo largo del tiempo: {"; ".join(tendencias) if tendencias else "sin cambios marcados"}

Redacta UN párrafo académico (4-6 oraciones) que interprete estos resultados
en el contexto de la prensa colombiana de los años 1930-1940.
Señala qué sugiere el tono dominante sobre la línea editorial,
qué implica el índice de polarización y qué significan las tendencias temporales.
Escribe en español, sin markdown."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=modelo,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════════════════════════
# EXTENSIÓN LINGÜÍSTICA: Subjetividad y emociones básicas (100% offline)
# ═══════════════════════════════════════════════════════════════════════════════

# ── Léxico de emociones básicas (NRC adaptado al español histórico) ────────────
# Cada entrada: {emocion: [palabras]}

_LEXICON_EMOCIONES: dict[str, list[str]] = {
    "alegria": [
        "alegre",
        "feliz",
        "gozo",
        "júbilo",
        "contento",
        "dichoso",
        "festivo",
        "triunfo",
        "celebración",
        "regocijo",
        "risueño",
        "animado",
        "entusiasta",
        "exultante",
        "alborozado",
        "placer",
        "satisfacción",
        "bienestar",
        "fiesta",
        "victoria",
        "éxito",
        "brillante",
        "glorioso",
    ],
    "tristeza": [
        "triste",
        "dolor",
        "pena",
        "luto",
        "melancolía",
        "aflicción",
        "llanto",
        "lágrimas",
        "desgracia",
        "duelo",
        "deplorable",
        "lamentable",
        "muerte",
        "fallecimiento",
        "pérdida",
        "soledad",
        "desamparo",
        "angustia",
        "sufrimiento",
        "miseria",
        "penoso",
        "funesto",
        "trágico",
    ],
    "miedo": [
        "miedo",
        "terror",
        "pánico",
        "amenaza",
        "peligro",
        "alarma",
        "temor",
        "espanto",
        "horror",
        "ansiedad",
        "nervioso",
        "inquieto",
        "intranquilo",
        "amenaza",
        "riesgo",
        "pavoroso",
        "aterrador",
        "temeroso",
    ],
    "ira": [
        "ira",
        "rabia",
        "furia",
        "cólera",
        "indignación",
        "enojo",
        "protesta",
        "denuncia",
        "acusación",
        "ataque",
        "combate",
        "lucha",
        "violencia",
        "conflicto",
        "escándalo",
        "controversia",
        "polémica",
    ],
    "sorpresa": [
        "sorpresa",
        "asombro",
        "admiración",
        "estupor",
        "maravilla",
        "increíble",
        "insólito",
        "extraordinario",
        "inusitado",
        "inesperado",
        "revelación",
        "novedad",
        "descubrimiento",
    ],
    "confianza": [
        "confianza",
        "seguridad",
        "fe",
        "esperanza",
        "progreso",
        "prosperidad",
        "desarrollo",
        "avance",
        "modernidad",
        "paz",
        "orden",
        "estabilidad",
        "patria",
        "nación",
        "república",
        "democracia",
    ],
    "disgusto": [
        "disgusto",
        "repugnancia",
        "repudio",
        "rechazo",
        "vergüenza",
        "deshonra",
        "escándalo",
        "corrupto",
        "depravado",
        "inmoral",
        "vicioso",
        "degradante",
    ],
    "anticipacion": [
        "espera",
        "futuro",
        "porvenir",
        "próximo",
        "venidero",
        "próximamente",
        "anuncio",
        "inauguración",
        "apertura",
        "proyecto",
        "plan",
        "propuesta",
    ],
}

# Conjunto de palabras subjetivas (marcadores de opinión vs. hecho)
_PALABRAS_SUBJETIVAS = {
    # verbos de opinión
    "creer",
    "opinar",
    "pensar",
    "considerar",
    "estimar",
    "juzgar",
    "suponer",
    "afirmar",
    "sostener",
    "argumentar",
    "defender",
    "criticar",
    "elogiar",
    # adjetivos evaluativos
    "bueno",
    "malo",
    "excelente",
    "pésimo",
    "notable",
    "destacado",
    "ilustre",
    "digno",
    "indigno",
    "loable",
    "reprobable",
    "admirable",
    "deplorable",
    "brillante",
    "mediocre",
    "extraordinario",
    "lamentable",
    # adverbios de modalidad
    "desafortunadamente",
    "lamentablemente",
    "afortunadamente",
    "evidentemente",
    "indudablemente",
    "naturalmente",
    "ciertamente",
    "sinceramente",
}

_PALABRAS_FACTUALES = {
    # verbos de reporte
    "informar",
    "reportar",
    "publicar",
    "anunciar",
    "declarar",
    "señalar",
    "indicar",
    "mostrar",
    "revelar",
    "confirmar",
    "negar",
    # expresiones de dato
    "según",
    "datos",
    "estadísticas",
    "cifras",
    "número",
    "total",
    "porcentaje",
    "fecha",
    "lugar",
    "año",
    "hora",
}

# Compilar índice invertido emoción → palabras para búsqueda rápida
_INDICE_EMO: dict[str, str] = {}
for _emo, _pals in _LEXICON_EMOCIONES.items():
    for _p in _pals:
        _INDICE_EMO[_p.lower()] = _emo


def analizar_emociones(texto: str) -> dict:
    """
    Detecta emociones básicas en el texto usando léxico offline.

    Retorna:
      {emociones: {emocion: {n, porcentaje}},
       emocion_dominante,
       palabras_detectadas: [{palabra, emocion}],
       subjetividad: 0.0-1.0,
       tipo_discurso: 'subjetivo' | 'factual' | 'mixto'}
    """
    if not texto:
        return {
            "emociones": {e: {"n": 0, "porcentaje": 0.0} for e in _LEXICON_EMOCIONES},
            "emocion_dominante": None,
            "palabras_detectadas": [],
            "subjetividad": 0.0,
            "tipo_discurso": "factual",
        }

    import re as _re

    palabras = _re.findall(r"\b[a-záéíóúüñ]{3,}\b", texto.lower())
    n_palabras = len(palabras) or 1

    conteo_emo: dict[str, int] = dict.fromkeys(_LEXICON_EMOCIONES, 0)
    palabras_det: list[dict] = []

    n_subjetivas = 0
    n_factuales = 0

    for p in palabras:
        if p in _INDICE_EMO:
            emo = _INDICE_EMO[p]
            conteo_emo[emo] += 1
            palabras_det.append({"palabra": p, "emocion": emo})
        if p in _PALABRAS_SUBJETIVAS:
            n_subjetivas += 1
        if p in _PALABRAS_FACTUALES:
            n_factuales += 1

    total_emo = sum(conteo_emo.values()) or 1
    distribucion = {
        emo: {
            "n": n,
            "porcentaje": round(100 * n / total_emo, 1),
        }
        for emo, n in conteo_emo.items()
    }

    emo_dominante = max(conteo_emo, key=lambda e: conteo_emo[e])
    if conteo_emo[emo_dominante] == 0:
        emo_dominante = None

    # Índice de subjetividad: ratio palabras subjetivas / (subj + fact + 1)
    subjetividad = round(n_subjetivas / (n_subjetivas + n_factuales + 1), 3)

    if subjetividad > 0.6:
        tipo_discurso = "subjetivo"
    elif subjetividad < 0.3:
        tipo_discurso = "factual"
    else:
        tipo_discurso = "mixto"

    return {
        "emociones": distribucion,
        "emocion_dominante": emo_dominante,
        "palabras_detectadas": palabras_det[:30],
        "subjetividad": subjetividad,
        "tipo_discurso": tipo_discurso,
        "n_palabras_analizadas": n_palabras,
    }


def analizar_subjetividad(texto: str) -> dict:
    """
    Análisis de subjetividad enfocado: ¿el texto es factual u opinativo?

    Retorna:
      {score_subjetividad: 0-1, tipo_discurso,
       marcadores_subjetivos: [palabras], marcadores_factuales: [palabras],
       oraciones_subjetivas: [str], oraciones_factuales: [str]}
    """
    if not texto:
        return {
            "score_subjetividad": 0.0,
            "tipo_discurso": "factual",
            "marcadores_subjetivos": [],
            "marcadores_factuales": [],
            "oraciones_subjetivas": [],
            "oraciones_factuales": [],
        }

    import re as _re

    oraciones = _re.split(r"[.!?]+", texto)
    oraciones = [o.strip() for o in oraciones if len(o.strip()) > 20]

    marc_subj: list[str] = []
    marc_fact: list[str] = []
    oraciones_subj: list[str] = []
    oraciones_fact: list[str] = []

    for oracion in oraciones:
        palabras = set(_re.findall(r"\b[a-záéíóúüñ]{3,}\b", oracion.lower()))
        n_s = len(palabras & _PALABRAS_SUBJETIVAS)
        n_f = len(palabras & _PALABRAS_FACTUALES)
        marc_subj.extend(list(palabras & _PALABRAS_SUBJETIVAS))
        marc_fact.extend(list(palabras & _PALABRAS_FACTUALES))
        if n_s > n_f:
            oraciones_subj.append(oracion)
        elif n_f > 0:
            oraciones_fact.append(oracion)

    n_total = len(oraciones) or 1
    score = round(len(oraciones_subj) / n_total, 3)

    if score > 0.5:
        tipo = "subjetivo"
    elif score < 0.25:
        tipo = "factual"
    else:
        tipo = "mixto"

    return {
        "score_subjetividad": score,
        "tipo_discurso": tipo,
        "marcadores_subjetivos": list(set(marc_subj))[:15],
        "marcadores_factuales": list(set(marc_fact))[:15],
        "oraciones_subjetivas": oraciones_subj[:5],
        "oraciones_factuales": oraciones_fact[:5],
    }


def analizar_intensidad(texto: str) -> dict:
    """
    Detecta la intensidad retórica del texto:
    superlatividad, exclamaciones, repeticiones, cuantificadores extremos.

    Retorna:
      {score_intensidad: 0-1, marcadores: [{tipo, ejemplo}]}
    """
    import re as _re

    if not texto:
        return {"score_intensidad": 0.0, "marcadores": []}

    marcadores = []
    score = 0.0

    # Superlativos en -ísimo
    superlativos = _re.findall(r"\b\w+ísim[ao]s?\b", texto, re.IGNORECASE)
    if superlativos:
        marcadores.extend({"tipo": "superlativo", "ejemplo": s} for s in superlativos[:3])
        score += 0.1 * min(len(superlativos), 5)

    # Exclamaciones
    exclamaciones = texto.count("!")
    if exclamaciones:
        marcadores.append({"tipo": "exclamacion", "ejemplo": f"{exclamaciones} signos !"})
        score += 0.05 * min(exclamaciones, 5)

    # Cuantificadores extremos
    _CUANT = {
        "nunca",
        "siempre",
        "jamás",
        "todo",
        "nada",
        "nadie",
        "todos",
        "completamente",
        "absolutamente",
        "totalmente",
        "enormemente",
    }
    cuant = [p for p in _re.findall(r"\b\w+\b", texto.lower()) if p in _CUANT]
    if cuant:
        marcadores.extend({"tipo": "cuantificador", "ejemplo": c} for c in sorted(set(cuant))[:3])
        score += 0.08 * min(len(cuant), 5)

    # Repetición de signos de admiración o interrogación
    if _re.search(r"[!?]{2,}", texto):
        marcadores.append({"tipo": "enfasis_grafico", "ejemplo": "!! o ??"})
        score += 0.15

    return {
        "score_intensidad": round(min(score, 1.0), 3),
        "marcadores": marcadores,
    }


def analisis_completo_emocion(texto: str) -> dict:
    """
    Análisis emocional completo: combina emociones + subjetividad + intensidad.
    Función de conveniencia para llamar desde la UI.
    """
    return {
        "emociones": analizar_emociones(texto),
        "subjetividad": analizar_subjetividad(texto),
        "intensidad": analizar_intensidad(texto),
    }

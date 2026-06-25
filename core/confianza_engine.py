"""core/confianza_engine.py — Sistema de confianza semáforo para Bashkar Station.

Niveles:
  GREEN  (≥ 0.75) — resultado confiable, listo para publicación
  YELLOW (0.45-0.75) — revisar antes de usar
  RED    (< 0.45)  — requiere validación humana obligatoria

Aplica a: OCR, NER, tono editorial, tópicos.
"""

from __future__ import annotations

from dataclasses import dataclass, field

VERDE = "green"
AMARILLO = "yellow"
ROJO = "red"

# Colores tkinter para semáforo
COLOR_VERDE = "#22c55e"
COLOR_AMARILLO = "#f59e0b"
COLOR_ROJO = "#ef4444"

COLOR_BG_VERDE = "#052e16"
COLOR_BG_AMARILLO = "#431407"
COLOR_BG_ROJO = "#450a0a"


def nivel_confianza(score: float) -> str:
    if score >= 0.75:
        return VERDE
    elif score >= 0.45:
        return AMARILLO
    else:
        return ROJO


def color_semaforo(score: float) -> str:
    n = nivel_confianza(score)
    return {VERDE: COLOR_VERDE, AMARILLO: COLOR_AMARILLO, ROJO: COLOR_ROJO}[n]


def color_fondo_semaforo(score: float) -> str:
    n = nivel_confianza(score)
    return {VERDE: COLOR_BG_VERDE, AMARILLO: COLOR_BG_AMARILLO, ROJO: COLOR_BG_ROJO}[n]


def etiqueta_semaforo(score: float) -> str:
    n = nivel_confianza(score)
    return {VERDE: "● CONFIABLE", AMARILLO: "◐ REVISAR", ROJO: "○ VALIDAR"}[n]


# ── Scoring de OCR ────────────────────────────────────────────────────────────


def score_ocr(conf_tesseract: float, mejorado_con_llm: bool = False) -> float:
    """Convierte confianza Tesseract (0-100) a score normalizado 0-1."""
    base = max(0.0, min(1.0, conf_tesseract / 100.0))
    if mejorado_con_llm:
        base = min(1.0, base + 0.15)
    return round(base, 3)


# ── Scoring de NER ────────────────────────────────────────────────────────────


def score_ner_entidad(
    en_kb: bool,  # está en la base de conocimiento
    verificada: bool,  # verificada manualmente
    spacy_conf: float,  # confianza spaCy (0-1)
    llm_conf: float,  # confianza Claude (0-1)
) -> float:
    """Calcula score de confianza para una entidad NER."""
    if verificada:
        return 1.0
    pesos = {
        "kb": 0.3,
        "spacy": 0.25,
        "llm": 0.45,
    }
    score = (
        pesos["kb"] * (1.0 if en_kb else 0.0)
        + pesos["spacy"] * spacy_conf
        + pesos["llm"] * llm_conf
    )
    return round(score, 3)


# ── Scoring de tono ───────────────────────────────────────────────────────────


def score_tono(confianza_llm: float, es_neutral: bool = False) -> float:
    """Score de confianza para análisis de tono editorial."""
    if es_neutral:
        return min(1.0, confianza_llm + 0.1)
    return confianza_llm


# ── Validación humana: registro de ediciones ─────────────────────────────────


@dataclass
class EntidadValidacion:
    nombre: str
    categoria: str
    score: float
    nivel: str = field(init=False)
    verificada: bool = False
    editado_por: str = ""
    nota: str = ""

    def __post_init__(self):
        self.nivel = nivel_confianza(self.score)


class ColaPendiente:
    """Cola de entidades/resultados que requieren validación humana."""

    def __init__(self):
        self._items: list[EntidadValidacion] = []

    def agregar(self, item: EntidadValidacion):
        if item.nivel in (AMARILLO, ROJO):
            self._items.append(item)

    def pendientes(self) -> list[EntidadValidacion]:
        return [i for i in self._items if not i.verificada]

    def verificar(self, nombre: str, categoria: str, editado_por: str = "") -> bool:
        for item in self._items:
            if item.nombre == nombre and item.categoria == categoria:
                item.verificada = True
                item.editado_por = editado_por
                return True
        return False

    def estadisticas(self) -> dict:
        total = len(self._items)
        verif = sum(1 for i in self._items if i.verificada)
        return {
            "total": total,
            "verificadas": verif,
            "pendientes": total - verif,
            "por_nivel": {
                VERDE: sum(1 for i in self._items if i.nivel == VERDE),
                AMARILLO: sum(1 for i in self._items if i.nivel == AMARILLO),
                ROJO: sum(1 for i in self._items if i.nivel == ROJO),
            },
        }


# ── Calcular confianza global del corpus ─────────────────────────────────────


def confianza_global_corpus(articulos: dict) -> dict:
    """
    Calcula estadísticas de confianza para todo el corpus.
    articulos: {art_id: {"conf_ocr": float, "mejorado_llm": bool, ...}}
    """
    scores_ocr = []
    for art in articulos.values():
        conf_raw = art.get("conf_ocr") or art.get("confianza_ocr") or 50.0
        mejorado = bool(art.get("mejorado_llm") or art.get("ocr_mejorado"))
        scores_ocr.append(score_ocr(conf_raw, mejorado))

    if not scores_ocr:
        return {"promedio_ocr": 0, "nivel": ROJO, "distribucion": {}}

    promedio = sum(scores_ocr) / len(scores_ocr)
    distribucion = {
        VERDE: sum(1 for s in scores_ocr if nivel_confianza(s) == VERDE),
        AMARILLO: sum(1 for s in scores_ocr if nivel_confianza(s) == AMARILLO),
        ROJO: sum(1 for s in scores_ocr if nivel_confianza(s) == ROJO),
    }

    return {
        "promedio_ocr": round(promedio, 3),
        "nivel": nivel_confianza(promedio),
        "distribucion": distribucion,
        "total_articulos": len(scores_ocr),
    }

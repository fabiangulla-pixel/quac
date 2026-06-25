"""frame_engine — análisis de *encuadre* (framing) de notas de prensa.

Operacionaliza el **Media Frames Corpus** (Boydstun et al.): clasifica cada nota
según el ÁNGULO desde el que cubre el tema, no solo su tono. Mientras el
sentimiento dice "positivo/negativo", el framing dice "desde qué marco":
¿se habla de un candidato en clave de *legalidad*, de *seguridad*, de *moralidad*,
de *identidad/cultura*…?

Implementación **100% local**: léxico de marcadores en español por frame (sin
API key). Si el usuario provee API key de Claude, se puede afinar con el LLM
(opcional, ver ``clasificar_frame_llm``), pero NO es necesario.

Es un motor nuevo de ¡Quac! (Bashkar analiza prensa histórica y no lo tenía);
sigue el mismo estilo de los demás: funciones puras texto→dict.
"""

from __future__ import annotations

import re

# 13 frames agnósticos al tema, adaptados del Media Frames Corpus al español
# periodístico. Cada frame tiene marcadores léxicos (lemas/raíces) frecuentes.
FRAMES: dict[str, dict] = {
    "economia": {
        "etiqueta": "Economía / costos",
        "marcadores": [
            "económic",
            "costo",
            "presupuesto",
            "gasto",
            "impuesto",
            "inversión",
            "empleo",
            "salario",
            "fiscal",
            "recursos",
            "millones",
            "peso",
            "dólar",
            "mercado",
            "financ",
        ],
    },
    "legalidad": {
        "etiqueta": "Legalidad / constitucionalidad / justicia",
        "marcadores": [
            "ley",
            "legal",
            "ilegal",
            "constituci",
            "tribunal",
            "juez",
            "juzgado",
            "demanda",
            "tutela",
            "fallo",
            "sentencia",
            "corte",
            "fiscal",
            "delito",
            "derecho",
            "norma",
            "medida",
            "recurso",
            "apelaci",
            "magistrad",
        ],
    },
    "seguridad": {
        "etiqueta": "Seguridad / defensa / conflicto armado",
        "marcadores": [
            "seguridad",
            "violencia",
            "armad",
            "guerrilla",
            "farc",
            "atentado",
            "amenaza",
            "ataque",
            "militar",
            "polic",
            "terroris",
            "secuestro",
            "homicidio",
            "asesinato",
            "guerra",
            "conflicto",
            "víctima",
            "paz",
            "desmoviliz",
        ],
    },
    "moralidad": {
        "etiqueta": "Moralidad / ética / valores",
        "marcadores": [
            "moral",
            "ético",
            "valores",
            "dios",
            "religi",
            "famili",
            "dignidad",
            "corrupción",
            "honesti",
            "decencia",
            "vergüenza",
            "principios",
            "integridad",
        ],
    },
    "politica": {
        "etiqueta": "Estrategia política / campaña",
        "marcadores": [
            "campaña",
            "candidat",
            "elección",
            "elector",
            "voto",
            "encuesta",
            "alianza",
            "coalición",
            "partido",
            "estrategia",
            "debate",
            "discurso",
            "popularidad",
            "segunda vuelta",
            "consulta",
            "aspirante",
        ],
    },
    "identidad": {
        "etiqueta": "Identidad / cultura / nación",
        "marcadores": [
            "identidad",
            "nacional",
            "patria",
            "símbolo",
            "camiseta",
            "selección",
            "bandera",
            "himno",
            "cultura",
            "tradici",
            "orgullo",
            "colombian",
            "pueblo",
            "ciudadan",
        ],
    },
    "salud": {
        "etiqueta": "Salud pública",
        "marcadores": [
            "salud",
            "hospital",
            "enfermedad",
            "epidemia",
            "pandemia",
            "eps",
            "médic",
            "sanitari",
            "vacuna",
        ],
    },
    "derechos": {
        "etiqueta": "Derechos / igualdad / minorías",
        "marcadores": [
            "derechos humanos",
            "igualdad",
            "discriminaci",
            "género",
            "minoría",
            "indígena",
            "afro",
            "lgbt",
            "mujer",
            "equidad",
            "inclusión",
            "libertad",
        ],
    },
    "ambiente": {
        "etiqueta": "Medio ambiente",
        "marcadores": [
            "ambient",
            "clima",
            "ecológic",
            "deforestaci",
            "agua",
            "contaminaci",
            "petróleo",
            "energía",
            "páramo",
            "selva",
        ],
    },
    "internacional": {
        "etiqueta": "Relaciones internacionales",
        "marcadores": [
            "internacional",
            "exterior",
            "frontera",
            "venezuela",
            "estados unidos",
            "diplomá",
            "tratado",
            "migra",
            "onu",
            "extranjer",
        ],
    },
    "opinion_publica": {
        "etiqueta": "Opinión pública / reacciones",
        "marcadores": [
            "redes sociales",
            "rechazo",
            "crítica",
            "polémica",
            "controversia",
            "indignación",
            "respaldo",
            "apoyo",
            "reacción",
            "trino",
            "tuit",
            "viral",
            "debate público",
        ],
    },
    "capacidad": {
        "etiqueta": "Capacidad / gestión / eficacia",
        "marcadores": [
            "gestión",
            "eficacia",
            "capacidad",
            "resultados",
            "obra",
            "ejecuci",
            "cumpl",
            "fracaso",
            "logr",
            "competencia",
            "experiencia",
            "trayectoria",
        ],
    },
    "equidad": {
        "etiqueta": "Equidad / justicia social",
        "marcadores": [
            "desigualdad",
            "pobreza",
            "social",
            "subsidio",
            "vulnerable",
            "brecha",
            "redistribu",
            "trabajador",
            "campesin",
            "popular",
        ],
    },
}


def registrar_marcos_personalizados(marcos: dict) -> None:
    """Añade/extiende frames con vocabulario del perfil del usuario.

    ``marcos``: {clave_frame: [términos...]} (p. ej. los del perfil electoral).
    Si la clave ya existe, fusiona los marcadores; si no, crea el frame nuevo.
    Permite que el investigador adapte el encuadre a su dominio sin tocar código.
    """
    etiquetas = {
        "politico": "Marco político (polarización/cambio)",
        "seguridad": "Marco de seguridad / orden público",
        "economico": "Marco económico",
        "social": "Marco social (salud/educación/igualdad)",
        "informativo": "Marco de desinformación / medios digitales",
        "mediatico": "Marco mediático (sesgo/concentración)",
        "electoral_integridad": "Integridad electoral (fraude/auditoría)",
    }
    for clave, terminos in (marcos or {}).items():
        if not terminos:
            continue
        if clave in FRAMES:
            existentes = set(FRAMES[clave]["marcadores"])
            FRAMES[clave]["marcadores"] = list(existentes | {t.lower() for t in terminos})
        else:
            FRAMES[clave] = {
                "etiqueta": etiquetas.get(clave, clave.replace("_", " ").title()),
                "marcadores": [t.lower() for t in terminos],
            }


def _contar_marcadores(texto_low: str) -> dict[str, int]:
    conteo: dict[str, int] = {}
    for frame, info in FRAMES.items():
        n = 0
        for m in info["marcadores"]:
            # palabra/raíz como subcadena con frontera al inicio
            n += len(re.findall(r"\b" + re.escape(m), texto_low))
        if n:
            conteo[frame] = n
    return conteo


def analizar_frame(texto: str, top_n: int = 3) -> dict:
    """Detecta los encuadres dominantes de una nota (offline, por léxico).

    Retorna:
      {frame_dominante, etiqueta, distribucion: [{frame, etiqueta, n, porcentaje}],
       total_marcadores}
    """
    if not texto or not texto.strip():
        return {
            "frame_dominante": None,
            "etiqueta": None,
            "distribucion": [],
            "total_marcadores": 0,
        }

    conteo = _contar_marcadores(texto.lower())
    total = sum(conteo.values())
    if total == 0:
        return {
            "frame_dominante": None,
            "etiqueta": None,
            "distribucion": [],
            "total_marcadores": 0,
        }

    dist = sorted(
        (
            {
                "frame": f,
                "etiqueta": FRAMES[f]["etiqueta"],
                "n": n,
                "porcentaje": round(100 * n / total, 1),
            }
            for f, n in conteo.items()
        ),
        key=lambda d: -d["n"],
    )

    dom = dist[0]
    return {
        "frame_dominante": dom["frame"],
        "etiqueta": dom["etiqueta"],
        "distribucion": dist[:top_n],
        "total_marcadores": total,
    }


def cruce_medio_frame(por_nota: dict) -> dict:
    """Matriz medio → distribución de frames (cuántas notas por frame dominante).

    ``por_nota``: {url: {"medio":..., "frame": <resultado de analizar_frame>}}
    """
    matriz: dict[str, dict] = {}
    for r in por_nota.values():
        medio = r.get("medio") or "?"
        frame = (r.get("frame") or {}).get("frame_dominante")
        if not frame:
            continue
        d = matriz.setdefault(medio, {})
        d[frame] = d.get(frame, 0) + 1
    return matriz


def clasificar_frame_llm(
    texto: str, api_key: str, modelo: str = "claude-haiku-4-5-20251001"
) -> dict | None:
    """(Opcional) Afina el frame con Claude. Solo si el usuario da API key.

    Devuelve None si la librería/clave no están; el flujo sigue con el léxico.
    """
    try:
        import anthropic
    except ImportError:
        return None
    etiquetas = "\n".join(f"- {k}: {v['etiqueta']}" for k, v in FRAMES.items())
    prompt = (
        "Clasifica el ENCUADRE periodístico dominante de esta nota en UNA de "
        "estas categorías (responde solo la clave, p. ej. 'legalidad'):\n"
        f"{etiquetas}\n\nNOTA:\n{texto[:4000]}\n\nClave:"
    )
    try:
        cli = anthropic.Anthropic(api_key=api_key)
        msg = cli.messages.create(
            model=modelo, max_tokens=20, messages=[{"role": "user", "content": prompt}]
        )
        clave = msg.content[0].text.strip().lower()
        clave = re.sub(r"[^a-z_]", "", clave)
        if clave in FRAMES:
            return {
                "frame_dominante": clave,
                "etiqueta": FRAMES[clave]["etiqueta"],
                "distribucion": [
                    {
                        "frame": clave,
                        "etiqueta": FRAMES[clave]["etiqueta"],
                        "n": 1,
                        "porcentaje": 100.0,
                    }
                ],
                "total_marcadores": 1,
                "fuente": "llm",
            }
    except Exception:
        return None
    return None

"""core/lexicon_engine.py — Glosario automático de léxico histórico colombiano.

Detecta y clasifica:
  - arcaísmos: palabras en desuso o con ortografía antigua
  - neologismos: términos nuevos o extranjerismos del período 1930-1940
  - colombianismos: regionalismos y expresiones propias del contexto colombiano
  - tecnicismos: términos técnicos o especializados del período
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

_PROMPT = """\
Eres un lexicógrafo especializado en español colombiano de los años 1930-1940.

Analiza el siguiente fragmento de texto y extrae vocabulario de interés histórico-lingüístico.

Responde ÚNICAMENTE con JSON válido (sin markdown):
{
  "arcaismos": [{"palabra": "...", "definicion": "...", "ejemplo": "..."}],
  "neologismos": [{"palabra": "...", "origen": "...", "contexto": "..."}],
  "colombianismos": [{"palabra": "...", "significado": "...", "region": "..."}],
  "tecnicismos": [{"palabra": "...", "campo": "...", "definicion": "..."}]
}

Definiciones de categorías:
- arcaismos: palabras con ortografía o uso que ya no son estándar ("habia", "vió", "á" como preposición)
- neologismos: extranjerismos, anglicismos, galicismos o tecnicismos nuevos adoptados en la época
- colombianismos: expresiones propias de Colombia o Latinoamérica no comunes en el español peninsular
- tecnicismos: vocabulario especializado de cualquier campo (medicina, política, industria, cine, radio)

Máximo 5 entradas por categoría. Solo incluir palabras realmente presentes en el texto.

Texto:
{texto}
"""


def extraer_lexico(
    texto: str,
    api_key: str,
    modelo: str = "claude-haiku-4-5-20251001",
) -> dict:
    """
    Extrae vocabulario de interés histórico-lingüístico del texto.
    Retorna dict con: arcaismos, neologismos, colombianismos, tecnicismos.
    """
    if not texto or not texto.strip():
        return {"arcaismos": [], "neologismos": [], "colombianismos": [], "tecnicismos": []}

    fragmento = texto[:6000]
    try:
        import anthropic
    except ImportError:
        raise ImportError("Instala anthropic: pip install anthropic>=0.25.0")

    client = anthropic.Anthropic(api_key=api_key)
    try:
        msg = client.messages.create(
            model=modelo,
            max_tokens=1500,
            messages=[{"role": "user", "content": _PROMPT.replace("{texto}", fragmento)}],
        )
        raw = msg.content[0].text.strip()
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception:
        return {"arcaismos": [], "neologismos": [], "colombianismos": [], "tecnicismos": []}


def construir_glosario(
    articulos: dict,
    api_key: str,
    modelo: str = "claude-haiku-4-5-20251001",
    callback: Callable[[int, int, str], None] | None = None,
) -> dict:
    """
    Construye glosario acumulado del corpus completo.

    articulos: {art_id: texto}
    Retorna: {categoria: {palabra: {info + [art_ids]}}}
    """
    glosario: dict[str, dict] = {
        "arcaismos": {},
        "neologismos": {},
        "colombianismos": {},
        "tecnicismos": {},
    }
    total = len(articulos)

    for i, (art_id, texto) in enumerate(articulos.items(), 1):
        if callback:
            callback(i, total, art_id)
        resultado = extraer_lexico(texto, api_key, modelo)
        for cat in glosario:
            for entry in resultado.get(cat, []):
                palabra = entry.get("palabra", "").strip().lower()
                if not palabra:
                    continue
                if palabra not in glosario[cat]:
                    glosario[cat][palabra] = {**entry, "articulos": []}
                if art_id not in glosario[cat][palabra]["articulos"]:
                    glosario[cat][palabra]["articulos"].append(art_id)

    return glosario


def exportar_glosario_csv(glosario: dict, ruta: Path) -> int:
    """Exporta el glosario a CSV. Retorna número total de entradas."""
    import csv

    ruta = Path(ruta)
    filas = []
    for cat, entradas in glosario.items():
        for palabra, info in entradas.items():
            arts = info.get("articulos", [])
            fila = {
                "categoria": cat,
                "palabra": palabra,
                "n_articulos": len(arts),
                "articulos": "; ".join(arts),
            }
            for campo in ("definicion", "origen", "significado", "campo", "contexto", "region"):
                if campo in info:
                    fila[campo] = info[campo]
            filas.append(fila)

    filas.sort(key=lambda r: (r["categoria"], r["palabra"]))
    campos = [
        "categoria",
        "palabra",
        "n_articulos",
        "articulos",
        "definicion",
        "origen",
        "significado",
        "campo",
        "contexto",
        "region",
    ]

    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)
    return len(filas)

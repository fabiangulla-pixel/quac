"""
core/timeline_engine.py — Generador de timeline editorial HTML interactiva.

Produce un archivo HTML standalone con vis.js (via CDN o inline-fallback)
que muestra los artículos del corpus ordenados cronológicamente,
coloreados por sección/tono, con tooltips de detalle.

Uso:
    from core.timeline_engine import generar_timeline_html
    ruta = generar_timeline_html(articulos, Path("timeline.html"), "Estampa 1939")
    import webbrowser; webbrowser.open(str(ruta))
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

# Colores por sección editorial (inspirado en paleta de prensa histórica)
_COLOR_SECCION = {
    "portada": "#E74C3C",
    "editorial": "#8E44AD",
    "politica": "#2980B9",
    "sociedad": "#27AE60",
    "cultura": "#F39C12",
    "deportes": "#16A085",
    "publicidad": "#95A5A6",
    "internacional": "#2C3E50",
    "literatura": "#D35400",
    "ciencia": "#1ABC9C",
    "variedades": "#E67E22",
}

_COLOR_TONO = {
    "celebratorio": "#27AE60",
    "critico": "#E74C3C",
    "neutro": "#7F8C8D",
    "elegiaco": "#8E44AD",
    "polemico": "#E67E22",
}

_COLOR_DEFAULT = "#3498DB"


def generar_timeline_html(
    articulos: list[dict],
    ruta: Path,
    titulo_corpus: str = "Corpus editorial",
    agrupar_por: str = "seccion",  # "seccion" | "tono" | "autor"
    callback=None,
) -> Path:
    """
    Genera un HTML standalone con timeline interactiva.

    articulos: lista de dicts con campos:
        titulo, autor, seccion, fecha (YYYY-MM-DD o YYYY-MM), tono, art_id, numero, pagina
    agrupar_por: campo que determina el color de cada item
    """
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    if callback:
        callback(0, len(articulos), "Preparando timeline…")

    items = []
    grupos_vistos: dict[str, str] = {}  # nombre → color

    for i, art in enumerate(articulos):
        if callback and i % 10 == 0:
            callback(i, len(articulos), art.get("titulo", "")[:40])

        # Fecha
        fecha_raw = art.get("fecha") or art.get("fecha_publicacion") or ""
        fecha_vis = _normalizar_fecha(fecha_raw)
        if not fecha_vis:
            continue

        # Color según agrupación
        clave = (art.get(agrupar_por) or "").lower().strip()
        if agrupar_por == "seccion":
            color = _COLOR_SECCION.get(clave, _COLOR_DEFAULT)
        elif agrupar_por == "tono":
            color = _COLOR_TONO.get(clave, _COLOR_DEFAULT)
        else:
            # Asignar color estable por hash del valor
            if clave not in grupos_vistos:
                paleta = [
                    "#3498DB",
                    "#E74C3C",
                    "#27AE60",
                    "#F39C12",
                    "#8E44AD",
                    "#16A085",
                    "#E67E22",
                    "#2C3E50",
                ]
                grupos_vistos[clave] = paleta[len(grupos_vistos) % len(paleta)]
            color = grupos_vistos[clave]

        titulo = art.get("titulo") or "(sin título)"
        autor = art.get("autor") or "Anónimo"
        seccion = art.get("seccion") or ""
        tono = art.get("tono") or ""
        numero = art.get("numero") or ""
        art_id = art.get("art_id") or str(i)

        tooltip = (
            f"<b>{titulo}</b><br>"
            f"Por: {autor}<br>"
            f"Sección: {seccion}<br>"
            f"Número: {numero}<br>" + (f"Tono: {tono}<br>" if tono else "")
        )

        items.append(
            {
                "id": art_id,
                "content": f"<span title='{titulo}'>{titulo[:35]}{'…' if len(titulo) > 35 else ''}</span>",
                "start": fecha_vis,
                "title": tooltip,
                "style": f"background-color:{color};border-color:{color};color:#fff;",
                "group": clave or "otros",
            }
        )

    grupos_html = sorted({it["group"] for it in items})

    items_json = json.dumps(items, ensure_ascii=False)
    grupos_json = json.dumps(
        [{"id": g, "content": g.capitalize()} for g in grupos_html],
        ensure_ascii=False,
    )
    fecha_export = datetime.now().strftime("%d/%m/%Y %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Timeline — {titulo_corpus}</title>
<script src="https://unpkg.com/vis-timeline@latest/standalone/umd/vis-timeline-graph2d.min.js"></script>
<link href="https://unpkg.com/vis-timeline@latest/styles/vis-timeline-graph2d.min.css" rel="stylesheet">
<style>
  body {{ font-family: 'Segoe UI', sans-serif; background:#0d1117; color:#cdd6f4; margin:0; padding:16px; }}
  h1   {{ font-size:1.3em; color:#58a6ff; margin-bottom:4px; }}
  .meta{{ color:#8b949e; font-size:.85em; margin-bottom:16px; }}
  #timeline {{ border:1px solid #30363d; border-radius:8px; background:#161b22; }}
  .vis-item {{ font-size:11px !important; }}
  .vis-item.vis-selected {{ border-width:3px !important; }}
</style>
</head>
<body>
<h1>📅 {titulo_corpus} — Timeline editorial</h1>
<p class="meta">Generado por Bashkar Station · {fecha_export} · {len(items)} artículos</p>
<div id="timeline"></div>
<script>
var items  = new vis.DataSet({items_json});
var groups = new vis.DataSet({grupos_json});
var opts = {{
  groupOrder: 'content',
  orientation: {{ axis:'top' }},
  stack: true,
  showMajorLabels: true,
  showMinorLabels: true,
  zoomKey: 'ctrlKey',
  tooltip: {{ followMouse: true, overflowMethod: 'cap' }},
}};
var tl = new vis.Timeline(
  document.getElementById('timeline'), items, groups, opts);
</script>
</body>
</html>"""

    ruta.write_text(html, encoding="utf-8")
    if callback:
        callback(len(articulos), len(articulos), "Timeline exportada")
    return ruta


def _normalizar_fecha(fecha: str) -> str:
    """Convierte fecha a formato YYYY-MM-DD que vis.js entiende."""
    if not fecha:
        return ""
    fecha = str(fecha).strip()
    # Ya en formato ISO
    if len(fecha) >= 10 and fecha[4] == "-":
        return fecha[:10]
    # Solo año
    if fecha.isdigit() and len(fecha) == 4:
        return f"{fecha}-01-01"
    # YYYY-MM
    if len(fecha) == 7 and fecha[4] == "-":
        return f"{fecha}-01"
    return ""

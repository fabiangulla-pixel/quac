"""lineas_tiempo.py — Series temporales DIARIAS de ¡Quac! para detectar
patrones, picos y cambios de tendencia a lo largo de la campaña.

Complementa analisis_avanzado.series_temporales (que agrega por MES, útil para
corpus largos). Aquí el grano es el DÍA, con MEDIA MÓVIL para ver la tendencia
sin el ruido diario — pensado para ventanas electorales cortas (p. ej. 16 días).

Cuatro señales en el tiempo:
  1. sesgo medio→candidato  — tono de UN medio o GRUPO de medios hacia cada
     candidato, día a día → ¿cambia a quién favorece?
  2. volumen                — nº de notas por día (total y por candidato) → picos.
  3. tono por candidato     — tono medio del corpus hacia cada candidato por día.
  4. encuadre               — marcos dominantes por día (% del día).

Todo se calcula sobre por_nota (lo que produce el pipeline). No toca los motores
de Bashkar.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable


def _dia(fecha: str) -> str:
    """Normaliza a AAAA-MM-DD (admite ISO con hora)."""
    f = (fecha or "").strip()
    return f[:10] if len(f) >= 10 else ""


def _rango_dias(
    dias: Iterable[str], desde: str | None = None, hasta: str | None = None
) -> list[str]:
    """Lista completa de días entre el mínimo y el máximo (rellena huecos).

    Si ``desde``/``hasta`` se dan (ventana del perfil), el rango se ACOTA a esa
    ventana — así la línea de tiempo muestra solo el período del estudio y no se
    estira a años por culpa de fechas-basura del scraping (2000, 2005…).
    """
    from datetime import date, timedelta

    ds = sorted({d for d in dias if d})
    if not ds:
        return []
    try:
        ini = date.fromisoformat(ds[0])
        fin = date.fromisoformat(ds[-1])
    except ValueError:
        return ds
    # Acotar a la ventana configurada por el usuario (si existe).
    try:
        if desde:
            ini = max(ini, date.fromisoformat(desde))
        if hasta:
            fin = min(fin, date.fromisoformat(hasta))
    except ValueError:
        pass
    if ini > fin:
        # la ventana no intersecta los datos: caer al rango real de los datos
        ini, fin = date.fromisoformat(ds[0]), date.fromisoformat(ds[-1])
    out, cur = [], ini
    while cur <= fin:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def _media_movil(serie: list[float | None], ventana: int = 3) -> list[float | None]:
    """Media móvil centrada que ignora None (días sin dato)."""
    n = len(serie)
    out: list[float | None] = []
    rad = ventana // 2
    for i in range(n):
        vals = [
            serie[j] for j in range(max(0, i - rad), min(n, i + rad + 1)) if serie[j] is not None
        ]
        out.append(round(sum(vals) / len(vals), 3) if vals else None)
    return out


def _candidatos_formas(perfil: dict) -> dict:
    formas = {}
    for e in (perfil or {}).get("entidades", []):
        if e.get("tipo") == "candidato":
            formas[e["nombre"]] = [e["nombre"]] + e.get("variantes", [])
    return formas


def series_diarias(
    por_nota: dict, perfil: dict, *, medios: Iterable[str] | None = None, ventana_mm: int = 3
) -> dict:
    """Calcula las series diarias. Si ``medios`` se da, restringe a ese medio o
    grupo de medios (coincidencia por subcadena, p. ej. 'eltiempo' o
    ['eltiempo.com','semana.com']) — así se ve si UN grupo cambia su tendencia.

    Devuelve un dict listo para graficar (eje = días, series = listas alineadas).
    """
    import sentimiento_politico as sp

    filtro = None
    if medios:
        ms = [medios] if isinstance(medios, str) else list(medios)
        ms = [m.lower() for m in ms if m]
        filtro = lambda medio: any(x in (medio or "").lower() for x in ms)

    cand_formas = _candidatos_formas(perfil)
    candidatos = list(cand_formas)

    # Acumuladores por día
    volumen = defaultdict(int)  # día → n
    vol_cand = {c: defaultdict(int) for c in candidatos}  # cand → día → n
    tono_cand = {c: defaultdict(list) for c in candidatos}  # cand → día → [scores]
    frames_dia = defaultdict(lambda: defaultdict(int))  # día → frame → n

    todos_dias = set()
    for r in por_nota.values():
        medio = r.get("medio") or "?"
        if filtro and not filtro(medio):
            continue
        dia = _dia(r.get("fecha") or "")
        if not dia:
            continue
        todos_dias.add(dia)
        volumen[dia] += 1
        # encuadre del día
        fr = (r.get("frame") or {}).get("frame_dominante")
        if fr:
            frames_dia[dia][fr] += 1
        # tono y volumen por candidato (polaridad_hacia sobre el cuerpo o titular)
        texto = r.get("cuerpo") or r.get("titular") or ""
        for cand, formas in cand_formas.items():
            ph = sp.polaridad_hacia(texto, formas)
            if ph.get("n_menciones", 0) > 0:
                vol_cand[cand][dia] += 1
                tono_cand[cand][dia].append(ph["score"])

    # Acotar la línea de tiempo a la ventana de fechas configurada en el perfil
    # (lo que el usuario pone en Configuración manda sobre el rango mostrado).
    _ventana = (perfil or {}).get("ventana", {}) if isinstance(perfil, dict) else {}
    dias = _rango_dias(todos_dias, desde=_ventana.get("desde"), hasta=_ventana.get("hasta"))

    def serie_int(d):
        return [d.get(x, 0) for x in dias]

    def serie_tono(acc):
        return [round(sum(acc[x]) / len(acc[x]), 3) if acc.get(x) else None for x in dias]

    # 1) sesgo medio→candidato por día = tono(cand A) - tono(cand B)
    sesgo = []
    if len(candidatos) >= 2:
        a, b = candidatos[0], candidatos[1]
        ta, tb = serie_tono(tono_cand[a]), serie_tono(tono_cand[b])
        for x, y in zip(ta, tb):
            sesgo.append(round(x - y, 3) if (x is not None and y is not None) else None)

    tono_por_cand = {c: serie_tono(tono_cand[c]) for c in candidatos}

    return {
        "dias": dias,
        "candidatos": candidatos,
        "ambito": (("grupo: " + ", ".join(ms)) if filtro else "todo el corpus"),
        # 2) volumen
        "volumen": serie_int(volumen),
        "volumen_por_candidato": {c: serie_int(vol_cand[c]) for c in candidatos},
        # 3) tono por candidato (+ media móvil)
        "tono_por_candidato": tono_por_cand,
        "tono_por_candidato_mm": {
            c: _media_movil(tono_por_cand[c], ventana_mm) for c in candidatos
        },
        # 1) sesgo (+ media móvil) — >0 favorece al primer candidato
        "sesgo": sesgo,
        "sesgo_mm": _media_movil(sesgo, ventana_mm) if sesgo else [],
        # 4) encuadre: % de cada frame por día
        "frames": _frames_pct(frames_dia, dias),
        "ventana_media_movil": ventana_mm,
    }


def _frames_pct(frames_dia: dict, dias: list[str]) -> dict:
    """Convierte conteos de frame/día en porcentaje del día (series por frame)."""
    todos = set()
    for d in frames_dia.values():
        todos |= set(d)
    series = {fr: [] for fr in todos}
    for dia in dias:
        conteo = frames_dia.get(dia, {})
        tot = sum(conteo.values()) or 1
        for fr in todos:
            series[fr].append(round(100 * conteo.get(fr, 0) / tot, 1))
    return series


def picos_volumen(
    serie_dias: list[str], serie_vol: list[int], umbral_sigma: float = 1.5
) -> list[dict]:
    """Detecta días-pico: volumen por encima de media + umbral·desviación.
    Útil para señalar automáticamente los días de mayor cobertura."""
    if not serie_vol:
        return []
    n = len(serie_vol)
    media = sum(serie_vol) / n
    var = sum((v - media) ** 2 for v in serie_vol) / n
    sd = var**0.5
    umbral = media + umbral_sigma * sd
    return [
        {"dia": d, "volumen": v} for d, v in zip(serie_dias, serie_vol) if v > umbral and v > media
    ]

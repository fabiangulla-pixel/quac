"""Registro de fuentes sociales + filtro por métricas de audiencia."""

from __future__ import annotations

from .base import Publicacion
from .tiktok import TikTok
from .x_twitter import XTwitter
from .youtube import YouTube

_FUENTES = {"youtube": YouTube, "tiktok": TikTok, "x": XTwitter}


def fuente_social(plataforma: str, api_key: str | None = None):
    cls = _FUENTES.get(plataforma.lower())
    return cls(api_key=api_key) if cls else None


def fuentes_disponibles(claves: dict | None = None) -> list[str]:
    """Plataformas usables ahora (con su credencial/condición cumplida)."""
    claves = claves or {}
    out = []
    for nombre, cls in _FUENTES.items():
        f = cls(api_key=claves.get(nombre))
        try:
            if f.disponible():
                out.append(nombre)
        except Exception:
            pass
    return out


def buscar_social(
    plataformas, query, *, claves=None, desde=None, hasta=None, max_por_fuente=50, callback=None
) -> list[Publicacion]:
    """Busca en varias plataformas y agrega las publicaciones."""
    claves = claves or {}
    pubs = []
    for p in plataformas:
        f = fuente_social(p, api_key=claves.get(p))
        if not f or not f.disponible():
            if callback:
                callback(f"  {p}: no disponible (falta credencial/condición)")
            continue
        try:
            pubs += f.buscar(
                query, desde=desde, hasta=hasta, max_resultados=max_por_fuente, callback=callback
            )
        except Exception as exc:
            if callback:
                callback(f"  {p} falló: {exc}")
    return pubs


# ── Filtro por métricas de audiencia (lo que pidió el investigador) ─────────


def publicacion_a_nota(p: Publicacion) -> dict:
    """Convierte una Publicacion (red social) al esquema de 'nota' del pipeline.

    Así el corpus social se analiza con el MISMO pipeline que la prensa (NER,
    sentimiento, framing, red…). El 'medio' es la plataforma; se conservan las
    métricas de audiencia en campos extra para el filtrado y el dashboard.
    """
    return {
        "url": p.url or f"{p.plataforma}:{p.id}",
        "medio": f"{p.plataforma}",
        "titular": (p.texto or "")[:120],
        "cuerpo": p.texto or "",
        "autor": p.autor,
        "fecha_publicacion": p.fecha,
        "seccion": p.tipo,
        "metodo_extraccion": "social_api",
        "screenshot_path": "",
        "hash_contenido": p.hash_contenido,
        # métricas de audiencia (no en prensa) para filtrar/ponderar
        "vistas": p.vistas,
        "likes": p.likes,
        "comentarios": p.comentarios,
        "compartidos": p.compartidos,
        "plataforma": p.plataforma,
    }


def filtrar_por_audiencia(
    publicaciones, *, min_vistas=0, min_interacciones=0, min_likes=0, top_n=None
) -> list[Publicacion]:
    """Conserva solo publicaciones que superan umbrales de audiencia/interacción,
    y opcionalmente recorta a las top_n por impacto. Permite quedarse con lo
    relevante (lo que mucha gente vio/compartió), no con el ruido."""
    out = [
        p
        for p in publicaciones
        if p.vistas >= min_vistas and p.interacciones >= min_interacciones and p.likes >= min_likes
    ]
    out.sort(key=lambda p: (p.vistas, p.interacciones), reverse=True)
    return out[:top_n] if top_n else out

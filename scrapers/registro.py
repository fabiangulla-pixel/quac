"""Registro central dominio → scraper.

``scraper_para_url`` devuelve una instancia del adaptador adecuado para una URL,
o ``ScraperGenerico`` (trafilatura) si el dominio no está registrado, de modo
que ¡Quac! pueda ingerir CUALQUIER medio colombiano aunque no tenga adaptador
dedicado todavía.
"""

from __future__ import annotations

from urllib.parse import urlparse

from .base import ScraperBase, ScraperGenerico
from .medios import ADAPTADORES

# dominio → clase de scraper
REGISTRO: dict[str, type[ScraperBase]] = {}
for _cls in ADAPTADORES:
    for _dom in _cls.DOMINIOS:
        REGISTRO[_dom] = _cls


def scraper_para_url(url: str, **kwargs) -> ScraperBase:
    """Instancia el adaptador cuyo dominio coincide; si no, el genérico."""
    host = urlparse(url).netloc.lower().replace("www.", "")
    for dom, cls in REGISTRO.items():
        if dom in host:
            return cls(**kwargs)
    return ScraperGenerico(**kwargs)


def listar_medios() -> list[dict]:
    """Lista de medios con adaptador dedicado (para mostrar en CLI/UI)."""
    vistos = []
    for cls in ADAPTADORES:
        vistos.append({"medio": cls.MEDIO, "dominios": list(cls.DOMINIOS)})
    return vistos

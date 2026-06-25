"""Capa de ingesta web de ¡Quac! — scraping de prensa colombiana contemporánea.

Diseño:
  - ``ScraperBase``: interfaz común (patrón Strategy). Un adaptador por medio.
  - Cada adaptador define selectores propios y SIEMPRE cae a una extracción
    genérica con ``trafilatura`` si los selectores fallan (anti-fragilidad).
  - ``REGISTRO`` mapea dominio → clase de scraper. ``scraper_para_url`` elige
    el adaptador adecuado, o el genérico si el dominio no está registrado.

Ética/legal: solo contenido público, con fines de investigación académica.
Se respeta ``robots.txt`` y un rate limit por defecto. No se evaden paywalls.
Cada nota guarda la fecha de captura para trazabilidad.
"""

from .base import Nota, ScraperBase, ScraperGenerico
from .registro import REGISTRO, listar_medios, scraper_para_url

__all__ = [
    "Nota",
    "ScraperBase",
    "ScraperGenerico",
    "REGISTRO",
    "scraper_para_url",
    "listar_medios",
]

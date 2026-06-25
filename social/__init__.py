"""Capa de redes sociales de ¡Quac! — corpus social con métricas de audiencia.

Mismo patrón Strategy que la prensa (scrapers/): una interfaz común
``SocialBase`` y un adaptador por plataforma (YouTube, TikTok, X…). Cada
publicación se modela como ``Publicacion`` con sus MÉTRICAS (vistas, likes,
comentarios, compartidos), para poder filtrar por audiencia/interacción como en
la prensa se filtra por calidad.

Realidad de las APIs (2026):
  - YouTube: API oficial gratuita (cuota diaria). La más sólida.
  - TikTok: Research API (gratis, requiere afiliación académica y aprobación).
  - X/Twitter: API cerrada/cara; alternativa = captura vía la sesión de Chrome
    del usuario (frágil, zona gris de ToS) para volúmenes pequeños.

Ética: solo contenido público, con fines de investigación; respetar ToS y
límites de cada plataforma; no recolectar datos personales más allá de lo
público necesario.
"""

from .base import Publicacion, SocialBase
from .registro import (
    buscar_social,
    filtrar_por_audiencia,
    fuente_social,
    fuentes_disponibles,
    publicacion_a_nota,
)

__all__ = [
    "Publicacion",
    "SocialBase",
    "fuente_social",
    "fuentes_disponibles",
    "buscar_social",
    "filtrar_por_audiencia",
    "publicacion_a_nota",
]

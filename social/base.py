"""Interfaz común de las fuentes sociales + modelo Publicacion con métricas."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime


@dataclass
class Publicacion:
    """Una publicación de red social (post, video, comentario, tuit).

    Unifica plataformas distintas en un esquema común. Las MÉTRICAS de audiencia
    permiten filtrar por relevancia (igual que la prensa por calidad): una
    publicación con muchas vistas/interacciones pesa más en el corpus.
    """

    id: str  # id nativo de la plataforma
    plataforma: str  # youtube | tiktok | x | ...
    url: str = ""
    autor: str = ""  # canal / cuenta
    texto: str = ""  # cuerpo (descripción, transcripción, tuit, comentario)
    fecha: str = ""  # ISO-8601
    tipo: str = "post"  # post | video | comentario | tuit
    # --- métricas de audiencia / interacción ---
    vistas: int = 0
    likes: int = 0
    comentarios: int = 0
    compartidos: int = 0
    seguidores_autor: int = 0  # tamaño de audiencia del autor (si se conoce)
    fecha_captura: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    hash_contenido: str = ""

    def __post_init__(self):
        if not self.hash_contenido and self.texto:
            base = " ".join(self.texto.lower().split())
            self.hash_contenido = hashlib.sha256(base.encode()).hexdigest()[:16]

    @property
    def interacciones(self) -> int:
        """Suma de interacciones (proxy de impacto)."""
        return self.likes + self.comentarios + self.compartidos

    @property
    def n_palabras(self) -> int:
        return len(self.texto.split())

    def to_dict(self) -> dict:
        return asdict(self)


class SocialBase:
    """Interfaz común de una fuente social (patrón Strategy, como ScraperBase).

    Subclases concretas implementan ``buscar`` para una plataforma. Todas
    devuelven ``Publicacion`` con métricas, normalizando el esquema.
    """

    PLATAFORMA = "desconocida"
    REQUIERE_KEY = False

    def __init__(self, api_key: str | None = None, **kwargs):
        self.api_key = api_key

    def disponible(self) -> bool:
        """¿Está la fuente lista para usarse (deps/credenciales)?"""
        return not self.REQUIERE_KEY or bool(self.api_key)

    def buscar(
        self,
        query: str,
        *,
        desde: str | None = None,
        hasta: str | None = None,
        max_resultados: int = 50,
        callback=None,
    ) -> list[Publicacion]:
        """Busca publicaciones sobre ``query``. Implementar en subclases."""
        raise NotImplementedError

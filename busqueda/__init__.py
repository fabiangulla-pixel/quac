"""Capa de búsqueda de ¡Quac! — encuentra URLs de notas a partir de criterios.

A diferencia de pasar URLs a mano, el usuario define QUÉ buscar (términos,
rango de fechas, entidades de interés) y ¡Quac! descubre las notas:

  CriteriosBusqueda  → qué buscar (modelo de datos validado)
  buscar(criterios)  → lista de Resultado (url, titular, fecha, medio, fuente)

Cascada de fuentes (la primera que devuelva resultados gana, se acumulan):
  1. buscador interno de cada medio (cuando hay adaptador),
  2. Google News RSS (universal, gratis, sin API key),
  3. site-search en un buscador web (último recurso).
"""

from .criterios import CriteriosBusqueda, EntidadInteres
from .motor import Resultado, buscar, buscar_masivo

__all__ = ["CriteriosBusqueda", "EntidadInteres", "buscar", "buscar_masivo", "Resultado"]

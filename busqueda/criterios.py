"""Modelo de criterios de búsqueda (el "formulario" que llena el investigador).

Mapea 1:1 a la GUI: caja de términos, fechas ida/regreso, y entidades de
interés (nombres con variantes, lugares, instituciones, hechos).

Las entidades de interés se usan para CUATRO cosas (ver motor/pipeline):
  - expandir la búsqueda (cada variante es un término más),
  - filtrar resultados (conservar solo notas que mencionan alguna),
  - sembrar la canonicalización (agrupar variantes con certeza),
  - resaltar en el análisis (marcar en red/frecuencias/reportes).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

TIPOS_ENTIDAD = ("persona", "lugar", "institucion", "hecho", "otro")


@dataclass
class EntidadInteres:
    """Una entidad que el investigador quiere rastrear, con sus variantes."""

    nombre: str  # forma canónica preferida
    tipo: str = "persona"  # persona | lugar | institucion | hecho | otro
    variantes: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.tipo not in TIPOS_ENTIDAD:
            self.tipo = "otro"

    @property
    def todas_las_formas(self) -> list[str]:
        """Nombre canónico + variantes, sin duplicados, preservando orden."""
        formas = [self.nombre, *self.variantes]
        vistos, out = set(), []
        for f in formas:
            f = (f or "").strip()
            if f and f.lower() not in vistos:
                vistos.add(f.lower())
                out.append(f)
        return out

    def menciona(self, texto: str) -> bool:
        low = (texto or "").lower()
        return any(f.lower() in low for f in self.todas_las_formas)


def _parse_fecha(valor) -> date | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, date):
        return valor
    if isinstance(valor, datetime):
        return valor.date()
    # admite "2026-06-01" o "01/06/2026"
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(valor).strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Fecha no reconocida: {valor!r} (usa AAAA-MM-DD)")


@dataclass
class CriteriosBusqueda:
    """Qué buscar. Es el contrato entre la GUI/CLI y el motor de búsqueda."""

    terminos: list[str] = field(default_factory=list)  # frases libres
    desde: date | None = None  # fecha de "ida"
    hasta: date | None = None  # fecha de "regreso"
    medios: list[str] = field(default_factory=list)  # dominios; vacío = todos
    entidades: list[EntidadInteres] = field(default_factory=list)
    max_resultados: int = 50
    # cómo usar las entidades (las 4 palancas, todas activas por defecto)
    expandir_busqueda: bool = True
    filtrar_por_entidades: bool = False  # opt-in: puede reducir mucho
    idioma: str = "es"
    pais: str = "CO"

    def __post_init__(self):
        self.desde = _parse_fecha(self.desde)
        self.hasta = _parse_fecha(self.hasta)
        if self.desde and self.hasta and self.desde > self.hasta:
            raise ValueError("La fecha 'desde' es posterior a 'hasta'.")

    # ---- términos efectivos ------------------------------------------------

    def terminos_efectivos(self) -> list[str]:
        """Términos del usuario + (si expandir) las formas de cada entidad."""
        terms = [t.strip() for t in self.terminos if t and t.strip()]
        if self.expandir_busqueda:
            for ent in self.entidades:
                terms.extend(ent.todas_las_formas)
        # únicos preservando orden
        vistos, out = set(), []
        for t in terms:
            if t.lower() not in vistos:
                vistos.add(t.lower())
                out.append(t)
        return out

    def query_principal(self) -> str:
        """Una sola cadena de consulta (términos del usuario unidos)."""
        base = [t.strip() for t in self.terminos if t and t.strip()]
        return " ".join(base) if base else (self.entidades[0].nombre if self.entidades else "")

    def en_rango(self, fecha_iso: str) -> bool:
        """True si una fecha ISO cae dentro de [desde, hasta] (o si no hay límites)."""
        if not (self.desde or self.hasta):
            return True
        f = _parse_fecha(fecha_iso[:10]) if fecha_iso else None
        if f is None:
            return True  # sin fecha → no se descarta (se marca dudosa luego)
        if self.desde and f < self.desde:
            return False
        if self.hasta and f > self.hasta:
            return False
        return True

    def menciona_entidad(self, texto: str) -> bool:
        return any(e.menciona(texto) for e in self.entidades)

    # ---- (de)serialización para la GUI / archivos de criterios -------------

    def to_dict(self) -> dict:
        d = asdict(self)
        d["desde"] = self.desde.isoformat() if self.desde else None
        d["hasta"] = self.hasta.isoformat() if self.hasta else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> CriteriosBusqueda:
        ents = [EntidadInteres(**e) if isinstance(e, dict) else e for e in d.get("entidades", [])]
        return cls(
            terminos=d.get("terminos", []),
            desde=d.get("desde"),
            hasta=d.get("hasta"),
            medios=d.get("medios", []),
            entidades=ents,
            max_resultados=d.get("max_resultados", 50),
            expandir_busqueda=d.get("expandir_busqueda", True),
            filtrar_por_entidades=d.get("filtrar_por_entidades", False),
            idioma=d.get("idioma", "es"),
            pais=d.get("pais", "CO"),
        )

    def guardar(self, ruta: str | Path):
        Path(ruta).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @classmethod
    def cargar(cls, ruta: str | Path) -> CriteriosBusqueda:
        return cls.from_dict(json.loads(Path(ruta).read_text(encoding="utf-8")))

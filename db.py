"""Persistencia SQLite por proyecto (mismo patrón que Bashkar Station).

Una base de datos por proyecto de investigación. Tabla ``notas`` con la nota
cruda + resultados de análisis (sentimiento, NER, etc.) almacenados como JSON.

Deduplicación:
  - de URL: ``url`` es UNIQUE → ``INSERT OR IGNORE`` evita reinsertar.
  - de contenido: ``hash_contenido`` indexado → ``existe_contenido`` detecta la
    misma nota republicada en otro medio/URL.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from scrapers.base import Nota

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS notas (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    url                 TEXT UNIQUE NOT NULL,
    medio               TEXT NOT NULL,
    titular             TEXT,
    cuerpo              TEXT,
    autor               TEXT,
    fecha_publicacion   TEXT,
    seccion             TEXT,
    fecha_captura       TEXT,
    metodo_extraccion   TEXT,
    screenshot_path     TEXT,
    hash_contenido      TEXT,
    -- resultados de análisis (JSON; NULL hasta que se analiza)
    sentimiento         TEXT,
    ner                 TEXT,
    confianza           TEXT,
    -- análisis social con transformer (pysentimiento): sentimiento+emoción+
    -- odio+ironía. Se llena por bloques, persistente y reanudable. NULL = pendiente.
    social_transformer  TEXT
);
CREATE INDEX IF NOT EXISTS idx_notas_hash   ON notas(hash_contenido);
CREATE INDEX IF NOT EXISTS idx_notas_medio  ON notas(medio);
CREATE INDEX IF NOT EXISTS idx_notas_fecha  ON notas(fecha_publicacion);
"""

_CAMPOS_NOTA = (
    "url",
    "medio",
    "titular",
    "cuerpo",
    "autor",
    "fecha_publicacion",
    "seccion",
    "fecha_captura",
    "metodo_extraccion",
    "screenshot_path",
    "hash_contenido",
)


class BaseDatos:
    def __init__(self, ruta: str | Path):
        self.ruta = Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.ruta))
        self.con.row_factory = sqlite3.Row
        self.con.executescript(_ESQUEMA)
        self._migrar_columnas()
        self.con.commit()

    def _migrar_columnas(self):
        """Añade columnas nuevas a BD ya creadas (migración suave, idempotente)."""
        cols = {r["name"] for r in self.con.execute("PRAGMA table_info(notas)")}
        if "social_transformer" not in cols:
            self.con.execute("ALTER TABLE notas ADD COLUMN social_transformer TEXT")

    def close(self):
        self.con.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---- escritura --------------------------------------------------------

    def existe_url(self, url: str) -> bool:
        cur = self.con.execute("SELECT 1 FROM notas WHERE url = ?", (url,))
        return cur.fetchone() is not None

    def existe_contenido(self, hash_contenido: str) -> bool:
        if not hash_contenido:
            return False
        cur = self.con.execute("SELECT 1 FROM notas WHERE hash_contenido = ?", (hash_contenido,))
        return cur.fetchone() is not None

    def guardar_nota(self, nota: Nota, dedupe_contenido: bool = True) -> bool:
        """Inserta una nota. Devuelve True si se insertó, False si era duplicada."""
        if self.existe_url(nota.url):
            return False
        if dedupe_contenido and self.existe_contenido(nota.hash_contenido):
            return False
        d = nota.to_dict()
        cols = ", ".join(_CAMPOS_NOTA)
        ph = ", ".join("?" for _ in _CAMPOS_NOTA)
        try:
            self.con.execute(
                f"INSERT INTO notas ({cols}) VALUES ({ph})",
                tuple(d.get(c) for c in _CAMPOS_NOTA),
            )
            self.con.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def guardar_muchas(self, notas: Iterable[Nota]) -> dict:
        """Inserta varias notas; devuelve {insertadas, duplicadas}."""
        ins = dup = 0
        for n in notas:
            if self.guardar_nota(n):
                ins += 1
            else:
                dup += 1
        return {"insertadas": ins, "duplicadas": dup}

    def guardar_analisis(self, url: str, *, sentimiento=None, ner=None, confianza=None):
        """Adjunta resultados de análisis (dicts) a una nota existente."""
        sets, vals = [], []
        for col, val in (("sentimiento", sentimiento), ("ner", ner), ("confianza", confianza)):
            if val is not None:
                sets.append(f"{col} = ?")
                vals.append(json.dumps(val, ensure_ascii=False))
        if not sets:
            return
        vals.append(url)
        self.con.execute(f"UPDATE notas SET {', '.join(sets)} WHERE url = ?", vals)
        self.con.commit()

    def guardar_social_transformer(self, url: str, social: dict):
        """Guarda el análisis social (pysentimiento) de una nota. Persistente."""
        self.con.execute(
            "UPDATE notas SET social_transformer = ? WHERE url = ?",
            (json.dumps(social, ensure_ascii=False), url),
        )
        self.con.commit()

    def notas_sin_transformer(self) -> list[dict]:
        """Notas que aún NO tienen análisis transformer (para reanudar bloques)."""
        cur = self.con.execute(
            "SELECT * FROM notas WHERE social_transformer IS NULL "
            "AND cuerpo IS NOT NULL AND length(cuerpo) > 0 ORDER BY id"
        )
        return [dict(r) for r in cur.fetchall()]

    def progreso_transformer(self) -> dict:
        """Cuántas notas tienen ya análisis transformer vs. total con cuerpo."""
        total = self.con.execute(
            "SELECT COUNT(*) FROM notas WHERE cuerpo IS NOT NULL AND length(cuerpo) > 0"
        ).fetchone()[0]
        hechas = self.con.execute(
            "SELECT COUNT(*) FROM notas WHERE social_transformer IS NOT NULL"
        ).fetchone()[0]
        return {"hechas": hechas, "total": total, "faltan": total - hechas}

    def social_transformer_todas(self) -> dict:
        """Devuelve {url: dict_social} de todas las notas ya analizadas con
        transformer, para compilar/ponderar los resultados de todos los bloques."""
        out = {}
        for r in self.con.execute(
            "SELECT url, social_transformer FROM notas WHERE social_transformer IS NOT NULL"
        ):
            try:
                out[r["url"]] = json.loads(r["social_transformer"])
            except (ValueError, TypeError):
                continue
        return out

    # ---- limpieza del corpus ---------------------------------------------

    def respaldar(self) -> Path:
        """Copia la BD a un archivo .bak con marca de tiempo. Devuelve la ruta."""
        import datetime
        import shutil

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = self.ruta.with_suffix(f".{ts}.bak")
        self.con.commit()
        shutil.copy2(self.ruta, destino)
        return destino

    def contar_irrelevantes(self, obligatorias, excluir=None) -> dict:
        """Cuenta cuántas notas se BORRARÍAN: las que NO mencionan ninguna de
        ``obligatorias`` (en titular+cuerpo) o que mencionan alguna de
        ``excluir``. No borra nada. Búsqueda sin acentos/mayúsculas."""
        oblig, excl = self._normalizar_terminos(obligatorias, excluir)
        total = self.contar()
        a_borrar = 0
        for r in self.con.execute("SELECT titular, cuerpo FROM notas"):
            txt = self._norm((r["titular"] or "") + " " + (r["cuerpo"] or ""))
            irrelevante = (oblig and not any(t in txt for t in oblig)) or (
                excl and any(t in txt for t in excl)
            )
            if irrelevante:
                a_borrar += 1
        return {"total": total, "a_borrar": a_borrar, "quedan": total - a_borrar}

    def purgar_irrelevantes(self, obligatorias, excluir=None, respaldar=True) -> dict:
        """BORRA de la BD las notas irrelevantes (mismo criterio que
        contar_irrelevantes). Respalda antes por seguridad. Devuelve
        {borradas, quedan, respaldo}."""
        respaldo = str(self.respaldar()) if respaldar else None
        oblig, excl = self._normalizar_terminos(obligatorias, excluir)
        ids_borrar = []
        for r in self.con.execute("SELECT id, titular, cuerpo FROM notas"):
            txt = self._norm((r["titular"] or "") + " " + (r["cuerpo"] or ""))
            irrelevante = (oblig and not any(t in txt for t in oblig)) or (
                excl and any(t in txt for t in excl)
            )
            if irrelevante:
                ids_borrar.append(r["id"])
        for i in range(0, len(ids_borrar), 500):
            lote = ids_borrar[i : i + 500]
            ph = ",".join("?" for _ in lote)
            self.con.execute(f"DELETE FROM notas WHERE id IN ({ph})", lote)
        self.con.commit()
        return {"borradas": len(ids_borrar), "quedan": self.contar(), "respaldo": respaldo}

    @staticmethod
    def _norm(s):
        import unicodedata

        s = unicodedata.normalize("NFKD", str(s or "").lower())
        return "".join(c for c in s if not unicodedata.combining(c))

    @classmethod
    def _normalizar_terminos(cls, obligatorias, excluir):
        oblig = [cls._norm(t) for t in (obligatorias or []) if str(t).strip()]
        excl = [cls._norm(t) for t in (excluir or []) if str(t).strip()]
        return oblig, excl

    # ---- lectura ----------------------------------------------------------

    def todas_las_notas(self) -> list[dict]:
        cur = self.con.execute("SELECT * FROM notas ORDER BY id")
        return [dict(r) for r in cur.fetchall()]

    def notas_por_medio(self) -> dict[str, int]:
        cur = self.con.execute("SELECT medio, COUNT(*) n FROM notas GROUP BY medio ORDER BY n DESC")
        return {r["medio"]: r["n"] for r in cur.fetchall()}

    def contar(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM notas").fetchone()[0]

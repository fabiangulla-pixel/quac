"""Revisión human-in-the-loop de entidades (metodología DH: anotación validada).

Tras el NER automático, el investigador necesita poder **validar, corregir o
descartar** entidades para que el corpus sea publicable. Este módulo:

  1. Puntúa cada entidad del índice global con ``confianza_engine`` y arma una
     cola de las dudosas (amarillo/rojo).
  2. Persiste las decisiones del usuario en la tabla ``revision_entidades``
     (verificada / descartada / renombrada), con trazabilidad (quién, cuándo).
  3. Re-aplica esas decisiones al índice global en análisis futuros
     (``aplicar_revisiones``): descarta lo rechazado y fusiona renombres.

Reutiliza ``confianza_engine`` (copiado de Bashkar); no reimplementa el scoring.
"""

from __future__ import annotations

from datetime import UTC, datetime

from core import confianza_engine

# Decisiones posibles del revisor
PENDIENTE = "pendiente"
VERIFICADA = "verificada"
DESCARTADA = "descartada"
RENOMBRADA = "renombrada"

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS revision_entidades (
    nombre        TEXT NOT NULL,
    categoria     TEXT NOT NULL,
    decision      TEXT NOT NULL DEFAULT 'pendiente',
    nombre_nuevo  TEXT DEFAULT '',
    score         REAL DEFAULT 0,
    nivel         TEXT DEFAULT '',
    n_articulos   INTEGER DEFAULT 0,
    editado_por   TEXT DEFAULT '',
    fecha         TEXT DEFAULT '',
    PRIMARY KEY (nombre, categoria)
);
"""


def _asegurar_tabla(db):
    db.con.executescript(_ESQUEMA)
    db.con.commit()


def _score_entidad(nombre: str, n_articulos: int, semillas: dict | None) -> float:
    """Puntúa la confianza de una entidad SIN LLM (0–1).

    Calibrado para el caso de ¡Quac! (NER offline, sin Claude): la señal
    principal es la **frecuencia** (en cuántas notas aparece) más un bono si es
    una entidad de interés declarada por el investigador (cuenta como "en KB").

    - en KB (semilla)         → siempre confiable (1.0): el usuario la declaró.
    - en ≥3 notas             → confiable (≥0.75).
    - en 2 notas              → revisar (amarillo).
    - en 1 nota               → validar (rojo): lo más propenso a ruido NER.
    """
    if semillas:
        formas = {f.lower() for fs in semillas.values() for f in fs}
        if nombre.lower() in formas:
            return 1.0
    # frecuencia saturando: 1 nota→0.3, 2→0.55, 3→0.75, 4+→≥0.85
    return round(min(1.0, 0.05 + 0.25 * n_articulos), 3)


def construir_cola(
    indice_global: dict,
    semillas: dict | None = None,
    categorias=("personas", "organizaciones", "lugares"),
) -> list[dict]:
    """Arma la cola de entidades dudosas (nivel amarillo/rojo) para revisar."""
    cola = []
    for cat in categorias:
        entidades = indice_global.get(cat, {})
        if not isinstance(entidades, dict):
            continue
        for nombre, arts in entidades.items():
            n = len(arts)
            score = _score_entidad(nombre, n, semillas)
            nivel = confianza_engine.nivel_confianza(score)
            if nivel != confianza_engine.VERDE:  # solo dudosas
                cola.append(
                    {
                        "nombre": nombre,
                        "categoria": cat,
                        "n_articulos": n,
                        "score": score,
                        "nivel": nivel,
                        "etiqueta": confianza_engine.etiqueta_semaforo(score),
                    }
                )
    cola.sort(key=lambda d: (d["score"], -d["n_articulos"]))
    return cola


def guardar_cola(db, cola: list[dict]):
    """Persiste la cola en la BD (sin pisar decisiones ya tomadas)."""
    _asegurar_tabla(db)
    for item in cola:
        # no sobrescribir si ya hay una decisión distinta de 'pendiente'
        cur = db.con.execute(
            "SELECT decision FROM revision_entidades WHERE nombre=? AND categoria=?",
            (item["nombre"], item["categoria"]),
        )
        row = cur.fetchone()
        if row and row["decision"] != PENDIENTE:
            continue
        db.con.execute(
            "INSERT OR REPLACE INTO revision_entidades "
            "(nombre, categoria, decision, score, nivel, n_articulos) "
            "VALUES (?,?,?,?,?,?)",
            (
                item["nombre"],
                item["categoria"],
                PENDIENTE,
                item["score"],
                item["nivel"],
                item["n_articulos"],
            ),
        )
    db.con.commit()


def pendientes(db) -> list[dict]:
    _asegurar_tabla(db)
    cur = db.con.execute(
        "SELECT * FROM revision_entidades WHERE decision=? ORDER BY score, n_articulos DESC",
        (PENDIENTE,),
    )
    return [dict(r) for r in cur.fetchall()]


def decidir(
    db,
    nombre: str,
    categoria: str,
    decision: str,
    nombre_nuevo: str = "",
    editado_por: str = "usuario",
) -> bool:
    """Registra la decisión del revisor sobre una entidad."""
    if decision not in (VERIFICADA, DESCARTADA, RENOMBRADA, PENDIENTE):
        raise ValueError(f"Decisión inválida: {decision}")
    _asegurar_tabla(db)
    db.con.execute(
        "UPDATE revision_entidades SET decision=?, nombre_nuevo=?, editado_por=?, "
        "fecha=? WHERE nombre=? AND categoria=?",
        (decision, nombre_nuevo, editado_por, datetime.now(UTC).isoformat(), nombre, categoria),
    )
    db.con.commit()
    return db.con.total_changes > 0


def cargar_decisiones(db) -> dict:
    """Devuelve {(nombre,categoria): {decision, nombre_nuevo}} ya resueltas."""
    _asegurar_tabla(db)
    cur = db.con.execute(
        "SELECT nombre, categoria, decision, nombre_nuevo FROM revision_entidades "
        "WHERE decision != ?",
        (PENDIENTE,),
    )
    return {
        (r["nombre"], r["categoria"]): {
            "decision": r["decision"],
            "nombre_nuevo": r["nombre_nuevo"],
        }
        for r in cur.fetchall()
    }


def aplicar_revisiones(indice_global: dict, decisiones: dict) -> dict:
    """Aplica las decisiones del revisor al índice global.

    - DESCARTADA: elimina la entidad.
    - RENOMBRADA: fusiona sus artículos en el nombre nuevo.
    - VERIFICADA: se conserva tal cual.
    Modifica y devuelve el índice.
    """
    for (nombre, categoria), d in decisiones.items():
        entidades = indice_global.get(categoria)
        if not isinstance(entidades, dict) or nombre not in entidades:
            continue
        if d["decision"] == DESCARTADA:
            entidades.pop(nombre, None)
        elif d["decision"] == RENOMBRADA and d["nombre_nuevo"]:
            arts = entidades.pop(nombre, [])
            destino = entidades.setdefault(d["nombre_nuevo"], [])
            for a in arts:
                if a not in destino:
                    destino.append(a)
    return indice_global


def estadisticas(db) -> dict:
    _asegurar_tabla(db)
    cur = db.con.execute("SELECT decision, COUNT(*) n FROM revision_entidades GROUP BY decision")
    por = {r["decision"]: r["n"] for r in cur.fetchall()}
    return {
        "total": sum(por.values()),
        "pendientes": por.get(PENDIENTE, 0),
        "verificadas": por.get(VERIFICADA, 0),
        "descartadas": por.get(DESCARTADA, 0),
        "renombradas": por.get(RENOMBRADA, 0),
    }

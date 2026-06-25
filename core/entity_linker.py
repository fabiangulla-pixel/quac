"""
core/entity_linker.py — Entity linking a Wikidata para entidades NER.

Estrategia:
  1. Búsqueda via API pública de Wikidata (wbsearchentities) — sin autenticación.
  2. Caché local SQLite para no repetir llamadas entre sesiones.
  3. Filtrado por tipo de entidad (humano, lugar, org) para reducir falsos positivos.
  4. Desambiguación por contexto: favorece candidatos con descripción que coincida
     con el tipo de entidad NER y con el período histórico 1930-1940.
  5. Funciona 100% offline si las entidades ya están en caché.

Dependencias: solo stdlib (urllib, sqlite3, json) — sin pip adicional.
"""

import json
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# --- Constantes ---------------------------------------------------------------

_API_WIKIDATA = "https://www.wikidata.org/w/api.php"
_API_WIKIPEDIA_ES = "https://es.wikipedia.org/w/api.php"

# Tiempo máximo de espera por petición HTTP (segundos)
_TIMEOUT_HTTP = 10

# Pausa entre llamadas a la API para respetar los rate limits de Wikidata
_PAUSA_ENTRE_LLAMADAS = 0.5

# Tipos Wikidata por categoría NER
# P31 = "instancia de", Q5 = humano, Q515 = ciudad, Q6256 = país, etc.
_TIPOS_WIKIDATA = {
    "personas": ["Q5"],  # humano
    "lugares": [
        "Q515",
        "Q6256",
        "Q35657",  # ciudad, país, estado
        "Q3957",
        "Q532",
        "Q486972",  # pueblo, aldea, asentamiento
        "Q82794",
    ],  # región geográfica
    "organizaciones": [
        "Q43229",
        "Q7210356",  # organización, organización política
        "Q31855",
        "Q2385804",  # institución educativa, institución
        "Q1114461",
        "Q1093829",
    ],  # cámara, municipio
    "obras_publicaciones": [
        "Q571",
        "Q11032",  # libro, periódico
        "Q732577",
        "Q13442814",
    ],  # publicación, artículo académico
}

# Ruta por defecto para la caché (en el mismo directorio que el módulo)
_CACHE_DEFAULT = Path(__file__).parent.parent / "datos" / "entity_cache.db"


# --- Caché local --------------------------------------------------------------


class _CacheEntidades:
    """Caché SQLite para resultados de Wikidata."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS cache_wikidata (
        texto       TEXT NOT NULL,
        categoria   TEXT NOT NULL,
        resultado   TEXT,          -- JSON con el resultado o NULL si no se encontró
        consultado  REAL NOT NULL,
        PRIMARY KEY (texto, categoria)
    );
    """

    def __init__(self, ruta: str):
        self._ruta = ruta
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(ruta, check_same_thread=False)
        self._con.execute(self._SCHEMA)
        self._con.commit()

    def obtener(self, texto: str, categoria: str) -> dict | None:
        """None = no está en caché; dict vacío {} = consultado y no encontrado."""
        cur = self._con.execute(
            "SELECT resultado FROM cache_wikidata WHERE texto=? AND categoria=?",
            (texto, categoria),
        )
        fila = cur.fetchone()
        if fila is None:
            return None  # no está en caché
        return json.loads(fila[0]) if fila[0] else {}

    def guardar(self, texto: str, categoria: str, resultado: dict | None):
        val = json.dumps(resultado, ensure_ascii=False) if resultado else None
        self._con.execute(
            "INSERT OR REPLACE INTO cache_wikidata(texto, categoria, resultado, consultado)"
            " VALUES (?,?,?,?)",
            (texto, categoria, val, time.time()),
        )
        self._con.commit()

    def estadisticas(self) -> dict:
        cur = self._con.execute(
            "SELECT COUNT(*), SUM(resultado IS NOT NULL AND resultado != 'null') "
            "FROM cache_wikidata"
        )
        total, encontrados = cur.fetchone()
        return {"total": total or 0, "encontrados": encontrados or 0}

    def limpiar(self, dias: int = 90):
        """Elimina entradas con más de `dias` días de antigüedad."""
        limite = time.time() - dias * 86400
        self._con.execute("DELETE FROM cache_wikidata WHERE consultado < ?", (limite,))
        self._con.commit()


# Instancia global de caché (se inicializa con la ruta por defecto)
_cache: _CacheEntidades | None = None


def _obtener_cache(ruta: str | None = None) -> _CacheEntidades:
    global _cache
    if _cache is None or (ruta and ruta != str(_CACHE_DEFAULT)):
        _cache = _CacheEntidades(ruta or str(_CACHE_DEFAULT))
    return _cache


# --- Lógica de linking --------------------------------------------------------


def _llamar_wikidata(texto: str, tipo_entidad: str, lang: str = "es") -> list[dict]:
    """
    Llama a wbsearchentities de Wikidata.
    Retorna lista de candidatos [{id, label, description, url, rango}].

    `rango` = posición en el ranking de Wikidata (0 = el más relevante).
    Wikidata ordena por número de enlaces/sitelinks, así que el orden es una
    señal fuerte de cuál es la acepción más conocida.
    """
    params = {
        "action": "wbsearchentities",
        "format": "json",
        "search": texto,
        "language": lang,
        "uselang": lang,  # ← descripciones en el idioma pedido (no inglés)
        "limit": "8",
        "type": "item",
    }
    url = _API_WIKIDATA + "?" + urllib.parse.urlencode(params)
    headers = {"User-Agent": "BashkarStation/1.0 (contact: bashkar@icc.gov.co)"}

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=_TIMEOUT_HTTP) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return []

    candidatos = []
    for rango, item in enumerate(data.get("search", [])):
        candidatos.append(
            {
                "id": item.get("id", ""),
                "label": item.get("label", texto),
                "description": item.get("description", ""),
                "url": item.get("concepturi", ""),
                "rango": rango,
            }
        )
    return candidatos


def _obtener_p31(qid: str) -> list[str]:
    """
    Devuelve los QIDs de 'instancia de' (P31) de una entidad — su(s) tipo(s).
    Permite descartar candidatos del tipo equivocado (un apellido, una pintura,
    un barco) cuando el NER esperaba una persona/lugar/organización.
    Vacío si falla la consulta (degradación sin red).
    """
    params = {
        "action": "wbgetclaims",
        "format": "json",
        "entity": qid,
        "property": "P31",
    }
    url = _API_WIKIDATA + "?" + urllib.parse.urlencode(params)
    headers = {"User-Agent": "BashkarStation/1.0 (contact: bashkar@icc.gov.co)"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=_TIMEOUT_HTTP) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return []
    tipos = []
    for claim in data.get("claims", {}).get("P31", []):
        try:
            tipos.append(claim["mainsnak"]["datavalue"]["value"]["id"])
        except (KeyError, TypeError):
            pass
    return tipos


# Descripciones que delatan que un candidato NO es la entidad buscada sino
# un homónimo de otro tipo (apellido, nombre de pila, barco, pintura, calle…).
_DESC_DESCARTE = (
    "apellido",
    "family name",
    "surname",
    "nombre de pila",
    "given name",
    "pintura",
    "painting",
    "escultura",
    "sculpture",
    "monumento",
    "monument",
    "buque",
    "barco",
    "battleship",
    "acorazado",
    "ship",
    "película",
    "film",
    "álbum",
    "album",
    "canción",
    "song",
    "estación de metro",
    "metro station",
    "calle",
    "street",
    "equipo ciclista",
    "cycling team",
    "personaje",
    "ficticio",
    "fictional",
)

# Tipos P31 aceptables por categoría NER. Si el candidato top tiene P31 y
# ninguno cae aquí, se rechaza (era un homónimo del tipo equivocado).
_P31_VALIDOS = {
    "personas": {"Q5"},  # humano
    "lugares": {
        "Q515",
        "Q6256",
        "Q35657",
        "Q3957",  # ciudad, país, estado, pueblo
        "Q532",
        "Q486972",
        "Q82794",
        "Q15284",  # aldea, asentamiento, región, municipio
        "Q1549591",
        "Q1637706",
    },  # gran ciudad, millón-hab
    "organizaciones": {
        "Q43229",
        "Q7210356",
        "Q31855",  # organización, org. política, inst.
        "Q2385804",
        "Q1114461",
        "Q1093829",
        "Q3918",
        "Q875538",
        "Q207320",  # universidad, univ. pública, partido
        "Q4830453",
        "Q163740",
    },  # empresa, sin ánimo de lucro
    "obras_publicaciones": {
        "Q571",
        "Q11032",
        "Q732577",  # libro, periódico, publicación
        "Q13442814",
        "Q5633421",
    },  # artículo, revista
}


def _puntuar_candidato(candidato: dict, texto: str, categoria: str) -> float:
    """
    Puntúa un candidato de Wikidata. El criterio dominante es el RANGO de
    Wikidata (orden por relevancia/enlaces): la primera acepción es casi
    siempre la más conocida, que es la que cita la prensa de 1939.

    Criterios:
      base 2.0 - rango*0.6   → premia fuertemente las primeras acepciones
      +1.0  label coincide exactamente (case-insensitive)
      +0.6  descripción coincide con el tipo de entidad esperado
      +0.4  descripción menciona Colombia / período (desempate, no dominante)
      -3.0  descripción delata homónimo de otro tipo (apellido, barco, pintura…)
    """
    score = 0.0
    label = candidato.get("label", "").lower()
    desc = candidato.get("description", "").lower()
    texto_l = texto.lower()
    rango = candidato.get("rango", 0)

    # Señal principal: posición en el ranking de Wikidata
    score += 2.0 - rango * 0.6

    if label == texto_l:
        score += 1.0
    elif texto_l in label or label in texto_l:
        score += 0.3

    # Descarte fuerte de homónimos de otro tipo
    if any(t in desc for t in _DESC_DESCARTE):
        score -= 3.0

    # Coincidencia con el tipo de entidad esperado (en español, ya que uselang=es)
    tipo_desc = {
        "personas": [
            "político",
            "escritor",
            "periodista",
            "poeta",
            "historiador",
            "abogado",
            "militar",
            "dictador",
            "general",
            "presidente",
            "diplomático",
            "pintor",
            "artista",
            "filósofo",
            "compositor",
        ],
        "lugares": [
            "ciudad",
            "municipio",
            "departamento",
            "país",
            "región",
            "capital",
            "provincia",
            "comunidad autónoma",
            "estado",
        ],
        "organizaciones": [
            "organización",
            "institución",
            "universidad",
            "partido",
            "periódico",
            "revista",
            "empresa",
            "club",
        ],
    }
    for palabra in tipo_desc.get(categoria, []):
        if palabra in desc:
            score += 0.6
            break

    # Desempate suave por relación con el corpus (NO debe dominar al rango)
    if "colombia" in desc or "colombiano" in desc or "colombiana" in desc:
        score += 0.4

    return score


def enlazar_entidad(
    texto: str,
    categoria: str,
    ruta_cache: str | None = None,
    sin_red: bool = False,
) -> dict | None:
    """
    Enlaza una entidad nombrada con su entrada en Wikidata.

    Args:
        texto:       Texto de la entidad (ej: "German Arciniegas")
        categoria:   Categoría NER (personas, lugares, organizaciones, etc.)
        ruta_cache:  Ruta al archivo SQLite de caché (usa la por defecto si None)
        sin_red:     Si True, solo consulta caché local (modo offline)

    Returns:
        dict con {id, label, description, url, confianza} o None si no se encontró.
        - id:          QID de Wikidata (ej: "Q1234567")
        - label:       Nombre canónico en español
        - description: Descripción corta de Wikidata
        - url:         URL completa de la entidad en Wikidata
        - confianza:   Float 0.0-1.0 basado en coincidencia con el corpus
    """
    if not texto or not texto.strip():
        return None

    texto = texto.strip()
    cache = _obtener_cache(ruta_cache)

    # Consultar caché primero
    cached = cache.obtener(texto, categoria)
    if cached is not None:
        return cached if cached else None  # {} → None (no encontrado)

    if sin_red:
        return None  # Modo offline: no hacer llamadas HTTP

    # Llamada a la API
    time.sleep(_PAUSA_ENTRE_LLAMADAS)
    candidatos = _llamar_wikidata(texto, categoria, lang="es")

    # Si no hay resultados en español, intentar en inglés
    if not candidatos:
        time.sleep(_PAUSA_ENTRE_LLAMADAS)
        candidatos = _llamar_wikidata(texto, categoria, lang="en")

    if not candidatos:
        cache.guardar(texto, categoria, None)
        return None

    # Puntuar y ordenar
    puntuados = [(c, _puntuar_candidato(c, texto, categoria)) for c in candidatos]
    puntuados.sort(key=lambda x: -x[1])

    # Filtro por tipo P31: recorrer en orden de score y quedarse con el primer
    # candidato cuyo tipo Wikidata sea compatible con la categoría NER. Así se
    # descartan homónimos (apellido, barco, pintura) que comparten nombre.
    tipos_validos = _P31_VALIDOS.get(categoria)
    mejor, mejor_score = None, 0.0
    for cand, sc in puntuados:
        if sc < 0.3:
            continue
        if tipos_validos and not sin_red:
            time.sleep(_PAUSA_ENTRE_LLAMADAS)
            p31 = _obtener_p31(cand["id"])
            # Si tiene P31 conocido y NINGUNO es válido, descartar.
            # Si no se pudo obtener P31 (lista vacía), no penalizar (fallback).
            if p31 and not (set(p31) & tipos_validos):
                continue
        mejor, mejor_score = cand, sc
        break

    if mejor is None:
        cache.guardar(texto, categoria, None)
        return None

    # Normalizar confianza a [0, 1]. El score máximo ronda ~4 (rango 0 + label
    # exacto + tipo + Colombia).
    confianza = max(0.0, min(1.0, mejor_score / 4.0))

    resultado = {
        "id": mejor["id"],
        "label": mejor["label"],
        "description": mejor["description"],
        "url": mejor["url"],
        "confianza": round(confianza, 3),
    }
    cache.guardar(texto, categoria, resultado)
    return resultado


def enlazar_indice_ner(
    indice_ner: dict,
    ruta_cache: str | None = None,
    sin_red: bool = False,
    callback=None,
) -> dict:
    """
    Enlaza todas las entidades de un índice NER completo.

    Args:
        indice_ner:  Dict {categoria: {texto: [articulo_ids]}} (formato del repositorio)
        ruta_cache:  Ruta al archivo SQLite de caché
        sin_red:     Si True, solo consulta caché local
        callback:    Función callback(n_procesadas, total) para progreso

    Returns:
        Dict {categoria: {texto: resultado_wikidata_o_None}}
    """
    resultado = {}
    total = sum(len(entidades) for entidades in indice_ner.values())
    n = 0

    for categoria, entidades in indice_ner.items():
        resultado[categoria] = {}
        for texto in entidades:
            enlace = enlazar_entidad(texto, categoria, ruta_cache, sin_red)
            resultado[categoria][texto] = enlace
            n += 1
            if callback:
                try:
                    callback(n, total)
                except Exception:
                    pass

    return resultado


def enlazar_lista_entidades(
    entidades: list[dict],
    ruta_cache: str | None = None,
    sin_red: bool = False,
) -> list[dict]:
    """
    Enlaza una lista de entidades NER (formato de ner_roberta / pipeline_ner).

    Args:
        entidades:  Lista de dicts {texto, categoria, confianza, fuente}
        ruta_cache: Ruta al archivo SQLite de caché
        sin_red:    Si True, solo consulta caché local

    Returns:
        La misma lista con un campo "wikidata" añadido a cada elemento.
        Si no se encontró enlace, "wikidata" es None.
    """
    enriquecidas = []
    for ent in entidades:
        ent_copia = dict(ent)
        enlace = enlazar_entidad(
            ent.get("texto", ""),
            ent.get("categoria", ""),
            ruta_cache,
            sin_red,
        )
        ent_copia["wikidata"] = enlace
        enriquecidas.append(ent_copia)
    return enriquecidas


def estadisticas_cache(ruta_cache: str | None = None) -> dict:
    """Retorna estadísticas de la caché local."""
    return _obtener_cache(ruta_cache).estadisticas()


def limpiar_cache(dias: int = 90, ruta_cache: str | None = None):
    """Elimina entradas con más de `dias` días de antigüedad de la caché."""
    _obtener_cache(ruta_cache).limpiar(dias)

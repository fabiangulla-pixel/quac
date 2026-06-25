"""origen_medios.py — ¿La nota es de un medio COLOMBIANO o EXTRANJERO? (¡Quac!)

Clasifica cada nota por el PAÍS de origen de su medio, para distinguir cobertura
nacional vs. internacional (p. ej. "los medios internacionales cubren distinto a
los nacionales"). La señal sólida es el MEDIO/dominio, no el autor.

Estrategia en tres niveles (de más a menos fiable):
  1. Lista CURADA dominio→país (medios conocidos del estudio + internacionales
     frecuentes en el corpus). Resuelve los casos ambiguos que el TLD no puede:
     eltiempo.com = Colombia,  elpais.com = España  (¡distinto de elpais.com.co!).
  2. Perfil del usuario: lo que esté en medios['internacional'] se marca como
     extranjero aunque no esté en la tabla; el resto de medios del perfil, como
     colombiano (el perfil es de prensa colombiana).
  3. Reglas de TLD: .co/.com.co → Colombia; .es → España; .ar → Argentina, etc.

No toca los motores de Bashkar; se integra por nota en el pipeline y se agrega.
"""

from __future__ import annotations

from urllib.parse import urlparse

COLOMBIA = "Colombia"

# ── 1) Tabla curada: dominio → país ──────────────────────────────────────────
# Dominios colombianos SIN TLD nacional (la regla de TLD no los detectaría).
_COLOMBIA = {
    "eltiempo.com",
    "elespectador.com",
    "semana.com",
    "elcolombiano.com",
    "lasillavacia.com",
    "pulzo.com",
    "cambiocolombia.com",
    "publimetro.co",
    "bluradio.com",
    "noticiascaracol.com",
    "minuto60.com",
    "kienyke.com",
    "mutante.org",
    "valoraanalitik.com",
    "ifmnoticias.com",
    "rtvcnoticias.com",
    "cuestionpublica.com",
    "razonpublica.com",
    "colombiacheck.com",
    "vanguardia.com",
    "las2orillas.co",
    "voragine.co",
    "larepublica.co",
    "portafolio.co",
    "elheraldo.co",
    "lafm.com.co",
    "caracol.com.co",
    "elpais.com.co",
    "eluniversal.com.co",
    "elnuevosiglo.com.co",
    "hoydiariodelmagdalena.com.co",
    "cerosetenta.uniandes.edu.co",
    # Regionales colombianos frecuentes en el corpus (sin TLD nacional).
    "colombia.com",
    "chicanoticias.com",
    "zonacero.com",
    "lapatria.com",
    "tropicanafm.com",
    "proclamadelpacifico.com",
    "diariolalibertad.com",
    "pluralidadz.com",
    "revistaraya.com",
    "ondasdelporvenir.com",
    "tolimaonline.com",
    "elirreverenteibague.com",
    "radioguatapuri.com",
    "ecosdelcombeima.com",
    "citytv.eltiempo.com",
}
# Medios internacionales (dominio → país de origen).
_EXTRANJERO = {
    "infobae.com": "Argentina",
    "bloomberglinea.com": "Estados Unidos",
    "elpais.com": "España",
    "bbc.com": "Reino Unido",
    "bbc.co.uk": "Reino Unido",
    "cnnespanol.cnn.com": "Estados Unidos",
    "cnn.com": "Estados Unidos",
    "dw.com": "Alemania",
    "france24.com": "Francia",
    "reuters.com": "Reino Unido",
    "efe.com": "España",
    "afp.com": "Francia",
    "es-us.noticias.yahoo.com": "Estados Unidos",
    "yahoo.com": "Estados Unidos",
    "elmundo.es": "España",
    "abc.es": "España",
    "lavanguardia.com": "España",
    "clarin.com": "Argentina",
    "lanacion.com.ar": "Argentina",
    "nytimes.com": "Estados Unidos",
    "washingtonpost.com": "Estados Unidos",
    "elnacional.com": "Venezuela",
    "telesurtv.net": "Venezuela",
    "mercopress.com": "Uruguay",
    "swissinfo.ch": "Suiza",
    "ntn24.com": "Venezuela",
    "cronista.com": "Argentina",
    "perfil.com": "Argentina",
    "eluniverso.com": "Ecuador",
    "marca.com": "España",
    "colombia.as.com": "España",
    "as.com": "España",
    "diario.elmundo.sv": "El Salvador",
}

# ── 3) TLD → país (respaldo) ──────────────────────────────────────────────────
_TLD_PAIS = {
    "co": COLOMBIA,
    "es": "España",
    "ar": "Argentina",
    "mx": "México",
    "pe": "Perú",
    "cl": "Chile",
    "ve": "Venezuela",
    "ec": "Ecuador",
    "uy": "Uruguay",
    "br": "Brasil",
    "us": "Estados Unidos",
    "uk": "Reino Unido",
    "fr": "Francia",
    "de": "Alemania",
    "ch": "Suiza",
    "it": "Italia",
}


def _dominio(url_o_medio: str) -> str:
    """Normaliza a dominio en minúsculas sin www. Acepta una URL o un dominio."""
    s = (url_o_medio or "").strip().lower()
    if "://" in s:
        s = urlparse(s).netloc
    elif "/" in s:
        s = s.split("/", 1)[0]
    return s.replace("www.", "").strip()


def _pais_por_tld(dominio: str) -> str | None:
    # ccTLD de segundo nivel: .com.co, .com.ar, .co.uk → tomar el penúltimo trozo.
    partes = dominio.rsplit(".", 2)
    if len(partes) == 3 and partes[1] in ("com", "co", "org", "net", "gob", "gov"):
        return _TLD_PAIS.get(partes[2])
    tld = dominio.rsplit(".", 1)[-1] if "." in dominio else ""
    return _TLD_PAIS.get(tld)


def clasificar_origen(url_o_medio: str, perfil: dict | None = None) -> dict:
    """Devuelve el origen del medio de una nota.

    Args:
        url_o_medio: URL de la nota o nombre/dominio del medio.
        perfil:      perfil del usuario (config.cargar()); su categoría
                     medios['internacional'] refuerza la detección de extranjeros.

    Returns:
        {"pais": str, "es_colombiano": bool, "es_extranjero": bool,
         "fuente": "tabla"|"perfil"|"tld"|"desconocido"}
    """
    dom = _dominio(url_o_medio)
    if not dom:
        return {
            "pais": None,
            "es_colombiano": False,
            "es_extranjero": False,
            "fuente": "desconocido",
        }

    # 1) Tabla curada
    if dom in _COLOMBIA:
        return {"pais": COLOMBIA, "es_colombiano": True, "es_extranjero": False, "fuente": "tabla"}
    if dom in _EXTRANJERO:
        return {
            "pais": _EXTRANJERO[dom],
            "es_colombiano": False,
            "es_extranjero": True,
            "fuente": "tabla",
        }

    # 2) Perfil del usuario
    if perfil:
        medios = perfil.get("medios") or {}
        internac = {_dominio(m) for m in (medios.get("internacional") or [])}
        if dom in internac:
            return {
                "pais": _EXTRANJERO.get(dom, "Extranjero"),
                "es_colombiano": False,
                "es_extranjero": True,
                "fuente": "perfil",
            }
        # Otros medios del perfil (prensa/digital/radio/tv) son colombianos.
        otros = set()
        for cat, lst in medios.items():
            if cat == "internacional":
                continue
            otros |= {_dominio(m) for m in (lst or [])}
        if dom in otros:
            return {
                "pais": COLOMBIA,
                "es_colombiano": True,
                "es_extranjero": False,
                "fuente": "perfil",
            }

    # 3) Respaldo por TLD
    pais = _pais_por_tld(dom)
    if pais:
        return {
            "pais": pais,
            "es_colombiano": pais == COLOMBIA,
            "es_extranjero": pais != COLOMBIA,
            "fuente": "tld",
        }

    return {"pais": None, "es_colombiano": False, "es_extranjero": False, "fuente": "desconocido"}


def resumen_origen(por_nota: dict) -> dict:
    """Agrega el origen de todo el corpus (lee por_nota[url]['origen']).

    Returns:
        {
          "n_colombianos": int, "n_extranjeros": int, "n_desconocidos": int,
          "por_pais": {pais: n_notas} ordenado desc,
          "medios_extranjeros": {dominio: n_notas},
        }
    """
    n_col = n_ext = n_desc = 0
    por_pais: dict[str, int] = {}
    medios_ext: dict[str, int] = {}
    for r in por_nota.values():
        o = r.get("origen") or {}
        if o.get("es_colombiano"):
            n_col += 1
        elif o.get("es_extranjero"):
            n_ext += 1
            medio = r.get("medio") or "?"
            medios_ext[medio] = medios_ext.get(medio, 0) + 1
        else:
            n_desc += 1
        pais = o.get("pais") or "desconocido"
        por_pais[pais] = por_pais.get(pais, 0) + 1
    return {
        "n_colombianos": n_col,
        "n_extranjeros": n_ext,
        "n_desconocidos": n_desc,
        "por_pais": dict(sorted(por_pais.items(), key=lambda kv: -kv[1])),
        "medios_extranjeros": dict(sorted(medios_ext.items(), key=lambda kv: -kv[1])),
    }

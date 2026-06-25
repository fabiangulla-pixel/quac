"""Control de calidad de la extracción — ¿el texto es la nota o es basura?

Para un estudio publicable, cada artículo scrapeado debe contener el CUERPO de
la nota y no ruido (menús, cookies, "lea también", pies de página, JS). Este
módulo puntúa la calidad de cada extracción con métricas usadas en la literatura
de extracción de contenido web (densidad de enlaces/boilerplate, longitud,
repetición, marcadores de UI), y emite un veredicto: confiable / revisar / malo.

No reemplaza la revisión humana (ver revision.py), la complementa: marca QUÉ
notas mirar primero. Es 100% local y determinista (reproducible para metodología).
"""

from __future__ import annotations

import re

# Frases/UI que delatan boilerplate de portal si abundan en el texto extraído.
_RUIDO_UI = re.compile(
    r"(reg[ií]strate|inicia sesi[oó]n|suscr[ií]b|aceptar cookies|pol[ií]tica de "
    r"privacidad|lea tambi[eé]n|le puede interesar|leer m[aá]s|s[ií]guenos|"
    r"comparte|todos los derechos reservados|newsletter|publicidad|"
    r"\bcompartir\b|whatsapp|facebook|twitter)",
    re.IGNORECASE,
)

# Señales de que NO se llegó al contenido (muro/consentimiento/login).
_MURO = re.compile(
    r"(para continuar leyendo|contenido exclusivo para suscriptores|"
    r"este art[ií]culo es exclusivo|acepta(r)? (las )?cookies|gestionar "
    r"consentimiento|inicia sesi[oó]n para|reg[ií]strate gratis)",
    re.IGNORECASE,
)


def _reglas_perfil():
    """Lee umbrales y frases del perfil del usuario (si hay), con fallback."""
    try:
        import config

        c = config.cargar().get("calidad", {})
    except Exception:
        c = {}
    muro = c.get("frases_muro")
    boiler = c.get("frases_boilerplate")
    re_muro = re.compile("|".join(re.escape(f) for f in muro), re.IGNORECASE) if muro else _MURO
    re_ruido = (
        re.compile("|".join(re.escape(f) for f in boiler), re.IGNORECASE) if boiler else _RUIDO_UI
    )
    return {
        "min_conf": c.get("min_palabras_confiable", 120),
        "min_breve": c.get("min_palabras_breve", 250),
        "re_muro": re_muro,
        "re_ruido": re_ruido,
    }


def evaluar_extraccion(nota: dict, reglas: dict | None = None) -> dict:
    """Puntúa la calidad de una nota extraída (0–1) y da un veredicto.

    Métricas (cada una resta del score):
      - cuerpo corto (< 120 palabras): probable extracción incompleta.
      - ratio de líneas-UI alto: se coló boilerplate.
      - presencia de muro/consentimiento: no se llegó al contenido real.
      - repetición excesiva (líneas duplicadas): menús/enlaces repetidos.
      - ratio título/cuerpo anómalo.
    Retorna {score, veredicto, n_palabras, motivos:[...]}.
    """
    reglas = reglas or _reglas_perfil()
    cuerpo = (nota.get("cuerpo") or "").strip()
    titular = (nota.get("titular") or "").strip()
    palabras = cuerpo.split()
    n = len(palabras)
    motivos = []
    score = 1.0

    if n == 0:
        return {"score": 0.0, "veredicto": "malo", "n_palabras": 0, "motivos": ["sin texto"]}

    # 1) longitud (umbrales del perfil)
    if n < reglas["min_conf"]:
        score -= 0.35
        motivos.append(f"cuerpo corto ({n} palabras)")
    elif n < reglas["min_breve"]:
        score -= 0.12
        motivos.append(f"cuerpo breve ({n} palabras)")

    # 2) muro / consentimiento no superado
    if reglas["re_muro"].search(cuerpo):
        score -= 0.40
        motivos.append("posible muro/consentimiento sin superar")

    # 3) ratio de ruido UI (frases de boilerplate por cada 100 palabras)
    n_ruido = len(reglas["re_ruido"].findall(cuerpo))
    ratio_ruido = n_ruido / max(1, n / 100)
    if ratio_ruido > 3:
        score -= 0.30
        motivos.append(f"mucho boilerplate ({n_ruido} marcadores UI)")
    elif ratio_ruido > 1.2:
        score -= 0.12
        motivos.append("algo de boilerplate")

    # 4) repetición de líneas (menús/enlaces que se repiten)
    lineas = [l.strip() for l in cuerpo.splitlines() if len(l.strip()) > 15]
    if lineas:
        unicas = len(set(lineas)) / len(lineas)
        if unicas < 0.6:
            score -= 0.20
            motivos.append("líneas muy repetidas")

    # 5) densidad de caracteres no-texto (señal de basura/JS)
    no_alfa = len(re.findall(r"[^\w\sáéíóúüñ.,;:¿?¡!()\"'%-]", cuerpo))
    if no_alfa / max(1, len(cuerpo)) > 0.08:
        score -= 0.15
        motivos.append("muchos caracteres no textuales")

    # 6) sin titular
    if not titular:
        score -= 0.08
        motivos.append("sin titular")

    score = max(0.0, round(score, 2))
    if score >= 0.75:
        ver = "confiable"
    elif score >= 0.45:
        ver = "revisar"
    else:
        ver = "malo"
    return {"score": score, "veredicto": ver, "n_palabras": n, "motivos": motivos}


def resumen_calidad(notas: list[dict]) -> dict:
    """Agrega la calidad del corpus para reportarla en metodología."""
    res = {"confiable": 0, "revisar": 0, "malo": 0, "total": len(notas), "detalle": []}
    reglas = _reglas_perfil()
    for nt in notas:
        ev = evaluar_extraccion(nt, reglas=reglas)
        res[ev["veredicto"]] += 1
        res["detalle"].append(
            {
                "url": nt.get("url"),
                "medio": nt.get("medio"),
                "titular": (nt.get("titular") or "")[:80],
                **ev,
            }
        )
    res["detalle"].sort(key=lambda d: d["score"])  # peores primero
    return res

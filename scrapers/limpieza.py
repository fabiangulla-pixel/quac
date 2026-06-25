"""Limpieza de texto propia de ¡Quac! (NO toca los motores copiados de Bashkar).

Dos funciones:
  - ``limpiar_cuerpo``: quita boilerplate de portal (CTAs, menús, "PUBLICIDAD",
    "Regístrate", compartir en redes…) que se cuela en la extracción y ensucia
    el conteo de palabras y el NER.
  - ``filtrar_entidades_ner``: descarta del resultado NER los falsos positivos
    típicos de spaCy en prensa web — conectores con mayúscula inicial de frase
    ("Además", "Según") y restos de UI ("PUBLICIDAD", "WhatsApp").

Se aplica en el pipeline, después de extraer y antes/después del NER. El motor
``ner_engine`` se deja intacto (su entrada en Bashkar es OCR histórico).
"""

from __future__ import annotations

import re

# Conectores / adverbios que spaCy etiqueta como entidad al ir en mayúscula
# inicial de oración. Comparación en minúsculas.
_CONECTORES = {
    "además",
    "así",
    "según",
    "también",
    "sin embargo",
    "no obstante",
    "por su parte",
    "entonces",
    "luego",
    "después",
    "antes",
    "mientras",
    "aunque",
    "pero",
    "porque",
    "como",
    "cuando",
    "donde",
    "lógicamente",
    "finalmente",
    "asimismo",
    "incluso",
    "tras",
    "pese",
}

# Restos de interfaz / navegación de los portales (no son entidades reales).
_UI_RUIDO = {
    "publicidad",
    "información",
    "foto",
    "regístrate",
    "ingrese",
    "ingresa",
    "whatsapp",
    "facebook",
    "twitter",
    "telegram",
    "instagram",
    "compartir",
    "suscríbete",
    "suscribete",
    "newsletter",
    "boletín",
    "lea también",
    "le puede interesar",
    "leer más",
    "ver más",
    "canal de el tiempo",
    "canal de whatsapp",
    "entérese",
    "enterese",
    "únete",
    "unete",
    "nueva",
    "entérate",
    "enterate",
    "más noticias",
    "temas relacionados",
    "etiquetas",
}

# Fragmentos que delatan boilerplate cuando aparecen en una línea del cuerpo.
_LINEAS_BOILERPLATE = re.compile(
    r"(reg[ií]strate|inicia sesi[oó]n|suscr[ií]b|publicidad|"
    r"s[ií]guenos|comparte|lea tambi[eé]n|le puede interesar|leer m[aá]s|"
    r"todos los derechos reservados|copyright|©|cookies|"
    r"canal de whatsapp|recibe noticias|descarga la app|"
    # Ruido de portales detectado en el corpus (El Tiempo, El Colombiano, etc.):
    # secciones de entretenimiento, navegación y promos que se cuelan en el body.
    r"signos del zodiaco|hor[oó]scopo|crucigrama|sopa de letras|"
    r"pon a prueba tus conocimientos|encuentra ac[aá] todos|"
    r"tenemos para ti consejos|consejos de amor|"
    r"videos? eltiempo|videos? el tiempo|m[aá]s noticias de|"
    r"otras noticias|temas relacionados|etiquetas:|"
    r"reciba noticias de|s[ií]guenos en|conozca m[aá]s|"
    r"^\s*(enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|octubre|noviembre|diciembre)\s+\d+\s+de\s+\d{4}\s*$)",
    re.IGNORECASE,
)


def limpiar_cuerpo(texto: str) -> str:
    """Quita líneas de boilerplate y normaliza espacios del cuerpo extraído."""
    if not texto:
        return ""
    lineas = []
    for linea in texto.splitlines():
        l = linea.strip()
        if not l:
            continue
        if _LINEAS_BOILERPLATE.search(l):
            continue
        # Líneas que son solo un grito de UI ("PUBLICIDAD", "WhatsApp")
        if l.lower() in _UI_RUIDO:
            continue
        lineas.append(l)
    return "\n\n".join(lineas)


# Verbos de atribución periodística que spaCy etiqueta como PERSONA cuando
# abren oración ("Agregó que…", "Reiteró…"). Forma lema/raíz en minúscula.
_VERBOS_ATRIBUCION = {
    "agregó",
    "añadió",
    "dijo",
    "afirmó",
    "señaló",
    "indicó",
    "explicó",
    "aseguró",
    "sostuvo",
    "reiteró",
    "manifestó",
    "expresó",
    "declaró",
    "aseveró",
    "negó",
    "admitió",
    "reconoció",
    "advirtió",
    "insistió",
    "concluyó",
    "precisó",
    "comentó",
    "respondió",
    "replicó",
    "apuntó",
    "subrayó",
    "destacó",
    "recalcó",
    "puntualizó",
    "enfatizó",
    "remató",
    "llegó",
    "generó",
    "resultó",
    "ocurrió",
    "sucedió",
    "pasó",
    "quedó",
    "mostró",
    "lanzó",
    "dejó",
    "tomó",
    "logró",
    "buscó",
    "intentó",
}

# Palabras genéricas que NO son entidades nombradas aunque vayan en mayúscula
# (cargos, roles, sustantivos comunes que spaCy confunde con nombres propios).
_GENERICOS = {
    "presidente",
    "presidenta",
    "candidato",
    "candidata",
    "senador",
    "senadora",
    "ministro",
    "ministra",
    "exministro",
    "gobernador",
    "alcalde",
    "magistrado",
    "fiscal",
    "procurador",
    "registrador",
    "periodista",
    "director",
    "directora",
    "líder",
    "lider",
    "vicepresidente",
    "precandidato",
    "abogado",
    "general",
    "doctor",
    "señor",
    "señora",
    "don",
    "doña",
    "ciudadano",
    "colombiano",
    "nueva",
    "nuevo",
    "más",
    "menos",
    "mismo",
    "según",
    "ley",
    "estado",
}

# Inicios de fragmento que delatan que NO es una entidad sino un sintagma mal
# cortado por spaCy ("de Colombia", "en Estados Unidos", "los Estados…").
_PREP_ART_INICIO = {
    "de",
    "del",
    "la",
    "el",
    "los",
    "las",
    "en",
    "a",
    "con",
    "por",
    "para",
    "un",
    "una",
    "su",
    "sus",
    "al",
    "y",
    "o",
    "que",
    "como",
    "ningún",
    "ningun",
}

_RE_TIENE_DIGITO = re.compile(r"\d")


def _es_ruido(entidad: str) -> bool:
    e = entidad.strip()
    low = e.lower()
    if not e:
        return True
    if low in _CONECTORES or low in _UI_RUIDO:
        return True
    # Verbo de atribución periodística ("Agregó", "Reiteró", "Llegó")
    if low in _VERBOS_ATRIBUCION:
        return True
    # Sustantivo/cargo genérico, no un nombre propio ("presidente", "ley")
    if low in _GENERICOS:
        return True
    # Siglas legítimas con número (M-19, G-8, FARC-EP): se conservan.
    _SIGLAS_CON_NUM = {"m-19", "g-8", "g8", "g-20", "g20", "g-77", "11-s"}
    if low in _SIGLAS_CON_NUM:
        return False
    # CUALQUIER otro dígito → cifra, porcentaje, fecha, "Estado de 2022", "43,7%"
    if _RE_TIENE_DIGITO.search(e):
        return True
    # Empieza con signo de interrogación/admiración → fragmento de UI
    if e[:1] in "¿¡?!":
        return True
    # Empieza en minúscula → spaCy casi nunca acierta una entidad así
    # ("agregó", "de Colombia", "los Estados Unidos", "ministro del Interior")
    if e[:1].islower():
        return True
    # Primer token es preposición/artículo → sintagma mal cortado
    primer = re.split(r"\s+", low, maxsplit=1)[0]
    if primer in _PREP_ART_INICIO:
        return True
    # Verbo de atribución como primer token ("Agregó el candidato")
    if primer in _VERBOS_ATRIBUCION:
        return True
    # Una sola palabra muy corta → poco fiable como entidad
    if len(e) <= 2:
        return True
    # Saltos de línea (entidad mal segmentada)
    if "\n" in entidad:
        return True
    # Termina en -ó/-aron/-ió (verbo conjugado disfrazado de nombre)
    if re.search(r"(ó|aron|ieron|ió)$", low) and " " not in low:
        return True
    # Fragmento mal cortado: demasiados tokens para un nombre propio (>5) suele
    # ser dos entidades pegadas o un sintagma ("Abelardo de la Espriella
    # Presidente José Manuel Restrepo Vicepresidente").
    n_tokens = len(low.split())
    if n_tokens > 5:
        return True
    # Contiene palabras-señal de boilerplate/cargo incrustado en medio
    # ("Roberto Sánchez Foto: Internacional", "… Posts TruthSocial").
    _SENALES_FRAGMENTO = (
        "foto",
        "posts",
        "video",
        "caracol",
        "radio",
        "rcn",
        "presidente",
        "vicepresidente",
        "internacional",
        "gobierno",
        "fundacion",
        "fundación",
    )
    if n_tokens >= 3 and any(s in low.split() for s in _SENALES_FRAGMENTO):
        return True
    return False


def filtrar_entidades_ner(ner: dict, relevantes: set | None = None) -> dict:
    """Devuelve un NER sin conectores, restos de UI ni entidades malformadas.

    Si ``relevantes`` (set de nombres normalizados) se pasa, además conserva SOLO
    las entidades que pertenecen al universo de interés del estudio (actores e
    instituciones del perfil curado). Esto evita que el análisis se llene de
    actores internacionales que aparecen por estadística pero no son parte de la
    discusión nacional (Trump, Fujimori, Milei…). Sin ``relevantes`` se comporta
    igual que antes (solo quita ruido evidente).
    """
    limpio: dict[str, list] = {}
    for categoria, entidades in ner.items():
        if not isinstance(entidades, (list, tuple)):
            limpio[categoria] = entidades
            continue
        out = []
        for e in entidades:
            s = str(e)
            if _es_ruido(s):
                continue
            if relevantes is not None and _norm_rel(s) not in relevantes:
                continue
            out.append(e)
        limpio[categoria] = out
    return limpio


def _norm_rel(s: str) -> str:
    """Normaliza un nombre para comparar relevancia (sin tildes, minúsculas)."""
    import unicodedata

    s = unicodedata.normalize("NFKD", str(s or "").lower().strip())
    return "".join(c for c in s if not unicodedata.combining(c))


# Actores, partidos y lugares EXTRANJEROS que aparecen en prensa colombiana por
# contexto internacional pero NO son de la discusión nacional. Se filtran aunque
# sean frecuentes (modo mixto). Comparación normalizada (sin tildes, minúsculas).
_EXTRANJEROS = {
    # políticos extranjeros
    "donald trump",
    "trump",
    "joe biden",
    "biden",
    "javier milei",
    "milei",
    "keiko fujimori",
    "fujimori",
    "alberto fujimori",
    "pedro castillo",
    "dina boluarte",
    "boluarte",
    "nicolas maduro",
    "maduro",
    "vladimir putin",
    "putin",
    "lula",
    "lula da silva",
    "bukele",
    "nayib bukele",
    "joe",
    "kamala",
    "kamala harris",
    "xi jinping",
    "zelenski",
    "zelensky",
    "netanyahu",
    "pedro sanchez",
    "emmanuel macron",
    "macron",
    "evo morales",
    # partidos/movimientos extranjeros
    "fuerza popular",
    "morena",
    "chavismo",
    # países/lugares extranjeros frecuentes en internacionales
    "peru",
    "venezuela",
    "estados unidos",
    "ee.uu.",
    "eeuu",
    "china",
    "rusia",
    "ucrania",
    "israel",
    "gaza",
    "argentina",
    "mexico",
    "brasil",
    "chile",
    "espana",
    "francia",
    "lima",
    "caracas",
    "washington",
    "buenos aires",
    "el salvador",
    "ecuador",
    "bolivia",
    "canada",
    "europa",
    "union europea",
}


# Apellidos/nombres de extranjeros que delatan la entidad aunque venga con texto
# pegado ("Donald J Trump Posts…", "Keiko Sofía Fujimori Higuchi").
_TOKENS_EXTRANJEROS = {
    "trump",
    "biden",
    "milei",
    "fujimori",
    "castillo",
    "boluarte",
    "maduro",
    "putin",
    "lula",
    "bukele",
    "harris",
    "zelenski",
    "zelensky",
    "netanyahu",
    "macron",
    "truthsocial",
}


def es_entidad_extranjera(nombre: str) -> bool:
    """True si la entidad es un actor/lugar internacional que no pertenece a la
    discusión política nacional colombiana (Trump, Perú, Fujimori…). Detecta
    también variantes con texto pegado por tokens delatores."""
    norm = _norm_rel(nombre)
    if norm in _EXTRANJEROS:
        return True
    toks = set(norm.split())
    return bool(toks & _TOKENS_EXTRANJEROS)


def construir_universo_relevante(perfil: dict) -> set:
    """A partir del perfil curado, devuelve el SET de nombres normalizados que
    cuentan como actores/instituciones relevantes del estudio: cada entidad del
    perfil + todas sus variantes declaradas. Lo que no esté aquí se considera
    periférico (ruido internacional, menciones incidentales).
    """
    universo: set = set()
    for e in perfil.get("entidades") or []:
        if not isinstance(e, dict):
            continue
        nombre = e.get("nombre")
        if nombre:
            universo.add(_norm_rel(nombre))
        for v in e.get("variantes") or []:
            universo.add(_norm_rel(v))
    return universo


# Partículas de apellidos que no deben tratarse como "nombre" al canonicalizar.
_PARTICULAS = {"de", "la", "del", "los", "las", "y", "san", "santa"}


def _tokens_significativos(nombre: str) -> set[str]:
    return {
        t.lower() for t in re.findall(r"\w+", nombre) if t.lower() not in _PARTICULAS and len(t) > 2
    }


def canonicalizar_personas(indice_global: dict, semillas: dict | None = None) -> dict:
    """Unifica variantes del mismo nombre de persona en el índice global.

    "Espriella", "De la Espriella", "Abelardo de la Espriella" → la forma más
    completa. Agrupa por solapamiento de tokens significativos (apellidos) y
    funde las listas de artículos. Solo afecta a la categoría 'personas'.

    ``semillas``: {forma_canónica: [variantes]} declaradas por el investigador.
    Cualquier nombre que coincida con una variante se asigna con CERTEZA a esa
    forma canónica (no se adivina por apellido). Modifica y devuelve el índice.
    """
    personas = indice_global.get("personas")
    if not isinstance(personas, dict) or not personas:
        return indice_global

    # Mapa variante(lower) → canónico, a partir de las semillas del usuario.
    semilla_map: dict[str, str] = {}
    for canon_nombre, formas in (semillas or {}).items():
        for f in formas:
            semilla_map[f.lower()] = canon_nombre

    # Orden de más completo a menos (más tokens primero) → la forma larga gana.
    nombres = sorted(personas, key=lambda n: -len(_tokens_significativos(n)))
    canon: dict[str, str] = {}  # nombre original → forma canónica
    grupos: list[tuple[str, set]] = []  # (canónico, tokens)

    for nombre in nombres:
        # 1) ¿coincide con una semilla declarada por el usuario?
        sem = semilla_map.get(nombre.lower())
        if sem:
            canon[nombre] = sem
            continue
        toks = _tokens_significativos(nombre)
        if not toks:
            canon[nombre] = nombre
            continue
        encontrado = None
        for c, ctoks in grupos:
            # Mismo actor si los tokens de uno están contenidos en el otro
            # (apellido compartido), y comparten al menos un apellido.
            if toks <= ctoks or ctoks <= toks:
                encontrado = c
                break
        if encontrado:
            canon[nombre] = encontrado
        else:
            grupos.append((nombre, toks))
            canon[nombre] = nombre

    # Reconstruir el dict de personas fusionando listas de artículos.
    fusionado: dict[str, list] = {}
    for nombre, arts in personas.items():
        c = canon.get(nombre, nombre)
        destino = fusionado.setdefault(c, [])
        for a in arts:
            if a not in destino:
                destino.append(a)

    indice_global["personas"] = fusionado
    return indice_global


def canonicalizar_organizaciones(indice_global: dict, perfil: dict) -> dict:
    """Unifica variantes de organizaciones/instituciones usando las VARIANTES
    declaradas en el perfil (siglas→nombre completo: CNE→Consejo Nacional
    Electoral, Farc→FARC, Presidencia→Presidencia de la República).

    Más seguro que adivinar por tokens (las siglas no comparten letras con el
    nombre). Solo funde lo que el perfil declara explícitamente; lo no declarado
    se conserva. Afecta a 'organizaciones' (y 'lugares' si aplica).
    """
    # Mapa variante_normalizada → nombre canónico, desde el perfil.
    var_a_canon: dict[str, str] = {}
    for e in perfil.get("entidades") or []:
        if not isinstance(e, dict):
            continue
        canon = e.get("nombre")
        if not canon:
            continue
        var_a_canon[_norm_rel(canon)] = canon
        for v in e.get("variantes") or []:
            var_a_canon[_norm_rel(v)] = canon

    for categoria in ("organizaciones", "lugares"):
        ents = indice_global.get(categoria)
        if not isinstance(ents, dict) or not ents:
            continue
        fusionado: dict[str, list] = {}
        for nombre, arts in ents.items():
            canon = var_a_canon.get(_norm_rel(nombre), nombre)
            destino = fusionado.setdefault(canon, [])
            for a in arts:
                if a not in destino:
                    destino.append(a)
        indice_global[categoria] = fusionado
    return indice_global

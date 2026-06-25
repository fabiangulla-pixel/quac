"""prominencia.py — ¿Quién aparece PRIMERO y con QUÉ adjetivos? (¡Quac!)

Dos señales nuevas, por nota, que el NER clásico (sets de entidades) descarta:

  1. PROMINENCIA / POSICIÓN — orden de aparición de cada actor en el cuerpo.
     En prensa el orden de mención señala jerarquía editorial: el actor del
     primer párrafo es el protagonista del enfoque, no un mero "mencionado".
     Medimos: offset de la PRIMERA mención, posición relativa 0–1 en la nota
     (0 = arranque, 1 = final) y el RANGO (1º, 2º, 3º… actor en aparecer).

  2. ADJETIVOS CALIFICATIVOS — los modificadores adjetivales que la nota asocia
     a cada actor. Combinamos:
       a) adjetivos DIRECTOS por dependencias de spaCy
          ("Cepeda radical" → amod;  "Cepeda es honesto" → cópula + attr/acomp;
           "Cepeda, controvertido senador" → aposición),
       b) adjetivos en una VENTANA de ±N tokens alrededor de cada mención
          (capta caracterización difusa que la dependencia no enlaza).
     Cada adjetivo se etiqueta con su CARGA (positivo/negativo/neutro) usando el
     léxico que ya tiene ¡Quac! (sentimiento_politico) — información extra, no
     filtra nada.

Este módulo NO toca los motores copiados de Bashkar: recibe el texto y un doc de
spaCy y trabaja sobre las dependencias. Diseñado para engancharse por nota en el
pipeline y agregarse al final (igual que analisis_avanzado.py / limpieza.py).
"""

from __future__ import annotations

import re
import unicodedata

# Relaciones de dependencia (spaCy es_core_news_*) por las que un adjetivo
# califica a un sustantivo/entidad.
_DEP_MODIFICA = {"amod", "appos", "acl", "nmod"}
# Verbos copulativos: "Cepeda ES/era/fue/parece honesto".
_LEMAS_COPULA = {"ser", "estar", "parecer", "resultar", "lucir", "verse"}
# Relaciones del atributo en una cópula.
_DEP_ATRIBUTO = {"attr", "acomp", "obj", "obl"}

# Adjetivos que NO caracterizan al actor: ordinales, deícticos y temáticos del
# dominio electoral ("segunda/primera vuelta", "electoral", "presidencial"). Se
# filtran de la ventana de contexto para quedarnos con la caracterización real.
_ADJ_RUIDO = {
    "primer",
    "primero",
    "primera",
    "segundo",
    "segunda",
    "tercero",
    "tercera",
    "ultimo",
    "ultima",
    "proximo",
    "proxima",
    "pasado",
    "pasada",
    "mismo",
    "misma",
    "otro",
    "otra",
    "tal",
    "tanto",
    "tanta",
    "cierto",
    "cierta",
    "electoral",
    "electorales",
    "presidencial",
    "presidenciales",
    "vicepresidencial",
    "nacional",
    "nacionales",
    "general",
    "generales",
    "contabilizado",
    "contabilizada",
    "contabilizados",
    "contabilizadas",
    "obtenido",
    "obtenida",
    "obtenidos",
    "obtenidas",
}


def _norm(s: str) -> str:
    """Minúsculas sin tildes para comparar robustamente."""
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _carga_lexica(adjetivo: str) -> str:
    """Etiqueta la carga del adjetivo con el léxico de ¡Quac!.
    Devuelve 'positivo' | 'negativo' | 'neutro'. Lazy import para no acoplar
    el módulo al de sentimiento si se usa suelto."""
    try:
        from sentimiento_politico import _NEG, _POS
    except Exception:
        return "neutro"
    a = _norm(adjetivo)
    pos = {_norm(w) for w in _POS}
    neg = {_norm(w) for w in _NEG}
    if a in pos:
        return "positivo"
    if a in neg:
        return "negativo"
    return "neutro"


def _formas_actor(canonico: str, semillas: dict | None) -> list[str]:
    """Todas las formas (canónica + variantes del perfil) por las que puede
    aparecer un actor en el texto. Se ordenan de más larga a más corta para
    casar primero la mención más específica."""
    formas = {canonico}
    for canon_nombre, variantes in (semillas or {}).items():
        if _norm(canon_nombre) == _norm(canonico) or canonico in (variantes or []):
            formas.add(canon_nombre)
            formas.update(variantes or [])
    # Añadir apellidos sueltos significativos (Cepeda, Espriella) como forma corta.
    for tok in re.findall(r"\w+", canonico):
        if len(tok) > 3 and tok.lower() not in {
            "abelardo",
            "ivan",
            "iván",
            "jose",
            "josé",
            "juan",
            "maria",
            "maría",
        }:
            formas.add(tok)
    return sorted(formas, key=lambda f: -len(f))


def _iter_menciones(texto_norm: str, formas: list[str]):
    """Itera (inicio, fin) de cada mención de cualquier forma del actor, en orden
    de aparición, sin solapamientos. Comparación normalizada con límite de palabra."""
    spans: list[tuple[int, int]] = []
    for forma in formas:
        f = _norm(forma)
        if len(f) < 3:
            continue
        for m in re.finditer(r"\b" + re.escape(f) + r"\b", texto_norm):
            spans.append((m.start(), m.end()))
    spans.sort()
    # Quitar solapamientos (p. ej. "Iván Cepeda" y "Cepeda" en la misma posición).
    limpio: list[tuple[int, int]] = []
    ult_fin = -1
    for ini, fin in spans:
        if ini >= ult_fin:
            limpio.append((ini, fin))
            ult_fin = fin
    return limpio


def _adjetivos_por_dependencia(doc, ini: int, fin: int) -> list[str]:
    """Adjetivos que dependen sintácticamente de los tokens de la mención
    [ini, fin) en caracteres: amod/appos directos y atributos por cópula."""
    adj: list[str] = []
    for tok in doc:
        if tok.idx < ini or tok.idx >= fin:
            continue
        # a) Hijos que son adjetivos modificadores directos.
        for hijo in tok.children:
            if hijo.pos_ == "ADJ" and hijo.dep_ in _DEP_MODIFICA:
                adj.append(hijo.text)
        # b) Cópula. spaCy es_core_news_* sigue Universal Dependencies, donde el
        #    ADJETIVO es el head y la cópula "es/era" cuelga de él como `cop`:
        #      Cepeda(nsubj) → honesto(head, ADJ) ← es(cop)
        #    Detectamos: entidad es nsubj y su head es ADJ con un hijo `cop`.
        if tok.dep_ in ("nsubj", "nsubj:pass"):
            head = tok.head
            if head.pos_ == "ADJ" and any(c.dep_ == "cop" for c in head.children):
                adj.append(head.text)
            # Esquema alternativo (modelos que ponen el verbo como head).
            elif head.lemma_ in _LEMAS_COPULA:
                for h in head.children:
                    if h.pos_ == "ADJ" and h.dep_ in _DEP_ATRIBUTO:
                        adj.append(h.text)
        # c) Aposición: "Cepeda, polémico senador" — adjetivos del aposito.
        for hijo in tok.children:
            if hijo.dep_ == "appos":
                for h in hijo.children:
                    if h.pos_ == "ADJ":
                        adj.append(h.text)
    return adj


def _adjetivos_por_ventana(doc, ini: int, fin: int, ventana: int) -> list[str]:
    """Adjetivos (ADJ) que caen en una ventana de ±`ventana` tokens alrededor de
    la mención. Captura caracterización que la dependencia no enlaza."""
    # Localizar índices de token cuyo offset cae dentro de la mención.
    idxs = [t.i for t in doc if ini <= t.idx < fin]
    if not idxs:
        return []
    tok_men = min(idxs)
    lo, hi = tok_men - ventana, max(idxs) + ventana
    adj = []
    for t in doc:
        if not (lo <= t.i <= hi) or t.pos_ != "ADJ":
            continue
        if _norm(t.text) in _ADJ_RUIDO:
            continue
        # Descartar si entre el adjetivo y la mención se cruza OTRO nombre propio
        # o un verbo finito: probablemente el adjetivo califica a ese otro, no al
        # actor (corta el "arrastre" de la ventana a través de la oración).
        a, b = (t.i, tok_men) if t.i < tok_men else (max(idxs), t.i)
        if any(doc[k].pos_ in ("PROPN",) or doc[k].pos_ == "VERB" for k in range(a + 1, b)):
            continue
        adj.append(t.text)
    return adj


def analizar_prominencia(
    texto: str,
    actores: list[str],
    *,
    nlp=None,
    doc=None,
    semillas: dict | None = None,
    ventana: int = 4,
) -> dict:
    """Calcula prominencia (posición) y adjetivos por actor en UNA nota.

    Args:
        texto:    cuerpo limpio de la nota.
        actores:  formas canónicas de los actores de interés (del NER/perfil).
        nlp:      modelo spaCy (si no se pasa `doc` ya parseado).
        doc:      doc de spaCy ya parseado (se reusa el del pipeline si existe).
        semillas: {canónico: [variantes]} del perfil para casar todas las formas.
        ventana:  nº de tokens a cada lado para los adjetivos de contexto.

    Returns:
        {
          "orden": [actor, ...]                # por orden de 1ª aparición
          "por_actor": {
             actor: {
               "primera_mencion": int|None,    # offset de carácter
               "posicion_relativa": float|None,# 0=lead .. 1=cola
               "rango": int|None,              # 1=aparece primero
               "n_menciones": int,
               "adjetivos": [{"texto","carga"}...],  # dedup, con carga léxica
             }
          },
          "lider": actor|None,                 # el que aparece primero
        }
    """
    texto = texto or ""
    L = max(len(texto), 1)
    texto_norm = _norm(texto)

    if doc is None and nlp is not None and texto.strip():
        doc = nlp(texto[:400_000])

    por_actor: dict[str, dict] = {}
    for actor in actores:
        formas = _formas_actor(actor, semillas)
        menciones = _iter_menciones(texto_norm, formas)
        if not menciones:
            por_actor[actor] = {
                "primera_mencion": None,
                "posicion_relativa": None,
                "rango": None,
                "n_menciones": 0,
                "adjetivos": [],
            }
            continue
        primera = menciones[0][0]
        adj_raw: list[str] = []
        if doc is not None:
            for ini, fin in menciones:
                adj_raw += _adjetivos_por_dependencia(doc, ini, fin)
                adj_raw += _adjetivos_por_ventana(doc, ini, fin, ventana)
        # Dedup preservando orden + etiquetar carga.
        vistos, adjetivos = set(), []
        for a in adj_raw:
            k = _norm(a)
            if k in vistos or len(k) < 3:
                continue
            vistos.add(k)
            adjetivos.append({"texto": a, "carga": _carga_lexica(a)})
        por_actor[actor] = {
            "primera_mencion": primera,
            "posicion_relativa": round(primera / L, 3),
            "rango": None,  # se rellena tras ordenar
            "n_menciones": len(menciones),
            "adjetivos": adjetivos,
        }

    # Orden por primera aparición (los que no aparecen quedan al final).
    presentes = [a for a in actores if por_actor[a]["primera_mencion"] is not None]
    presentes.sort(key=lambda a: por_actor[a]["primera_mencion"])
    for i, a in enumerate(presentes, 1):
        por_actor[a]["rango"] = i

    return {
        "orden": presentes,
        "por_actor": por_actor,
        "lider": presentes[0] if presentes else None,
    }


def resumen_prominencia(por_nota: dict) -> dict:
    """Agrega la prominencia de todo el corpus (se calcula sobre los resultados
    por nota que el pipeline guarda en por_nota[url]['prominencia']).

    Devuelve, por actor:
      - veces_primero: en cuántas notas es el PRIMER actor mencionado (líder).
      - posicion_media: posición relativa media (0 cerca del lead, 1 cola).
      - adjetivos: conteo de adjetivos agregados con su carga.
      - balance_adjetivos: {positivo, negativo, neutro}.
    """
    acc: dict[str, dict] = {}
    for r in por_nota.values():
        prom = r.get("prominencia") or {}
        for actor, datos in (prom.get("por_actor") or {}).items():
            if datos.get("primera_mencion") is None:
                continue
            a = acc.setdefault(
                actor,
                {
                    "veces_primero": 0,
                    "_pos_sum": 0.0,
                    "_pos_n": 0,
                    "n_notas": 0,
                    "adjetivos": {},
                    "balance_adjetivos": {"positivo": 0, "negativo": 0, "neutro": 0},
                },
            )
            a["n_notas"] += 1
            if datos.get("rango") == 1:
                a["veces_primero"] += 1
            if datos.get("posicion_relativa") is not None:
                a["_pos_sum"] += datos["posicion_relativa"]
                a["_pos_n"] += 1
            for adj in datos.get("adjetivos", []):
                t = adj["texto"]
                slot = a["adjetivos"].setdefault(t, {"n": 0, "carga": adj.get("carga", "neutro")})
                slot["n"] += 1
                a["balance_adjetivos"][adj.get("carga", "neutro")] += 1

    salida = {}
    for actor, a in acc.items():
        top = sorted(a["adjetivos"].items(), key=lambda kv: -kv[1]["n"])[:15]
        salida[actor] = {
            "veces_primero": a["veces_primero"],
            "n_notas": a["n_notas"],
            "posicion_media": round(a["_pos_sum"] / a["_pos_n"], 3) if a["_pos_n"] else None,
            "adjetivos_top": [{"texto": t, "n": d["n"], "carga": d["carga"]} for t, d in top],
            "balance_adjetivos": a["balance_adjetivos"],
        }
    # Ordenar el resumen por quién encabeza más notas.
    return dict(sorted(salida.items(), key=lambda kv: -kv[1]["veces_primero"]))

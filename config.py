"""Perfil de usuario configurable de ¡Quac! (persistente entre sesiones).

Guarda en un JSON editable (por GUI o a mano) todo lo afinable: parámetros de
análisis, medios a monitorear, entidades/candidatos con variantes y normalización,
y reglas de calidad/limpieza. Al abrir la app se cargan estos valores por defecto;
no hay que re-teclear nada cada sesión.

Ubicación del perfil: %APPDATA%/Quac/quac_config.json (Windows). Si no existe, se
crea con el PERFIL SEMILLA del estudio de la segunda vuelta presidencial Colombia
2026 (diccionario NER curado por el investigador).
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def ruta_config() -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = Path(base) / "Quac"
    d.mkdir(parents=True, exist_ok=True)
    return d / "quac_config.json"


# ──────────────────────────────────────────────────────────────────────────
# PERFIL SEMILLA — Segunda vuelta presidencial Colombia 2026 (1–21 jun 2026).
# Diccionario NER curado por el investigador. El usuario puede editarlo en la
# pestaña Configuración o en el JSON. Las entidades llevan tipo + variantes
# (se usan para búsqueda, canonicalización/normalización, NER y resaltado).
# ──────────────────────────────────────────────────────────────────────────

PERFIL_SEMILLA = {
    "nombre_perfil": "Segunda vuelta presidencial Colombia 2026",
    "ventana": {
        "desde": "2026-06-01",
        "hasta": "2026-06-21",
        "nota": "1ª vuelta 31-may; 2ª vuelta 21-jun; exterior desde 15-jun",
    },
    # --- parámetros de análisis (valores por defecto de la GUI) ---
    "parametros": {
        "n_topicos": 8,
        "umbral_red": 2,
        "ventana_colocaciones": 6,
        "min_palabras_nota": 120,
        "calidad_minima": 0.45,
        "usar_coref": True,
        "usar_navegador": True,
        "max_resultados": 100,
        "stopwords_extra": [
            "dijo",
            "según",
            "however",
            "informó",
            "afirmó",
            "señaló",
            "agregó",
            "explicó",
        ],
        "analisis_activos": [
            "ner",
            "sentimiento",
            "framing",
            "red",
            "topicos",
            "coref",
            "series",
            "polarizacion",
        ],
        "idioma": "es",
        "pais": "CO",
    },
    # --- medios a monitorear (clasificados por tipo) ---
    "medios": {
        "tv": [
            "noticiascaracol.com",
            "canalrcn.com",
            "noticiasrcn.com",
            "canal1.com.co",
            "rtvcnoticias.com",
        ],
        "radio": [
            "caracol.com.co",
            "wradio.com.co",
            "bluradio.com",
            "lafm.com.co",
            "rcnradio.com",
            "radionacional.co",
        ],
        "prensa": [
            "eltiempo.com",
            "elespectador.com",
            "semana.com",
            "cambiocolombia.com",
            "elcolombiano.com",
            "elheraldo.co",
            "elpais.com.co",
            "larepublica.co",
            "portafolio.co",
            "vanguardia.com",
            "eluniversal.com.co",
            "elnuevosiglo.com.co",
        ],
        "digital": [
            "lasillavacia.com",
            "voragine.co",
            "cuestionpublica.com",
            "razonpublica.com",
            "cerosetenta.uniandes.edu.co",
            "mutante.org",
            "kienyke.com",
            "pulzo.com",
            "las2orillas.co",
            "infobae.com",
        ],
        "fact_checking": ["colombiacheck.com", "afp.com"],
        "internacional": [
            "elpais.com",
            "bbc.com",
            "cnnespanol.cnn.com",
            "dw.com",
            "france24.com",
            "reuters.com",
            "efe.com",
        ],
    },
    # --- entidades de interés (diccionario NER curado) ---
    # cada una: {nombre, tipo, variantes:[...]}
    "entidades": [
        # Núcleo electoral
        {
            "nombre": "Iván Cepeda Castro",
            "tipo": "candidato",
            "variantes": [
                "Iván Cepeda",
                "Cepeda",
                "candidato del Pacto Histórico",
                "candidato de izquierda",
            ],
        },
        {
            "nombre": "Aída Quilcué Vivas",
            "tipo": "formula_vp",
            "variantes": ["Aida Quilcué", "Quilcué", "fórmula vicepresidencial de Cepeda"],
        },
        {
            "nombre": "Abelardo de la Espriella",
            "tipo": "candidato",
            "variantes": [
                "Abelardo De la Espriella",
                "De la Espriella",
                "Abelardo",
                "candidato de Salvación Nacional",
                "candidato de derecha",
                "candidato de ultraderecha",
            ],
        },
        {
            "nombre": "José Manuel Restrepo",
            "tipo": "formula_vp",
            "variantes": [
                "Restrepo",
                "exministro José Manuel Restrepo",
                "fórmula de De la Espriella",
            ],
        },
        {
            "nombre": "voto en blanco",
            "tipo": "opcion_electoral",
            "variantes": ["voto blanco", "casilla de voto en blanco"],
        },
        # Excandidatos / líderes
        {"nombre": "Paloma Valencia", "tipo": "excandidato", "variantes": []},
        {"nombre": "Sergio Fajardo", "tipo": "excandidato", "variantes": []},
        {"nombre": "Claudia López", "tipo": "excandidato", "variantes": []},
        {"nombre": "Luis Gilberto Murillo", "tipo": "excandidato", "variantes": ["Murillo"]},
        {"nombre": "Miguel Uribe Londoño", "tipo": "excandidato", "variantes": []},
        {"nombre": "Clara López", "tipo": "excandidato", "variantes": []},
        {"nombre": "Roy Barreras", "tipo": "excandidato", "variantes": []},
        {"nombre": "Carlos Caicedo", "tipo": "excandidato", "variantes": []},
        {"nombre": "Mauricio Lizcano", "tipo": "excandidato", "variantes": []},
        {
            "nombre": "Gustavo Petro",
            "tipo": "lider_politico",
            "variantes": ["Petro", "presidente Petro", "Gustavo Petro Urrego"],
        },
        {
            "nombre": "Álvaro Uribe",
            "tipo": "lider_politico",
            "variantes": ["Uribe", "Álvaro Uribe Vélez", "expresidente Uribe"],
        },
        {"nombre": "Iván Duque", "tipo": "lider_politico", "variantes": ["Duque"]},
        {"nombre": "Juan Fernando Cristo", "tipo": "lider_politico", "variantes": ["Cristo"]},
        {"nombre": "Enrique Gómez", "tipo": "lider_politico", "variantes": []},
        # Partidos / bloques
        {"nombre": "Pacto Histórico", "tipo": "partido_movimiento", "variantes": ["Pacto"]},
        {"nombre": "Salvación Nacional", "tipo": "partido_movimiento", "variantes": []},
        {"nombre": "Centro Democrático", "tipo": "partido_movimiento", "variantes": []},
        {"nombre": "Fuerza Ciudadana", "tipo": "partido_movimiento", "variantes": []},
        {
            "nombre": "Polo Democrático Alternativo",
            "tipo": "partido_movimiento",
            "variantes": ["Polo Democrático", "Polo"],
        },
        # Instituciones electorales / control / observación
        {
            "nombre": "Registraduría Nacional del Estado Civil",
            "tipo": "autoridad_electoral",
            "variantes": ["Registraduría", "RNEC", "registrador nacional"],
        },
        {
            "nombre": "Consejo Nacional Electoral",
            "tipo": "autoridad_electoral",
            "variantes": ["CNE"],
        },
        {
            "nombre": "Hernán Penagos",
            "tipo": "autoridad_electoral",
            "variantes": ["registrador Penagos"],
        },
        {
            "nombre": "Procuraduría General de la Nación",
            "tipo": "organismo_control",
            "variantes": ["Procuraduría"],
        },
        {
            "nombre": "Fiscalía General de la Nación",
            "tipo": "organismo_control",
            "variantes": ["Fiscalía"],
        },
        {
            "nombre": "Contraloría General de la República",
            "tipo": "organismo_control",
            "variantes": ["Contraloría"],
        },
        {
            "nombre": "Defensoría del Pueblo",
            "tipo": "organismo_control",
            "variantes": ["Defensoría"],
        },
        {"nombre": "Consejo de Estado", "tipo": "justicia", "variantes": []},
        {"nombre": "Corte Suprema de Justicia", "tipo": "justicia", "variantes": ["Corte Suprema"]},
        {
            "nombre": "Misión de Observación Electoral",
            "tipo": "organismo_observacion",
            "variantes": ["MOE"],
        },
        {
            "nombre": "Organización de los Estados Americanos",
            "tipo": "organismo_observacion",
            "variantes": ["OEA"],
        },
        {
            "nombre": "URIEL",
            "tipo": "denuncia_electoral",
            "variantes": ["Unidad de Recepción Inmediata para la Transparencia Electoral"],
        },
        # Encuestadoras
        {"nombre": "Centro Nacional de Consultoría", "tipo": "encuestadora", "variantes": ["CNC"]},
        {"nombre": "Guarumo", "tipo": "encuestadora", "variantes": ["Guarumo Ecoanalítica"]},
        {"nombre": "Atlas Intel", "tipo": "encuestadora", "variantes": ["AtlasIntel"]},
        {"nombre": "Invamer", "tipo": "encuestadora", "variantes": []},
        {"nombre": "Datexco", "tipo": "encuestadora", "variantes": []},
        {"nombre": "YanHaas", "tipo": "encuestadora", "variantes": []},
        # Lugares con carga simbólica de campaña
        {"nombre": "Soledad", "tipo": "lugar_campaña", "variantes": ["Soledad, Atlántico"]},
        {"nombre": "Buga", "tipo": "lugar_campaña", "variantes": ["Buga, Valle del Cauca"]},
    ],
    # --- marcos / temas de cobertura (ISSUE_FRAME) ---
    # Refuerzan el frame_engine con vocabulario del dominio electoral colombiano.
    "marcos": {
        "politico": [
            "polarización",
            "continuidad",
            "cambio",
            "democracia",
            "autoritarismo",
            "populismo",
            "moderación",
            "radicalización",
            "voto útil",
            "petrismo",
            "antipetrismo",
            "uribismo",
        ],
        "seguridad": [
            "seguridad",
            "orden público",
            "disturbios",
            "Plan Democracia",
            "Fuerza Pública",
            "grupos armados",
            "violencia electoral",
            "PMU",
        ],
        "economico": [
            "impuestos",
            "empleo",
            "tasas de interés",
            "inversión",
            "reformas económicas",
            "gasto público",
        ],
        "social": [
            "salud",
            "educación",
            "pensiones",
            "tierras",
            "desigualdad",
            "pobreza",
            "mujeres",
            "pueblos indígenas",
        ],
        "informativo": [
            "desinformación",
            "noticias falsas",
            "bodegas",
            "bots",
            "inteligencia artificial",
            "deepfakes",
            "propaganda",
            "pauta política",
        ],
        "mediatico": [
            "sesgo mediático",
            "línea editorial",
            "concentración de medios",
            "independencia periodística",
            "confianza en medios",
        ],
        "electoral_integridad": [
            "fraude",
            "irregularidades",
            "auditoría",
            "preconteo",
            "E-14",
            "censo electoral",
            "testigos electorales",
            "observadores",
            "escrutinio",
        ],
    },
    # --- reglas de calidad / limpieza (umbrales editables) ---
    "calidad": {
        "min_palabras_confiable": 120,
        "min_palabras_breve": 250,
        "frases_muro": [
            "contenido exclusivo para suscriptores",
            "para continuar leyendo",
            "acepta las cookies",
            "inicia sesión para",
            "regístrate gratis",
        ],
        "frases_boilerplate": [
            "regístrate",
            "inicia sesión",
            "suscríbete",
            "lea también",
            "le puede interesar",
            "síguenos",
            "todos los derechos reservados",
            "newsletter",
            "publicidad",
            "compartir",
        ],
    },
    # --- API key opcional (vacía por defecto; local-first) ---
    "api_key": "",
}


_cache = {}


def cargar() -> dict:
    """Carga el perfil del usuario; si no existe, lo crea con la semilla."""
    if "perfil" in _cache:
        return _cache["perfil"]
    ruta = ruta_config()
    if ruta.exists():
        try:
            perfil = json.loads(ruta.read_text(encoding="utf-8"))
            # completar claves nuevas faltantes con la semilla (migración suave)
            for k, v in PERFIL_SEMILLA.items():
                perfil.setdefault(k, v)
        except Exception:
            perfil = json.loads(json.dumps(PERFIL_SEMILLA))
    else:
        perfil = json.loads(json.dumps(PERFIL_SEMILLA))
        guardar(perfil)
    _cache["perfil"] = perfil
    return perfil


def guardar(perfil: dict) -> Path:
    ruta = ruta_config()
    ruta.write_text(json.dumps(perfil, ensure_ascii=False, indent=2), encoding="utf-8")
    _cache["perfil"] = perfil
    return ruta


def restaurar_semilla() -> dict:
    """Vuelve al perfil semilla (descarta cambios del usuario)."""
    perfil = json.loads(json.dumps(PERFIL_SEMILLA))
    guardar(perfil)
    return perfil


def todos_los_medios(perfil: dict | None = None) -> list[str]:
    """Lista plana de dominios de medios del perfil."""
    perfil = perfil or cargar()
    out = []
    for grupo in perfil.get("medios", {}).values():
        out.extend(grupo)
    return out


def entidades_como_objetos(perfil: dict | None = None):
    """Devuelve las entidades del perfil como EntidadInteres (para búsqueda)."""
    from busqueda.criterios import EntidadInteres

    perfil = perfil or cargar()
    return [
        EntidadInteres(e["nombre"], e.get("tipo", "persona"), e.get("variantes", []))
        for e in perfil.get("entidades", [])
    ]


def semillas_normalizacion(perfil: dict | None = None) -> dict:
    """{nombre_canónico: [todas_las_formas]} para canonicalización/normalización."""
    perfil = perfil or cargar()
    out = {}
    for e in perfil.get("entidades", []):
        formas = [e["nombre"]] + e.get("variantes", [])
        out[e["nombre"]] = formas
    return out

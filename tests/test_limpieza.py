"""Tests de la limpieza propia de ¡Quac! (filtro de ruido NER + canonicalización)."""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from scrapers.limpieza import canonicalizar_personas, filtrar_entidades_ner, limpiar_cuerpo


def test_limpia_boilerplate_de_portal():
    """El cuerpo se queda con el artículo y descarta horóscopo/crucigrama/videos."""
    cuerpo = (
        "Videos Eltiempo MAYO 13 DE 2026\n"
        "La operación dejó una hacienda destruida y comunidades aterrorizadas.\n"
        "El hecho ocurrió en la Troncal del Caribe según las autoridades.\n"
        "Encuentra acá todos los signos del zodiaco.\n"
        "Pon a prueba tus conocimientos con el crucigrama de EL TIEMPO\n"
        "Horóscopo de hoy: consejos de amor y finanzas.\n"
    )
    out = limpiar_cuerpo(cuerpo)
    assert "hacienda destruida" in out  # se conserva el artículo
    assert "Troncal del Caribe" in out
    assert "zodiaco" not in out.lower()  # se quita el ruido
    assert "crucigrama" not in out.lower()
    assert "horóscopo" not in out.lower()
    assert "Videos Eltiempo" not in out


def test_filtra_conectores_y_ui():
    ner = {
        "personas": ["Iván Cepeda", "Además", "Según", "Abelardo de la Espriella"],
        "organizaciones": ["PUBLICIDAD", "FCF", "WhatsApp"],
    }
    out = filtrar_entidades_ner(ner)
    assert "Iván Cepeda" in out["personas"]
    assert "Abelardo de la Espriella" in out["personas"]
    assert "Además" not in out["personas"]
    assert "Según" not in out["personas"]
    assert "FCF" in out["organizaciones"]
    assert "PUBLICIDAD" not in out["organizaciones"]
    assert "WhatsApp" not in out["organizaciones"]


def test_limpiar_cuerpo_quita_boilerplate():
    texto = (
        "Petro lidera la campaña.\n"
        "PUBLICIDAD\n"
        "Regístrate para recibir noticias\n"
        "El candidato visitó Bogotá.\n"
        "Síguenos en Twitter"
    )
    out = limpiar_cuerpo(texto)
    assert "Petro lidera" in out
    assert "Bogotá" in out
    assert "PUBLICIDAD" not in out
    assert "Regístrate" not in out
    assert "Síguenos" not in out


def test_canonicaliza_variantes_de_persona():
    indice = {
        "personas": {
            "Espriella": ["a1"],
            "De la Espriella": ["a2"],
            "Abelardo de la Espriella": ["a2", "a3"],
            "Iván Cepeda": ["a1"],
            "Cepeda": ["a4"],
        }
    }
    out = canonicalizar_personas(indice)
    personas = out["personas"]
    # Las tres variantes de Espriella colapsan en una sola entrada
    claves_espriella = [k for k in personas if "spriella" in k.lower()]
    assert len(claves_espriella) == 1
    # y acumula los artículos de todas las variantes
    canon = claves_espriella[0]
    assert set(personas[canon]) == {"a1", "a2", "a3"}
    # Cepeda también se unifica
    claves_cepeda = [k for k in personas if "cepeda" in k.lower()]
    assert len(claves_cepeda) == 1


# ── Tests del refuerzo de limpieza NER (sesión paper, 2026-06-20) ────────────


def test_filtra_cifras_y_porcentajes():
    """Números, porcentajes y fechas NO son entidades (queja del investigador)."""
    ner = {
        "personas": ["43,7%", "52,6%", "Iván Cepeda"],
        "organizaciones": ["Estado de 2022", "Canadá 2026", "Consejo Nacional Electoral"],
    }
    out = filtrar_entidades_ner(ner)
    assert out["personas"] == ["Iván Cepeda"]
    assert out["organizaciones"] == ["Consejo Nacional Electoral"]


def test_filtra_verbos_de_atribucion():
    """Verbos como 'agregó'/'llegó'/'reiteró' no deben colarse como personas."""
    ner = {"personas": ["agregó", "llegó", "reiteró", "negó", "Abelardo de la Espriella"]}
    out = filtrar_entidades_ner(ner)
    assert out["personas"] == ["Abelardo de la Espriella"]


def test_filtra_fragmentos_y_sintagmas():
    """Sintagmas mal cortados por spaCy ('de Colombia', fragmentos) se descartan."""
    ner = {
        "personas": [
            "de Colombia",
            "en Estados Unidos",
            "los Estados Unidos",
            "ministro del Interior",
            "Gustavo Petro",
        ],
        "organizaciones": [
            "Roberto Sánchez Foto: Internacional",
            "Abelardo de la Espriella Presidente José Manuel Restrepo Vicepresidente",
            "Fiscalía General de la Nación",
        ],
    }
    out = filtrar_entidades_ner(ner)
    assert out["personas"] == ["Gustavo Petro"]
    assert out["organizaciones"] == ["Fiscalía General de la Nación"]


def test_conserva_siglas_legitimas_con_numero():
    """M-19, G-8 (siglas con número) NO deben filtrarse como cifras."""
    ner = {"organizaciones": ["M-19", "G-8", "43,7%"]}
    out = filtrar_entidades_ner(ner)
    assert "M-19" in out["organizaciones"]
    assert "G-8" in out["organizaciones"]
    assert "43,7%" not in out["organizaciones"]


def test_es_entidad_extranjera():
    """Detecta actores/lugares internacionales, incluso con texto pegado."""
    from scrapers.limpieza import es_entidad_extranjera

    assert es_entidad_extranjera("Donald Trump")
    assert es_entidad_extranjera("Keiko Sofía Fujimori Higuchi")  # token delator
    assert es_entidad_extranjera("Perú")
    assert not es_entidad_extranjera("Iván Cepeda")
    assert not es_entidad_extranjera("Gustavo Petro")


def test_filtro_relevancia_universo():
    """Con un universo de relevantes, filtrar_entidades_ner conserva solo esos."""
    from scrapers.limpieza import construir_universo_relevante

    perfil = {
        "entidades": [
            {"nombre": "Iván Cepeda", "variantes": ["Cepeda", "Iván Cepeda Castro"]},
            {"nombre": "Consejo Nacional Electoral", "variantes": ["CNE"]},
        ]
    }
    universo = construir_universo_relevante(perfil)
    ner = {
        "personas": ["Iván Cepeda Castro", "Donald Trump", "Cepeda"],
        "organizaciones": ["CNE", "Google"],
    }
    out = filtrar_entidades_ner(ner, relevantes=universo)
    assert set(out["personas"]) == {"Iván Cepeda Castro", "Cepeda"}
    assert out["organizaciones"] == ["CNE"]


def test_canonicalizar_organizaciones():
    """Funde siglas/variantes de orgs por el perfil (CNE→Consejo, Farc→FARC)."""
    from scrapers.limpieza import canonicalizar_organizaciones

    perfil = {
        "entidades": [
            {"nombre": "Consejo Nacional Electoral", "variantes": ["CNE"]},
            {"nombre": "FARC", "variantes": ["Farc", "FARC-EP"]},
            {
                "nombre": "Presidencia de la República",
                "variantes": ["Presidencia", "Gobierno Petro"],
            },
        ]
    }
    idx = {
        "organizaciones": {
            "CNE": ["a", "b"],
            "Consejo Nacional Electoral": ["b", "c"],
            "Farc": ["d"],
            "FARC": ["e"],
            "Presidencia": ["f"],
            "Presidencia de la República": ["g"],
            "Google": ["h"],
        }
    }
    canonicalizar_organizaciones(idx, perfil)
    orgs = idx["organizaciones"]
    assert set(orgs["Consejo Nacional Electoral"]) == {"a", "b", "c"}
    assert set(orgs["FARC"]) == {"d", "e"}
    assert set(orgs["Presidencia de la República"]) == {"f", "g"}
    assert orgs["Google"] == ["h"]  # no declarada → se conserva

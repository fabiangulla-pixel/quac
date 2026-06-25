"""Tests de la capa de redes sociales (modelo, filtro, registro)."""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from social.base import Publicacion
from social.registro import filtrar_por_audiencia, fuente_social, fuentes_disponibles


def test_publicacion_metricas():
    p = Publicacion(
        id="1",
        plataforma="youtube",
        texto="hola mundo prueba",
        likes=10,
        comentarios=5,
        compartidos=2,
        vistas=1000,
    )
    assert p.interacciones == 17
    assert p.n_palabras == 3
    assert p.hash_contenido  # se calcula solo


def test_filtrar_por_audiencia_umbral():
    ps = [
        Publicacion(id=str(i), plataforma="x", texto=f"t{i}", vistas=v, likes=l)
        for i, (v, l) in enumerate([(5000, 100), (50, 1), (200, 30)])
    ]
    f = filtrar_por_audiencia(ps, min_vistas=100)
    assert len(f) == 2  # excluye el de 50 vistas
    assert f[0].vistas == 5000  # ordenado por impacto desc


def test_filtrar_top_n():
    ps = [
        Publicacion(id=str(i), plataforma="x", texto="t", vistas=v)
        for i, v in enumerate([10, 100, 50, 1000])
    ]
    f = filtrar_por_audiencia(ps, top_n=2)
    assert len(f) == 2
    assert [p.vistas for p in f] == [1000, 100]


def test_fuente_social_factory():
    assert fuente_social("youtube") is not None
    assert fuente_social("tiktok") is not None
    assert fuente_social("x") is not None
    assert fuente_social("inexistente") is None


def test_youtube_requiere_key():
    yt = fuente_social("youtube")
    assert yt.REQUIERE_KEY is True
    assert yt.disponible() is False  # sin key
    assert yt.buscar("Petro") == []  # sin key devuelve vacío, no rompe


def test_fuentes_disponibles_sin_claves():
    # sin claves ni Chrome debug, no debería haber fuentes disponibles
    disp = fuentes_disponibles()
    assert isinstance(disp, list)

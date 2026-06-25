# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — ¡Quac! (GUI)
# Run: python -m PyInstaller quac.spec --clean

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

APP_DIR = Path(SPECPATH)

# Modelo spaCy español (se empaqueta completo) + recursos de paquetes
datas = []
datas += collect_data_files("es_core_news_sm")
datas += collect_data_files("spacy")
datas += collect_data_files("pyvis")        # plantillas HTML de la red
datas += collect_data_files("trafilatura")
datas += collect_data_files("justext")      # stoplists (fallback de trafilatura)
datas += collect_data_files("courlan")      # usado por trafilatura
datas += [(str(APP_DIR / "README.md"), ".")]

hiddenimports = []
hiddenimports += collect_submodules("es_core_news_sm")
hiddenimports += collect_submodules("spacy")
hiddenimports += collect_submodules("thinc")
hiddenimports += collect_submodules("sklearn")     # NMF (topic_engine)
hiddenimports += [
    # paquetes propios de ¡Quac!
    "core", "core.ner_engine", "core.sentiment_engine", "core.network_engine",
    "core.confianza_engine", "core.frame_engine", "core.coref_engine",
    "core.topic_engine", "core.collocation_engine", "core.lexicon_engine",
    "core.viz_engine", "core.entity_linker", "core.timeline_engine",
    "scrapers", "scrapers.base", "scrapers.medios", "scrapers.registro",
    "scrapers.limpieza", "scrapers.captura_navegador",
    "busqueda", "busqueda.criterios", "busqueda.motor",
    "db", "pipeline", "analisis_avanzado", "revision",
    "dashboard", "spacy_loader", "calidad", "config", "sentimiento_politico",
    "validacion", "exportar_excel", "openpyxl", "et_xmlfile",
    "openpyxl.cell._writer",
    # terceros que PyInstaller a veces no detecta
    "bs4", "lxml", "trafilatura", "httpx", "websocket", "networkx",
    "pyvis", "sklearn.utils._cython_blas", "sklearn.utils._typedefs",
    "scipy._lib.array_api_compat.numpy.fft",
    "justext", "courlan", "htmldate", "trafilatura.external",
    "trafilatura.metadata",
]

block_cipher = None

a = Analysis(
    [str(APP_DIR / "gui.py")],
    pathex=[str(APP_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["torch", "tensorflow", "transformers", "matplotlib"],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Quac",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # app GUI, sin consola
    icon=None,
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=True, upx_exclude=[],
    name="Quac",
)

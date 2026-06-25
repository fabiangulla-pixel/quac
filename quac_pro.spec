# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — ¡Quac! PRO (con transformers: pysentimiento + BERTopic)
# Construir DESDE el venv Python 3.12:
#   C:/quac_pro_env/Scripts/pyinstaller.exe quac_pro.spec --clean --noconfirm
# El .exe resultante es grande (~3GB) porque incluye torch + transformers.

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

APP_DIR = Path(SPECPATH)

datas = []
datas += collect_data_files("es_core_news_sm")
datas += collect_data_files("spacy")
datas += collect_data_files("pyvis")
datas += collect_data_files("trafilatura")
datas += collect_data_files("justext")
datas += collect_data_files("courlan")
datas += [(str(APP_DIR / "README.md"), ".")]
# handControls.js: dashboard.py lo lee en tiempo de ejecución para incrustar el
# control por gestos de mano en el HTML. DEBE empaquetarse o el .exe no lo halla.
datas += [(str(APP_DIR / "handControls.js"), ".")]
# studyInfo.js: panel de información técnica del estudio, incrustado en runtime.
datas += [(str(APP_DIR / "studyInfo.js"), ".")]
# pysentimiento / transformers / tokenizers traen archivos de datos
datas += collect_data_files("pysentimiento")
datas += collect_data_files("transformers")
datas += collect_data_files("tokenizers")

hiddenimports = []
hiddenimports += collect_submodules("es_core_news_sm")
hiddenimports += collect_submodules("spacy")
hiddenimports += collect_submodules("thinc")
hiddenimports += collect_submodules("sklearn")
hiddenimports += collect_submodules("pysentimiento")
hiddenimports += collect_submodules("transformers")
hiddenimports += collect_submodules("torch")
hiddenimports += collect_submodules("sentence_transformers")
hiddenimports += collect_submodules("bertopic")
hiddenimports += collect_submodules("umap")
hiddenimports += collect_submodules("hdbscan")
hiddenimports += [
    "core", "core.ner_engine", "core.sentiment_engine", "core.network_engine",
    "core.confianza_engine", "core.frame_engine", "core.coref_engine",
    "core.topic_engine", "core.collocation_engine", "core.lexicon_engine",
    "core.viz_engine", "core.entity_linker", "core.timeline_engine",
    "scrapers", "scrapers.base", "scrapers.medios", "scrapers.registro",
    "scrapers.limpieza", "scrapers.captura_navegador",
    "busqueda", "busqueda.criterios", "busqueda.motor",
    "db", "pipeline", "analisis_avanzado", "revision", "dashboard",
    "spacy_loader", "calidad", "config", "sentimiento_politico",
    "prominencia", "origen_medios", "lineas_tiempo",
    "transformer_lotes", "automatico",
    "social", "social.base", "social.registro", "social.youtube",
    "social.tiktok", "social.x_twitter",
    "validacion", "exportar_excel", "openpyxl", "et_xmlfile",
    "bs4", "lxml", "trafilatura", "httpx", "websocket", "networkx", "pyvis",
    "justext", "courlan", "htmldate",
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
    # NO excluir torch/transformers aquí — son el punto de la versión PRO
    excludes=["tensorflow", "matplotlib"],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Quac_PRO",
    debug=False, bootloader_ignore_signals=False, strip=False,
    upx=False,          # UPX puede corromper DLLs de torch
    console=False, icon=None,
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, upx_exclude=[],
    name="Quac_PRO",
)

# Changelog — ¡Quac!

## Sesión 2026-06-19/20 (v0.15): prominencia, origen, líneas de tiempo, redes en GUI

Sesión orientada a la **prueba definitiva (Cepeda vs De la Espriella)**: nuevas
señales de análisis, integración de funciones que solo estaban en CLI, mejora de
la calidad del scraping y recompilación del .exe.

### Funcionalidades nuevas

| Área | Qué se hizo |
|------|-------------|
| Prominencia | `prominencia.py` (NUEVO): **quién aparece primero** (posición/lead, rango) y **con qué adjetivos** se le califica (dependencias spaCy + ventana, con carga pos/neg). Tarjeta 🥇 en dashboard. |
| Origen del medio | `origen_medios.py` (NUEVO): **país del medio** (colombiano vs extranjero) por tabla curada + perfil + TLD. Corpus: 1141 CO / 554 ext / 168 desc. Tarjeta 🌎. |
| Líneas del tiempo | `lineas_tiempo.py` (NUEVO): series **diarias** con media móvil — **sesgo medio→candidato**, volumen+picos, tono por candidato, encuadre. **Filtrable por medio o grupo** (¿cambia su tendencia?). Pestaña 📈 en dashboard. |
| Búsqueda masiva | Llevada a la **GUI** (casilla + días/tramo); antes solo CLI. Verificado: 100 → 400 resultados con troceo. |
| Redes sociales | Pestaña **📱** en la GUI (YouTube/TikTok/X + API key + filtro de audiencia); antes solo CLI. |
| Retomar corpus | Botones **📂 Elegir…** y **📂 Abrir BD y analizar lo ya guardado**: analiza una BD existente sin re-buscar/scrapear. |

### Bugs / mejoras (causa raíz → solución)
- **Autor no se capturaba** (corpus_grande = 0 autores): la ruta navegador/CDP
  extraía el autor del HTML real y lo **descartaba** al construir la `Nota`. Fix en
  `scrapers/base.py`: propaga autor+fecha del reprocesamiento + JSON-LD/meta del
  HTML renderizado. Aplica a notas NUEVAS.
- **Boilerplate en el cuerpo** (16% de notas, sobre todo El Tiempo): horóscopo,
  crucigrama, "Videos Eltiempo", "signos del zodiaco". Causa: se leía el innerText
  del `<body>` cuando no había `<article>` limpio. Solución: `limpiar_cuerpo`
  ampliado (reducción 100% del ruido auditado) + JS de `captura_navegador` que
  elige el contenedor de artículo con más texto antes de caer al body +
  `LOAD_SETTLE_S` 3→5s. **Verificado que el cuerpo se captura COMPLETO** (mediana
  540 palabras, 66% con 400+, 0 vacías) — no titulares.
- **.exe PRO recompilado** con las 3 funciones nuevas (`quac_pro.spec` actualizado
  con prominencia/origen_medios/social/lineas_tiempo en hiddenimports). **ARRANCA
  ESTABLE** (ya no crashea: torch carga perezoso). Copiado a "Para usar en cualquier
  PC/Quac_PRO" + acceso directo "Quac (exe)" en el Escritorio.

### Archivos
- NUEVOS: `prominencia.py`, `origen_medios.py`, `lineas_tiempo.py` + sus 3 tests.
- MODIFICADOS: `pipeline.py` (integra las 3 señales), `dashboard.py` (3 secciones +
  pestaña 📈), `gui.py` (masiva + pestaña redes + retomar BD), `scrapers/base.py`
  (autor), `scrapers/captura_navegador.py` (selector de artículo + settle),
  `scrapers/limpieza.py` (boilerplate), `quac_pro.spec`.

### Investigación de última hora (GitHub/HF/arXiv)
- **Fundus** (F1 97.69%, mejor que trafilatura) NO aplica: solo cubre US/Europa, sin
  medios colombianos. Anotado por si se escriben parsers para Colombia.
- Modelos PLN español punteros 2025-26 siguen siendo BETO/RoBERTuito/**pysentimiento**
  (ya en uso). No hay upgrade libre que supere lo actual. Quac alineado con el estado del arte.

### Pendientes para la próxima sesión
1. **CORRER LA PRUEBA DEFINITIVA** (Cepeda vs De la Espriella): GUI Buscar (☑ masiva,
   2026-06-01→06-21) → Análisis (☑ transformer) → dashboard → pestaña 📈. O directo:
   "Base de datos" = `datos/corpus_grande.db` → "📂 Abrir BD y analizar lo ya guardado".
2. Re-correr el estudio con corpus grande y actualizar `docs/BORRADOR_RESULTADOS.md`.
3. YouTube: generar API key (Google Cloud → YouTube Data API v3) y pegarla en 📱.
4. Validar tono con Kappa (`datos/muestra_validacion_tono.csv`).
5. Re-scrapear muestra para poblar AUTOR (las 1863 actuales no lo tienen).

### Tests
81 pasan (`python -m pytest tests/ -q`).

## Sesión 2026-06-15

Sesión larga: de un MVP a una herramienta de investigación de prensa electoral
con análisis lingüístico computacional + humanidades digitales, dos modos de
ejecución, y corpus ampliable (prensa masiva + redes sociales).

### Funcionalidades añadidas

| Área | Qué se hizo |
|------|-------------|
| Dashboard | Grafo interactivo **2D/3D rotable** (vis-network + 3d-force-graph), gráficas Chart.js, KWIC, comparativa de candidatos, tendencia de medios, tarjeta de toxicidad. Red **estabilizada y congelada** (ya no es "nube de moscas": top-60 nodos, etiquetas selectivas, hover resalta vecinos). |
| Sentimiento | **Polaridad política discriminante** (léxico) — antes todo salía "confianza". Opción **transformer (pysentimiento)**: sentimiento+emoción+**odio**+ironía. |
| Metodologías DH | Tesis Garzón-Velandia (USC 2024): **índice de polarización afectiva** + marco **nosotros/ellos** (endogrupo/exogrupo). Framing con marcos del perfil. |
| Medios | **Tendencia/filiación política**: tono de cada medio hacia cada candidato + índice de sesgo (a quién favorece). |
| Validación | `validacion.py`: muestra reproducible + **Kappa de Cohen** (para publicar). |
| Excel | `exportar_excel.py`: libro multi-hoja para el paper. |
| Perfil | `config.py`: perfil de usuario persistente + diccionario NER curado de la 2ª vuelta; pestaña ⚙ Configuración. |
| Corpus prensa | **Búsqueda masiva** (`buscar --masivo`): trocea fechas×términos → 204→**2704 notas / 340 medios**. |
| Redes sociales | Capa enchufable `social/` (YouTube/TikTok/X) con **métricas de audiencia** + filtro; comando `social`; se analiza con el mismo pipeline. |
| Empaquetado | Versión completa vía **lanzador `Quac.bat`** (venv Py3.12); acceso directo único "Quac". Instaladores `instalar.py` / `instalar_pro.py`. |

### Bugs resueltos (causa raíz → solución)
- **spaCy no cargaba en el .exe** ("Can't find model"): spacy.load busca paquete,
  no resuelto en frozen → `spacy_loader.py` carga por RUTA (sys._MEIPASS).
- **justext/stoplists faltaban en el .exe** (WinError 3 en trafilatura) →
  `collect_data_files("justext"/"courlan")` en el spec + `extraer_generico`
  blindado con fallback BeautifulSoup.
- **Búsqueda 0 resultados:** el filtro anti-buscador excluía `news.google.com` →
  borraba todos los enlaces de Google News. Fix: excluir solo bing/google SEARCH
  directo. (Petro→103, Cepeda→100). Test de regresión añadido.
- **Encoding/mojibake** ("prohibiciÃ³n"): requests asumía ISO-8859-1 → usar
  apparent_encoding. UnicodeEncodeError en consola → UTF-8 en stdout.
- **Ruido NER** (Además/PUBLICIDAD/WhatsApp) + variantes sin unir →
  `scrapers/limpieza.py` (filtro + canonicalización, sin tocar motores de Bashkar).
- **GUI se colgaba al abrir** (venv): `transformer_disponible()` importaba torch
  durante la construcción → usar `importlib.util.find_spec` (no importa).
- **torch/transformers SEGFAULTEAN en Python 3.14** (incompat. binaria): la versión
  normal (3.14) se blindó para no cargarlos; la completa corre en venv **Py3.12**.
- **.exe PRO crashea** (torch+PyInstaller, access violation) → descartado; se usa
  el lanzador `Quac.bat` desde el venv 3.12.
- **bing.com / "generico" como medios** → excluidos / derivar nombre del dominio.
- **Pestañas de Chrome acumulándose** → `_cerrar_tab` tras cada captura.
- **Pestaña pegada / mojibake El Colombiano / fechas vacías** → varios fixes de
  scraping y propagación de fecha desde la búsqueda.

### Pendientes para la próxima sesión
1. Scrapear una **muestra estratificada** del corpus masivo (datos/corpus_masivo_urls.json,
   2704 URLs) y re-correr el estudio con corpus grande.
2. Probar **YouTube** con API key real (guía en README §Corpus de redes sociales).
3. Mostrar **métricas sociales** (vistas/likes) en el dashboard.
4. **Validar el tono** (Kappa): codificar datos/muestra_validacion_tono.csv.
5. Integrar el corpus social en la GUI (hoy solo por CLI `social`).

### Tests
55 pasan (`python -m pytest tests/ -q`).

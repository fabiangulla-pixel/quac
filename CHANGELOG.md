# Changelog — ¡Quac!

## Sesión 2026-06-30: costo IA cableado + 3 fixes de calidad de datos

Sesión de "resolver pendientes". Además se **desactivó la tarea programada de
Windows `Quac_Analisis_6am`** (a petición del usuario): queda `Disabled`,
reactivable con `Enable-ScheduledTask -TaskName Quac_Analisis_6am`.

### Estándar de costo IA — cableado a la CLI (antes era motor huérfano)

| Commit | Qué |
|--------|-----|
| `ebd0817` | `core/costos.py` + `tests/test_costos.py` (10 tests) bajo control de versiones. Tabla de precios Claude, `estimar_lote_tono()`, `costo_real_desde_usages()`. `sentiment_engine.analizar_corpus_tono(devolver_costo=True)` → `(resultados, CostoReal)`. |
| `0fbe2f7` | **Comando CLI `tono`**: estima volumen→tokens→USD, muestra el resumen, **pide confirmación antes de gastar** (`--si` para flujos automáticos), ejecuta el lote y reporta el **costo REAL** del usage. Lee titular+cuerpo de la BD; `--salida` guarda resultados+costo en JSON. 3 tests (cancelar NO llama a Claude; sin key falla; `--si` estima y ejecuta). Probado en `quac.db`: estima **$12.88 USD** para 3 572 notas y cancela sin gastar. |

`analizar_corpus_tono` (Claude por lote) estaba implementado pero sin llamador.
El pipeline usa `analizar_emociones` (léxico, offline) para el sentimiento; el
motor Claude de tono ahora tiene su punto de disparo en la CLI con el estándar
de costo completo.

### Calidad de datos — 3 fixes de raíz (lección [[feedback_calidad_datos_antes_que_features]])

| Commit | Causa raíz | Solución |
|--------|------------|----------|
| `d068f33` | Los enlaces de **Bing News RSS** (`apiclick.aspx?...&url=<medio real>`) NO se desenvolvían → la nota se guardaba con `medio="bing.com"` (ruido que llegaba al dashboard y a la muestra de validación). | `busqueda/motor._desenvolver_bing` extrae la URL real del parámetro `url=`. 2 tests. **Nota: arregla notas NUEVAS; las filas bing.com ya en `quac.db` siguen ahí (pendiente purgarlas).** |
| `182c9f3` | La canonicalización emparejaba semillas **sensible a acentos**: "Ivan Cepeda" (sin tilde, frecuente en scraping) quedaba como nodo separado de la semilla "Iván Cepeda". | `canonicalizar_personas` + `_tokens_significativos` pliegan acentos con `_norm_rel`. +1 test. |
| `4345798` | La tabla `entidades_interes` de la BD traía **semillas basura** ("Petro" e "Iván Cepeda" como canónicos PROPIOS, "Iván Cepeda Castro" sin variantes) que, al hacer `.update()`, **pisaban al perfil** y partían un actor en varios nodos del grafo. | `cli._combinar_semillas`: **el PERFIL manda** — descarta los canónicos de BD que son variante reclamada por el perfil y une variantes sin perder ninguna. +1 test. También: `analizar` gana `--estricto`, `--oblig`, `--excluir`, `--dashboard` (genera el HTML, antes solo la GUI). |

### Reanálisis estricto del corpus publicable (EN CURSO al cerrar)

- Se corrió `analizar --estricto --oblig "Cepeda,De la Espriella,Espriella"
  --excluir "Fujimori,Keiko,Boluarte,Florentino Pérez" --peso-minimo 2
  --dashboard datos/quac.dashboard.html --excel datos/quac.xlsx`.
- Run 1 y 2 revelaron el split Petro/Cepeda → motivaron los fixes de acentos y
  de semillas. **Run 3 (con TODOS los fixes) TERMINÓ OK (exit 0).** Verificado
  el merge: Cepeda 1755+177→**Iván Cepeda Castro 1894** (un nodo); Petro
  1036+463→**Gustavo Petro 1141** (un nodo); Espriella 2155. Grafo 48→**45
  nodos** (sin duplicados), densidad 0.59. `datos/quac.dashboard.html` y
  `datos/quac.xlsx` regenerados 07:35 con datos LIMPIOS. **El dashboard
  publicable ya está listo.**
- Backup `datos/quac.db.bak_20260630_0619` antes de tocar la BD.
- Corpus tras filtro estricto: 3 572 → **2 575 notas** (descarta ~1 000 de ruido).
- **14 118 entidades dudosas** en cola de revisión (HITL) — alto, revisar.

### Validación Kappa — preparada, pendiente de codificación humana

`datos/muestra_validacion_tono.csv` (50 notas, `polaridad_auto` poblada,
`polaridad_manual` VACÍA). Decisión del usuario: **la codifica él a mano**; yo
no invento la codificación (invalidaría el Kappa). Pendiente: regenerar la
muestra desde el corpus LIMPIO (sin bing.com) tras el run 3, codificar y correr
`python cli.py --db datos/quac.db validar --concordancia datos/muestra_validacion_tono.csv`.

### Pendientes para la próxima sesión

1. **Re-correr el reanálisis estricto** (comando arriba) y verificar Petro/Cepeda
   en un solo nodo en el dashboard y la tabla de actores.
2. **Purgar las filas `bing.com` ya en `quac.db`** (desenvolver su URL y
   re-derivar el medio, o borrarlas) — el fix solo cubre notas nuevas.
3. **Regenerar `muestra_validacion_tono.csv`** desde el corpus limpio para que
   el usuario codifique el Kappa.
4. Recompilar el `.exe` PRO (incluye `costos.py`, comando `tono`, los 3 fixes).
5. Revisar la cola HITL (14 118 entidades dudosas es mucho).

---

## Sesión 2026-06-25 (v0.16): panel técnico del grafo + control de calidad (git/lint/CI)

Sesión doble: una funcionalidad nueva en el dashboard y la elevación del proyecto
al estándar de ingeniería (antes no tenía git, lint ni CI).

### Funcionalidad nueva — panel de información técnica del estudio

| Qué | Detalle |
|-----|---------|
| `studyInfo.js` (NUEVO) | Panel PERMANENTE en la pestaña "Red interactiva": lateral fijo a la derecha de la red, tipografía monoespacio, legible sin hover. **Todo se calcula en el frontend** desde el grafo ya cargado (sin servidor ni deps nuevas). |
| Métricas | Corpus (fuente, rango de fechas, nº documentos) · Grafo (nodos, aristas, **densidad 2E/N(N-1)**, tipo dirigido/no dirigido/bipartito, pesos sí/no) · Grado (prom/máx+nodo/mín sin aislados/nº aislados) · Componentes (nº, mayor, ¿conexo?) · **Diferido en setTimeout** (no bloquea el render 3D): clustering promedio + diámetro (omite si N>5000) · Top-5 por grado · botón **"Copiar métricas"** (texto plano). |
| Integración | `dashboard.py` incrusta el módulo igual que `handControls.js` (reemplaza `/*__STUDYINFO_JS__*/`, lee en runtime, busca en `sys._MEIPASS` para el .exe) + CSS `.study-panel`/`.red-wrap` + monta en `#study-mount`. `quac_pro.spec` lo empaqueta en datas. |
| Verificado | Lógica probada con Node sobre el grafo real (48 nodos, 518 aristas, densidad 0.4592, Cepeda grado máx 47, conexo). Dashboard real regenerado (1989 notas relevantes) con el panel incrustado. **.exe PRO recompilado** (94 MB) con `studyInfo.js` empaquetado en `_internal/`. No rompe la viz 3D ni los gestos de mano. |

Forma real del grafo (confirmada): `nodes={id,categoria,color,freq}`,
`edges={source,target,weight}` → **no dirigido con pesos**.

### Modo-Ingeniero — el proyecto no tenía control de versiones ni calidad estática

- **Causa raíz:** Quac se desarrolló sin git, `.gitignore`, lint ni CI. Riesgo alto:
  `datos/` pesa **11 GB** (BD + dashboards + Excel), `dist/` 1.8 GB, `build/` 508 MB.
- **Git:** `git init` + identidad (Fabian Gulla) + `.gitignore` (excluye datos/dist/
  build/BD/secretos) + `.gitattributes` (normaliza LF/CRLF en Windows). 2 commits:
  estado inicial (92 archivos, 19721 líneas) + fix de check.bat. Verificado que NADA
  pesado se versiona (commit inicial = 1.6 MB).
- **Lint+formato (ruff):** instalado en el venv PRO + `pyproject.toml` [tool.ruff]
  (select E/F/I/B/C4/UP/W; ignore documentado de reglas que cambiarían semántica).
  **De 340 errores → 0** (243 autofix + 61 archivos formateados). Código muerto
  eliminado: variable `mapa` en `analisis_avanzado.py`, `medios` en `busqueda/motor.py`.
- **CI local:** `Makefile` + `check.bat` (cp1252-safe, sin unicode) + hook de
  pre-commit (`scripts/install_hooks.py`) **verificado funcionando** (corre lint+
  formato+tests y deja pasar el commit). 88 tests pasan.
- **Higiene:** `scratch_regen.py` (temporal de la sesión) → archivado en
  `scripts/_experimentos/regen_dashboard_bd.py` con README (regenera el dashboard
  desde la BD sin re-scrapear). pytest+ruff ahora presentes en el venv.

### Pendiente Kappa preparado

`datos/muestra_validacion_tono.csv` con 50 notas (polaridad_auto poblada:
7 neg / 21 neu / 22 pos; `polaridad_manual` VACÍA). **Falta codificación humana**
(es el sentido del Kappa) y luego:
`python cli.py --db datos/quac.db validar --concordancia datos/muestra_validacion_tono.csv`

### Archivos
- NUEVOS: `studyInfo.js`, `.gitignore`, `.gitattributes`, `pyproject.toml`,
  `Makefile`, `check.bat`, `scripts/install_hooks.py`,
  `scripts/_experimentos/regen_dashboard_bd.py` (+README).
- MODIFICADOS: `dashboard.py` (incrusta panel + CSS + montaje), `quac_pro.spec`
  (+studyInfo.js), `analisis_avanzado.py` y `busqueda/motor.py` (código muerto),
  +61 archivos reformateados por ruff.

### Lección
Regenerar el dashboard desde BD tarda ~17 min (3423 notas, fase NER la más larga).
**No correr con pipe a grep** (el buffer no se vacía y parece colgado): usar
`python -u` con log a archivo propio.

---

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

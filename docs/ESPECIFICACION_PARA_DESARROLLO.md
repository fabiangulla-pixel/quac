# ¡Quac! — Especificación para desarrollo

> Documento para entregar a otra IA o equipo de desarrollo. Describe **qué** es
> el programa y **qué debe hacer**, no cómo está implementado el original.

---

## 1. Resumen en una frase

**¡Quac!** es una aplicación de escritorio (Windows, en español) para el
**análisis computacional de la cobertura mediática de un proceso electoral**:
descubre y descarga noticias de prensa digital (y opcionalmente redes sociales),
las procesa con PLN (entidades, sentimiento, encuadre, redes de actores) y
produce un **dashboard interactivo + un Excel** con los hallazgos, pensado para
sustentar un **paper académico** de humanidades digitales / lingüística
computacional.

Caso de uso semilla: segunda vuelta presidencial de Colombia 2026
(Iván Cepeda vs. Abelardo de la Espriella), pero el perfil es **configurable**
para cualquier elección o tema.

---

## 2. Objetivo del usuario

Un investigador quiere responder, con evidencia cuantitativa y reproducible:

- ¿**Quién** aparece en la prensa, **cuánto** y con **qué tono**?
- ¿Con **qué encuadre/marco** (seguridad, economía, integridad electoral,
  estrategia de campaña…) se cubre a cada candidato?
- ¿Qué **medios** favorecen o desfavorecen a quién (sesgo/filiación)?
- ¿Cómo **evoluciona en el tiempo** el volumen y el tono?
- ¿Cómo es la **red de co-ocurrencia** de actores?
- ¿Hay **discurso de odio** o polarización afectiva?
- Y poder **defender metodológicamente** los resultados (validación con Kappa).

---

## 3. Arquitectura funcional (4 capas)

```
┌─────────────────────────────────────────────────────────────┐
│ 1. INGESTA          Descubrir y descargar el corpus           │
│    - Búsqueda (términos + fechas + entidades) vía Google News │
│    - Búsqueda MASIVA (trocea fechas×términos: miles de notas) │
│    - Scraping en cascada: selectores → trafilatura → navegador│
│    - (Opcional) Redes sociales: YouTube / TikTok / X          │
├─────────────────────────────────────────────────────────────┤
│ 2. ALMACENAMIENTO   SQLite por proyecto                        │
│    - Tabla de notas con dedupe por URL y por hash de contenido│
│    - Guarda fecha de captura (trazabilidad), screenshot, etc. │
├─────────────────────────────────────────────────────────────┤
│ 3. ANÁLISIS (PLN)   Pipeline texto → métricas                 │
│    - NER + canonicalización (unir variantes de un nombre)     │
│    - Sentimiento/polaridad política (léxico o transformer)    │
│    - Encuadre/framing, discurso de odio, polarización         │
│    - Red de co-ocurrencia, series temporales, tópicos         │
│    - Control de calidad de extracción + validación (Kappa)    │
├─────────────────────────────────────────────────────────────┤
│ 4. PRESENTACIÓN     Resultados para humanos y para el paper   │
│    - Dashboard HTML interactivo (red 2D/3D, gráficas, KWIC)   │
│    - Exportación a Excel multi-hoja + grafo Gephi             │
│    - GUI de escritorio en español                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Funcionalidades detalladas (requisitos)

### 4.1 Ingesta / descubrimiento de notas
- **Búsqueda por criterios:** términos/frases + rango de fechas (desde/hasta) +
  entidades de interés (con variantes). Motor universal sin API key vía
  **Google News RSS**; respaldo Bing News RSS.
- **Búsqueda masiva:** trocear el rango de fechas en ventanas (p. ej. 7 días) y
  cruzarlas con cada término para superar el límite (~100 resultados) de Google
  News y reunir **miles** de URLs. Salida: un JSON `[{url, fecha, medio, titular}]`.
- **Resolución de enlaces de Google News:** los enlaces RSS de GNews son opacos
  (no contienen la URL real). Hay que **abrirlos en un navegador real** (el JS
  redirige al medio) y leer la URL final. Requisito clave: integración con un
  navegador controlable (CDP/Chrome DevTools Protocol o Playwright).

### 4.2 Scraping
- Cascada de extracción de 3 niveles por nota:
  1. **Selectores por medio** (adaptadores dedicados a los portales frecuentes:
     usar JSON-LD / OpenGraph + selectores CSS del cuerpo).
  2. **trafilatura** (extracción genérica de artículos) como respaldo.
  3. **Navegador real (CDP/Playwright)** para notas con JavaScript, muros de
     consentimiento de cookies o suscripción del usuario.
- **Ética obligatoria:** respetar `robots.txt`, rate-limit por dominio (~2 s),
  **no evadir paywalls** (usar solo el acceso legítimo que el usuario ya tiene
  en su sesión), guardar `fecha_captura` para trazabilidad.
- **Auto-aceptar banners de cookies** (Didomi/OneTrust/Quantcast…) vía el navegador.
- **Limpieza:** quitar boilerplate (menús, "PUBLICIDAD", "comparte en WhatsApp"),
  arreglar encoding/mojibake, deduplicar por hash de contenido.
- **Control de calidad por nota:** puntaje 0–1 + veredicto (confiable / revisar /
  basura) según longitud, ratio de boilerplate, repetición de líneas, etc., para
  poder excluir basura del análisis.

### 4.3 Redes sociales (opcional, enchufable)
- Adaptadores intercambiables que devuelven `Publicacion` con **métricas de
  audiencia** (vistas, likes, comentarios, compartidos, seguidores):
  - **YouTube** — YouTube Data API v3 (gratis con API key): videos + comentarios.
  - **TikTok** — Research API (requiere afiliación académica).
  - **X/Twitter** — vía sesión de navegador (frágil; documentar como zona gris).
- Filtro por audiencia (mínimo de vistas/interacciones, top-N).
- Las publicaciones se convierten a "notas" y se analizan con **el mismo pipeline**.

### 4.4 Análisis (pipeline PLN)
- **NER** en español (modelo tipo spaCy `es_core_news_sm/md`; opción de un
  modelo BERT/RoBERTa para mayor precisión).
- **Canonicalización** de entidades: unir "Cepeda" / "Iván Cepeda" / "Senador
  Cepeda" en una sola, **sembrable** con las variantes que declara el usuario en
  el perfil. Coincidencia estricta para no etiquetar mal homónimos.
- **Sentimiento / polaridad política:** debe ser **discriminante** (positivo /
  negativo / neutro), no un léxico genérico que dé todo "confianza". Dos modos:
  - **Léxico** (rápido, offline, sin dependencias pesadas).
  - **Transformer** (p. ej. pysentimiento/robertuito): sentimiento + emoción +
    **discurso de odio** + ironía. Carga perezosa, con fallback al léxico.
- **Encuadre / framing:** clasificar cada nota en marcos temáticos (basados en
  el Media Frames Corpus + marcos del dominio definidos en el perfil). El salto
  metodológico clave es pasar de "tono" a "ángulo/encuadre".
- **Polarización afectiva** y marco **nosotros/ellos** (endogrupo/exogrupo).
- **Tendencia/filiación de medios:** tono medio de cada medio hacia cada
  candidato + índice de sesgo (a quién favorece).
- **Red de co-ocurrencia** de actores (networkx): métricas de centralidad.
- **Series temporales:** volumen / tono / encuadre por mes.
- **Tópicos:** NMF (clásico) y opción BERTopic (embeddings).
- **Colocaciones (PMI)** del actor principal; frecuencias de términos.
- **Correferencia** (heurística + opcional avanzada) para contar menciones reales.
- **Human-in-the-loop:** cola de entidades dudosas puntuadas por confianza, que
  el usuario verifica / descarta / renombra; las decisiones persisten y se
  re-aplican.

### 4.5 Validación metodológica (para publicar)
- Exportar una **muestra aleatoria reproducible** (semilla fija) a CSV con la
  polaridad automática, para codificar a mano.
- Calcular **acuerdo % + Kappa de Cohen** + matriz de confusión (auto vs. manual).

### 4.6 Presentación
- **Dashboard HTML interactivo autocontenido** (un archivo, librerías por CDN):
  - Red de actores **2D y 3D rotable** (vis-network + 3d-force-graph): filtrar
    por tipo de entidad, aislar ego-red, clic en nodo → ficha del actor.
  - Gráficas (Chart.js): barras de actores/encuadre, línea temporal, dona de
    emociones.
  - **KWIC** (concordancias: palabra clave en contexto) por actor.
  - Comparativa de candidatos (visibilidad / tono / encuadre) y tabla de
    tendencia de medios. Tarjeta de toxicidad si hay datos de odio.
- **Excel multi-hoja** (openpyxl): Candidatos, Tendencia de medios, Notas,
  Series, Frecuencias, Tópicos, Cobertura por tipo, Calidad.
- **Exportar grafo Gephi** (.gexf).

### 4.7 Perfil configurable
- Perfil de usuario **persistente** (JSON en `%APPDATA%`): diccionario NER curado
  (entidades con tipo + variantes), lista de medios, marcos temáticos, ventana de
  fechas del estudio, y parámetros por defecto (nº de tópicos, calidad mínima,
  mínimo de palabras por nota, stopwords extra).
- Editable desde la GUI; restaurable a una "semilla" de referencia.
- Recomendación metodológica embebida: el NER no debe basarse solo en nombres
  propios; hay que añadir **marcos y eventos**, porque en prensa electoral la
  disputa está en "con qué tema/verbo/adjetivo/fuente aparece" cada actor.

---

## 5. Interfaces de usuario

### 5.1 GUI de escritorio (español)
Flujo en pestañas:
1. **Buscar** — términos, fechas (desde/hasta), tabla de entidades, casilla de
   búsqueda masiva, API key opcional.
2. **Resultados** — total de notas encontradas + lista con casillas para elegir
   cuáles descargar + filtro por medio.
3. **Análisis** — casillas para elegir qué análisis correr + parámetros
   (calidad mínima, nº tópicos, etc.) + casillas de transformer/BERTopic.
4. **⚙ Configuración** — editar/guardar/restaurar el perfil.

Corre búsqueda+scraping+análisis en un hilo (no congelar la ventana) y abre el
dashboard al terminar. Muestra un indicador de modo (si hay transformers o no).

### 5.2 CLI (subcomandos)
- `medios` — listar portales con adaptador dedicado.
- `buscar` — descubrir + descargar (flags `--masivo`, `--dias-tramo`, `--filtrar`).
- `corpus <json>` — descargar un corpus masivo desde el JSON de `buscar --masivo`
  (reanudable: salta lo ya descargado; siembra el perfil automáticamente).
- `scrape` — descargar URLs sueltas o de un archivo.
- `social` — recolectar de redes sociales (filtro por audiencia).
- `analizar` — correr el pipeline (flags `--transformer`, `--bertopic`, `--excel`,
  `--salida` red.html, `--gephi`, `--peso-minimo`).
- `revisar` — human-in-the-loop de entidades dudosas.
- `validar` — exportar muestra / calcular Kappa.
- `listar` — conteo de notas por medio.

---

## 6. Requisitos no funcionales

- **Plataforma:** Windows 10/11. Empaquetable como `.exe` (PyInstaller) o
  lanzador de entorno virtual.
- **Idioma de toda la interfaz:** español.
- **Local-first:** funciona **offline** por defecto; las API keys (Anthropic,
  YouTube) solo potencian, son opcionales.
- **Reproducibilidad:** semillas fijas en muestreo; trazabilidad por fecha de
  captura y screenshot.
- **Robustez:** ninguna URL/medio que falle debe tumbar la corrida; reanudable.
- **Eficiencia:** la descarga vía navegador es el cuello de botella (segundos por
  URL); diseñar progreso visible, reanudación y, si es posible, paralelismo.
- **Ética/legal:** respetar robots.txt, rate-limit, no evadir paywalls, solo
  contenido público; dejar esto explícito en el README.

---

## 7. Stack tecnológico sugerido (referencia, no obligatorio)

- **Lenguaje:** Python 3.12 (los transformers/torch son inestables en 3.14).
- **PLN:** spaCy (`es_core_news_sm`), pysentimiento (transformer ES), BERTopic
  (opcional), scikit-learn (NMF, métricas), networkx (redes).
- **Scraping:** requests/httpx, BeautifulSoup, lxml, trafilatura; control de
  navegador vía CDP (Chrome DevTools Protocol) o Playwright.
- **Datos:** SQLite (una BD por proyecto).
- **Salidas:** HTML + vis-network + 3d-force-graph + Chart.js (CDN); openpyxl
  (Excel); Gephi `.gexf`.
- **GUI:** Tkinter (o PySide6/Qt si se prefiere algo más moderno).
- **Estadística:** Kappa de Cohen para validación.

> Nota de portabilidad: torch/transformers **segfaultean en Python 3.14**. Si se
> usan transformers, fijar el entorno en 3.12. La versión "ligera" (solo léxico)
> debe poder correr sin torch.

---

## 8. Definición de "terminado" (criterios de aceptación)

1. Desde una elección y unas entidades, la app **descubre miles de noticias**,
   las **descarga** resolviendo los enlaces de Google News, y las guarda
   deduplicadas en una BD.
2. El **análisis** produce: ranking de actores, tono por actor, encuadre
   dominante, tendencia de cada medio, red de co-ocurrencia, series temporales
   y (en modo transformer) detección de odio.
3. Genera un **dashboard interactivo** y un **Excel** coherentes con esas cifras.
4. Permite **validar** el tono automático contra codificación manual con Kappa.
5. Todo en **español**, **offline por defecto**, **reanudable** y respetando la
   **ética** de scraping. Con **tests** que cubran búsqueda, limpieza, pipeline
   y validación.

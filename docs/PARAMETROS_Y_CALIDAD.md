# Parámetros afinables y control de calidad — ¡Quac! para estudios publicables

Documento de referencia para tu estudio de cobertura electoral. Reúne (1) los
parámetros que ¡Quac! deja afinar y por qué importan según la literatura de
humanidades digitales / PLN, y (2) cómo garantizamos que el texto analizado sea
la nota y no basura — la base de la validez de los datos.

---

## 1. Parámetros afinables (control metodológico)

La investigación en DH insiste en que el análisis de texto **no es una caja
negra**: cada decisión de preprocesamiento y modelado debe ser explícita y
reproducible (Arnold & Tilton; guías de topic modeling). ¡Quac! expone:

| Parámetro | Qué controla | Por qué importa (literatura) |
|-----------|--------------|------------------------------|
| **Nº de tópicos** | granularidad del topic modeling (NMF) | El nº de tópicos es la decisión central del topic modeling; cambia qué temas emergen. No hay un valor "correcto": se explora. |
| **Umbral de red** (notas/arista) | cuántas notas deben compartir dos actores para conectarlos | Controla densidad/legibilidad de la red de co-ocurrencia. Umbral alto = solo relaciones fuertes. |
| **Ventana de colocaciones** | nº de palabras a cada lado para medir asociación (PMI) | La ventana define qué cuenta como "contexto". Ventanas cortas = relaciones sintácticas; largas = temáticas. |
| **Mín. palabras/nota** | excluir notas demasiado cortas | Filtro estadístico estándar: textos muy cortos distorsionan frecuencias y tópicos. |
| **Calidad mínima** | excluir notas con baja calidad de extracción | Evita que basura (menús, muros) contamine los resultados. Ver §2. |
| **Stopwords extra** | palabras a ignorar (además de las estándar) | Permite quitar términos ubicuos del dominio ("dijo", "según", nombre del medio) que dominan frecuencias sin aportar. |
| **Correferencia on/off** | contar pronombres como menciones del actor | Mejora el conteo real de presencia; cuesta tiempo. |
| **Entidades de interés + variantes** | siembra de canonicalización y expansión de búsqueda | Anclaje del gold standard del investigador (las entidades que importan). |
| **API key (opcional)** | enriquece NER/tono/encuadre con LLM | Potencia, no sustituye, el análisis local. |

**Buenas prácticas para publicar:** corre el análisis variando estos parámetros
y reporta los valores usados (reproducibilidad). ¡Quac! los guarda en el JSON de
resultados.

**Próximos parámetros sugeridos** (roadmap): min_df/max_df del vectorizador de
tópicos, elección lematización vs. forma de superficie, modelo de sentimiento
(léxico vs. transformer pysentimiento vs. LLM), idioma/país de búsqueda.

---

## 2. ¿Cómo confiar en que el texto es la nota y no basura?

Es la pregunta correcta para un estudio serio: **garbage in, garbage out**. La
extracción web siempre arrastra ruido (menús, "lea también", cookies, pies). La
solución de la literatura (Barbaresi, autor de *trafilatura*) combina tres capas:

### Capa 1 — Extracción robusta (ya integrada)
- **trafilatura** es el mejor extractor open-source en los benchmarks de
  extracción de artículos (ScrapingHub, ROUGE-LSum). Usa densidad de texto,
  densidad de enlaces y análisis de etiquetas para aislar el cuerpo.
- Adaptadores por medio con **selectores propios** cuando se conoce el HTML.
- Fallback en cascada: selectores → trafilatura → BeautifulSoup, para nunca
  perder una nota ni tumbar el corpus.
- **Captura con tu Chrome** que ejecuta el JS y **auto-acepta consentimientos**,
  para llegar al contenido real tras muros de cookies.

### Capa 2 — Validación automática de calidad (`calidad.py`, NUEVO)
Cada nota recibe un **score de calidad (0–1)** y un veredicto
(**confiable / revisar / malo**) según métricas de la literatura:
- **Longitud** del cuerpo (textos muy cortos = extracción incompleta).
- **Detección de muro/consentimiento** no superado (frases tipo "contenido
  exclusivo para suscriptores", "acepta las cookies").
- **Ratio de boilerplate** (densidad de frases-UI: "regístrate", "lea también",
  "síguenos"…).
- **Repetición de líneas** (menús/enlaces que se repiten).
- **Densidad de caracteres no textuales** (señal de JS/basura).
El dashboard muestra el resumen y **lista las peores notas primero** para
revisarlas. El investigador puede **excluir por umbral** (parámetro calidad mín.).

### Capa 3 — Revisión humana (human-in-the-loop, `revision.py`)
Para un estudio publicable, la validez no se delega 100% a la máquina. ¡Quac!:
- Marca las **entidades dudosas** (cola de revisión por confianza).
- Permite **validar / descartar / renombrar** con trazabilidad (quién, cuándo).
- Las decisiones se **re-aplican** en análisis futuros (reproducible).

### Veredicto sobre "confiar al 100%"
No existe extracción 100% perfecta automática (los mejores sistemas llegan a
F1≈0.93 en artículos). La estrategia honesta y publicable es: **extraer bien +
medir la calidad + revisar lo dudoso + reportar la tasa de calidad** del corpus
en la metodología. Eso es lo que ¡Quac! ahora hace de punta a punta. Para máxima
confianza en una muestra: revisa manualmente las notas marcadas "revisar/malo"
(son minoría) y, si el estudio lo exige, una submuestra aleatoria de las
"confiable" para estimar precisión.

---

## 2.bis Tipos NER ricos (perfil) y comparativa de candidatos

El perfil de usuario (config.py / quac_config.json) define entidades con su
**tipo del dominio electoral** (candidato, formula_vp, excandidato,
lider_politico, partido_movimiento, autoridad_electoral, organismo_control,
organismo_observacion, encuestadora, justicia…). ¡Quac! usa esos tipos para:
- **Cobertura por tipo**: agrupa los actores detectados por su rol (cuántos
  candidatos, excandidatos, encuestadoras… y su cobertura).
- **Comparativa de candidatos** (tabla central del estudio): para cada candidato,
  visibilidad (nº de notas), tono dominante y encuadre dominante.

Para que la clasificación sea precisa, ¡Quac! **canonicaliza con las semillas del
perfil** (normalización): "Cepeda" → "Iván Cepeda Castro", que es la forma del
diccionario con tipo=candidato. Por eso conviene tener el perfil cargado: la GUI
fusiona automáticamente las semillas del perfil con las de la búsqueda.

## 2.ter Validación metodológica (para publicar)

El análisis automático debe validarse contra codificación humana para ser
defendible en una revista. ¡Quac! incluye el flujo estándar (`validacion.py`):

```
# 1) exporta una muestra aleatoria (reproducible, semilla fija) a CSV
python cli.py --db datos/X.db validar --n 30 --salida datos/muestra.csv
# 2) abre el CSV y codifica a mano la columna 'polaridad_manual'
#    (positivo/negativo/neutro). Ideal: un 2º codificador independiente.
# 3) calcula acuerdo % + Kappa de Cohen
python cli.py validar --concordancia datos/muestra.csv
```

Reporta en tu metodología el **Kappa de Cohen** (acuerdo corregido por azar) y
el % de acuerdo de la muestra. Interpretación estándar (Landis & Koch): <0.20
leve, 0.21–0.40 aceptable, 0.41–0.60 moderado, 0.61–0.80 sustancial, >0.80 casi
perfecto. La polaridad automática se calcula al vuelo, así que no depende de
análisis previos. La muestra usa semilla fija → reproducible por revisores.

## 3. Para tu estudio pre-electoral (todos los candidatos)

Flujo sugerido para resultados "poderosos" y defendibles:
1. Define la lista de **candidatos como entidades de interés** (con variantes:
   "Petro" / "Gustavo Petro", etc.) → siembra canonicalización y búsqueda.
2. Busca por candidato + período; revisa el **total** y selecciona muestra
   (por medio, por fecha) de forma transparente.
3. Scrapea con Chrome (cookies auto) y **revisa el panel de calidad**; excluye
   o corrige lo malo.
4. Corre el análisis comparando **medio × candidato**: visibilidad (nº de notas
   y menciones por coref), **tono** (sentimiento), **encuadre** (framing) y
   **series temporales** (evolución de la cobertura). Estas son justo las
   dimensiones que la literatura de cobertura electoral mide
   (visibilidad + tonalidad + framing).
5. Exporta dashboard + Gephi + JSON; reporta parámetros y tasa de calidad.

Conclusiones típicas que habilita: qué candidato recibe más cobertura y de qué
medios, con qué tono y encuadre cada medio trata a cada candidato, cómo cambia
la cobertura cerca de la elección, y la estructura de la red de actores.

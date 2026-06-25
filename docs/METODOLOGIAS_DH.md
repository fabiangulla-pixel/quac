# Metodologías de Humanidades Digitales para potenciar ¡Quac!

Investigación de enfoques académicos consolidados que dialogan con lo que ¡Quac!
hace (análisis computacional de prensa electoral colombiana) y marcan el roadmap.
Para cada uno: **qué es**, **qué aporta a ¡Quac!**, y **cómo encaja** con lo ya
construido (reutilizando motores de Bashkar siempre que se pueda).

---

## 1. Análisis de *encuadre* / framing (Media Frames Corpus)

**Qué es.** La línea más sólida en análisis computacional de prensa política. El
**Media Frames Corpus (MFC)** operacionaliza el framing en ~15 categorías
*agnósticas al tema* (economía, moralidad, legalidad, seguridad, etc.). Trabajos
recientes (FrAC) lo extienden a artículos + comentarios y a varios países.

**Qué aporta a ¡Quac!** Responde la pregunta central de la investigación: *¿cómo
encuadra cada medio a cada candidato?* No basta el sentimiento (positivo/negativo);
el framing dice *desde qué ángulo* (¿se habla de Cepeda en clave de "seguridad/
FARC" o de "memoria/víctimas"? ¿De la Espriella en clave "legalidad" o "identidad
nacional"?). Es el salto de "tono" a "encuadre".

**Cómo encaja.** Clasificador de frame por nota (zero-shot con un modelo local de
NLI en español, o con Claude si el usuario activa la API key). Cruce
**medio × frame × actor** → la tabla que hoy ya insinúan los agregados por medio.
Roadmap: nuevo `frame_engine.py`.

Refs: Media Frames Corpus; *Retain or Reframe?* (arXiv 2507.04612);
*Generalizability of Media Frames* (arXiv 2506.16337).

---

## 2. Detección de polarización y *selection bias* entre medios

**Qué es.** Métodos que comparan *qué dicen distintas fuentes sobre las mismas
entidades* para revelar sesgo de selección y polarización del paisaje mediático.

**Qué aporta a ¡Quac!** Mide objetivamente la asimetría de cobertura: qué medios
mencionan a qué actores, con qué carga, y qué *callan*. Para una campaña, esto es
el mapa de polarización del ecosistema de prensa.

**Cómo encaja.** ¡Quac! ya tiene el insumo: índice global entidad×nota×medio.
Falta el cruce comparativo (matriz medio×actor con sentimiento/frame y un índice
de divergencia). Roadmap: extender `pipeline._agregados`.

Refs: *Corpus-Scale Discovery of Selection Biases* (arXiv 2304.03414);
*Network analysis reveals news press landscape and asymmetric user polarization*
(arXiv 2408.07900).

---

## 3. Análisis de redes sociales (SNA) con métricas de centralidad

**Qué es.** Tradición consolidada en DH/ciencias sociales: redes de actores con
**betweenness, closeness, eigenvector centrality**, detección de comunidades
(Louvain) y visualización (Gephi).

**Qué aporta a ¡Quac!** Ya lo hacemos en parte (la red de co-ocurrencia con
centralidad y Louvain del `network_engine`). El aporte metodológico es
*interpretar* esas métricas: un actor con alta betweenness es "puente" entre
temas; las comunidades son los "clusters" de la campaña (p. ej. bloque
Cepeda–UP–víctimas vs. bloque De la Espriella–identidad–FCF).

**Cómo encaja.** Está construido. Roadmap: exportar a **Gephi** (network_engine
ya tiene `exportar_gephi`) y documentar la lectura de métricas en el reporte.

Refs: Recuero et al. (2019), *User Roles on Polarized Political Conversations*.

---

## 4. Anotación con *humano en el bucle* (human-in-the-loop)

**Qué es.** El estándar metodológico en corpus políticos serios (p. ej.
AgoraSpeech, debates electorales españoles 1993–2023): **anotación automática
primero, validación humana después**. Garantiza trazabilidad y validez para
publicar.

**Qué aporta a ¡Quac!** Rigor académico. Hoy el NER/sentimiento son automáticos;
para investigación publicable hace falta una capa de revisión y corrección
manual con registro de quién anotó qué.

**Cómo encaja.** Bashkar ya tiene `annotation_engine.py` y `confianza_engine.py`
(semáforo de calidad) — reutilizables. Roadmap: cola de revisión de entidades
dudosas en la GUI (igual que el patrón de confianza de Bashkar).

Refs: *AgoraSpeech* (arXiv 2501.06265); *Annotated Spanish general election
debates 1993–2023* (PMC12480686).

---

## 5. Resolución de correferencia (coreference)

**Qué es.** Resolver que "el candidato", "el senador", "él" y "Cepeda" son el
mismo referente. Componente nuclear de la comprensión de texto.

**Qué aporta a ¡Quac!** Hoy contamos menciones por forma de superficie; la
canonicalización de ¡Quac! une variantes del *nombre*, pero no los *pronombres y
descripciones*. La correferencia mejora el conteo real de menciones y la fuerza
de las aristas de la red.

**Cómo encaja.** Bashkar ya tiene `coref_engine.py`. Roadmap: integrarlo antes
del NER en el pipeline (resolver correferencia → contar menciones reales).

Refs: *Anaphora and coreference resolution: A review* (ScienceDirect 2019).

---

## 6. Modelado de tópicos + series temporales (distant reading)

**Qué es.** "Lectura distante" (Moretti): ver patrones en miles de textos. Tópicos
(NMF/BERTopic) + su **evolución temporal** durante la campaña.

**Qué aporta a ¡Quac!** Los temas de la campaña y *cuándo* emergen (¿el tema FARC
sube tras un evento concreto?). ¡Quac! ya tiene fechas reales por nota → series
temporales ricas.

**Cómo encaja.** Ya integramos `topic_engine` (NMF). Falta cruzar tópico×fecha y
tono×fecha. Bashkar tiene `timeline_engine.py` (ya copiado) — usarlo. Roadmap:
heatmap temporal en la GUI.

---

## Síntesis: roadmap priorizado para ¡Quac!

| Estado | Metodología | Implementación en ¡Quac! |
|--------|-------------|--------------------------|
| ✅ **Hecho** | Framing (#1) | `core/frame_engine.py` (13 frames, léxico ES, LLM opcional) |
| ✅ **Hecho** | Series temporales (#6) | `analisis_avanzado.series_temporales` (volumen/tono/frame por mes) |
| ✅ **Hecho** | Polarización medio×actor (#2) | `analisis_avanzado.comparar_medios` (matriz + emoción/medio) |
| ✅ **Hecho** | Export Gephi + SNA (#3) | `analizar --gephi` (network_engine ya tenía métricas + Louvain) |
| ✅ **Hecho** | Correferencia (#5) | `core/coref_engine.py` + métrica "presencia real" (menciones+pronombres) en el pipeline |
| ✅ **Hecho** | Human-in-the-loop (#4) | `revision.py` (cola por confianza) + `cli.py revisar` (validar/descartar/renombrar, persistido y re-aplicado) |

**Implementado (sesión 2026-06-14):** las SEIS líneas del roadmap.
El framing fue el salto clave (de "tono" a "encuadre"); validado con el corpus
Cepeda+FARC → encuadre dominante "Seguridad/conflicto armado", series con pico de
cobertura en mayo 2026, y correferencia que mide la presencia real de cada actor
(De la Espriella 90 menciones, Petro 83, Cepeda 73…). La revisión human-in-the-
loop puntúa la confianza de cada entidad (frecuencia + entidades de interés) y
deja al investigador validar/descartar/renombrar las dudosas, con trazabilidad,
para un corpus publicable.

**Conclusión.** ¡Quac! ya implementa la base de cuatro de estas seis líneas. Los
dos saltos de mayor valor académico son: **(1) framing** (de "tono" a "encuadre",
el verdadero objeto de la investigación de cobertura electoral) y **(6) series
temporales** (aprovechar las fechas reales que la prensa web sí da, a diferencia
de la histórica de Bashkar). Ambos encajan con la arquitectura actual y, salvo
framing, reutilizan motores ya copiados.

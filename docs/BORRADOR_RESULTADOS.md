# Cobertura mediática de la segunda vuelta presidencial colombiana (2026): un análisis computacional

> Borrador de sección de resultados generado con ¡Quac!. Las cifras provienen del
> corpus analizado el 15-jun-2026 (N=204 notas, 53 medios). **Antes de publicar:**
> ampliar el corpus (ver §6) y validar el tono con codificación humana (Kappa, §5).

## 1. Datos y método

Se recolectaron **204 notas de prensa** de **53 medios** colombianos e
internacionales sobre la segunda vuelta presidencial (Iván Cepeda Castro vs.
Abelardo de la Espriella), mediante búsqueda por términos y rango de fechas
(1–21 jun 2026) sobre Google News y captura del contenido con extracción
automática. El análisis combinó: reconocimiento de entidades (spaCy) con
canonicalización; **sentimiento por transformer** (pysentimiento/RoBERTuito,
clases positivo/negativo/neutro); detección de **discurso de odio**; análisis de
**encuadre** (adaptación del Media Frames Corpus al dominio electoral
colombiano); y **redes de co-ocurrencia** de actores. Se reporta la
visibilidad (volumen de cobertura), el tono, el encuadre y el sesgo por medio.

## 2. Visibilidad y tono por candidato

| Candidato | Notas | Pos | Neg | Neutro | Tono medio | Encuadre dominante |
|-----------|------:|----:|----:|-------:|-----------:|--------------------|
| Iván Cepeda Castro | 142 | 11 | 45 | 86 | −0.18 | Estrategia/campaña |
| Abelardo de la Espriella | 124 | 11 | 46 | 67 | −0.21 | Estrategia/campaña |
| José Manuel Restrepo (VP) | 14 | 1 | 1 | 12 | −0.02 | Estrategia/campaña |

Cepeda recibió **mayor visibilidad** (142 vs. 124 notas). Ambos candidatos
fueron cubiertos con un tono **mayoritariamente neutro pero negativo en el
balance** (más referencias negativas que positivas), consistente con la
literatura sobre el predominio de la negatividad en la cobertura electoral. La
diferencia de tono entre ambos es pequeña (De la Espriella ligeramente más
negativo). Medido por **correferencia** (menciones reales, incluidos pronombres
y descripciones), la presencia se concentra en Petro, Cepeda y De la Espriella
—el presidente en ejercicio articula el marco de la contienda—.

## 3. Encuadre de la cobertura

| Encuadre | Notas |
|----------|------:|
| Estrategia política / campaña | 108 |
| Seguridad / conflicto armado | 23 |
| Legalidad / constitucionalidad | 20 |
| Identidad / cultura / nación | 18 |
| Economía | 9 |
| Relaciones internacionales | 7 |

Predomina con claridad el encuadre de **"estrategia/campaña"** (carrera
electoral: encuestas, alianzas, quién gana) sobre los encuadres sustantivos
(propuestas, economía). Este patrón —*horse-race journalism*— es un hallazgo
recurrente y bien documentado en estudios de cobertura electoral.

## 4. Filiación / sesgo de los medios

De 50 medios con cobertura suficiente, **28 mostraron un sesgo de trato**
(diferencia de tono hacia un candidato respecto al otro):

- **Trato más favorable a Cepeda:** medios internacionales (DW, BBC Mundo, CNN en
  Español), El País (Cali), La República, RTVC, y fuentes oficiales/analíticas.
- **Trato más favorable a De la Espriella:** algunos medios comerciales y
  regionales (Noticias Caracol, Publimetro, minuto60).

La inclinación de los **medios internacionales** hacia Cepeda y la dispersión de
los nacionales sugiere una estructura de cobertura no homogénea, coherente con
la literatura sobre concentración y línea editorial de la prensa colombiana.

## 5. Discurso de odio y validación

La detección automática de discurso de odio (pysentimiento) halló **0 notas con
odio explícito y 0 agresivas** en el corpus de prensa. Es un hallazgo en sí
mismo: el registro periodístico formal evita el lenguaje hostil explícito, a
diferencia de lo esperable en redes sociales (contraste a explorar, §6).

**Validación pendiente (obligatoria para publicar):** el tono automático debe
contrastarse con codificación humana sobre una muestra. ¡Quac! exporta una
muestra aleatoria reproducible y calcula el **Kappa de Cohen**:

```
python cli.py --db datos/quac.db validar --n 30 --salida muestra.csv
# (codificar a mano la columna polaridad_manual)
python cli.py validar --concordancia muestra.csv
```

## 6. Limitaciones y ampliación del corpus

**Tamaño del corpus.** N=204 es insuficiente para inferencias robustas. ¡Quac!
incorpora **búsqueda masiva** (troceo por fechas × términos): una prueba elevó la
cobertura a **745 notas de 137 medios** para el mismo período. Recomendado
ampliar a varios miles antes de las conclusiones definitivas.

**Redes sociales.** El estudio de prensa debe complementarse con el discurso en
redes (donde el debate y la polarización afectiva son más intensos). ¡Quac!
incorpora fuentes sociales enchufables con **métricas de audiencia** (vistas,
likes, comentarios, compartidos) para filtrar por impacto: **YouTube** (API
oficial), **TikTok** (Research API académica) y **X** (vía sesión del usuario).
La comparación prensa vs. redes —especialmente la presencia/ausencia de discurso
de odio— es una línea prometedora.

---

*Generado por ¡Quac! — análisis computacional de prensa electoral. Tablas
completas en el archivo .xlsx exportado; exploración interactiva en el dashboard.*

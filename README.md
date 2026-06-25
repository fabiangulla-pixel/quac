# ¡Quac! 🦆

**Análisis lingüístico computacional de prensa electoral colombiana contemporánea.**

Proyecto hermano de **Bashkar Station**. Mientras Bashkar analiza prensa
*histórica* desde imágenes escaneadas (OCR), ¡Quac! analiza prensa
*contemporánea* directamente desde la web (scraping + parsing de HTML),
enfocado en el estudio de **notas alrededor de procesos electorales**.

El nombre evoca al pato que *grazna* — la prensa que opina sobre la campaña.

---

## Qué hace

0. **Busca** notas a partir de **términos** (como en Google), un **rango de
   fechas** (ida/regreso, estilo aerolínea) y **entidades de interés** (nombres
   con variantes, lugares, instituciones, hechos). No hace falta pegar URLs.
1. **Scrapea** las notas (adaptador por medio + fallback genérico + captura vía
   tu sesión de Chrome para notas con JavaScript o suscripción).
2. **Almacena** cada nota en una base SQLite por proyecto, con deduplicación de
   URLs y de contenido (misma noticia republicada).
3. **Analiza** el corpus reutilizando los motores de Bashkar Station + métodos
   de humanidades digitales (ver [docs/METODOLOGIAS_DH.md](docs/METODOLOGIAS_DH.md)):
   - **NER** + **canonicalización** de actores (unifica "Cepeda"/"Iván Cepeda").
   - **Sentimiento / emociones** por nota (léxico offline; opción Claude).
   - **Encuadre / framing** (Media Frames Corpus): el ángulo de cada nota
     (seguridad, legalidad, identidad, economía…), no solo el tono.
   - **Red de co-ocurrencia** de actores con centralidad + comunidades; export
     a HTML interactivo (pyvis) y a **Gephi** (`.gexf`).
   - **Polaridad política** (positivo/negativo/neutro) por nota y por candidato,
     más discriminante que las 8 emociones; **índice de polarización afectiva**
     y marco **nosotros/ellos** (endogrupo/exogrupo), inspirados en la tesis de
     Garzón-Velandia (USC 2024) sobre polarización política.
   - **Tendencia / filiación política de los medios**: tono medio de cada medio
     hacia cada candidato y un **índice de sesgo** (a quién favorece).
   - **Polarización / sesgo de selección**: matriz medio × actor (qué medio
     cubre o calla a quién, con qué emoción dominante).
   - **Series temporales**: volumen, tono y encuadre por mes (distant reading).
   - **Tópicos** (NMF), **colocaciones** (PMI) y **frecuencias** del corpus.
   - **Confianza** de scraping (semáforo: cuerpo corto / sin fecha → dudoso).

### 🔒 Local primero, IA opcional

¡Quac! funciona **100% local y sin claves API**: la búsqueda usa Google News
RSS (gratis), la extracción usa tu propio Chrome, y el análisis usa **spaCy +
léxicos offline**. Las **API keys son opcionales** y solo *potencian* el
análisis (NER y tono con Claude) si tú decides ponerlas — nunca son necesarias.
El principio de diseño es: **preferir siempre librerías y recursos locales**;
la nube es un extra, no un requisito.

---

## Arquitectura

```
Quac/
├── core/            ← motores reutilizados de Bashkar (NO reescribir)
│   ├── ner_engine.py        sentiment_engine.py   network_engine.py
│   ├── entity_linker.py     confianza_engine.py   viz_engine.py
│   ├── topic_engine.py      lexicon_engine.py     timeline_engine.py …
├── scrapers/        ← capa de ingesta web (lo NUEVO de ¡Quac!)
│   ├── base.py        ScraperBase (contrato) + ScraperGenerico (trafilatura)
│   ├── medios.py      un adaptador por medio (selectores propios)
│   └── registro.py    dominio → scraper; cae al genérico si no hay adaptador
├── db.py            ← SQLite por proyecto + deduplicación
├── pipeline.py      ← orquesta los motores sobre las notas
├── cli.py           ← interfaz de línea de comandos
└── tests/           ← tests con HTML fixture (sin red)
```

**Patrón de scraping (Strategy):** cada adaptador define `MEDIO`, `DOMINIOS` y
selectores propios; hereda de `ScraperBase` el **fallback automático a
`trafilatura`** si los selectores fallan. Así, aunque un portal cambie su HTML,
la extracción sigue funcionando de forma degradada pero útil. El registro mapea
dominio → adaptador y, para dominios no registrados, usa el genérico — de modo
que ¡Quac! puede ingerir **cualquier** medio colombiano desde el día uno.

**Cadena de extracción (3 niveles):**

1. `requests` + selectores del adaptador (rápido, respeta `robots.txt`).
2. `requests` + `trafilatura` (extracción genérica si los selectores fallan).
3. **Captura vía tu sesión de Chrome** (CDP) — si lo anterior da un cuerpo corto
   (la nota exige JavaScript, o la ves porque tienes una suscripción legítima).

El nivel 3 reutiliza el patrón de **ReactivosFlow**: se conecta a un Chrome
lanzado con `--remote-debugging-port=9222` (perfil `C:/ChromeDebug`), navega a
la URL y extrae el **texto renderizado del DOM** + un **screenshot PNG** de
página completa (guardado junto a la BD, en `datos/screenshots/`). Inicia sesión
en tus medios en esa ventana de Chrome y ¡Quac! aprovechará tu acceso.

> ⚠️ Esto **no evade paywalls** de quien no ha pagado: usa el acceso que **tú ya
> tienes** en tu navegador, igual que ReactivosFlow usa tu sesión de Google. No
> se inyecta nada para borrar muros ni falsear credenciales. Desactívalo con
> `--sin-navegador`.

**Medios con adaptador dedicado:** El Tiempo, El Espectador, Semana,
El Colombiano, Cambio, Volcánicas, La Silla Vacía, Razón Pública,
El País (Cali), Pulzo, La FM, Blu Radio, Caracol, Noticias RCN, Vorágine,
Cuestión Pública. (Cualquier otro medio funciona vía extracción genérica.)

---

## Instalación

```powershell
pip install -r requirements.txt
python -m spacy download es_core_news_sm
```

(Python 3.14. Nota: `gensim` no compila en 3.14; ¡Quac! no lo necesita —
si más adelante se usan word vectors, usar el backend PyTorch de Bashkar.)

---

## Uso

### Interfaz gráfica (recomendada)

```powershell
python gui.py
```

Flujo de 3 pestañas:
1. **Buscar** — términos, fechas desde/hasta (ida/regreso), entidades de interés
   (nombre · tipo · variantes). Pulsa *Buscar*.
2. **Resultados** — muestra el **total de notas encontradas**, una lista con
   **casillas para elegir cuáles** scrapear, y un **filtro por medio**.
3. **Análisis** — casillas para elegir **qué análisis ejecutar** (NER,
   sentimiento, framing, red, tópicos, correferencia, series, polarización),
   parámetros (umbral de red, nº de tópicos), uso de tu sesión de Chrome
   (cookies/JS/suscripción, con **auto-aceptación de consentimientos**) y API
   key opcional. Al terminar abre un **dashboard HTML interactivo**.

**Dashboard interactivo** (se abre solo): pestañas Resumen / Actores /
Relaciones / Medios / Notas. Haz **clic en un actor** para ver sus notas, su
emoción, su encuadre y sus **concordancias** (frases reales donde aparece).
En *Relaciones* eliges dos términos y ves **cómo aparecen juntos** en el texto.

### Línea de comandos

```powershell
# Buscar por términos + rango de fechas + entidades, scrapear y dejar listo
python cli.py --db datos/cepeda.db buscar `
    --termino "Iván Cepeda Farc" `
    --desde 2025-11-05 --hasta 2026-06-11 `
    --entidad "Iván Cepeda|persona|Cepeda,Senador Cepeda" `
    --entidad "FARC|institucion|Farc,exFARC" `
    --max 12
#   --solo-listar  para ver resultados sin scrapear
#   --filtrar      para conservar solo notas que mencionan una entidad

# (Alternativa) pasar URLs a mano
python cli.py --db datos/x.db scrape https://... --archivo urls.txt

# Analizar: NER + sentimiento + red + tópicos + colocaciones + frecuencias
python cli.py --db datos/cepeda.db analizar `
    --salida datos/red.html --json datos/resultados.json
#   --peso-minimo 1   para corpus pequeños
#   --api-key sk-...  para enriquecer NER/tono con Claude (opcional)

python cli.py medios     # medios con adaptador dedicado
python cli.py --db datos/cepeda.db listar    # conteo por medio
```

### Ampliar el corpus (prensa masiva)

Para superar el límite (~100 notas) de una sola búsqueda, usa la **búsqueda
masiva** (trocea fechas × términos):

```powershell
python cli.py --db datos/X.db buscar --masivo --dias-tramo 3 `
    --termino "Iván Cepeda" --termino "Abelardo de la Espriella" `
    --termino "encuesta segunda vuelta" --desde 2026-06-01 --hasta 2026-06-21
```
Probado: pasa de ~200 a **cientos/miles** de notas y decenas → 130+ medios.

### Corpus de redes sociales

Fuentes con **métricas de audiencia** (vistas/likes/comentarios), enchufables:

```powershell
# YouTube (API oficial gratis): videos + comentarios + métricas reales
python cli.py --db datos/X.db social --plataforma youtube `
    --youtube-key TU_API_KEY --query "Cepeda Espriella segunda vuelta" `
    --desde 2026-06-01 --hasta 2026-06-21 --min-vistas 1000 --top 100
# luego se analiza igual que la prensa:
python cli.py --db datos/X.db analizar
```

**Conseguir la API key de YouTube (gratis, ~5 min):**
1. Entra a https://console.cloud.google.com y crea un proyecto.
2. *APIs y servicios → Biblioteca →* busca **"YouTube Data API v3"** → **Habilitar**.
3. *Credenciales → Crear credenciales → Clave de API*. Cópiala.
4. Úsala con `--youtube-key`. Cuota gratuita diaria (~10.000 unidades/día).

Otras fuentes: **TikTok** Research API (`--tiktok-token`, requiere afiliación
académica) y **X** (vía tu sesión de Chrome :9222, sin key, frágil).

El filtro `--min-vistas` / `--min-interacciones` / `--top` conserva solo las
publicaciones de mayor impacto (audiencia real), no el ruido.

---

## ⚖️ Ética y aspectos legales

¡Quac! es una herramienta de **investigación académica**. Su uso debe ceñirse a:

- **Solo contenido público.** No se evaden *paywalls* ni muros de registro.
- **Se respeta `robots.txt`** por defecto (puede consultarse antes de cada
  descarga). El flag `--ignorar-robots` existe pero **no se recomienda** y queda
  bajo responsabilidad de quien lo use.
- **Rate limiting** por dominio (≥2 s entre peticiones) para no sobrecargar los
  servidores de los medios.
- **Trazabilidad:** cada nota guarda su `fecha_captura` y el medio/URL de origen.
- Se almacena **solo lo necesario** para el análisis (texto, metadatos), con
  fines de investigación, citando siempre la fuente y la fecha de captura.
- El `User-Agent` identifica al bot y un contacto.

El respeto a los términos de uso de cada portal y a la legislación de derechos
de autor es responsabilidad de quien ejecuta la herramienta.

---

## Estado

**v0.1 — MVP funcional.** Scraping con adaptadores + fallback, persistencia con
deduplicación, y pipeline NER + sentimiento + red corriendo de punta a punta
(validado offline con fixture). UI: solo CLI por ahora.

Próximos pasos sugeridos: tópicos (topic_engine), series temporales de tono
(timeline_engine), entity linking a Wikidata (entity_linker), y dashboard.

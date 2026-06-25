"""Interfaz común de scraping y extractor genérico (fallback).

``ScraperBase`` define el contrato que cumple cada adaptador de medio.
``ScraperGenerico`` extrae el artículo con ``trafilatura`` y sirve tanto de
fallback dentro de cada adaptador como de scraper por defecto para dominios
no registrados.
"""

from __future__ import annotations

import hashlib
import time
import urllib.robotparser
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlparse

import requests

# trafilatura es opcional en import time para que los tests con HTML fixture
# no exijan red; las funciones que lo usan lo importan dentro.
USER_AGENT = (
    "QuacBot/0.1 (investigacion academica; prensa electoral colombiana; "
    "contacto: fabian.gulla@gmail.com)"
)

# Rate limit por defecto: segundos mínimos entre peticiones al MISMO dominio.
RATE_LIMIT_SEG = 2.0


@dataclass
class Nota:
    """Una nota de prensa extraída de un portal.

    Es la unidad de almacenamiento (mapea 1:1 a una fila de la tabla ``notas``).
    """

    url: str
    medio: str
    titular: str = ""
    cuerpo: str = ""
    autor: str = ""
    fecha_publicacion: str = ""  # ISO-8601 si se pudo extraer
    seccion: str = ""
    fecha_captura: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metodo_extraccion: str = ""  # "selectores" | "trafilatura" | "navegador"
    screenshot_path: str = ""  # ruta al PNG si se capturó vía navegador
    # huella del cuerpo para deduplicar notas republicadas
    hash_contenido: str = ""

    def __post_init__(self):
        if not self.hash_contenido and self.cuerpo:
            self.hash_contenido = self.calcular_hash()

    def calcular_hash(self) -> str:
        """Hash del cuerpo normalizado — detecta la misma nota republicada."""
        base = " ".join(self.cuerpo.lower().split())
        return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]

    @property
    def n_palabras(self) -> int:
        return len(self.cuerpo.split())

    def to_dict(self) -> dict:
        return asdict(self)


class ScraperBase:
    """Interfaz común de un adaptador de medio (patrón Strategy).

    Subclases concretas definen ``MEDIO``, ``DOMINIOS`` y, opcionalmente,
    ``_extraer_con_selectores`` para precisión. Si los selectores no producen
    un cuerpo razonable, se cae automáticamente a ``trafilatura``.
    """

    MEDIO: str = "desconocido"
    DOMINIOS: tuple[str, ...] = ()
    # Cuerpo más corto que esto se considera extracción fallida → fallback.
    MIN_PALABRAS_CUERPO = 40

    def __init__(
        self,
        session: requests.Session | None = None,
        rate_limit: float = RATE_LIMIT_SEG,
        respetar_robots: bool = True,
        usar_navegador: bool = True,
        screenshots_dir: str | None = None,
    ):
        self.session = session or self._nueva_session()
        self.rate_limit = rate_limit
        self.respetar_robots = respetar_robots
        # Fallback de captura vía la sesión real de Chrome del usuario (CDP).
        # Útil cuando la nota exige JavaScript o cuando el usuario tiene una
        # suscripción legítima que requests no aprovecha.
        self.usar_navegador = usar_navegador
        self.screenshots_dir = screenshots_dir
        self._ultimo_request: dict[str, float] = {}
        self._robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}

    # ---- infraestructura compartida ---------------------------------------

    @staticmethod
    def _nueva_session() -> requests.Session:
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "es-CO,es;q=0.9"})
        return s

    def _esperar_rate_limit(self, dominio: str):
        ahora = time.monotonic()
        ultimo = self._ultimo_request.get(dominio, 0.0)
        delta = ahora - ultimo
        if delta < self.rate_limit:
            time.sleep(self.rate_limit - delta)
        self._ultimo_request[dominio] = time.monotonic()

    def _robots_permite(self, url: str) -> bool:
        if not self.respetar_robots:
            return True
        partes = urlparse(url)
        dominio = f"{partes.scheme}://{partes.netloc}"
        rp = self._robots_cache.get(dominio)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(f"{dominio}/robots.txt")
            try:
                rp.read()
            except Exception:
                # Si no se puede leer robots.txt, ser conservador pero no bloquear
                # del todo: permitir y dejar constancia en logs del llamador.
                self._robots_cache[dominio] = rp
                return True
            self._robots_cache[dominio] = rp
        return rp.can_fetch(USER_AGENT, url)

    def descargar(self, url: str, timeout: int = 20) -> str | None:
        """Descarga el HTML respetando robots.txt y rate limit. None si falla.

        Corrige el encoding: requests usa ISO-8859-1 cuando el header no declara
        charset, aunque el HTML sea UTF-8 (declarado en un <meta>). Eso producía
        mojibake ("prohibiciÃ³n"). Cuando el charset no viene en el header, se usa
        el que requests deduce del contenido (apparent_encoding).
        """
        if not self._robots_permite(url):
            return None
        dominio = urlparse(url).netloc
        self._esperar_rate_limit(dominio)
        try:
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
        except requests.RequestException:
            return None
        # ¿El servidor declaró charset en el header? requests lo refleja en
        # resp.encoding solo si vino explícito; si no, pone ISO-8859-1 por RFC.
        charset_en_header = "charset=" in resp.headers.get("content-type", "").lower()
        if not charset_en_header and resp.apparent_encoding:
            resp.encoding = resp.apparent_encoding
        return resp.text

    # ---- contrato (overridable) -------------------------------------------

    def acepta(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return any(d in host for d in self.DOMINIOS)

    def _extraer_con_selectores(self, html: str, url: str) -> Nota | None:
        """Extracción específica del medio. Por defecto no hay → usa fallback."""
        return None

    def extraer_nota(self, url: str, html: str | None = None) -> Nota | None:
        """Extrae una nota. Cadena: selectores → trafilatura → navegador (CDP).

        Si se pasa ``html`` no se descarga (útil para tests con fixtures) y no
        se usa el fallback de navegador.
        """
        html_provisto = html is not None
        if html is None:
            html = self.descargar(url)

        if html:
            nota = self._extraer_con_selectores(html, url)
            if nota and nota.n_palabras >= self.MIN_PALABRAS_CUERPO:
                nota.metodo_extraccion = "selectores"
                if not nota.hash_contenido:
                    nota.hash_contenido = nota.calcular_hash()
                return nota

            # Fallback genérico (trafilatura)
            nota_fb = extraer_generico(html, url, medio=self.MEDIO)
            if nota_fb and nota_fb.n_palabras >= self.MIN_PALABRAS_CUERPO:
                return nota_fb
        else:
            nota = nota_fb = None

        # Último recurso: capturar con la sesión real de Chrome del usuario.
        # Solo si requests no dio un cuerpo razonable (JS / suscripción).
        if self.usar_navegador and not html_provisto:
            nota_nav = self._capturar_con_navegador(url)
            if nota_nav and nota_nav.n_palabras >= self.MIN_PALABRAS_CUERPO:
                return nota_nav

        # Devuelve lo mejor que se haya logrado (aunque corto) para que
        # confianza_engine lo marque como dudoso, en vez de perderlo.
        return nota_fb or nota

    def _capturar_con_navegador(self, url: str) -> Nota | None:
        """Captura la nota vía CDP usando la sesión de Chrome del usuario.

        Si Chrome resolvió un redirect/JS y terminó en otro dominio (típico de
        los enlaces de Google News, que apuntan al medio real), se reprocesa el
        HTML renderizado con el extractor del medio correcto y se guarda la URL
        final real — no la intermedia de Google News.
        """
        try:
            from .captura_navegador import capturar_con_sesion, guardar_screenshot
        except ImportError:
            return None
        try:
            cap = capturar_con_sesion(url, screenshot=bool(self.screenshots_dir))
        except Exception:
            return None
        if not cap or not cap.texto:
            return None

        url_real = cap.url_final or url
        medio = self.MEDIO
        cuerpo = cap.texto.strip()
        titular = cap.titulo.strip()
        autor = ""
        fecha = ""

        # ¿Chrome resolvió a otro dominio (p. ej. news.google.com → eltiempo.com)?
        cambio_dominio = urlparse(url_real).netloc.replace("www.", "") != urlparse(
            url
        ).netloc.replace("www.", "")
        if cambio_dominio and cap.html:
            # Reprocesar con el adaptador del dominio real para limpieza/medio.
            from .registro import scraper_para_url

            adaptador = scraper_para_url(url_real, usar_navegador=False)
            nota_real = adaptador._extraer_con_selectores(cap.html, url_real)
            if not (nota_real and nota_real.n_palabras >= self.MIN_PALABRAS_CUERPO):
                nota_real = extraer_generico(cap.html, url_real, medio=adaptador.MEDIO)
            if nota_real and nota_real.n_palabras >= self.MIN_PALABRAS_CUERPO:
                # Si el adaptador es el genérico, usar el dominio como nombre de
                # medio legible en vez de "generico".
                if adaptador.MEDIO == "generico":
                    medio = urlparse(url_real).netloc.replace("www.", "")
                else:
                    medio = nota_real.medio or adaptador.MEDIO
                cuerpo = nota_real.cuerpo
                titular = nota_real.titular or titular
                # Propagar autor/fecha del HTML real (antes se perdían: por eso
                # el corpus por navegador quedaba sin autor).
                autor = nota_real.autor or autor
                fecha = nota_real.fecha_publicacion or fecha

        # Si no se obtuvo autor por reprocesamiento, intentar sacarlo del HTML
        # renderizado por el navegador (JSON-LD / <meta author> / OpenGraph).
        if not autor and cap.html:
            try:
                from bs4 import BeautifulSoup

                from .medios import _autor_de_jsonld, _json_ld, _meta

                soup = BeautifulSoup(cap.html, "lxml")
                autor = (
                    _autor_de_jsonld(_json_ld(soup))
                    or _meta(soup, "author")
                    or _meta(soup, "article:author")
                ).strip()
            except Exception:
                pass

        screenshot_path = ""
        if cap.screenshot_png and self.screenshots_dir:
            from pathlib import Path

            ruta = guardar_screenshot(cap.screenshot_png, url_real, Path(self.screenshots_dir))
            screenshot_path = str(ruta)

        # Nunca etiquetar "generico": usar el dominio real como nombre de medio.
        if not medio or medio == "generico":
            medio = urlparse(url_real).netloc.replace("www.", "")

        return Nota(
            url=url_real,
            medio=medio,
            titular=titular,
            cuerpo=cuerpo,
            autor=autor.strip(),
            fecha_publicacion=fecha.strip(),
            metodo_extraccion="navegador",
            screenshot_path=screenshot_path,
        )


def extraer_generico(html: str, url: str, medio: str = "") -> Nota | None:
    """Extrae artículo limpio con trafilatura; si falla, cae a BeautifulSoup.

    Nunca lanza: un fallo de trafilatura (p. ej. recursos faltantes) no debe
    tumbar el scraping de todo el corpus.
    """
    cuerpo = titular = autor = fecha = ""
    try:
        import trafilatura

        cuerpo = (
            trafilatura.extract(
                html,
                include_comments=False,
                include_tables=False,
                favor_recall=True,
                url=url,
            )
            or ""
        )
        try:
            meta = trafilatura.extract_metadata(html, default_url=url)
            if meta:
                titular = meta.title or ""
                autor = meta.author or ""
                fecha = meta.date or ""
        except Exception:
            pass
    except Exception:
        cuerpo = ""

    # Fallback robusto si trafilatura no produjo cuerpo: párrafos del HTML.
    if not cuerpo:
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "lxml")
            cont = soup.find("article") or soup.find("main") or soup.body
            if cont:
                parrafos = [p.get_text(" ", strip=True) for p in cont.find_all("p")]
                cuerpo = "\n\n".join(p for p in parrafos if len(p) > 30)
            if not titular and soup.title and soup.title.string:
                titular = soup.title.string.strip()
        except Exception:
            pass

    if not cuerpo:
        return None

    if not medio:
        medio = urlparse(url).netloc.replace("www.", "")

    return Nota(
        url=url,
        medio=medio,
        titular=titular.strip(),
        cuerpo=cuerpo.strip(),
        autor=autor.strip(),
        fecha_publicacion=fecha.strip(),
        metodo_extraccion="trafilatura",
    )


class ScraperGenerico(ScraperBase):
    """Scraper por defecto para dominios no registrados (solo trafilatura)."""

    MEDIO = "generico"

    def acepta(self, url: str) -> bool:
        return True  # acepta cualquier cosa como último recurso

    def extraer_nota(self, url: str, html: str | None = None) -> Nota | None:
        html_provisto = html is not None
        if html is None:
            html = self.descargar(url)

        nota = None
        if html:
            nota = extraer_generico(html, url)
            if nota and not nota.medio:
                nota.medio = self.MEDIO
            if nota and nota.n_palabras >= self.MIN_PALABRAS_CUERPO:
                return nota

        # Fallback de navegador (CDP): clave para enlaces de Google News, que
        # requests no puede seguir pero Chrome sí resuelve al medio real.
        if self.usar_navegador and not html_provisto:
            nota_nav = self._capturar_con_navegador(url)
            if nota_nav and nota_nav.n_palabras >= self.MIN_PALABRAS_CUERPO:
                return nota_nav
        return nota

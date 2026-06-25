"""Captura de una nota usando la sesión REAL de Chrome del usuario (vía CDP).

Patrón tomado de ReactivosFlow (``cdp_agent.py``): se conecta a un Chrome con
``--remote-debugging-port=9222`` y le pide a la pestaña el render de la URL.
Esto reutiliza la sesión ya iniciada del usuario — sus suscripciones, sus
cookies — para acceder a notas que ``requests`` no ve porque exigen JavaScript
o porque el usuario tiene una cuenta de pago legítima.

Alcance y ética:
  - Esto NO evade paywalls de quien no ha pagado: usa el acceso que el usuario
    YA tiene en su navegador (igual que ReactivosFlow usa la sesión de Google).
  - No se inyecta nada para borrar muros ni falsear credenciales.
  - Sigue siendo contenido público al que el usuario tiene acceso legítimo.

Devuelve texto renderizado (post-JS, del DOM) + un screenshot PNG de página
completa para trazabilidad/archivo.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

logger = logging.getLogger(__name__)

CDP_HOST = "http://localhost:9222"
CHROME_DEBUG_PROFILE = "C:/ChromeDebug"
_CHROME_PATHS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
)
LOAD_SETTLE_S = 5.0  # espera tras navegar para que el JS de la nota renderice
# (5s da margen a portales lentos sin disparar el tiempo total)


@dataclass
class CapturaResultado:
    html: str  # outerHTML renderizado (post-JS)
    texto: str  # innerText del <article>/<main>/<body>
    titulo: str
    screenshot_png: bytes | None = None
    url_final: str = ""  # URL tras seguir redirects/JS (p. ej. resolver GNews)


# ── infraestructura CDP (adaptada de ReactivosFlow) ────────────────────────


def _cdp_alive(host: str = CDP_HOST) -> bool:
    try:
        httpx.get(f"{host}/json/version", timeout=2.0)
        return True
    except Exception:
        return False


def ensure_chrome_debug(host: str = CDP_HOST) -> bool:
    """Garantiza un Chrome con puerto de debug. Lo lanza si no responde."""
    if _cdp_alive(host):
        return False
    chrome = next((p for p in _CHROME_PATHS if Path(p).exists()), None)
    if not chrome:
        raise RuntimeError(
            "Chrome con debugging no está activo y no se encontró chrome.exe.\n"
            "Lánzalo manualmente con:\n"
            "  chrome.exe --remote-debugging-port=9222 --remote-allow-origins=* "
            f"--user-data-dir={CHROME_DEBUG_PROFILE}\n"
            "e inicia sesión en los medios a los que estés suscrito."
        )
    logger.info("Lanzando Chrome debug: %s", chrome)
    subprocess.Popen(
        [
            chrome,
            "--remote-debugging-port=9222",
            "--remote-allow-origins=*",
            f"--user-data-dir={CHROME_DEBUG_PROFILE}",
            "--window-size=1400,1000",
        ]
    )
    for _ in range(30):
        time.sleep(1.0)
        if _cdp_alive(host):
            return True
    raise RuntimeError("Chrome se lanzó pero el puerto 9222 no respondió en 30 s.")


def _get_tabs(host: str = CDP_HOST) -> list[dict]:
    resp = httpx.get(f"{host}/json", timeout=5.0)
    resp.raise_for_status()
    return resp.json()


def _abrir_tab(url: str, host: str = CDP_HOST) -> dict:
    endpoint = f"{host}/json/new?{quote(url, safe='')}"
    resp = httpx.put(endpoint, timeout=10.0)
    if resp.status_code >= 400:
        resp = httpx.get(endpoint, timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def _cerrar_tab(tab_id: str, host: str = CDP_HOST) -> None:
    """Cierra una pestaña por su id (evita que se acumulen y ralenticen Chrome)."""
    if not tab_id:
        return
    try:
        httpx.get(f"{host}/json/close/{tab_id}", timeout=5.0)
    except Exception:
        pass


class _CDPSession:
    def __init__(self, ws_url: str) -> None:
        import websocket

        self._ws = websocket.create_connection(ws_url, timeout=30)
        self._id = 0

    def send(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        self._ws.send(json.dumps({"id": self._id, "method": method, "params": params or {}}))
        while True:
            data = json.loads(self._ws.recv())
            if data.get("id") == self._id:
                if "error" in data:
                    raise RuntimeError(f"CDP error: {data['error']}")
                return data.get("result", {})

    def eval(self, expression: str, await_promise: bool = False) -> object:
        result = self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": await_promise,
            },
        )
        if "exceptionDetails" in result:
            raise RuntimeError(f"JS error: {result['exceptionDetails']}")
        return result.get("result", {}).get("value")

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:
            pass


# innerText del contenedor principal de artículo (post-render).
# Se prueban selectores de cuerpo de artículo de más específico a más genérico
# (cubre los CMS comunes de la prensa colombiana) antes de caer a <body>, que
# arrastra navegación/horóscopo/crucigrama. Se elige el contenedor con MÁS texto
# entre los candidatos específicos para evitar quedarse con un teaser corto.
_JS_TEXTO = """
(function(){
    var sels = ['article','[itemprop="articleBody"]','[class*="article-body"]',
                '[class*="articleBody"]','[class*="cuerpo"]','[class*="contenido"]',
                '[class*="post-content"]','[class*="entry-content"]','main'];
    var mejor = '', maxLen = 0;
    for (var i=0;i<sels.length;i++){
        var nodos = document.querySelectorAll(sels[i]);
        for (var j=0;j<nodos.length;j++){
            var t = (nodos[j].innerText || '').trim();
            if (t.length > maxLen){ maxLen = t.length; mejor = t; }
        }
        if (maxLen > 600) break;   // contenedor de artículo claro: úsalo
    }
    if (maxLen >= 250) return mejor;
    return document.body ? document.body.innerText : '';
})()
"""

_JS_HTML = "document.documentElement.outerHTML"
_JS_TITULO = "document.title"

# Auto-aceptar banners de consentimiento de cookies/datos. Cubre las plataformas
# más usadas por la prensa colombiana (Didomi → El Tiempo/Semana, OneTrust,
# Quantcast/IAB TCF) más un barrido por texto de botón. Devuelve cuántos clicó.
_JS_ACEPTAR_CONSENTIMIENTO = r"""
(function(){
    var n = 0;
    function clic(el){ if (el){ try { el.click(); n++; } catch(e){} } }

    // 1) IDs/selectores conocidos de plataformas de consentimiento
    var sels = [
        '#didomi-notice-agree-button',
        'button[aria-label="Aceptar"]',
        '#onetrust-accept-btn-handler',
        '.qc-cmp2-summary-buttons button[mode="primary"]',
        'button.sp_choice_type_11',                 // Sourcepoint
        'button[title="ACCEPT ALL"]',
        'button[data-testid="uc-accept-all-button"]',// Usercentrics
    ];
    for (var i=0;i<sels.length;i++){
        document.querySelectorAll(sels[i]).forEach(clic);
    }

    // 2) Barrido por texto del botón (es/en)
    var textos = ['aceptar y continuar','aceptar todo','aceptar todas',
                  'estoy de acuerdo','acepto','aceptar','consentir','continuar',
                  'entendido','accept all','i agree','agree','got it'];
    var botones = document.querySelectorAll('button, a[role="button"], input[type="button"], input[type="submit"]');
    botones.forEach(function(b){
        var t = (b.innerText || b.value || '').trim().toLowerCase();
        if (!t || t.length > 40) return;
        for (var j=0;j<textos.length;j++){
            if (t === textos[j] || t.indexOf(textos[j]) === 0){ clic(b); break; }
        }
    });

    // 3) Banners dentro de iframes de consentimiento (mismo origen)
    document.querySelectorAll('iframe').forEach(function(f){
        try {
            var d = f.contentDocument;
            if (!d) return;
            ['#didomi-notice-agree-button','#onetrust-accept-btn-handler',
             'button[mode="primary"]'].forEach(function(s){
                d.querySelectorAll(s).forEach(clic);
            });
        } catch(e){}
    });
    return n;
})()
"""


# ── API pública ────────────────────────────────────────────────────────────


def capturar_con_sesion(
    url: str,
    *,
    screenshot: bool = True,
    host: str = CDP_HOST,
    settle_s: float = LOAD_SETTLE_S,
    load_timeout_s: float = 25.0,
) -> CapturaResultado | None:
    """Navega a ``url`` en el Chrome del usuario y devuelve texto + HTML + PNG.

    Usa la sesión iniciada del usuario. Devuelve None si no se pudo capturar.
    """
    ensure_chrome_debug(host)
    tab = _abrir_tab(url, host)
    tab_id = tab.get("id")
    ws_url = tab.get("webSocketDebuggerUrl")
    if not ws_url:
        # reintenta localizando la pestaña recién creada
        for t in _get_tabs(host):
            if t.get("id") == tab_id:
                ws_url = t.get("webSocketDebuggerUrl")
                break
    if not ws_url:
        logger.warning("No se obtuvo WebSocket para la pestaña de %s", url)
        _cerrar_tab(tab_id, host)
        return None

    cdp = _CDPSession(ws_url)
    try:
        cdp.send("Page.enable")
        try:
            cdp.send("Page.bringToFront")
        except Exception:
            pass

        # Esperar a que el documento termine de cargar y el JS asiente
        deadline = time.monotonic() + load_timeout_s
        while time.monotonic() < deadline:
            estado = cdp.eval("document.readyState")
            if estado == "complete":
                break
            time.sleep(0.5)
        time.sleep(settle_s)

        # Auto-aceptar consentimiento de cookies/datos (Semana, El Tiempo, etc.)
        # y dar un instante a que el contenido real aparezca tras el clic.
        try:
            n_clics = cdp.eval(_JS_ACEPTAR_CONSENTIMIENTO)
            if n_clics:
                logger.info("Consentimiento aceptado (%s botón/es) en %s", n_clics, url)
                time.sleep(1.5)
        except Exception:
            pass

        titulo = str(cdp.eval(_JS_TITULO) or "")
        html = str(cdp.eval(_JS_HTML) or "")
        texto = str(cdp.eval(_JS_TEXTO) or "").strip()
        url_final = str(cdp.eval("window.location.href") or url)

        png = None
        if screenshot:
            try:
                res = cdp.send(
                    "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True}
                )
                png = base64.b64decode(res["data"])
            except Exception as exc:
                logger.warning("Screenshot falló para %s: %s", url, exc)

        return CapturaResultado(
            html=html, texto=texto, titulo=titulo, screenshot_png=png, url_final=url_final
        )
    finally:
        cdp.close()
        # Cerrar la pestaña para que no se acumulen y ralenticen Chrome.
        _cerrar_tab(tab_id, host)


def guardar_screenshot(png: bytes, url: str, dir_destino: Path) -> Path:
    """Guarda el PNG con un nombre derivado del dominio + hash de la URL."""
    import hashlib

    dir_destino.mkdir(parents=True, exist_ok=True)
    dom = urlparse(url).netloc.replace("www.", "").replace(".", "_")
    h = hashlib.sha1(url.encode()).hexdigest()[:10]
    ruta = dir_destino / f"{dom}_{h}.png"
    ruta.write_bytes(png)
    return ruta

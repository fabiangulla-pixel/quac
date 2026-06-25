"""Adaptador X/Twitter vía la sesión de Chrome del usuario (CDP).

La API de X está cerrada/cara, así que para volúmenes pequeños se capturan los
resultados públicos de búsqueda usando el Chrome logueado del usuario (mismo
mecanismo que ¡Quac! usa para prensa). FRÁGIL (X cambia el DOM y detecta bots) y
en zona gris de los ToS: úsese con criterio, solo para investigación y volumen
reducido. ``disponible()`` True solo si hay Chrome debug accesible.

Extrae tuits del HTML renderizado de https://x.com/search; las métricas
(likes/retweets) se parsean si están en el DOM.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from .base import Publicacion, SocialBase


class XTwitter(SocialBase):
    PLATAFORMA = "x"
    REQUIERE_KEY = False

    def disponible(self) -> bool:
        try:
            from scrapers.captura_navegador import _cdp_alive

            return _cdp_alive()
        except Exception:
            return False

    def buscar(self, query, *, desde=None, hasta=None, max_resultados=50, callback=None):
        def log(m):
            if callback:
                callback(m)

        try:
            from scrapers.captura_navegador import capturar_con_sesion
        except Exception:
            return []
        # construir query de búsqueda de X con rango de fechas
        q = query
        if desde:
            q += f" since:{desde}"
        if hasta:
            q += f" until:{hasta}"
        q += " lang:es"
        url = f"https://x.com/search?q={quote(q)}&f=live"
        try:
            cap = capturar_con_sesion(url, screenshot=False, settle_s=5.0)
        except Exception as exc:
            log(f"X captura falló: {exc}")
            return []
        if not cap or not cap.texto:
            log("X: sin contenido (¿sesión iniciada en Chrome :9222?).")
            return []
        # parseo best-effort: bloques de texto del timeline renderizado
        out, vistos = [], set()
        for bloque in re.split(r"\n{2,}", cap.texto):
            b = bloque.strip()
            if len(b) < 40 or b.lower() in vistos:
                continue
            vistos.add(b.lower())
            out.append(
                Publicacion(
                    id=str(abs(hash(b)))[:16], plataforma="x", url=url, texto=b, tipo="tuit"
                )
            )
            if len(out) >= max_resultados:
                break
        log(f"X: {len(out)} bloques de tuit capturados (best-effort) para «{query}».")
        return out

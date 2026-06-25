"""Adaptador TikTok — Research API (oficial, académica).

La Research API de TikTok es gratuita pero requiere: (1) afiliación a una
institución académica, (2) solicitud aprobada, (3) credenciales OAuth (client
key/secret) → token. Doc: https://developers.tiktok.com/products/research-api/

Este adaptador implementa la llamada a /v2/research/video/query/ cuando hay
token; si no, ``disponible()`` es False y el pipeline lo omite. Devuelve
Publicacion con métricas (vistas, likes, comentarios, compartidos).
"""

from __future__ import annotations

import requests

from .base import Publicacion, SocialBase

_API = "https://open.tiktokapis.com/v2/research/video/query/"


class TikTok(SocialBase):
    PLATAFORMA = "tiktok"
    REQUIERE_KEY = True  # requiere token de la Research API

    def buscar(self, query, *, desde=None, hasta=None, max_resultados=50, callback=None):
        if not self.api_key:
            return []

        def log(m):
            if callback:
                callback(m)

        # La Research API filtra por fecha en formato YYYYMMDD y por keyword.
        cuerpo = {
            "query": {
                "and": [{"operation": "IN", "field_name": "keyword", "field_values": [query]}]
            },
            "max_count": min(100, max_resultados),
            "fields": "id,video_description,create_time,like_count,comment_count,"
            "share_count,view_count,username",
        }
        if desde:
            cuerpo["start_date"] = desde.replace("-", "")
        if hasta:
            cuerpo["end_date"] = hasta.replace("-", "")
        try:
            r = requests.post(
                _API, json=cuerpo, timeout=25, headers={"Authorization": f"Bearer {self.api_key}"}
            )
            if r.status_code != 200:
                log(f"TikTok Research API: HTTP {r.status_code} (¿token válido?)")
                return []
            videos = r.json().get("data", {}).get("videos", [])
        except Exception as exc:
            log(f"TikTok falló: {exc}")
            return []
        out = []
        for v in videos:
            ct = v.get("create_time")
            fecha = ""
            if ct:
                import datetime as _dt

                fecha = _dt.datetime.utcfromtimestamp(int(ct)).date().isoformat()
            out.append(
                Publicacion(
                    id=str(v.get("id", "")),
                    plataforma="tiktok",
                    url=f"https://www.tiktok.com/@{v.get('username', '')}/video/{v.get('id', '')}",
                    autor=v.get("username", ""),
                    texto=v.get("video_description", ""),
                    fecha=fecha,
                    tipo="video",
                    vistas=int(v.get("view_count", 0) or 0),
                    likes=int(v.get("like_count", 0) or 0),
                    comentarios=int(v.get("comment_count", 0) or 0),
                    compartidos=int(v.get("share_count", 0) or 0),
                )
            )
        log(f"TikTok: {len(out)} videos para «{query}».")
        return out

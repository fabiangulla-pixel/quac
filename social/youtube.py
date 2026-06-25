"""Adaptador YouTube — busca videos sobre un tema y trae métricas + comentarios.

Usa la YouTube Data API v3 (oficial, gratuita con cuota diaria). Solo necesita
una API key de Google (https://console.cloud.google.com → habilitar "YouTube
Data API v3" → crear API key). Sin librerías extra: REST con requests.

Devuelve Publicacion por video (con vistas/likes/comentarios) y, opcionalmente,
los comentarios top de cada video como publicaciones tipo 'comentario'.
"""

from __future__ import annotations

import requests

from .base import Publicacion, SocialBase

_API = "https://www.googleapis.com/youtube/v3"


class YouTube(SocialBase):
    PLATAFORMA = "youtube"
    REQUIERE_KEY = True

    def buscar(
        self,
        query,
        *,
        desde=None,
        hasta=None,
        max_resultados=50,
        con_comentarios=True,
        max_comentarios=20,
        callback=None,
    ):
        if not self.api_key:
            return []

        def log(m):
            if callback:
                callback(m)

        pubs: list[Publicacion] = []
        # 1) buscar videos (search.list)
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": min(50, max_resultados),
            "relevanceLanguage": "es",
            "regionCode": "CO",
            "key": self.api_key,
        }
        if desde:
            params["publishedAfter"] = desde + "T00:00:00Z"
        if hasta:
            params["publishedBefore"] = hasta + "T23:59:59Z"
        try:
            r = requests.get(f"{_API}/search", params=params, timeout=20)
            r.raise_for_status()
            items = r.json().get("items", [])
        except Exception as exc:
            log(f"YouTube search falló: {exc}")
            return []

        ids = [it["id"]["videoId"] for it in items if it.get("id", {}).get("videoId")]
        if not ids:
            return []

        # 2) estadísticas de los videos (videos.list) — métricas reales
        stats = {}
        try:
            rv = requests.get(
                f"{_API}/videos",
                params={"part": "statistics,snippet", "id": ",".join(ids), "key": self.api_key},
                timeout=20,
            )
            rv.raise_for_status()
            for v in rv.json().get("items", []):
                stats[v["id"]] = v
        except Exception as exc:
            log(f"YouTube videos.list falló: {exc}")

        for vid in ids:
            v = stats.get(vid, {})
            sn = v.get("snippet", {})
            st = v.get("statistics", {})
            pub = Publicacion(
                id=vid,
                plataforma="youtube",
                url=f"https://www.youtube.com/watch?v={vid}",
                autor=sn.get("channelTitle", ""),
                texto=(sn.get("title", "") + ". " + sn.get("description", "")).strip(),
                fecha=(sn.get("publishedAt", "") or "")[:10],
                tipo="video",
                vistas=int(st.get("viewCount", 0) or 0),
                likes=int(st.get("likeCount", 0) or 0),
                comentarios=int(st.get("commentCount", 0) or 0),
            )
            pubs.append(pub)
            # 3) comentarios top del video (commentThreads.list)
            if con_comentarios and pub.comentarios:
                pubs.extend(self._comentarios(vid, max_comentarios, log))
        log(f"YouTube: {len(pubs)} publicaciones (videos+comentarios) para «{query}».")
        return pubs

    def _comentarios(self, video_id, maxn, log):
        out = []
        try:
            r = requests.get(
                f"{_API}/commentThreads",
                params={
                    "part": "snippet",
                    "videoId": video_id,
                    "maxResults": min(100, maxn),
                    "order": "relevance",
                    "textFormat": "plainText",
                    "key": self.api_key,
                },
                timeout=20,
            )
            if r.status_code != 200:
                return out
            for it in r.json().get("items", []):
                c = it["snippet"]["topLevelComment"]["snippet"]
                out.append(
                    Publicacion(
                        id=it["id"],
                        plataforma="youtube",
                        url=f"https://www.youtube.com/watch?v={video_id}&lc={it['id']}",
                        autor=c.get("authorDisplayName", ""),
                        texto=c.get("textDisplay", ""),
                        fecha=(c.get("publishedAt", "") or "")[:10],
                        tipo="comentario",
                        likes=int(c.get("likeCount", 0) or 0),
                    )
                )
        except Exception:
            pass
        return out

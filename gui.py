#!/usr/bin/env python
"""GUI de ¡Quac! — búsqueda en 2 pasos + análisis configurable + dashboard.

Flujo:
  1) BUSCAR → muestra el TOTAL de notas encontradas y una lista con casillas
     (seleccionar cuáles scrapear) + filtro por medio.
  2) SCRAPEAR + ANALIZAR → con los análisis que el usuario elija (casillas) y
     parámetros ajustables. Abre un DASHBOARD HTML interactivo al terminar.

100% local; API key opcional. GUI en español (tkinter).
"""

from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

sys.path.insert(0, str(Path(__file__).parent))

import config
from busqueda import buscar, buscar_masivo
from busqueda.criterios import TIPOS_ENTIDAD, CriteriosBusqueda, EntidadInteres
from busqueda.motor import medios_de
from db import BaseDatos
from scrapers.registro import scraper_para_url


class QuacGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("¡Quac! — Búsqueda de prensa electoral colombiana")
        self.geometry("980x800")
        self._cola = queue.Queue()
        self.perfil = config.cargar()  # perfil de usuario persistente
        self._db_path = tk.StringVar(value="datos/quac.db")
        self._resultados = []  # Resultado de la última búsqueda
        self._vars_sel = {}  # iid → BooleanVar (notas seleccionadas)
        self._construir()
        self._aplicar_perfil()  # cargar defaults del perfil
        self.after(150, self._vaciar_cola)

    # ---- UI ---------------------------------------------------------------

    def _construir(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        self.tab_buscar = ttk.Frame(nb)
        self.tab_resultados = ttk.Frame(nb)
        self.tab_analisis = ttk.Frame(nb)
        self.tab_social = ttk.Frame(nb)
        self.tab_config = ttk.Frame(nb)
        nb.add(self.tab_buscar, text="1 · Buscar")
        nb.add(self.tab_resultados, text="2 · Resultados")
        nb.add(self.tab_analisis, text="3 · Análisis")
        nb.add(self.tab_social, text="📱 Redes sociales")
        nb.add(self.tab_config, text="⚙ Configuración")
        self.nb = nb
        self._construir_buscar()
        self._construir_resultados()
        self._construir_analisis()
        self._construir_social()
        self._construir_config()

        self.log = tk.Text(
            self, height=8, wrap="word", state="disabled", bg="#1e1e1e", fg="#d4d4d4"
        )
        self.log.pack(fill="both", expand=False, padx=10, pady=(0, 8))

    def _construir_buscar(self):
        f = self.tab_buscar
        pad = {"padx": 8, "pady": 4}
        ttk.Label(f, text="🦆 ¡Quac!", font=("Segoe UI", 16, "bold")).pack(
            anchor="w", padx=12, pady=(10, 0)
        )

        f1 = ttk.LabelFrame(f, text="¿Qué buscar?")
        f1.pack(fill="x", **pad)
        ttk.Label(f1, text="Términos o palabras clave (separa varios con ';'):").pack(
            anchor="w", padx=6, pady=2
        )
        self.txt_terminos = ttk.Entry(f1, width=90)
        self.txt_terminos.pack(fill="x", padx=6, pady=(0, 6))

        f2 = ttk.LabelFrame(f, text="Rango de fechas")
        f2.pack(fill="x", **pad)
        ttk.Label(f2, text="Desde (ida):").grid(row=0, column=0, padx=6, pady=4)
        self.txt_desde = ttk.Entry(f2, width=14)
        self.txt_desde.grid(row=0, column=1)
        self.txt_desde.insert(0, "AAAA-MM-DD")
        ttk.Label(f2, text="Hasta (regreso):").grid(row=0, column=2, padx=6)
        self.txt_hasta = ttk.Entry(f2, width=14)
        self.txt_hasta.grid(row=0, column=3)
        self.txt_hasta.insert(0, "AAAA-MM-DD")

        f3 = ttk.LabelFrame(
            f, text="Entidades de interés (nombres y variantes, lugares, instituciones, hechos)"
        )
        f3.pack(fill="both", **pad)
        cols = ("nombre", "tipo", "variantes")
        self.tabla = ttk.Treeview(f3, columns=cols, show="headings", height=4)
        for c, txt, w in (
            ("nombre", "Nombre", 200),
            ("tipo", "Tipo", 90),
            ("variantes", "Variantes (coma)", 380),
        ):
            self.tabla.heading(c, text=txt)
            self.tabla.column(c, width=w)
        self.tabla.grid(row=0, column=0, columnspan=5, sticky="we", padx=6, pady=4)
        ttk.Label(f3, text="Nombre:").grid(row=1, column=0, padx=4)
        self.e_nombre = ttk.Entry(f3, width=20)
        self.e_nombre.grid(row=1, column=1)
        self.e_tipo = ttk.Combobox(f3, values=list(TIPOS_ENTIDAD), width=11, state="readonly")
        self.e_tipo.set("persona")
        self.e_tipo.grid(row=1, column=2, padx=4)
        self.e_var = ttk.Entry(f3, width=32)
        self.e_var.grid(row=1, column=3, padx=4)
        ttk.Button(f3, text="Añadir", command=self._añadir_entidad).grid(row=1, column=4)
        ttk.Button(f3, text="Quitar", command=self._quitar_entidad).grid(row=2, column=4, pady=2)

        f4 = ttk.LabelFrame(f, text="Opciones de búsqueda")
        f4.pack(fill="x", **pad)
        ttk.Label(f4, text="Máx. a traer:").grid(row=0, column=0, padx=6)
        self.e_max = ttk.Entry(f4, width=6)
        self.e_max.insert(0, "100")
        self.e_max.grid(row=0, column=1)
        ttk.Label(f4, text="Base de datos:").grid(row=0, column=2, padx=6)
        ttk.Entry(f4, textvariable=self._db_path, width=26).grid(row=0, column=3)
        self.var_filtrar = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            f4, text="Solo notas que mencionan una entidad de interés", variable=self.var_filtrar
        ).grid(row=1, column=0, columnspan=4, sticky="w", padx=6)
        # Búsqueda MASIVA: trocea fechas×términos para superar el tope ~100 de
        # Google News por consulta y reunir miles de notas (no solo las 100).
        self.var_masivo = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            f4,
            text="Búsqueda masiva (supera el límite de ~100 de Google News)",
            variable=self.var_masivo,
        ).grid(row=2, column=0, columnspan=3, sticky="w", padx=6)
        ttk.Label(f4, text="Días por tramo:").grid(row=2, column=3, sticky="e", padx=6)
        self.e_dias_tramo = ttk.Entry(f4, width=5)
        self.e_dias_tramo.insert(0, "7")
        self.e_dias_tramo.grid(row=2, column=4, sticky="w")

        self.btn_buscar = ttk.Button(f, text="🔎 Buscar (paso 1)", command=self._lanzar_busqueda)
        self.btn_buscar.pack(anchor="w", padx=14, pady=8)

    def _construir_resultados(self):
        f = self.tab_resultados
        top = ttk.Frame(f)
        top.pack(fill="x", padx=8, pady=6)
        self.lbl_total = ttk.Label(top, text="Aún no has buscado.", font=("Segoe UI", 11, "bold"))
        self.lbl_total.pack(side="left")
        ttk.Button(top, text="Marcar todo", command=lambda: self._marcar(True)).pack(
            side="right", padx=4
        )
        ttk.Button(top, text="Desmarcar todo", command=lambda: self._marcar(False)).pack(
            side="right"
        )

        filtro = ttk.Frame(f)
        filtro.pack(fill="x", padx=8)
        ttk.Label(filtro, text="Filtrar por medio:").pack(side="left")
        self.cmb_medio = ttk.Combobox(filtro, width=30, state="readonly")
        self.cmb_medio.pack(side="left", padx=6)
        self.cmb_medio.bind("<<ComboboxSelected>>", lambda e: self._render_resultados())

        cont = ttk.Frame(f)
        cont.pack(fill="both", expand=True, padx=8, pady=6)
        self.canvas = tk.Canvas(cont, highlightthickness=0)
        sb = ttk.Scrollbar(cont, orient="vertical", command=self.canvas.yview)
        self.lista = ttk.Frame(self.canvas)
        self.lista.bind(
            "<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.create_window((0, 0), window=self.lista, anchor="nw")
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.btn_a_analisis = ttk.Button(
            f,
            text="Continuar al análisis (paso 3) →",
            command=lambda: self.nb.select(self.tab_analisis),
        )
        self.btn_a_analisis.pack(anchor="e", padx=10, pady=6)

    def _construir_analisis(self):
        f = self.tab_analisis
        pad = {"padx": 8, "pady": 4}
        fa = ttk.LabelFrame(f, text="¿Qué análisis ejecutar?")
        fa.pack(fill="x", **pad)
        self.an = {
            "ner": tk.BooleanVar(value=True),
            "sentimiento": tk.BooleanVar(value=True),
            "framing": tk.BooleanVar(value=True),
            "red": tk.BooleanVar(value=True),
            "topicos": tk.BooleanVar(value=True),
            "coref": tk.BooleanVar(value=True),
            "series": tk.BooleanVar(value=True),
            "polarizacion": tk.BooleanVar(value=True),
            "solo_relevantes": tk.BooleanVar(value=True),
        }
        etiquetas = {
            "ner": "NER + actores",
            "sentimiento": "Sentimiento/emociones",
            "framing": "Encuadre (framing)",
            "red": "Red de co-ocurrencia",
            "topicos": "Tópicos + colocaciones",
            "coref": "Correferencia",
            "series": "Series temporales",
            "polarizacion": "Polarización medio×actor",
            "solo_relevantes": "Solo actores del perfil (sin ruido internacional)",
        }
        for i, (k, var) in enumerate(self.an.items()):
            ttk.Checkbutton(fa, text=etiquetas[k], variable=var).grid(
                row=i // 4, column=i % 4, sticky="w", padx=8, pady=3
            )

        fp = ttk.LabelFrame(f, text="Parámetros")
        fp.pack(fill="x", **pad)
        ttk.Label(fp, text="Umbral red (notas/arista):").grid(row=0, column=0, padx=6, sticky="w")
        self.e_peso = ttk.Entry(fp, width=5)
        self.e_peso.insert(0, "1")
        self.e_peso.grid(row=0, column=1)
        ttk.Label(fp, text="Nº tópicos:").grid(row=0, column=2, padx=6, sticky="w")
        self.e_ntop = ttk.Entry(fp, width=5)
        self.e_ntop.insert(0, "5")
        self.e_ntop.grid(row=0, column=3)
        ttk.Label(fp, text="Ventana colocaciones:").grid(row=1, column=0, padx=6, sticky="w")
        self.e_vent = ttk.Entry(fp, width=5)
        self.e_vent.insert(0, "6")
        self.e_vent.grid(row=1, column=1)
        ttk.Label(fp, text="Mín. palabras/nota:").grid(row=1, column=2, padx=6, sticky="w")
        self.e_minpal = ttk.Entry(fp, width=5)
        self.e_minpal.insert(0, "0")
        self.e_minpal.grid(row=1, column=3)
        ttk.Label(fp, text="Calidad mínima (0–1):").grid(row=2, column=0, padx=6, sticky="w")
        self.e_calmin = ttk.Entry(fp, width=5)
        self.e_calmin.insert(0, "0")
        self.e_calmin.grid(row=2, column=1)
        ttk.Label(fp, text="Stopwords extra (coma):").grid(row=2, column=2, padx=6, sticky="w")
        self.e_stop = ttk.Entry(fp, width=24)
        self.e_stop.grid(row=2, column=3, sticky="w")
        # Filtros de RELEVANCIA temática (quitan ruido de la búsqueda masiva).
        ttk.Label(fp, text="Debe mencionar (coma):").grid(row=3, column=0, padx=6, sticky="w")
        self.e_oblig = ttk.Entry(fp, width=24)
        self.e_oblig.grid(row=3, column=1, columnspan=1, sticky="w")
        ttk.Label(fp, text="Excluir si menciona (coma):").grid(row=3, column=2, padx=6, sticky="w")
        self.e_excl = ttk.Entry(fp, width=24)
        self.e_excl.grid(row=3, column=3, sticky="w")
        self.var_navegador = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            fp,
            text="Usar mi sesión de Chrome (JS/suscripción/cookies)",
            variable=self.var_navegador,
        ).grid(row=4, column=0, columnspan=4, sticky="w", padx=6)
        # ¿Están los transformers disponibles? (versión completa vs. ligera)
        try:
            import sentimiento_politico as _sp

            _pro = _sp.transformer_disponible()
        except Exception:
            _pro = False
        _suf = "" if _pro else "  (no disponible en esta instalación)"
        self.var_transformer = tk.BooleanVar(value=False)
        cbt = ttk.Checkbutton(
            fp,
            text="Sentimiento+emoción+ODIO con transformer (pysentimiento, más preciso)" + _suf,
            variable=self.var_transformer,
        )
        cbt.grid(row=5, column=0, columnspan=4, sticky="w", padx=6)
        self.var_bertopic = tk.BooleanVar(value=False)
        cbb = ttk.Checkbutton(
            fp, text="Tópicos con BERTopic (embeddings)" + _suf, variable=self.var_bertopic
        )
        cbb.grid(row=6, column=0, columnspan=4, sticky="w", padx=6)
        if not _pro:
            cbt.state(["disabled"])
            cbb.state(["disabled"])
        # rótulo del modo de la instalación
        modo = (
            "✅ versión COMPLETA (transformers disponibles)"
            if _pro
            else "modo ligero (léxico) — para análisis con transformers usa la versión completa"
        )
        ttk.Label(fp, text=modo, foreground=("#2e7d32" if _pro else "gray")).grid(
            row=7, column=0, columnspan=4, sticky="w", padx=6, pady=(2, 0)
        )
        self.var_excel = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            fp, text="Exportar tablas a Excel (.xlsx) para el paper", variable=self.var_excel
        ).grid(row=6, column=0, columnspan=4, sticky="w", padx=6)
        ttk.Label(fp, text="API key Claude (opcional):").grid(row=4, column=0, sticky="w", padx=6)
        self.e_apikey = ttk.Entry(fp, width=44, show="•")
        self.e_apikey.grid(row=4, column=1, columnspan=3, sticky="w")

        barra = ttk.Frame(f)
        barra.pack(fill="x", **pad)
        self.btn_analizar = ttk.Button(
            barra, text="⚙ Scrapear seleccionadas y analizar", command=self._lanzar_analisis
        )
        self.btn_analizar.pack(side="left", padx=6)
        self.prog = ttk.Progressbar(barra, mode="indeterminate", length=240)
        self.prog.pack(side="left", padx=10)

        # Retomar un corpus de una sesión anterior: analizar la BD ya guardada
        # sin volver a buscar ni scrapear.
        barra2 = ttk.Frame(f)
        barra2.pack(fill="x", **pad)
        ttk.Label(barra2, text="Retomar sesión anterior:").pack(side="left", padx=6)
        self.btn_analizar_bd = ttk.Button(
            barra2, text="📂 Abrir BD y analizar lo ya guardado", command=self._lanzar_analizar_bd
        )
        self.btn_analizar_bd.pack(side="left", padx=6)
        ttk.Button(barra2, text="📂 Elegir…", command=self._elegir_db).pack(side="left")
        self.btn_limpiar_bd = ttk.Button(
            barra2, text="🧹 Limpiar BD (borrar ruido)", command=self._lanzar_limpiar_bd
        )
        self.btn_limpiar_bd.pack(side="left", padx=6)
        ttk.Label(
            barra2,
            text="(usa el corpus del campo «Base de datos» de la pestaña Buscar)",
            foreground="gray",
        ).pack(side="left", padx=8)

    # ---- PESTAÑA REDES SOCIALES ------------------------------------------
    def _construir_social(self):
        f = self.tab_social
        pad = {"padx": 8, "pady": 4}
        ttk.Label(f, text="📱 Redes sociales", font=("Segoe UI", 13, "bold")).pack(
            anchor="w", padx=12, pady=(10, 0)
        )
        ttk.Label(
            f,
            text="Recolecta publicaciones (con métricas de audiencia) y las "
            "guarda en la misma base de datos para analizarlas con el mismo "
            "pipeline que la prensa.\nLuego ve a «3 · Análisis» y pulsa analizar.",
            foreground="gray",
            justify="left",
        ).pack(anchor="w", padx=12)

        fq = ttk.LabelFrame(f, text="¿Qué buscar?")
        fq.pack(fill="x", **pad)
        ttk.Label(fq, text="Términos / consulta:").grid(row=0, column=0, sticky="w", padx=6, pady=2)
        self.soc_query = ttk.Entry(fq, width=60)
        self.soc_query.grid(row=0, column=1, columnspan=3, sticky="w")

        fp = ttk.LabelFrame(f, text="Plataformas")
        fp.pack(fill="x", **pad)
        self.soc_plats = {
            "youtube": tk.BooleanVar(value=True),
            "tiktok": tk.BooleanVar(value=False),
            "x": tk.BooleanVar(value=False),
        }
        etiq = {
            "youtube": "YouTube (API gratis con key)",
            "tiktok": "TikTok (Research API, requiere afiliación)",
            "x": "X/Twitter (sesión de Chrome, frágil)",
        }
        for i, p in enumerate(["youtube", "tiktok", "x"]):
            ttk.Checkbutton(fp, text=etiq[p], variable=self.soc_plats[p]).grid(
                row=i, column=0, columnspan=3, sticky="w", padx=6
            )
        ttk.Label(fp, text="API key de YouTube:").grid(
            row=3, column=0, sticky="w", padx=6, pady=(6, 2)
        )
        self.soc_yt_key = ttk.Entry(fp, width=50, show="•")
        self.soc_yt_key.grid(row=3, column=1, columnspan=2, sticky="w")
        self.soc_yt_key.insert(0, self.perfil.get("youtube_key", ""))
        ttk.Label(
            fp,
            text="(Google Cloud → habilita «YouTube Data API v3» → crea una API key)",
            foreground="gray",
        ).grid(row=4, column=1, columnspan=2, sticky="w", padx=4)

        ff = ttk.LabelFrame(f, text="Filtro por audiencia (quedarse con lo relevante)")
        ff.pack(fill="x", **pad)
        ttk.Label(ff, text="Mín. vistas:").grid(row=0, column=0, sticky="e", padx=4)
        self.soc_min_vistas = ttk.Entry(ff, width=8)
        self.soc_min_vistas.insert(0, "0")
        self.soc_min_vistas.grid(row=0, column=1, sticky="w")
        ttk.Label(ff, text="Mín. interacciones:").grid(row=0, column=2, sticky="e", padx=4)
        self.soc_min_int = ttk.Entry(ff, width=8)
        self.soc_min_int.insert(0, "0")
        self.soc_min_int.grid(row=0, column=3, sticky="w")
        ttk.Label(ff, text="Top N:").grid(row=0, column=4, sticky="e", padx=4)
        self.soc_top = ttk.Entry(ff, width=8)
        self.soc_top.insert(0, "100")
        self.soc_top.grid(row=0, column=5, sticky="w")
        ttk.Label(ff, text="Máx. por plataforma:").grid(row=1, column=0, sticky="e", padx=4)
        self.soc_max = ttk.Entry(ff, width=8)
        self.soc_max.insert(0, "50")
        self.soc_max.grid(row=1, column=1, sticky="w")

        barra = ttk.Frame(f)
        barra.pack(fill="x", **pad)
        self.btn_social = ttk.Button(
            barra, text="📥 Recolectar y guardar en la BD", command=self._lanzar_social
        )
        self.btn_social.pack(side="left", padx=6)
        ttk.Label(barra, text="(usa la BD de la pestaña Buscar)", foreground="gray").pack(
            side="left"
        )

    def _lanzar_social(self):
        plataformas = [p for p, v in self.soc_plats.items() if v.get()]
        query = self.soc_query.get().strip()
        if not plataformas:
            messagebox.showwarning("Redes sociales", "Elige al menos una plataforma.")
            return
        if not query:
            messagebox.showwarning("Redes sociales", "Escribe una consulta.")
            return
        claves = {"youtube": self.soc_yt_key.get().strip() or None}
        if "youtube" in plataformas and not claves["youtube"]:
            messagebox.showwarning(
                "YouTube", "Para YouTube necesitas una API key (gratis en Google Cloud)."
            )
            return
        try:
            filtros = dict(
                min_vistas=int(self.soc_min_vistas.get() or 0),
                min_interacciones=int(self.soc_min_int.get() or 0),
                top=int(self.soc_top.get() or 0) or None,
                max_por_fuente=int(self.soc_max.get() or 50),
            )
        except ValueError:
            messagebox.showerror("Redes sociales", "Los filtros deben ser números.")
            return
        # Persistir la API key de YouTube en el perfil (cómodo entre sesiones).
        if claves.get("youtube"):
            try:
                self.perfil["youtube_key"] = claves["youtube"]
                config.guardar(self.perfil)
            except Exception:
                pass
        self.btn_social.configure(state="disabled")
        self.prog.start()
        self._escribir(f"Recolectando «{query}» en {', '.join(plataformas)}…")
        threading.Thread(
            target=self._worker_social, args=(plataformas, query, claves, filtros), daemon=True
        ).start()

    def _worker_social(self, plataformas, query, claves, filtros):
        log = lambda m: self._cola.put(("log", m))
        try:
            from db import BaseDatos
            from scrapers.base import Nota
            from social import buscar_social, filtrar_por_audiencia, publicacion_a_nota

            desde = self.txt_desde.get().strip()
            hasta = self.txt_hasta.get().strip()
            desde = None if (not desde or desde == "AAAA-MM-DD") else desde
            hasta = None if (not hasta or hasta == "AAAA-MM-DD") else hasta
            pubs = buscar_social(
                plataformas,
                query,
                claves=claves,
                desde=desde,
                hasta=hasta,
                max_por_fuente=filtros["max_por_fuente"],
                callback=log,
            )
            if filtros["min_vistas"] or filtros["min_interacciones"] or filtros["top"]:
                pubs = filtrar_por_audiencia(
                    pubs,
                    min_vistas=filtros["min_vistas"],
                    min_interacciones=filtros["min_interacciones"],
                    top_n=filtros["top"],
                )
            db = BaseDatos(self._db_path.get())
            ins = 0
            for p in pubs:
                d = publicacion_a_nota(p)
                nota = Nota(
                    url=d["url"],
                    medio=d["medio"],
                    titular=d["titular"],
                    cuerpo=d["cuerpo"],
                    autor=d.get("autor", ""),
                    fecha_publicacion=d.get("fecha_publicacion", ""),
                    metodo_extraccion="social_api",
                )
                if d["cuerpo"] and db.guardar_nota(nota):
                    ins += 1
            self._cola.put(("social_fin", (len(pubs), ins)))
        except Exception as e:
            import traceback

            self._cola.put(("error", f"{e}\n\n{traceback.format_exc()}"))

    def _construir_config(self):
        f = self.tab_config
        pad = {"padx": 8, "pady": 4}
        ttk.Label(f, text="⚙ Perfil de usuario", font=("Segoe UI", 13, "bold")).pack(
            anchor="w", padx=12, pady=(8, 0)
        )
        self.lbl_perfil = ttk.Label(f, text="", foreground="gray")
        self.lbl_perfil.pack(anchor="w", padx=12)
        ttk.Label(f, text=f"Se guarda en: {config.ruta_config()}", foreground="gray").pack(
            anchor="w", padx=12
        )

        # Defaults de análisis
        fa = ttk.LabelFrame(f, text="Valores por defecto del análisis")
        fa.pack(fill="x", **pad)
        self.cfg = {}
        campos = [
            ("n_topicos", "Nº tópicos", 6),
            ("umbral_red", "Umbral red", 6),
            ("ventana_colocaciones", "Ventana colocaciones", 6),
            ("min_palabras_nota", "Mín. palabras/nota", 6),
            ("calidad_minima", "Calidad mínima (0–1)", 6),
            ("max_resultados", "Máx. resultados", 6),
        ]
        for i, (k, txt, w) in enumerate(campos):
            ttk.Label(fa, text=txt + ":").grid(
                row=i // 3, column=(i % 3) * 2, sticky="w", padx=6, pady=3
            )
            e = ttk.Entry(fa, width=w)
            e.grid(row=i // 3, column=(i % 3) * 2 + 1, sticky="w")
            self.cfg[k] = e
        ttk.Label(fa, text="Stopwords extra (coma):").grid(row=2, column=0, sticky="w", padx=6)
        self.cfg_stop = ttk.Entry(fa, width=60)
        self.cfg_stop.grid(row=2, column=1, columnspan=5, sticky="w")

        # Medios
        fm = ttk.LabelFrame(f, text="Medios a monitorear (un dominio por línea)")
        fm.pack(fill="both", **pad)
        self.cfg_medios = tk.Text(fm, height=6, wrap="word")
        self.cfg_medios.pack(fill="x", padx=6, pady=4)

        # Entidades / candidatos (diccionario NER)
        fe = ttk.LabelFrame(
            f,
            text="Entidades de interés / diccionario NER "
            "(una por línea: Nombre | tipo | variante1, variante2)",
        )
        fe.pack(fill="both", expand=True, **pad)
        self.cfg_entidades = tk.Text(fe, height=8, wrap="word")
        self.cfg_entidades.pack(fill="both", expand=True, padx=6, pady=4)

        # Botones
        bar = ttk.Frame(f)
        bar.pack(fill="x", **pad)
        ttk.Button(bar, text="💾 Guardar perfil", command=self._guardar_perfil).pack(
            side="left", padx=6
        )
        ttk.Button(
            bar, text="Usar este perfil en la búsqueda", command=self._perfil_a_busqueda
        ).pack(side="left", padx=6)
        ttk.Button(
            bar, text="Restaurar semilla (2ª vuelta 2026)", command=self._restaurar_semilla
        ).pack(side="left", padx=6)
        ttk.Label(bar, text="API key:").pack(side="left", padx=(20, 4))
        self.cfg_apikey = ttk.Entry(bar, width=30, show="•")
        self.cfg_apikey.pack(side="left")

    # ---- perfil -----------------------------------------------------------

    def _aplicar_perfil(self):
        """Vuelca el perfil cargado en los campos de la GUI (defaults)."""
        p = self.perfil
        par = p.get("parametros", {})
        self.lbl_perfil.configure(
            text=f"Perfil: {p.get('nombre_perfil', '')}  ·  "
            f"ventana {p.get('ventana', {}).get('desde', '')} → "
            f"{p.get('ventana', {}).get('hasta', '')}"
        )
        # pestaña análisis
        self.e_peso.delete(0, "end")
        self.e_peso.insert(0, str(par.get("umbral_red", 2)))
        self.e_ntop.delete(0, "end")
        self.e_ntop.insert(0, str(par.get("n_topicos", 5)))
        self.e_vent.delete(0, "end")
        self.e_vent.insert(0, str(par.get("ventana_colocaciones", 6)))
        self.e_minpal.delete(0, "end")
        self.e_minpal.insert(0, str(par.get("min_palabras_nota", 0)))
        self.e_calmin.delete(0, "end")
        self.e_calmin.insert(0, str(par.get("calidad_minima", 0)))
        self.e_stop.delete(0, "end")
        self.e_stop.insert(0, ", ".join(par.get("stopwords_extra", [])))
        self.var_navegador.set(par.get("usar_navegador", True))
        self.e_max.delete(0, "end")
        self.e_max.insert(0, str(par.get("max_resultados", 100)))
        self.e_apikey.delete(0, "end")
        self.e_apikey.insert(0, p.get("api_key", ""))
        # fechas de la ventana
        v = p.get("ventana", {})
        if v.get("desde"):
            self.txt_desde.delete(0, "end")
            self.txt_desde.insert(0, v["desde"])
        if v.get("hasta"):
            self.txt_hasta.delete(0, "end")
            self.txt_hasta.insert(0, v["hasta"])
        # pestaña config: parámetros
        for k, e in self.cfg.items():
            e.delete(0, "end")
            e.insert(0, str(par.get(k, "")))
        self.cfg_stop.delete(0, "end")
        self.cfg_stop.insert(0, ", ".join(par.get("stopwords_extra", [])))
        self.cfg_medios.delete("1.0", "end")
        self.cfg_medios.insert("1.0", "\n".join(config.todos_los_medios(p)))
        self.cfg_entidades.delete("1.0", "end")
        lineas = [
            f"{e['nombre']} | {e.get('tipo', 'persona')} | {', '.join(e.get('variantes', []))}"
            for e in p.get("entidades", [])
        ]
        self.cfg_entidades.insert("1.0", "\n".join(lineas))
        self.cfg_apikey.delete(0, "end")
        self.cfg_apikey.insert(0, p.get("api_key", ""))

    def _recoger_perfil(self):
        """Lee los campos de la pestaña config y arma el dict del perfil."""
        p = self.perfil
        par = p.setdefault("parametros", {})
        for k, e in self.cfg.items():
            val = e.get().strip()
            try:
                par[k] = float(val) if k == "calidad_minima" else int(val)
            except ValueError:
                pass
        par["stopwords_extra"] = (
            [
                s.strip()
                for s in self.cfg_stop.get("1.0", "end").replace("\n", ",").split(",")
                if s.strip()
            ]
            if hasattr(self.cfg_stop, "get")
            else par.get("stopwords_extra", [])
        )
        # medios → un solo grupo "personalizado" (preserva los del perfil si no se tocó)
        medios_txt = [
            m.strip() for m in self.cfg_medios.get("1.0", "end").splitlines() if m.strip()
        ]
        if medios_txt:
            p["medios"] = {"personalizado": medios_txt}
        # entidades
        ents = []
        for ln in self.cfg_entidades.get("1.0", "end").splitlines():
            if "|" not in ln:
                continue
            partes = [x.strip() for x in ln.split("|")]
            nombre = partes[0]
            tipo = partes[1] if len(partes) > 1 and partes[1] else "persona"
            vars_ = [v.strip() for v in partes[2].split(",")] if len(partes) > 2 else []
            if nombre:
                ents.append({"nombre": nombre, "tipo": tipo, "variantes": [v for v in vars_ if v]})
        if ents:
            p["entidades"] = ents
        p["api_key"] = self.cfg_apikey.get().strip()
        return p

    def _guardar_perfil(self):
        try:
            p = self._recoger_perfil()
            config.guardar(p)
            self.perfil = p
            messagebox.showinfo("¡Quac!", f"Perfil guardado en:\n{config.ruta_config()}")
        except Exception as e:
            messagebox.showerror("Error al guardar", str(e))

    def _restaurar_semilla(self):
        if messagebox.askyesno(
            "Restaurar", "¿Volver al perfil semilla de la 2ª vuelta 2026? Se perderán tus cambios."
        ):
            self.perfil = config.restaurar_semilla()
            self._aplicar_perfil()

    def _perfil_a_busqueda(self):
        """Carga las entidades del perfil en la tabla de la pestaña Buscar."""
        self._recoger_perfil()
        for iid in self.tabla.get_children():
            self.tabla.delete(iid)
        for e in self.perfil.get("entidades", []):
            self.tabla.insert(
                "",
                "end",
                values=(e["nombre"], e.get("tipo", "persona"), ", ".join(e.get("variantes", []))),
            )
        self.nb.select(self.tab_buscar)
        messagebox.showinfo(
            "¡Quac!",
            f"{len(self.perfil.get('entidades', []))} "
            "entidades del perfil cargadas en la búsqueda.",
        )

    # ---- entidades --------------------------------------------------------

    def _añadir_entidad(self):
        nombre = self.e_nombre.get().strip()
        if nombre:
            self.tabla.insert(
                "", "end", values=(nombre, self.e_tipo.get(), self.e_var.get().strip())
            )
            self.e_nombre.delete(0, "end")
            self.e_var.delete(0, "end")

    def _quitar_entidad(self):
        for s in self.tabla.selection():
            self.tabla.delete(s)

    def _entidades(self):
        ents = []
        for iid in self.tabla.get_children():
            nombre, tipo, var = self.tabla.item(iid, "values")
            ents.append(
                EntidadInteres(nombre, tipo, [x.strip() for x in var.split(",") if x.strip()])
            )
        return ents

    # ---- log/cola ---------------------------------------------------------

    def _escribir(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _vaciar_cola(self):
        try:
            while True:
                tipo, dato = self._cola.get_nowait()
                if tipo == "log":
                    self._escribir(dato)
                elif tipo == "busqueda_lista":
                    self._on_busqueda_lista(dato)
                elif tipo == "fin":
                    self.prog.stop()
                    self.btn_analizar.configure(state="normal")
                    if hasattr(self, "btn_analizar_bd"):
                        self.btn_analizar_bd.configure(state="normal")
                    ruta = dato.get("dashboard")
                    messagebox.showinfo("¡Quac!", dato["msg"])
                    if ruta:
                        webbrowser.open(Path(ruta).resolve().as_uri())
                elif tipo == "social_fin":
                    self.prog.stop()
                    self.btn_social.configure(state="normal")
                    encontradas, guardadas = dato
                    messagebox.showinfo(
                        "Redes sociales",
                        f"{encontradas} publicaciones recolectadas · "
                        f"{guardadas} nuevas guardadas en la BD.\n\n"
                        "Ve a «3 · Análisis» y pulsa analizar para incluirlas.",
                    )
                elif tipo == "error":
                    self.prog.stop()
                    self.btn_buscar.configure(state="normal")
                    self.btn_analizar.configure(state="normal")
                    if hasattr(self, "btn_social"):
                        self.btn_social.configure(state="normal")
                    if hasattr(self, "btn_analizar_bd"):
                        self.btn_analizar_bd.configure(state="normal")
                    messagebox.showerror("Error", dato)
        except queue.Empty:
            pass
        self.after(150, self._vaciar_cola)

    # ---- criterios --------------------------------------------------------

    def _criterios(self):
        def _f(v):
            v = v.strip()
            return None if (not v or v == "AAAA-MM-DD") else v

        terminos = [t.strip() for t in self.txt_terminos.get().split(";") if t.strip()]
        return CriteriosBusqueda(
            terminos=terminos,
            desde=_f(self.txt_desde.get()),
            hasta=_f(self.txt_hasta.get()),
            entidades=self._entidades(),
            max_resultados=int(self.e_max.get() or 100),
            filtrar_por_entidades=self.var_filtrar.get(),
        )

    # ---- PASO 1: buscar ---------------------------------------------------

    def _lanzar_busqueda(self):
        try:
            criterios = self._criterios()
        except ValueError as e:
            messagebox.showerror("Criterios inválidos", str(e))
            return
        if not criterios.terminos_efectivos():
            messagebox.showwarning("¡Quac!", "Escribe un término o una entidad.")
            return
        self._criterios_actuales = criterios
        masivo = self.var_masivo.get()
        try:
            dias_tramo = max(1, int(self.e_dias_tramo.get() or 7))
        except ValueError:
            dias_tramo = 7
        if masivo and not (criterios.desde and criterios.hasta):
            if not messagebox.askyesno(
                "Búsqueda masiva",
                "La búsqueda masiva rinde mucho más con un rango de fechas "
                "(desde/hasta), porque trocea el período en tramos.\n\n"
                "Sin fechas solo se trocea por términos. ¿Continuar igual?",
            ):
                return
        self.btn_buscar.configure(state="disabled")
        modo = f"masiva (tramos de {dias_tramo} días)" if masivo else "normal"
        self._escribir(f"Buscando «{criterios.query_principal()}» — {modo}…")
        threading.Thread(
            target=self._worker_buscar, args=(criterios, masivo, dias_tramo), daemon=True
        ).start()

    def _worker_buscar(self, criterios, masivo=False, dias_tramo=7):
        try:
            cb = lambda m: self._cola.put(("log", m))
            if masivo:
                res = buscar_masivo(criterios, callback=cb, dias_tramo=dias_tramo)
            else:
                res = buscar(criterios, callback=cb, aplicar_max=False)  # traer TODO lo encontrado
            self._cola.put(("busqueda_lista", res))
        except Exception as e:
            import traceback

            self._cola.put(("error", f"{e}\n\n{traceback.format_exc()}"))

    def _on_busqueda_lista(self, resultados):
        self.btn_buscar.configure(state="normal")
        self._resultados = resultados
        total = len(resultados)
        self.lbl_total.configure(
            text=f"📊 {total} notas encontradas para el período y términos dados."
        )
        medios = medios_de(resultados)
        valores = ["(todos los medios)"] + [f"{m} ({n})" for m, n in medios.items()]
        self.cmb_medio["values"] = valores
        self.cmb_medio.set(valores[0])
        self._render_resultados()
        self.nb.select(self.tab_resultados)

    def _render_resultados(self):
        for w in self.lista.winfo_children():
            w.destroy()
        self._vars_sel = {}
        filtro = self.cmb_medio.get()
        medio_f = None
        if filtro and not filtro.startswith("(todos"):
            medio_f = filtro.rsplit(" (", 1)[0]
        for i, r in enumerate(self._resultados):
            medio = r.medio or r.dominio()
            if medio_f and medio != medio_f:
                continue
            var = tk.BooleanVar(value=True)
            self._vars_sel[i] = var
            fila = ttk.Frame(self.lista)
            fila.pack(fill="x", anchor="w", pady=1)
            ttk.Checkbutton(fila, variable=var).pack(side="left")
            txt = f"[{r.fecha or '?'}] {medio} — {r.titular[:85]}"
            ttk.Label(fila, text=txt).pack(side="left")

    def _marcar(self, val):
        for v in self._vars_sel.values():
            v.set(val)

    # ---- PASO 3: scrapear seleccionadas + analizar ------------------------

    def _lanzar_analisis(self):
        sel = [self._resultados[i] for i, v in self._vars_sel.items() if v.get()]
        if not sel:
            messagebox.showwarning("¡Quac!", "No hay notas seleccionadas (paso 2).")
            return
        self.btn_analizar.configure(state="disabled")
        self.prog.start()
        threading.Thread(target=self._worker_analisis, args=(sel,), daemon=True).start()

    def _worker_analisis(self, seleccion):
        log = lambda m: self._cola.put(("log", m))
        try:
            criterios = self._criterios_actuales
            db = BaseDatos(self._db_path.get())
            self._sembrar(db, criterios)
            screenshots = str(Path(db.ruta).parent / "screenshots")
            ins = 0
            for i, r in enumerate(seleccion, 1):
                log(f"[{i}/{len(seleccion)}] {r.medio or r.dominio()} — {r.titular[:55]}")
                scr = scraper_para_url(
                    r.url, usar_navegador=self.var_navegador.get(), screenshots_dir=screenshots
                )
                nota = scr.extraer_nota(r.url)
                if nota and not nota.fecha_publicacion and r.fecha:
                    nota.fecha_publicacion = r.fecha
                if nota and nota.cuerpo and db.guardar_nota(nota):
                    ins += 1
                    log(f"    ✓ {nota.medio} · {nota.n_palabras} palabras")
                else:
                    log("    ↺ duplicada o no extraíble")

            entidades = list(criterios.entidades)
            titulo = criterios.query_principal()
            self._analizar_bd(db, log, entidades=entidades, titulo=titulo, notas_nuevas=ins)
        except Exception as e:
            import traceback

            self._cola.put(("error", f"{e}\n\n{traceback.format_exc()}"))

    def _analizar_bd(self, db, log, *, entidades=None, titulo="", notas_nuevas=None):
        """Corre el pipeline sobre TODAS las notas de la BD y genera entregables.
        Compartido por «scrapear y analizar» y «abrir BD ya guardada»."""
        import dashboard
        import revision
        from core import network_engine
        from pipeline import analizar_corpus

        entidades = entidades or []

        log("Analizando corpus…")
        notas = db.todas_las_notas()
        if not notas:
            self._cola.put(("error", "La base de datos no tiene notas que analizar."))
            return
        api = self.e_apikey.get().strip() or None
        # Semillas de normalización: del perfil + las de la búsqueda (si hubo).
        semillas = dict(config.semillas_normalizacion(self.perfil))
        semillas.update({e.nombre: e.todas_las_formas for e in entidades})
        decisiones = revision.cargar_decisiones(db)
        stop = [s.strip() for s in self.e_stop.get().split(",") if s.strip()]
        oblig = [s.strip() for s in self.e_oblig.get().split(",") if s.strip()]
        excl = [s.strip() for s in self.e_excl.get().split(",") if s.strip()]
        res = analizar_corpus(
            notas,
            api_key=api,
            peso_minimo_red=int(self.e_peso.get() or 1),
            semillas_entidades=semillas,
            usar_coref=self.an["coref"].get(),
            decisiones_revision=decisiones,
            n_topicos=int(self.e_ntop.get() or 5),
            ventana_colocaciones=int(self.e_vent.get() or 6),
            min_palabras_nota=int(self.e_minpal.get() or 0),
            calidad_minima=float(self.e_calmin.get() or 0),
            entidades_obligatorias=oblig,
            excluir_terminos=excl,
            solo_actores_relevantes=self.an["solo_relevantes"].get(),
            stopwords_extra=stop,
            usar_transformer=self.var_transformer.get(),
            usar_bertopic=self.var_bertopic.get(),
            callback=log,
        )
        for url, rr in res["por_nota"].items():
            db.guardar_analisis(
                url, sentimiento=rr["emociones"], ner=rr["ner"], confianza=rr["confianza"]
            )
        revision.guardar_cola(db, revision.construir_cola(res["indice_global"], semillas=semillas))
        # Si la BD ya tiene análisis transformer por bloques, compilarlo y
        # añadirlo al dashboard (tarjeta de tono real + odio + ironía).
        try:
            import transformer_lotes

            st = transformer_lotes.compilar(str(db.ruta))
            if st.get("n_analizadas"):
                res["social_transformer"] = st
                log(
                    f"Transformer: {st['n_analizadas']} notas compiladas "
                    f"(odio {st['odio']['pct']}%, ironía {st['ironia']['pct']}%)."
                )
        except Exception:
            pass
        G = network_engine.dict_a_grafo(res["grafo"])
        red_html = Path(db.ruta).with_suffix(".red.html")
        network_engine.exportar_pyvis(G, red_html, titulo="¡Quac! — Red de actores")
        dash = Path(db.ruta).with_suffix(".dashboard.html")
        dashboard.generar_dashboard(
            res, notas, dash, titulo=f"¡Quac! — {titulo or Path(db.ruta).stem}"
        )
        if self.var_excel.get():
            import exportar_excel

            xlsx = Path(db.ruta).with_suffix(".xlsx")
            exportar_excel.exportar(res, notas, xlsx)
            log(f"Excel exportado: {xlsx}")
        db.close()
        cuantas = notas_nuevas if notas_nuevas is not None else len(notas)
        detalle = (
            f"{cuantas} notas nuevas + corpus analizado"
            if notas_nuevas is not None
            else f"{len(notas)} notas analizadas"
        )
        self._cola.put(
            (
                "fin",
                {"msg": f"{detalle}. Se abrirá el dashboard interactivo.", "dashboard": str(dash)},
            )
        )

    def _lanzar_limpiar_bd(self):
        """Borra de la BD las notas de ruido según los filtros de relevancia
        («Debe mencionar» / «Excluir si menciona»). Respalda antes y pide
        confirmación mostrando cuántas se eliminarán."""
        ruta = self._db_path.get().strip()
        if not Path(ruta).exists():
            messagebox.showwarning(
                "¡Quac!",
                f"No existe la base de datos:\n{ruta}\n\n"
                "Elige un .db con «📂 Elegir…» o en la pestaña «1 · Buscar».",
            )
            return
        oblig = [s.strip() for s in self.e_oblig.get().split(",") if s.strip()]
        excl = [s.strip() for s in self.e_excl.get().split(",") if s.strip()]
        if not oblig and not excl:
            messagebox.showinfo(
                "¡Quac!",
                "No hay filtros de relevancia definidos.\n\n"
                "Llena «Debe mencionar» (p. ej. Cepeda, Espriella) y/o "
                "«Excluir si menciona» (p. ej. Perú, Fujimori) en los parámetros "
                "de arriba, y vuelve a pulsar Limpiar.",
            )
            return
        try:
            db = BaseDatos(ruta)
            info = db.contar_irrelevantes(oblig, excl)
            db.close()
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return
        if not info["a_borrar"]:
            messagebox.showinfo(
                "¡Quac!",
                f"Ninguna nota de las {info['total']} cumple criterio de ruido. "
                "La BD ya está limpia.",
            )
            return
        msg = (
            f"Se BORRARÁN {info['a_borrar']} notas de ruido de un total de "
            f"{info['total']}.\nQuedarán {info['quedan']} notas relevantes.\n\n"
            f"Criterio:\n"
            + (f"  • deben mencionar: {', '.join(oblig)}\n" if oblig else "")
            + (f"  • se excluyen si mencionan: {', '.join(excl)}\n" if excl else "")
            + "\nSe creará un respaldo .bak antes de borrar.\n¿Continuar?"
        )
        if not messagebox.askyesno("Limpiar BD — borrado definitivo", msg, icon="warning"):
            return
        try:
            db = BaseDatos(ruta)
            res = db.purgar_irrelevantes(oblig, excl, respaldar=True)
            db.close()
        except Exception as e:
            messagebox.showerror("Error al limpiar", str(e))
            return
        messagebox.showinfo(
            "¡Quac!",
            f"Limpieza completa.\n\nBorradas: {res['borradas']}\n"
            f"Quedan: {res['quedan']}\nRespaldo: {Path(res['respaldo']).name}\n\n"
            "Ahora pulsa «📂 Abrir BD y analizar lo ya guardado» para el dashboard.",
        )
        self._escribir(
            f"BD limpiada: -{res['borradas']} notas de ruido. "
            f"Quedan {res['quedan']}. Respaldo: {res['respaldo']}"
        )

    def _lanzar_analizar_bd(self):
        """Analiza directamente lo que ya está guardado en la BD (sin buscar
        ni scrapear): para retomar un corpus de una sesión anterior."""
        ruta = self._db_path.get().strip()
        if not Path(ruta).exists():
            messagebox.showwarning(
                "¡Quac!",
                f"No existe la base de datos:\n{ruta}\n\n"
                "Escribe la ruta de un .db existente en la pestaña «1 · Buscar» "
                "(campo «Base de datos») o usa «📂 Elegir…».",
            )
            return
        self.btn_analizar.configure(state="disabled")
        self.btn_analizar_bd.configure(state="disabled")
        self.prog.start()
        self._escribir(f"Abriendo corpus guardado: {ruta}")
        threading.Thread(target=self._worker_analizar_bd, daemon=True).start()

    def _worker_analizar_bd(self):
        log = lambda m: self._cola.put(("log", m))
        try:
            db = BaseDatos(self._db_path.get())
            # Entidades de interés: las del perfil (no hubo búsqueda con criterios).
            from busqueda.criterios import EntidadInteres

            ents = [
                EntidadInteres(e["nombre"], e.get("tipo", "persona"), e.get("variantes", []))
                for e in self.perfil.get("entidades", [])
            ]
            self._analizar_bd(db, log, entidades=ents, titulo=Path(db.ruta).stem)
        except Exception as e:
            import traceback

            self._cola.put(("error", f"{e}\n\n{traceback.format_exc()}"))

    def _elegir_db(self):
        from tkinter import filedialog

        ruta = filedialog.askopenfilename(
            title="Elegir base de datos de un estudio anterior",
            initialdir="datos",
            filetypes=[("Base de datos SQLite", "*.db"), ("Todos", "*.*")],
        )
        if ruta:
            self._db_path.set(ruta)
            self._escribir(f"Base de datos seleccionada: {ruta}")

    def _sembrar(self, db, criterios):
        import json

        if not criterios.entidades:
            return
        db.con.execute(
            "CREATE TABLE IF NOT EXISTS entidades_interes "
            "(nombre TEXT PRIMARY KEY, tipo TEXT, formas TEXT)"
        )
        for e in criterios.entidades:
            db.con.execute(
                "INSERT OR REPLACE INTO entidades_interes VALUES (?,?,?)",
                (e.nombre, e.tipo, json.dumps(e.todas_las_formas, ensure_ascii=False)),
            )
        db.con.commit()


if __name__ == "__main__":
    QuacGUI().mainloop()

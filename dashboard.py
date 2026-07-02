"""Generador de dashboard HTML interactivo de ¡Quac!.

Toma el dict de resultados de ``pipeline.analizar_corpus`` y produce un HTML
autocontenido (sin servidor) con pestañas para EXPLORAR:

  - Resumen: actores, medios, encuadre, series temporales.
  - Actores: clic en un actor → sus notas, emoción, colocaciones, ego-red.
  - Relaciones: co-ocurrencia entre dos entidades + concordancias (KWIC).
  - Medios: matriz medio × actor (sesgo de selección) + emoción por medio.
  - Notas: tabla con titular, medio, fecha, sentimiento, encuadre, screenshot.

Todo el dato va embebido como JSON; el JS del HTML hace la interacción. Es
portátil (se abre en cualquier navegador) y no requiere conexión.
"""

from __future__ import annotations

import json
from pathlib import Path


def _kwic(notas: list[dict], termino: str, ventana: int = 60, max_n: int = 40):
    """Concordancias KWIC: fragmentos de texto alrededor de un término."""
    res = []
    t = termino.lower()
    for n in notas:
        cuerpo = n.get("cuerpo") or ""
        low = cuerpo.lower()
        i = low.find(t)
        while i != -1 and len(res) < max_n:
            ini = max(0, i - ventana)
            fin = min(len(cuerpo), i + len(termino) + ventana)
            frag = cuerpo[ini:fin].replace("\n", " ")
            res.append({"medio": n.get("medio", ""), "fragmento": frag})
            i = low.find(t, i + 1)
    return res


def generar_dashboard(
    res: dict, notas: list[dict], ruta: str | Path, titulo: str = "¡Quac! — Análisis de prensa"
) -> Path:
    """Genera el HTML interactivo. ``notas`` = filas de la BD (para KWIC)."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    # KWIC para los actores principales (precalculado, liviano)
    personas = res.get("indice_global", {}).get("personas", {})
    top_actores = [a for a, _ in sorted(personas.items(), key=lambda kv: -len(kv[1]))[:15]]
    kwic = {a: _kwic(notas, a.split()[-1] if a.split() else a) for a in top_actores}

    # ── Aligerar el payload del dashboard ────────────────────────────────────
    # El HTML incrusta `por_nota` como JSON. El JS de la plantilla SOLO lee, por
    # nota: medio, titular, fecha, emociones.emocion_dominante y frame.etiqueta.
    # Incrustar el dict completo (ner, coref, prominencia, origen, calidad…) por
    # cada una de miles de notas inflaba el HTML a cientos de MB y disparaba la
    # memoria al generarlo (causa del cierre silencioso con corpus grandes en
    # equipos de ~8 GB de RAM). Proyectamos solo lo que el dashboard consume.
    def _nota_ligera(r: dict) -> dict:
        emo = r.get("emociones") or {}
        fr = r.get("frame") or {}
        return {
            "medio": r.get("medio"),
            "titular": r.get("titular"),
            "fecha": r.get("fecha"),
            "emociones": {"emocion_dominante": emo.get("emocion_dominante")},
            "frame": {"etiqueta": fr.get("etiqueta")},
        }

    por_nota_ligero = {u: _nota_ligera(r) for u, r in (res.get("por_nota") or {}).items()}

    datos = {
        "titulo": titulo,
        "por_nota": por_nota_ligero,
        "indice_global": res.get("indice_global", {}),
        "metricas_red": res.get("metricas_red", {}),
        "grafo": res.get("grafo", {}),
        "frames": res.get("frames", {}),
        "comparacion": res.get("comparacion_medios", {}),
        "series": res.get("series_temporales", {}),
        "frecuencias": res.get("frecuencias", []),
        "colocaciones": res.get("colocaciones", {}),
        "menciones_coref": res.get("menciones_coref", []),
        "calidad_corpus": res.get("calidad_corpus", {}),
        "cobertura_por_tipo": res.get("cobertura_por_tipo", {}),
        "comparacion_candidatos": res.get("comparacion_candidatos", {}),
        "tendencia_medios": res.get("tendencia_medios", {}),
        "toxicidad": res.get("toxicidad", {}),
        "prominencia": res.get("prominencia", {}),
        "origen": res.get("origen", {}),
        "lineas_tiempo": res.get("lineas_tiempo", {}),
        "social_transformer": res.get("social_transformer", {}),
        "kwic": kwic,
    }
    payload = json.dumps(datos, ensure_ascii=False)

    # Incrustar el módulo de control por gestos de mano (handControls.js) en el
    # HTML, para que el dashboard siga siendo un único archivo portable. El
    # módulo es opcional: si el archivo no está, el dashboard funciona igual
    # (el botón ✋ Mano queda deshabilitado).
    hc_js = "/* handControls.js no encontrado: control por mano desactivado */"
    # Buscar en varias ubicaciones: junto al .py (desarrollo) y en el bundle de
    # PyInstaller (sys._MEIPASS, donde el .spec empaqueta el .js en la raíz).
    import sys as _sys

    _candidatos = [Path(__file__).with_name("handControls.js")]
    _mei = getattr(_sys, "_MEIPASS", None)
    if _mei:
        _candidatos.append(Path(_mei) / "handControls.js")
    for _c in _candidatos:
        try:
            hc_js = _c.read_text(encoding="utf-8")
            break
        except OSError:
            continue

    # Incrustar studyInfo.js (panel de información técnica del estudio) con el
    # mismo patrón: módulo separado, leído en runtime, empaquetado en el .exe.
    si_js = "/* studyInfo.js no encontrado: panel técnico desactivado */"
    _cand_si = [Path(__file__).with_name("studyInfo.js")]
    if _mei:
        _cand_si.append(Path(_mei) / "studyInfo.js")
    for _c in _cand_si:
        try:
            si_js = _c.read_text(encoding="utf-8")
            break
        except OSError:
            continue

    html = (
        _PLANTILLA.replace("/*__DATOS__*/", payload)
        .replace("/*__HANDCONTROLS_JS__*/", hc_js)
        .replace("/*__STUDYINFO_JS__*/", si_js)
        .replace("__TITULO__", titulo)
    )
    ruta.write_text(html, encoding="utf-8")
    return ruta


_PLANTILLA = r"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<title>__TITULO__</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<script src="https://unpkg.com/3d-force-graph@1.73.4/dist/3d-force-graph.min.js"></script>
<script src="https://unpkg.com/three-spritetext@1.8.2/dist/three-spritetext.min.js"></script>
<script>/*__HANDCONTROLS_JS__*/</script>
<script>/*__STUDYINFO_JS__*/</script>
<style>
 :root{--bg:#0f1115;--card:#1b1f27;--fg:#e6e6e6;--mut:#9aa3b2;--acc:#4ea1ff;--ok:#34d399;--bad:#f87171;}
 *{box-sizing:border-box} body{margin:0;font-family:Segoe UI,system-ui,sans-serif;background:var(--bg);color:var(--fg)}
 header{padding:14px 20px;background:#12141a;border-bottom:1px solid #262b36}
 h1{margin:0;font-size:20px} .sub{color:var(--mut);font-size:13px}
 nav{display:flex;gap:6px;padding:8px 16px;background:#12141a;flex-wrap:wrap}
 nav button{background:var(--card);color:var(--fg);border:1px solid #2b313c;border-radius:8px;padding:8px 14px;cursor:pointer}
 nav button.act{background:var(--acc);color:#06121f;font-weight:600}
 main{padding:18px}
 .tab{display:none} .tab.act{display:block}
 .grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}
 .card{background:var(--card);border:1px solid #262b36;border-radius:12px;padding:14px}
 .card h3{margin:0 0 8px;font-size:14px;color:var(--acc)}
 table{width:100%;border-collapse:collapse;font-size:13px} th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #262b36}
 th{color:var(--mut);font-weight:600} tr:hover td{background:#222732}
 .chip{display:inline-block;background:#222a38;border-radius:12px;padding:2px 10px;margin:2px;font-size:12px;cursor:pointer}
 .chip:hover{background:var(--acc);color:#06121f}
 .bar{height:10px;background:var(--acc);border-radius:5px;display:inline-block;vertical-align:middle}
 select,input{background:#0f1115;color:var(--fg);border:1px solid #2b313c;border-radius:8px;padding:6px}
 .kwic{font-size:12px;color:#cdd3dd;border-left:2px solid var(--acc);padding:4px 8px;margin:4px 0}
 .mut{color:var(--mut)} .big{font-size:26px;font-weight:700}
 mark{background:#3a4660;color:#fff;border-radius:3px;padding:0 2px}
 #red{height:72vh;background:#0c0e13;border:1px solid #262b36;border-radius:12px}
 #redbox{background:radial-gradient(ellipse at 50% 38%,#161c2a 0%,#0a0c11 75%);
   border:1px solid #262b36;border-radius:12px;position:relative;overflow:hidden}
 .seg{display:inline-flex;border:1px solid #2b313c;border-radius:9px;overflow:hidden}
 .seg button{background:#151a22;color:var(--mut);border:none;padding:7px 16px;cursor:pointer;font-weight:600;font-size:13px}
 .seg button.act{background:var(--acc);color:#06121f}
 .leyenda{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
 .lg-chip{display:inline-flex;align-items:center;gap:6px;background:#1a2029;border:1px solid #2b313c;
   border-radius:14px;padding:3px 12px;font-size:12px;cursor:pointer;user-select:none;transition:opacity .15s}
 .lg-chip.off{opacity:.32;filter:grayscale(.85)}
 .lg-chip:hover{border-color:var(--acc)}
 .btn-acc{background:#222a38;color:var(--fg);border:1px solid #2b313c;border-radius:8px;
   padding:6px 12px;font-size:12px;cursor:pointer}
 .btn-acc:hover{background:var(--acc);color:#06121f}
 .btn-acc.act{background:var(--ok);color:#06121f;border-color:var(--ok)}
 .controles{display:flex;gap:10px;align-items:center;margin:8px 0;flex-wrap:wrap}
 canvas.chart{max-height:240px}
 .leg{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:middle}
 /* --- Panel de información técnica del estudio (studyInfo.js) --- */
 .red-wrap{display:flex;gap:14px;align-items:flex-start}
 .red-wrap #redbox{flex:1;min-width:0}
 .study-panel{flex:0 0 300px;max-height:72vh;overflow:auto;background:var(--card);
   border:1px solid #262b36;border-radius:12px;padding:12px 14px;
   font-family:"Cascadia Code",Consolas,ui-monospace,monospace}
 .study-panel .si-head{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:8px}
 .study-panel .si-titulo{font-weight:700;color:var(--acc);font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .study-panel .si-copy{background:#222a38;color:var(--fg);border:1px solid #2b313c;border-radius:7px;padding:4px 8px;font-size:11px;cursor:pointer;white-space:nowrap}
 .study-panel .si-copy:hover{background:var(--acc);color:#06121f}
 .study-panel .si-tbl{width:100%;border-collapse:collapse;font-size:12px}
 .study-panel .si-tbl td{padding:3px 4px;border-bottom:1px solid #20252f;vertical-align:top}
 .study-panel .si-k{color:var(--mut)} .study-panel .si-v{text-align:right;color:#e6e6e6;font-variant-numeric:tabular-nums}
 .study-panel .si-sec td,.study-panel .si-sec{color:var(--acc);font-weight:700;padding-top:8px;border-bottom:none;font-size:11px;text-transform:uppercase;letter-spacing:.04em}
 .study-panel .si-toplabel{margin:8px 0 4px}
 .study-panel .si-top{width:100%;border-collapse:collapse;font-size:12px}
 .study-panel .si-top th{color:var(--mut);font-weight:600;text-align:left;padding:3px 4px;border-bottom:1px solid #262b36}
 .study-panel .si-top td{padding:3px 4px;border-bottom:1px solid #20252f}
 @media(max-width:900px){.red-wrap{flex-direction:column}.study-panel{flex-basis:auto;width:100%;max-height:none}}
</style></head><body>
<header><h1>🦆 __TITULO__</h1><div class="sub" id="meta"></div></header>
<nav id="nav"></nav>
<main>
  <section class="tab act" id="t-resumen"></section>
  <section class="tab" id="t-red"></section>
  <section class="tab" id="t-actores"></section>
  <section class="tab" id="t-relaciones"></section>
  <section class="tab" id="t-medios"></section>
  <section class="tab" id="t-tiempo"></section>
  <section class="tab" id="t-notas"></section>
</main>
<script>
const D = /*__DATOS__*/;
const $ = s => document.querySelector(s);
const el = (t,c,h)=>{const e=document.createElement(t); if(c)e.className=c; if(h!=null)e.innerHTML=h; return e;};
const porNota = Object.entries(D.por_nota||{});
const personas = D.indice_global.personas||{};
const orgs = D.indice_global.organizaciones||{};

// ---- navegación
const tabs=[["resumen","Resumen"],["red","Red interactiva"],["actores","Actores"],["relaciones","Relaciones"],["medios","Medios"],["tiempo","📈 Líneas del tiempo"],["notas","Notas"]];
const nav=$("#nav");
tabs.forEach(([id,txt],i)=>{const b=el("button",i==0?"act":"",txt);b.onclick=()=>{
  document.querySelectorAll("nav button").forEach(x=>x.classList.remove("act"));
  document.querySelectorAll(".tab").forEach(x=>x.classList.remove("act"));
  b.classList.add("act"); $("#t-"+id).classList.add("act");
  if(id==="red") dibujarRed();
  if(id==="relaciones") dibujarRelaciones();
  if(id==="tiempo") dibujarTiempo();}; nav.appendChild(b);});

$("#meta").textContent = porNota.length+" notas · "+(D.metricas_red.nodos||0)+" actores en la red";

// ---- helpers
function ranking(obj){return Object.entries(obj).map(([k,v])=>[k,v.length]).sort((a,b)=>b[1]-a[1]);}
function barRow(label,n,max,onclick){
  const row=el("div"); row.style.margin="4px 0";
  const a=el("span","chip",label); if(onclick)a.onclick=onclick;
  const bar=el("span","bar"); bar.style.width=Math.max(6,Math.round(160*n/(max||1)))+"px"; bar.style.marginLeft="8px";
  row.appendChild(a); row.appendChild(bar); row.appendChild(el("span",null," "+n)); return row;
}

// ---- RESUMEN
(function(){const c=$("#t-resumen");
  // ---- COMPARATIVA DE CANDIDATOS (tabla central del estudio electoral) ----
  const cand=D.comparacion_candidatos||{};
  if(Object.keys(cand).length){
    const cc=el("div","card"); cc.style.marginBottom="14px";
    cc.appendChild(el("h3",null,"⭐ Comparativa de candidatos (visibilidad · polaridad · encuadre)"));
    const t=el("table"); t.innerHTML="<tr><th>Candidato</th><th>Notas</th><th>Polaridad (pos/neg/neu)</th><th>Tono medio</th><th>Polariz. afectiva</th><th>Encuadre dominante</th></tr>";
    Object.entries(cand).sort((a,b)=>b[1].n_notas-a[1].n_notas).forEach(([n,d])=>{
      const p=d.polaridad||{positivo:0,negativo:0,neutro:0};
      const sc=d.score_polaridad_medio||0;
      const col=sc>0.1?"#34d399":(sc<-0.1?"#f87171":"#9aa3b2");
      const pa=d.polarizacion_afectiva||0;
      const pac=pa>0.5?"#f87171":(pa>0.25?"#f59e0b":"#9aa3b2");
      const tr=el("tr"); tr.innerHTML="<td><span class='chip'>"+n+"</span></td><td>"+d.n_notas+
        "</td><td><span style='color:#34d399'>"+p.positivo+"</span> / <span style='color:#f87171'>"+p.negativo+
        "</span> / "+p.neutro+"</td><td style='color:"+col+"'>"+sc+"</td>"+
        "<td style='color:"+pac+"'>"+pa+"</td>"+
        "<td class='mut'>"+(d.encuadre_dominante||"—")+"</td>";
      tr.querySelector(".chip").onclick=()=>verActor(n); t.appendChild(tr);});
    cc.appendChild(t); c.appendChild(cc);
  }
  // ---- PROMINENCIA: quién aparece PRIMERO y con qué ADJETIVOS ----
  const prom=D.prominencia||{};
  if(Object.keys(prom).length){
    const pc=el("div","card"); pc.style.marginBottom="14px";
    pc.appendChild(el("h3",null,"🥇 Prominencia: quién aparece primero y cómo se le califica"));
    pc.appendChild(el("div","mut","Veces que el actor es el PRIMERO mencionado en la nota (lead), posición media en el texto (0 = arranque, 1 = cola) y adjetivos con que se le caracteriza (verde = positivo, rojo = negativo)."));
    const t=el("table"); t.innerHTML="<tr><th>Actor</th><th>1º mencionado</th><th>Posición media</th><th>Adjetivos calificativos</th></tr>";
    const maxv=Math.max(1,...Object.values(prom).map(d=>d.veces_primero||0));
    Object.entries(prom).slice(0,12).forEach(([n,d])=>{
      const pm=d.posicion_media; const pmTxt=(pm==null)?"—":pm.toFixed(2);
      const pmCol=(pm==null)?"#9aa3b2":(pm<0.2?"#34d399":(pm>0.5?"#f59e0b":"#9aa3b2"));
      const adj=(d.adjetivos_top||[]).map(a=>{
        const col=a.carga==="positivo"?"#34d399":(a.carga==="negativo"?"#f87171":"");
        const st=col?(" style='color:"+col+"'"):"";
        return "<span class='chip'"+st+" title='"+a.n+" notas · "+a.carga+"'>"+a.texto+"</span>";
      }).join(" ");
      const w=Math.round(120*(d.veces_primero||0)/maxv);
      const tr=el("tr");
      tr.innerHTML="<td><span class='chip'>"+n+"</span></td>"+
        "<td><span class='bar' style='width:"+Math.max(6,w)+"px'></span> "+(d.veces_primero||0)+"/"+(d.n_notas||0)+"</td>"+
        "<td style='color:"+pmCol+"'>"+pmTxt+"</td>"+
        "<td>"+(adj||"<span class='mut'>—</span>")+"</td>";
      tr.querySelector(".chip").onclick=()=>verActor(n); t.appendChild(tr);
    });
    pc.appendChild(t); c.appendChild(pc);
  }
  // ---- ORIGEN: cobertura nacional (Colombia) vs. internacional ----
  const org=D.origen||{};
  if((org.n_colombianos||0)+(org.n_extranjeros||0)+(org.n_desconocidos||0)>0){
    const oc=el("div","card"); oc.style.marginBottom="14px";
    oc.appendChild(el("h3",null,"🌎 Origen de la cobertura (medio colombiano vs. extranjero)"));
    const tot=(org.n_colombianos||0)+(org.n_extranjeros||0)+(org.n_desconocidos||0);
    const pct=n=>tot?Math.round(100*n/tot):0;
    oc.appendChild(el("div",null,
      "<span class='big' style='color:#34d399'>"+(org.n_colombianos||0)+"</span> "+
      "<span class='mut'>colombianas ("+pct(org.n_colombianos||0)+"%)</span> &nbsp;·&nbsp; "+
      "<span class='big' style='color:#4ea1ff'>"+(org.n_extranjeros||0)+"</span> "+
      "<span class='mut'>extranjeras ("+pct(org.n_extranjeros||0)+"%)</span> &nbsp;·&nbsp; "+
      "<span class='mut'>"+(org.n_desconocidos||0)+" sin clasificar</span>"));
    const porPais=org.por_pais||{};
    const t=el("table"); t.innerHTML="<tr><th>País</th><th>Notas</th></tr>";
    const maxp=Math.max(1,...Object.values(porPais));
    Object.entries(porPais).forEach(([p,n])=>{
      const w=Math.round(160*n/maxp);
      const tr=el("tr"); tr.innerHTML="<td>"+p+"</td><td><span class='bar' style='width:"+Math.max(6,w)+"px'></span> "+n+"</td>";
      t.appendChild(tr);
    });
    oc.appendChild(t); c.appendChild(oc);
  }
  // ---- ANÁLISIS TRANSFORMER (pysentimiento): tono real + odio + ironía ----
  const st=D.social_transformer||{};
  if(st.n_analizadas){
    const sc=el("div","card"); sc.style.marginBottom="14px";
    sc.appendChild(el("h3",null,"🤖 Análisis con transformer (pysentimiento) — "+st.n_analizadas+" notas"));
    sc.appendChild(el("div","mut","Tono medido con modelo de lenguaje (más preciso que el léxico, capta contexto/negación). El discurso de odio y la ironía SOLO los detecta el transformer."));
    const pp=st.polaridad_pct||{};
    sc.appendChild(el("div",null,
      "<span class='big' style='color:#34d399'>"+(pp.positivo||0)+"%</span> <span class='mut'>positivo</span> &nbsp;·&nbsp; "+
      "<span class='big' style='color:#f87171'>"+(pp.negativo||0)+"%</span> <span class='mut'>negativo</span> &nbsp;·&nbsp; "+
      "<span class='big' style='color:#9aa3b2'>"+(pp.neutro||0)+"%</span> <span class='mut'>neutro</span>"));
    const od=st.odio||{}, ir=st.ironia||{}, ag=st.agresividad||{};
    sc.appendChild(el("div",null,
      "<span class='chip' style='color:#f87171'>Discurso de odio: "+(od.pct||0)+"% ("+(od.n||0)+")</span> "+
      "<span class='chip'>Ironía: "+(ir.pct||0)+"% ("+(ir.n||0)+")</span> "+
      "<span class='chip'>Agresividad: "+(ag.pct||0)+"% ("+(ag.n||0)+")</span>"));
    const emo=st.emocion_dominante||{};
    if(Object.keys(emo).length){
      const t2=el("table"); t2.innerHTML="<tr><th>Emoción (transformer)</th><th>Notas</th></tr>";
      const mxe=Math.max(1,...Object.values(emo));
      Object.entries(emo).slice(0,6).forEach(([k,n])=>{const w=Math.round(160*n/mxe);
        const tr=el("tr"); tr.innerHTML="<td>"+k+"</td><td><span class='bar' style='width:"+Math.max(6,w)+"px'></span> "+n+"</td>"; t2.appendChild(tr);});
      sc.appendChild(t2);
    }
    c.appendChild(sc);
  }
  const g=el("div","grid");
  // actores
  const ca=el("div","card"); ca.appendChild(el("h3",null,"Actores más mencionados (por notas)"));
  const ra=ranking(personas).slice(0,10); const maxa=ra.length?ra[0][1]:1;
  ra.forEach(([k,n])=>ca.appendChild(barRow(k,n,maxa,()=>verActor(k)))); g.appendChild(ca);
  // presencia real (coref)
  if((D.menciones_coref||[]).length){const cc=el("div","card");cc.appendChild(el("h3",null,"Presencia real (menciones + correferencia)"));
    const mx=D.menciones_coref[0].menciones; D.menciones_coref.slice(0,10).forEach(x=>cc.appendChild(barRow(x.actor,x.menciones,mx,()=>verActor(x.actor)))); g.appendChild(cc);}
  // toxicidad / discurso de odio (solo versión PRO con transformer)
  const tox=D.toxicidad||{};
  if(tox.disponible){const ct=el("div","card");
    ct.appendChild(el("h3",null,"🚨 Discurso de odio y agresividad (PRO)"));
    ct.appendChild(el("div",null,"De "+tox.n_analizadas+" notas: <span style='color:#f87171'>"+
      tox.odio+" con odio</span>, "+tox.agresivo+" agresivas, "+tox.ironia+" irónicas."));
    const peores=Object.entries(tox.por_medio||{}).filter(([m,d])=>d.odio>0)
      .sort((a,b)=>b[1].odio-a[1].odio).slice(0,6);
    if(peores.length){ct.appendChild(el("div","mut","Medios con más notas de odio:"));
      peores.forEach(([m,d])=>ct.appendChild(el("div",null,"<span class='chip'>"+m+"</span> "+d.odio+"/"+d.n)));}
    g.appendChild(ct);}
  // calidad de extracción (validez de los datos)
  const cq=D.calidad_corpus||{};
  if(cq.total){const cc=el("div","card"); cc.appendChild(el("h3",null,"Calidad de extracción (validez de datos)"));
    cc.appendChild(el("div",null,"<span class='leg' style='background:#34d399'></span>Confiable: "+(cq.confiable||0)+
      " &nbsp; <span class='leg' style='background:#f59e0b'></span>Revisar: "+(cq.revisar||0)+
      " &nbsp; <span class='leg' style='background:#f87171'></span>Malo: "+(cq.malo||0)+" / "+cq.total));
    const peores=(cq.detalle||[]).filter(d=>d.veredicto!=="confiable").slice(0,6);
    if(peores.length){cc.appendChild(el("div","mut","Revisar primero:"));
      peores.forEach(d=>cc.appendChild(el("div","kwic","["+d.medio+"] "+d.titular+" — "+d.veredicto+" ("+d.motivos.join(", ")+")")));}
    g.appendChild(cc);}
  // framing
  const cf=el("div","card"); cf.appendChild(el("h3",null,"Encuadre (framing) del corpus"));
  (D.frames.distribucion||[]).forEach(f=>cf.appendChild(el("div",null,"<span class='chip'>"+f.etiqueta+"</span> "+f.n))); g.appendChild(cf);
  // series — VOLUMEN POR DÍA (la ventana del corpus suele ser de pocos días;
  // por mes no sirve). Usa las líneas de tiempo diarias y RECORTA al rango real
  // con notas (ignora días vacíos por fechas-basura del scraping que estirarían
  // el eje a años). Si no hay datos diarios, cae al volumen mensual.
  const _lt=(D.lineas_tiempo&&D.lineas_tiempo.global)||{};
  let diasLbl=[], volDia=[];
  if((_lt.dias||[]).length && (_lt.volumen||[]).length){
    const dias=_lt.dias, v=_lt.volumen;
    // Recorte por DENSIDAD: el scraping deja unas pocas notas con fecha-basura
    // (años 1999/2005/2026-01…) que estiran el eje. Tomamos la ventana mínima
    // que concentra el 98% del volumen, así el gráfico muestra los días reales.
    const total=v.reduce((a,b)=>a+b,0)||1;
    const idxNoVacios=[]; v.forEach((x,i)=>{ if(x>0) idxNoVacios.push(i); });
    // mediana ponderada para centrar en el grueso de las notas
    let acum=0, centro=idxNoVacios[0]||0;
    for(const i of idxNoVacios){ acum+=v[i]; if(acum>=total*0.5){ centro=i; break; } }
    // expandir alrededor del centro hasta cubrir el 98% del volumen
    let lo=centro, hi=centro, cubierto=v[centro];
    while(cubierto<total*0.98 && (lo>0||hi<v.length-1)){
      const izq=lo>0?v[lo-1]:-1, der=hi<v.length-1?v[hi+1]:-1;
      if(der>=izq){ hi++; cubierto+=Math.max(0,v[hi]); }
      else { lo--; cubierto+=Math.max(0,v[lo]); }
    }
    lo=Math.max(0,lo-1); hi=Math.min(v.length-1,hi+1);  // 1 día de margen
    diasLbl=dias.slice(lo,hi+1); volDia=v.slice(lo,hi+1);
  }
  const cs=el("div","card");
  if(diasLbl.length){
    cs.appendChild(el("h3",null,"Volumen por día"));
    const mxd=Math.max(1,...volDia);
    diasLbl.forEach((d,i)=>cs.appendChild(barRow(d,volDia[i],mxd)));
  } else {
    cs.appendChild(el("h3",null,"Volumen por mes"));
    const vol=(D.series.volumen)||{}; const meses=D.series.meses||[]; const mxv=Math.max(1,...Object.values(vol));
    meses.forEach(m=>cs.appendChild(barRow(m,vol[m],mxv)));
  }
  g.appendChild(cs);
  // términos
  const ct=el("div","card"); ct.appendChild(el("h3",null,"Términos más frecuentes"));
  (D.frecuencias||[]).slice(0,20).forEach(f=>{const ch=el("span","chip",f.palabra+" ("+f.freq+")"); ch.onclick=()=>verRelacion(f.palabra); ct.appendChild(ch);}); g.appendChild(ct);
  c.appendChild(g);

  // ---- GRÁFICAS (Chart.js) ----
  const gg=el("div","grid"); gg.style.marginTop="14px"; c.appendChild(gg);
  function cardChart(titulo){const cd=el("div","card"); cd.appendChild(el("h3",null,titulo));
    const cv=el("canvas","chart"); cd.appendChild(cv); gg.appendChild(cd); return cv;}
  const COL=["#4ea1ff","#34d399","#f59e0b","#f87171","#a78bfa","#22d3ee","#fb7185","#facc15","#4ade80","#60a5fa"];

  if(window.Chart){
    // barras: actores por nº de notas
    new Chart(cardChart("Actores (nº de notas)"),{type:"bar",
      data:{labels:ra.map(x=>x[0]),datasets:[{data:ra.map(x=>x[1]),backgroundColor:"#4ea1ff"}]},
      options:{indexAxis:"y",plugins:{legend:{display:false}},scales:{x:{ticks:{color:"#9aa3b2"}},y:{ticks:{color:"#cdd3dd"}}}}});
    // línea: volumen por DÍA (recortado al rango real con notas)
    if(diasLbl.length) new Chart(cardChart("Volumen por día"),{type:"line",
      data:{labels:diasLbl,datasets:[{data:volDia,borderColor:"#34d399",backgroundColor:"rgba(52,211,153,.2)",fill:true,tension:.3}]},
      options:{plugins:{legend:{display:false}},scales:{x:{ticks:{color:"#9aa3b2",maxRotation:60}},y:{ticks:{color:"#9aa3b2"}}}}});
    // dona: emociones del corpus
    const emoTot={}; porNota.forEach(([u,r])=>{const e=(r.emociones||{}).emocion_dominante; if(e)emoTot[e]=(emoTot[e]||0)+1;});
    if(Object.keys(emoTot).length) new Chart(cardChart("Emociones dominantes"),{type:"doughnut",
      data:{labels:Object.keys(emoTot),datasets:[{data:Object.values(emoTot),backgroundColor:COL}]},
      options:{plugins:{legend:{labels:{color:"#cdd3dd"}}}}});
    // barras: encuadre
    const fr=D.frames.distribucion||[];
    if(fr.length) new Chart(cardChart("Encuadre (framing)"),{type:"bar",
      data:{labels:fr.map(f=>f.etiqueta),datasets:[{data:fr.map(f=>f.n),backgroundColor:"#a78bfa"}]},
      options:{indexAxis:"y",plugins:{legend:{display:false}},scales:{x:{ticks:{color:"#9aa3b2"}},y:{ticks:{color:"#cdd3dd"}}}}});
  }
})();

// ---- RED INTERACTIVA (vis-network 2D + 3d-force-graph) ----
let _redInit=false, _net2d=null, _fg3d=null, _modoRed="2d";
const _catsOff=new Set();   // categorías apagadas desde la leyenda
// Paleta moderna por categoría. Manda sobre el color que traiga el backend,
// así los dashboards generados con datos viejos también estrenan diseño.
const PALETA_CAT={personas:"#ff6b81",organizaciones:"#54a0ff",lugares:"#2ed8a7",
  fechas:"#feca57",obras_publicaciones:"#c56cf0",eventos_historicos:"#48dbfb"};
const colorCat=c=>PALETA_CAT[c]||"#8395a7";
const _sombra=(hex,f)=>{const n=parseInt(hex.slice(1),16);
  return "rgb("+[16,8,0].map(s=>Math.round(((n>>s)&255)*f)).join(",")+")";};
function _datosRed(soloVecinosDe){
  const g=D.grafo||{}; let nodos=g.nodes||[], aristas=g.edges||[];
  if(_catsOff.size) nodos=nodos.filter(n=>!_catsOff.has(n.categoria||""));
  if(soloVecinosDe){ // ego-red: nodo + vecinos directos (sin límite de nodos)
    const vec=new Set([soloVecinosDe]);
    aristas.forEach(e=>{ if(e.source===soloVecinosDe)vec.add(e.target); if(e.target===soloVecinosDe)vec.add(e.source);});
    nodos=nodos.filter(n=>vec.has(n.id));
  } else {
    // Limitar a los N más conectados (control "Nodos") para que sea legible.
    const sel=$("#red-topn"); const LIMITE=sel?parseInt(sel.value,10):60;
    if(nodos.length > LIMITE){
      const grado={};
      aristas.forEach(e=>{ grado[e.source]=(grado[e.source]||0)+(e.weight||1);
                           grado[e.target]=(grado[e.target]||0)+(e.weight||1); });
      nodos=nodos.slice().sort((a,b)=>(grado[b.id]||0)-(grado[a.id]||0)).slice(0,LIMITE);
    }
  }
  const ids=new Set(nodos.map(n=>n.id));
  aristas=aristas.filter(e=>ids.has(e.source)&&ids.has(e.target));
  return {nodos, aristas};
}
function dibujar2D(ego){
  if(!window.vis){ $("#redbox").innerHTML="<div class='mut'>Sin internet: no se cargó vis-network.</div>"; return; }
  const {nodos,aristas}=_datosRed(ego);
  // Umbral de etiqueta: solo los nodos importantes muestran texto fijo; el resto
  // al pasar el cursor. Reduce el amontonamiento.
  const freqs = nodos.map(n=>n.freq||1).sort((a,b)=>b-a);
  const umbralEtq = freqs[Math.min(freqs.length-1, 24)] || 1;
  const pmax = aristas.reduce((m,e)=>Math.max(m,e.weight||1),1);

  const vnodes=nodos.map(n=>{const c=colorCat(n.categoria); return {id:n.id,
    label:(n.freq||1)>=umbralEtq ? n.id : " ",   // etiqueta solo si relevante
    color:{background:c,border:_sombra(c,0.55),
           highlight:{background:"#ffffff",border:c},hover:{background:c,border:"#ffffff"}},
    value:(n.freq||1),
    title:n.id+" · "+(n.categoria||"")+" · "+(n.freq||1)+" notas",
    font:{color:"#eef2f8",size:15,face:"Segoe UI",strokeWidth:4,strokeColor:"#0a0c11"}};});
  // Aristas: grosor Y opacidad proporcionales al peso (las relaciones fuertes
  // se VEN fuertes; las débiles se insinúan sin ensuciar).
  const colorBase=i=>"rgba(126,146,176,"+(0.16+0.5*((aristas[i].weight||1)/pmax)).toFixed(2)+")";
  const vedges=aristas.map((e,i)=>({id:i,from:e.source,to:e.target,value:e.weight||1,
    color:{color:colorBase(i),highlight:"#4ea1ff",hover:"#4ea1ff"}}));
  const cont=document.getElementById("redbox"); cont.innerHTML="";
  const datos={nodes:new vis.DataSet(vnodes),edges:new vis.DataSet(vedges)};
  _net2d=new vis.Network(cont, datos, {
    nodes:{shape:"dot",borderWidth:2,borderWidthSelected:3,
      shadow:{enabled:true,color:"rgba(0,0,0,0.45)",size:12,x:0,y:3},
      scaling:{min:9,max:48,label:{enabled:true,min:12,max:30}}},
    edges:{smooth:{enabled:true,type:"continuous",roundness:0.35},
      scaling:{min:1,max:6},selectionWidth:2,hoverWidth:1.6},
    layout:{improvedLayout:true},
    physics:{solver:"forceAtlas2Based",
      forceAtlas2Based:{gravitationalConstant:-70,centralGravity:0.012,
                        springLength:130,springConstant:0.09,avoidOverlap:1},
      stabilization:{enabled:true,iterations:400,updateInterval:25,fit:true},
      minVelocity:0.6},
    interaction:{hover:true,tooltipDelay:100,navigationButtons:true,
                 keyboard:true,multiselect:true}});
  // CLAVE: al terminar de estabilizar, CONGELAR la física → la red deja de
  // vibrar y queda estática y navegable (arrastrar nodos sigue funcionando).
  _net2d.once("stabilizationIterationsDone", function(){
    _net2d.setOptions({physics:false}); _net2d.fit();
  });
  // FOCO de vecindario al pasar el cursor: vecinos a color; el RESTO —nodos y
  // también aristas— se apaga, y las aristas propias se encienden en azul.
  const conexPor={}; aristas.forEach((e,i)=>{ (conexPor[e.source]=conexPor[e.source]||[]).push(i);
                                              (conexPor[e.target]=conexPor[e.target]||[]).push(i); });
  _net2d.on("hoverNode", function(p){
    const con=new Set([p.node]);
    _net2d.getConnectedNodes(p.node).forEach(x=>con.add(x));
    datos.nodes.update(nodos.map(n=>({id:n.id,
      opacity: con.has(n.id)?1:0.12,
      label:(con.has(n.id) || (n.freq||1)>=umbralEtq)?n.id:" "})));
    const mios=new Set(conexPor[p.node]||[]);
    datos.edges.update(vedges.map(e=>({id:e.id,
      color: mios.has(e.id)?{color:"#4ea1ff"}:{color:"rgba(126,146,176,0.04)"}})));
  });
  _net2d.on("blurNode", function(){
    datos.nodes.update(nodos.map(n=>({id:n.id,opacity:1,
      label:(n.freq||1)>=umbralEtq?n.id:" "})));
    datos.edges.update(vedges.map(e=>({id:e.id,
      color:{color:colorBase(e.id),highlight:"#4ea1ff",hover:"#4ea1ff"}})));
  });
  _net2d.on("click",p=>{ if(p.nodes.length && personas[p.nodes[0]]) verActor(p.nodes[0]); });
}
function dibujar3D(ego){
  if(!window.ForceGraph3D){ $("#redbox").innerHTML="<div class='mut'>Sin internet: no se cargó 3d-force-graph.</div>"; return; }
  const {nodos,aristas}=_datosRed(ego);
  // grado de cada nodo (nº de conexiones) → tamaño/relevancia visual
  const grado={}; aristas.forEach(e=>{grado[e.source]=(grado[e.source]||0)+1;grado[e.target]=(grado[e.target]||0)+1;});
  const pmax=aristas.reduce((m,e)=>Math.max(m,e.weight||1),1);
  const data={nodes:nodos.map(n=>({id:n.id,color:colorCat(n.categoria),
      val:Math.max(1,(grado[n.id]||0)),freq:n.freq||1,cat:n.categoria,deg:grado[n.id]||0})),
    links:aristas.map(e=>({source:e.source,target:e.target,w:e.weight||1}))};
  // umbral para mostrar etiqueta SIEMPRE solo en los nodos importantes (evita
  // el amontonamiento de texto); el resto muestra label al pasar el cursor.
  const degs=data.nodes.map(n=>n.deg).sort((a,b)=>b-a);
  const umbralEtq=degs.length>18?(degs[Math.min(17,degs.length-1)]||2):0;
  const cont=document.getElementById("redbox"); cont.innerHTML="";

  // sprite de texto para etiquetas legibles en 3D (usa three-spritetext si está)
  function makeLabel(n){
    if(!window.SpriteText) return null;
    const s=new SpriteText(n.id);
    s.color="#eef2f8"; s.textHeight=Math.max(4,Math.min(9,4+n.deg*0.5));
    s.backgroundColor="rgba(10,12,17,0.65)"; s.padding=1.5; s.borderRadius=2;
    s.position.y=-(6+Math.cbrt(n.val)*2);  // debajo del nodo
    return s;
  }

  // preserveDrawingBuffer permite capturar el canvas → botón 📷 PNG.
  _fg3d=ForceGraph3D({rendererConfig:{preserveDrawingBuffer:true,antialias:true}})(cont)
    .backgroundColor("#0a0c11").graphData(data)
    .nodeColor(n=>n.color)
    .nodeVal(n=>n.val)
    .nodeRelSize(5)                              // nodos más grandes y diferenciados
    .nodeOpacity(0.95)
    .nodeResolution(16)                          // esferas más suaves
    .nodeLabel(n=>"<b>"+n.id+"</b> · "+(n.cat||"")+" · "+n.deg+" conexiones")
    // Aristas: opacidad y grosor por peso; partículas viajando por las
    // relaciones más fuertes (la red se lee y además se ve VIVA).
    .linkColor(l=>"rgba(126,156,205,"+(0.12+0.45*(l.w/pmax)).toFixed(2)+")")
    .linkWidth(l=>Math.min(3,0.3+l.w*0.35))
    .linkOpacity(0.85)
    .linkDirectionalParticles(l=> l.w>=pmax*0.6 ? 2 : 0)
    .linkDirectionalParticleWidth(1.6)
    .linkDirectionalParticleSpeed(0.0045)
    .width(cont.clientWidth).height(cont.clientHeight)
    // ETIQUETAS 3D: sprite de texto bajo los nodos importantes (deg>=umbral).
    .nodeThreeObjectExtend(true)
    .nodeThreeObject(n=> (n.deg>=umbralEtq) ? makeLabel(n) : null);

  // SEPARAR la bola: más repulsión entre nodos y enlaces más largos.
  try{
    _fg3d.d3Force("charge").strength(-220).distanceMax(900);
    _fg3d.d3Force("link").distance(l=>40+(l.w?12/l.w:12)).strength(0.35);
    if(_fg3d.d3Force("center")) _fg3d.d3Force("center").strength(0.04);
  }catch(e){}

  _fg3d
    // ESTÁTICO: corre unos ticks, se DETIENE y se congela (no "zumba").
    .warmupTicks(80).cooldownTicks(140)
    .onEngineStop(()=>{ data.nodes.forEach(n=>{ n.fx=n.x; n.fy=n.y; n.fz=n.z; });
      try{_fg3d.zoomToFit(600,60);}catch(e){} })
    // ARRASTRAR Y FIJAR: al soltar un nodo queda clavado donde lo dejaste.
    .onNodeDragEnd(n=>{ n.fx=n.x; n.fy=n.y; n.fz=n.z; })
    .onNodeClick(n=>{ if(personas[n.id]) verActor(n.id);
      const dist=70; const r=Math.hypot(n.x,n.y,n.z)||1;
      _fg3d.cameraPosition({x:n.x*(1+dist/r),y:n.y*(1+dist/r),z:n.z*(1+dist/r)},n,1200);});
  // clic derecho libera un nodo fijado (vuelve a flotar)
  _fg3d.onNodeRightClick&&_fg3d.onNodeRightClick(n=>{ n.fx=null;n.fy=null;n.fz=null; });
}
function renderRed(){
  const ego=$("#red-ego").value||null;
  if(_modoRed==="3d") dibujar3D(ego); else dibujar2D(ego);
}
function dibujarRed(){ if(_redInit) return; _redInit=true; renderRed(); }
(function(){const c=$("#t-red");
  const g=D.grafo||{};
  if(!(g.nodes||[]).length){ c.innerHTML="<div class='card mut'>Red vacía: pocas notas comparten actores. Baja el umbral de red al analizar.</div>"; return; }
  const NOMBRES_CAT={personas:"Personas",organizaciones:"Organizaciones",lugares:"Lugares",
    fechas:"Fechas",obras_publicaciones:"Obras",eventos_historicos:"Eventos"};
  // categorías realmente presentes en el grafo, con conteo de nodos
  const nCat={}; (g.nodes||[]).forEach(n=>{const k=n.categoria||"otros"; nCat[k]=(nCat[k]||0)+1;});
  // barra de controles
  const ctr=el("div","controles");
  ctr.innerHTML=
    "<span class='seg'><button id='b2d' class='act'>2D</button><button id='b3d'>3D rotable</button></span>"+
    " <input id='red-buscar' list='red-actores' placeholder='🔍 Buscar actor…' style='min-width:180px'>"+
    "<datalist id='red-actores'>"+(g.nodes||[]).map(n=>"<option>"+n.id+"</option>").join("")+"</datalist>"+
    " Aislar: <select id='red-ego'><option value=''>(toda la red)</option>"+
      Object.keys(personas).sort().map(p=>"<option>"+p+"</option>").join("")+"</select>"+
    " Nodos: <select id='red-topn'><option>40</option><option selected>60</option>"+
      "<option>100</option><option>150</option><option value='9999'>todos</option></select>"+
    " <button id='b-png' class='btn-acc' title='Descargar la red como imagen PNG (figura para el paper)'>📷 PNG</button>"+
    " <button id='b-reset' class='btn-acc' title='Restablecer filtros'>↺</button>"+
    " <button id='b-mano' class='btn-acc' title='Controla la red con gestos de la mano (necesita cámara)'>✋ Mano</button>";
  c.appendChild(ctr);
  // leyenda de categorías: clic = ocultar/mostrar esa categoría en la red
  const ley=el("div","leyenda");
  ley.innerHTML="<span class='mut' style='font-size:12px'>Categorías:</span>"+
    Object.keys(nCat).map(k=>
      "<span class='lg-chip' data-cat='"+k+"'><span class='leg' style='background:"+colorCat(k)+"'></span>"+
      (NOMBRES_CAT[k]||k)+" <b>"+nCat[k]+"</b></span>").join("")+
    "<span class='mut' style='font-size:11px;margin-left:6px'>(clic para ocultar/mostrar)</span>";
  c.appendChild(ley);
  c.appendChild(el("div","mut","Pasa el cursor sobre un nodo para iluminar su vecindario · arrastra nodos · rueda = zoom · clic en nodo = ficha del actor. En 3D arrastra para ROTAR; las partículas recorren las relaciones más fuertes."));
  // Contenedor flex: visualización (izq) + panel de info técnica (der).
  const wrap=el("div","red-wrap");
  wrap.innerHTML="<div id='redbox' style='height:72vh'></div><div id='study-mount'></div>";
  c.appendChild(wrap);
  // Panel permanente de información técnica del estudio. Se calcula en el
  // frontend desde el grafo ya cargado; se actualiza solo si cambia el grafo.
  if(window.StudyInfo){
    StudyInfo.render({mount:$("#study-mount"),grafo:D.grafo||{},
      titulo:(D.titulo||"Estudio").replace(/^🦆\s*/,"").replace(/^¡?Quac!?\s*[—-]\s*/i,""),
      porNota:D.por_nota||{}});
  }
  // listeners
  $("#b2d").onclick=()=>{_modoRed="2d";$("#b2d").classList.add("act");$("#b3d").classList.remove("act");renderRed();};
  $("#b3d").onclick=()=>{_modoRed="3d";$("#b3d").classList.add("act");$("#b2d").classList.remove("act");renderRed();};
  $("#red-ego").onchange=renderRed; $("#red-topn").onchange=renderRed;
  $("#b-reset").onclick=()=>{$("#red-ego").value="";$("#red-buscar").value="";_catsOff.clear();
    ley.querySelectorAll(".lg-chip").forEach(x=>x.classList.remove("off"));renderRed();};
  ley.querySelectorAll(".lg-chip").forEach(ch=>{ch.onclick=()=>{
    const k=ch.dataset.cat;
    if(_catsOff.has(k)){_catsOff.delete(k);ch.classList.remove("off");}
    else{_catsOff.add(k);ch.classList.add("off");}
    renderRed();};});
  // buscador: centra la cámara en el actor elegido (2D y 3D)
  $("#red-buscar").onchange=()=>{const q=$("#red-buscar").value.trim(); if(!q)return;
    if(_modoRed==="2d"&&_net2d){ try{_net2d.selectNodes([q]);
      _net2d.focus(q,{scale:1.15,animation:{duration:700}});}catch(e){} }
    else if(_fg3d){ const n=(_fg3d.graphData().nodes||[]).find(x=>x.id===q);
      if(n&&n.x!=null){const d=90,r=Math.hypot(n.x,n.y,n.z)||1;
        _fg3d.cameraPosition({x:n.x*(1+d/r),y:n.y*(1+d/r),z:n.z*(1+d/r)},n,1000);}}};
  // exportar la red como imagen PNG con fondo (figura lista para el paper)
  $("#b-png").onclick=()=>{
    const cv=document.querySelector("#redbox canvas"); if(!cv) return;
    const out=document.createElement("canvas"); out.width=cv.width; out.height=cv.height;
    const cx=out.getContext("2d"); cx.fillStyle="#0a0c11"; cx.fillRect(0,0,out.width,out.height);
    cx.drawImage(cv,0,0);
    const a=document.createElement("a"); a.download="quac_red.png";
    a.href=out.toDataURL("image/png"); a.click();};

  // --- Control por gestos de mano (webcam) sobre el grafo 3D --------------
  // Indicador discreto en una esquina del contenedor de la red.
  const hcStatus=el("div"); hcStatus.id="hc-status";
  hcStatus.style.cssText="display:none;position:fixed;right:16px;bottom:16px;z-index:50;"+
    "background:#0c0e13ee;border:1px solid #5a3;border-radius:8px;padding:8px 12px;"+
    "font-size:13px;color:#cdd3dd;box-shadow:0 4px 18px #0008";
  document.body.appendChild(hcStatus);
  if(window.HandControls){
    const _hc=HandControls.attach({
      getGraph:()=>_fg3d, getNet2d:()=>_net2d, getModo:()=>_modoRed,
      toggleEl:$("#b-mano"), statusEl:hcStatus,
    });
    // Funciona en 2D (mano=desplazar, pellizco=zoom) y en 3D (rotar/zoom/
    // arrastrar/escalar). El dispatcher interno enruta según el modo activo.

    // --- Panel de ajustes de sensibilidad (sliders en vivo) --------------
    const panel=el("div"); panel.id="hc-ajustes";
    panel.style.cssText="display:none;position:fixed;right:16px;bottom:64px;z-index:50;"+
      "background:#1b1f27f2;border:1px solid #4ea1ff;border-radius:10px;padding:12px 14px;"+
      "width:240px;font-size:12px;color:#cdd3dd;box-shadow:0 6px 24px #000a";
    const _sl=(id,label,min,max,step,val)=>
      "<label style='display:block;margin:7px 0 2px'>"+label+
      " <span id='"+id+"-v' style='color:#4ea1ff'>"+val+"</span></label>"+
      "<input id='"+id+"' type='range' min='"+min+"' max='"+max+"' step='"+step+"' value='"+val+"' style='width:100%'>";
    panel.innerHTML="<b style='color:#fff'>Sensibilidad de gestos</b>"+
      _sl("hc-rot","Rotación (mano abierta)",0.5,8,0.1,_hc.cfg.rotacion)+
      _sl("hc-zoom","Zoom (pellizco)",0.1,1.5,0.05,_hc.cfg.zoom)+
      _sl("hc-suav","Suavizado (anti-temblor)",0.1,0.7,0.05,_hc.cfg.suavizado)+
      _sl("hc-pin","Umbral de pellizco",0.25,0.7,0.05,_hc.cfg.pellizco)+
      _sl("hc-esc","Escala (dos manos)",0.5,3.5,0.1,_hc.cfg.escala)+
      "<div class='mut' style='margin-top:8px;font-size:11px'>Mueve los sliders y prueba con la mano. Los cambios son inmediatos.</div>";
    document.body.appendChild(panel);
    const _bind=(id,key,suav)=>{const i=$("#"+id),o=$("#"+id+"-v");
      i.oninput=()=>{const v=parseFloat(i.value);o.textContent=v;
        if(suav)_hc.setSuavizado(v); else _hc.cfg[key]=v;};};
    _bind("hc-rot","rotacion",false); _bind("hc-zoom","zoom",false);
    _bind("hc-suav",null,true); _bind("hc-pin","pellizco",false);
    _bind("hc-esc","escala",false);
    // Botón ⚙ para mostrar/ocultar el panel, junto al de Mano.
    const bAj=el("button","chip","⚙ Ajustes"); bAj.id="b-mano-ajustes";
    bAj.title="Ajustar la sensibilidad de los gestos";
    $("#b-mano").insertAdjacentElement("afterend",bAj);
    bAj.onclick=()=>{panel.style.display=(panel.style.display==="none"?"block":"none");};
  } else {
    $("#b-mano").disabled=true; $("#b-mano").title="Control por mano no disponible (módulo no cargado).";
  }
})();

// ---- ACTORES (clic → profundizar)
function verActor(nombre){
  document.querySelectorAll("nav button").forEach((x,i)=>x.classList.toggle("act",i==1));
  document.querySelectorAll(".tab").forEach(x=>x.classList.remove("act")); $("#t-actores").classList.add("act");
  const c=$("#t-actores"); c.innerHTML="";
  const arts=personas[nombre]||[]; c.appendChild(el("h2",null,nombre));
  c.appendChild(el("div","mut",arts.length+" notas lo mencionan"));
  // emoción y framing de sus notas + colocaciones
  const notas=porNota.filter(([u,r])=>arts.includes(u));
  const emo={}; const fr={};
  notas.forEach(([u,r])=>{const e=(r.emociones||{}).emocion_dominante; if(e)emo[e]=(emo[e]||0)+1;
    const f=(r.frame||{}).etiqueta; if(f)fr[f]=(fr[f]||0)+1;});
  const g=el("div","grid");
  const ce=el("div","card"); ce.appendChild(el("h3",null,"Emoción dominante en sus notas"));
  Object.entries(emo).sort((a,b)=>b[1]-a[1]).forEach(([k,n])=>ce.appendChild(el("div",null,"<span class='chip'>"+k+"</span> "+n))); g.appendChild(ce);
  const cfr=el("div","card"); cfr.appendChild(el("h3",null,"Encuadre de sus notas"));
  Object.entries(fr).sort((a,b)=>b[1]-a[1]).forEach(([k,n])=>cfr.appendChild(el("div",null,"<span class='chip'>"+k+"</span> "+n))); g.appendChild(cfr);
  // KWIC
  const ck=el("div","card"); ck.style.gridColumn="1/-1"; ck.appendChild(el("h3",null,"Concordancias (cómo aparece en el texto)"));
  (D.kwic[nombre]||[]).slice(0,25).forEach(k=>{const d=el("div","kwic"); d.innerHTML="<b class='mut'>["+k.medio+"]</b> …"+k.fragmento+"…"; ck.appendChild(d);});
  if(!(D.kwic[nombre]||[]).length) ck.appendChild(el("div","mut","(sin concordancias precalculadas para este actor)"));
  g.appendChild(ck); c.appendChild(g);
  window.scrollTo(0,0);
}
(function(){const c=$("#t-actores"); if(!c.innerHTML){c.appendChild(el("h2",null,"Actores"));
  c.appendChild(el("div","mut","Haz clic en un actor del Resumen, o elige uno:"));
  const wrap=el("div"); ranking(personas).slice(0,30).forEach(([k,n])=>{const ch=el("span","chip",k+" ("+n+")"); ch.onclick=()=>verActor(k); wrap.appendChild(ch);}); c.appendChild(wrap);} })();

// ---- RELACIONES entre dos términos/entidades
function verRelacion(pre){
  const c=$("#t-relaciones"); c.innerHTML=""; c.appendChild(el("h2",null,"Relación entre términos"));
  // universo de términos: actores + organizaciones, SIN duplicados, ordenado.
  const opts=Array.from(new Set(Object.keys(personas).concat(Object.keys(orgs)))).sort();
  c.appendChild(el("div","mut","Escribe en cada caja para BUSCAR un actor o término; "
    +"se desplegará una lista para elegir. Luego pulsa «Ver relación» para hallar "
    +"las notas donde ambos aparecen juntos."));

  // ---- buscador con autocompletado propio (dropdown filtrado, clic para elegir)
  function buscador(valorInicial, placeholder){
    const box=el("div"); box.style.cssText="position:relative;display:inline-block;vertical-align:top";
    const inp=el("input"); inp.placeholder=placeholder; inp.value=valorInicial||"";
    inp.autocomplete="off";
    inp.style.cssText="min-width:240px;padding:7px 10px;background:#0c0e13;color:#e6e6e6;"
      +"border:1px solid #2b313c;border-radius:8px";
    const menu=el("div"); menu.style.cssText="display:none;position:absolute;left:0;top:38px;"
      +"z-index:60;width:300px;max-height:260px;overflow:auto;background:#1b1f27;"
      +"border:1px solid #4ea1ff;border-radius:8px;box-shadow:0 8px 28px #000a";
    box.appendChild(inp); box.appendChild(menu);
    function pintar(filtro){
      const f=(filtro||"").toLowerCase().trim();
      const lista=(f? opts.filter(o=>o.toLowerCase().includes(f)) : opts).slice(0,40);
      menu.innerHTML="";
      if(!lista.length){ menu.style.display="none"; return; }
      lista.forEach(o=>{
        const it=el("div"); it.textContent=o;
        // nº de notas del término, si es actor/org
        const n=(personas[o]||orgs[o]||[]).length;
        if(n){ const b=el("span","mut"," · "+n); it.appendChild(b); }
        it.style.cssText="padding:7px 11px;cursor:pointer;border-bottom:1px solid #2b313c";
        it.onmouseenter=()=>it.style.background="#263042";
        it.onmouseleave=()=>it.style.background="";
        it.onmousedown=(e)=>{ e.preventDefault(); inp.value=o; menu.style.display="none"; };
        menu.appendChild(it);
      });
      menu.style.display="block";
    }
    inp.addEventListener("input",()=>pintar(inp.value));
    inp.addEventListener("focus",()=>pintar(inp.value));
    inp.addEventListener("blur",()=>setTimeout(()=>menu.style.display="none",150));
    return {box, get value(){return inp.value;}, set value(v){inp.value=v;}};
  }

  const row=el("div"); row.style.cssText="margin:12px 0;display:flex;align-items:center;gap:8px;flex-wrap:wrap";
  const b1=buscador(pre||"", "buscar actor / término A…");
  const b2=buscador("", "buscar actor / término B…");
  const btn=el("button","chip","Ver relación"); btn.style.padding="8px 14px";
  row.appendChild(b1.box); row.appendChild(el("span",null,"+")); row.appendChild(b2.box); row.appendChild(btn);
  c.appendChild(row); const out=el("div"); c.appendChild(out);

  btn.onclick=()=>{out.innerHTML="";
    const a=b1.value.trim().toLowerCase(), b=b2.value.trim().toLowerCase();
    if(!a||!b){ out.appendChild(el("div","mut","Escribe y elige los DOS términos a relacionar.")); return; }
    let frags=[];
    Object.entries(D.kwic).forEach(([act,arr])=>{ if(act.toLowerCase().includes(a)){ arr.forEach(k=>{ if(k.fragmento.toLowerCase().includes(b)) frags.push(k);});}});
    if(!frags.length){
      Object.entries(D.kwic).forEach(([act,arr])=>{ arr.forEach(k=>{const f=k.fragmento.toLowerCase(); if(f.includes(a)&&f.includes(b)) frags.push(k);});});
    }
    const tabla=el("table"); tabla.innerHTML="<tr><th>Medio</th><th>Fragmento donde coinciden</th></tr>";
    let n=0;
    frags.slice(0,40).forEach(k=>{let frag=k.fragmento.replace(new RegExp("("+a+"|"+b+")","gi"),"<mark>$1</mark>");
      const tr=el("tr"); tr.innerHTML="<td class='mut'>"+k.medio+"</td><td>…"+frag+"…</td>"; tabla.appendChild(tr); n++;});
    out.appendChild(el("div","mut",n+" coincidencias de «"+b1.value+"» con «"+b2.value+"»"));
    out.appendChild(tabla);
  };
  if(pre) btn.onclick();
  document.querySelectorAll("nav button").forEach((x,i)=>x.classList.toggle("act",i==2));
  document.querySelectorAll(".tab").forEach(x=>x.classList.remove("act")); $("#t-relaciones").classList.add("act"); window.scrollTo(0,0);
}
// Al abrir la pestaña Relaciones, construir los DOS SELECTORES de inmediato
// (antes solo mostraba un texto y los inputs aparecían al venir de un término).
function dibujarRelaciones(){ const c=$("#t-relaciones"); if(c.dataset.init) return; c.dataset.init="1"; verRelacion(); }

// ---- MEDIOS: tendencia política + matriz de cobertura
(function(){const c=$("#t-medios"); c.appendChild(el("h2",null,"Tendencia política de los medios"));
  // --- Filiación/tendencia: tono de cada medio hacia cada candidato ---
  const tm=D.tendencia_medios||{}; const cands=tm.candidatos||[]; const meds=tm.medios||{};
  function celTono(v){ if(v==null) return "<td class='mut'>·</td>";
    const col=v>0.1?"#34d399":(v<-0.1?"#f87171":"#9aa3b2");
    return "<td style='color:"+col+";font-weight:600'>"+(v>0?"+":"")+v+"</td>"; }
  if(Object.keys(meds).length){
    const cd=el("div","card");
    cd.appendChild(el("h3",null,"¿Con qué tono trata cada medio a cada candidato? (filiación)"));
    cd.appendChild(el("div","mut","Tono medio hacia el candidato (−1 muy negativo … +1 muy positivo). 'Sesgo' = diferencia de trato; 'favorece' = a quién trata mejor."));
    const t=el("table"); let h="<tr><th>Medio</th>"; cands.forEach(c=>h+="<th>"+c.split(' ').slice(0,2).join(' ')+"</th>"); h+="<th>Sesgo</th><th>Favorece</th></tr>"; t.innerHTML=h;
    Object.entries(meds).forEach(([m,d])=>{
      let tr="<td>"+m+"</td>"; cands.forEach(c=>tr+=celTono(d.tono[c]));
      const sc=d.sesgo||0; const scol=Math.abs(sc)<0.1?"#9aa3b2":(sc>0?"#4ea1ff":"#a78bfa");
      tr+="<td style='color:"+scol+"'>"+(sc>0?"+":"")+sc+"</td><td class='mut'>"+(d.favorece||"—")+"</td>";
      const r=el("tr"); r.innerHTML=tr; t.appendChild(r);});
    cd.appendChild(t); c.appendChild(cd);
  } else { c.appendChild(el("div","mut","Tendencia no disponible (define candidatos en el perfil).")); }

  c.appendChild(el("h2",null,"Cobertura por medio (sesgo de selección)"));
  const comp=D.comparacion||{}; const A=comp.actores||[]; const M=comp.medios||[]; const emo=comp.emocion_por_medio||{};
  if(!M.length){c.appendChild(el("div","mut","Sin datos.")); return;}
  const t=el("table"); let head="<tr><th>Medio</th><th>Emoción</th>"; A.forEach(a=>head+="<th>"+a+"</th>"); head+="</tr>"; t.innerHTML=head;
  M.forEach(m=>{const row=comp.matriz[m]||{}; let tr="<td>"+m+"</td><td class='mut'>"+(emo[m]||"—")+"</td>";
    A.forEach(a=>{const v=row[a]||0; tr+="<td>"+(v?("<span class='chip'>"+v+"</span>"):"·")+"</td>";});
    const r=el("tr"); r.innerHTML=tr; t.appendChild(r);}); c.appendChild(t);
})();

// ---- NOTAS
(function(){const c=$("#t-notas"); c.appendChild(el("h2",null,"Notas del corpus"));
  const t=el("table"); t.innerHTML="<tr><th>Fecha</th><th>Medio</th><th>Titular</th><th>Emoción</th><th>Encuadre</th></tr>";
  porNota.forEach(([u,r])=>{const tr=el("tr");
    tr.innerHTML="<td class='mut'>"+(r.fecha||"?")+"</td><td>"+(r.medio||"")+"</td>"+
      "<td><a href='"+u+"' target='_blank' style='color:var(--acc)'>"+(r.titular||u).slice(0,90)+"</a></td>"+
      "<td>"+((r.emociones||{}).emocion_dominante||"—")+"</td><td class='mut'>"+((r.frame||{}).etiqueta||"—")+"</td>";
    t.appendChild(tr);}); c.appendChild(t);
})();

// ====== LÍNEAS DEL TIEMPO ======
let _tiempoInit=false; let _charts={};
const COLORES=["#4ea1ff","#f87171","#34d399","#f59e0b","#a78bfa","#22d3ee"];
function _mm(serie,v){ // media móvil centrada ignorando null
  v=v||3; const r=Math.floor(v/2), out=[];
  for(let i=0;i<serie.length;i++){let s=0,n=0;
    for(let j=Math.max(0,i-r);j<Math.min(serie.length,i+r+1);j++){if(serie[j]!=null){s+=serie[j];n++;}}
    out.push(n?Math.round(1000*s/n)/1000:null);}
  return out;
}
// Combina las series diarias de un GRUPO de medios (promedio de tono ponderado
// por volumen; suma de volumen). Si no hay selección, usa la serie global.
function _combinar(medios){
  const LT=D.lineas_tiempo||{}; const g=LT.global||{};
  if(!medios||!medios.length) return g;
  const dias=g.dias||[]; const cands=g.candidatos||[];
  const pm=LT.por_medio||{};
  const vol=dias.map(()=>0);
  const tono={}; cands.forEach(c=>tono[c]=dias.map(()=>({s:0,n:0})));
  const volC={}; cands.forEach(c=>volC[c]=dias.map(()=>0));
  medios.forEach(m=>{const s=pm[m]; if(!s)return;
    (s.volumen||[]).forEach((v,i)=>vol[i]+=v||0);
    cands.forEach(c=>{
      (s.volumen_por_candidato?.[c]||[]).forEach((v,i)=>volC[c][i]+=v||0);
      (s.tono_por_candidato?.[c]||[]).forEach((t,i)=>{
        const w=(s.volumen_por_candidato?.[c]||[])[i]||0;
        if(t!=null && w){tono[c][i].s+=t*w; tono[c][i].n+=w;}});
    });
  });
  const tono_pc={}; cands.forEach(c=>tono_pc[c]=tono[c].map(o=>o.n?Math.round(1000*o.s/o.n)/1000:null));
  let sesgo=[];
  if(cands.length>=2){const a=tono_pc[cands[0]],b=tono_pc[cands[1]];
    sesgo=a.map((x,i)=>(x!=null&&b[i]!=null)?Math.round(1000*(x-b[i]))/1000:null);}
  return {dias,candidatos:cands,volumen:vol,volumen_por_candidato:volC,
          tono_por_candidato:tono_pc,sesgo,frames:g.frames};
}
function _linea(canvasId,labels,datasets,opts){
  if(_charts[canvasId]) _charts[canvasId].destroy();
  _charts[canvasId]=new Chart(document.getElementById(canvasId),{
    type:"line", data:{labels,datasets},
    options:Object.assign({responsive:true,interaction:{mode:"index",intersect:false},
      plugins:{legend:{labels:{color:"#cdd3dd"}}},
      scales:{x:{ticks:{color:"#9aa3b2"}},y:{ticks:{color:"#9aa3b2"}}}},opts||{})});
}
function pintarTiempo(){
  const LT=D.lineas_tiempo||{}; const sel=Array.from(document.querySelectorAll(".selMedio:checked")).map(x=>x.value);
  const g=_combinar(sel); const dias=g.dias||[]; const cands=g.candidatos||[];
  const amb=sel.length?("Grupo: "+sel.join(", ")):"Todo el corpus";
  document.getElementById("tiempo-amb").textContent=amb;
  // 1) SESGO medio→candidato (>0 favorece al primero)
  if(cands.length>=2){
    _linea("ch-sesgo",dias,[
      {label:"sesgo diario",data:g.sesgo,borderColor:"#9aa3b2",borderWidth:1,pointRadius:2,tension:.2},
      {label:"tendencia (media móvil 3d)",data:_mm(g.sesgo,3),borderColor:"#4ea1ff",borderWidth:3,pointRadius:0,tension:.3},
    ],{plugins:{legend:{labels:{color:"#cdd3dd"}},title:{display:true,color:"#e6e6e6",
       text:"Sesgo hacia "+cands[0]+" (+) vs "+cands[1]+" (−)"}}});
  }
  // 2) VOLUMEN total + por candidato, con picos marcados
  const dsVol=[{label:"volumen total",data:g.volumen,borderColor:"#34d399",backgroundColor:"rgba(52,211,153,.15)",fill:true,tension:.2}];
  cands.forEach((c,i)=>dsVol.push({label:c,data:g.volumen_por_candidato[c],borderColor:COLORES[i+1],borderWidth:2,pointRadius:1,tension:.2}));
  _linea("ch-vol",dias,dsVol,{plugins:{legend:{labels:{color:"#cdd3dd"}},title:{display:true,color:"#e6e6e6",text:"Volumen de cobertura por día"}}});
  const picos=(LT.picos_volumen||[]).map(p=>p.dia);
  document.getElementById("tiempo-picos").innerHTML = picos.length
    ? "📌 Días pico de cobertura: "+picos.map(d=>"<span class='chip'>"+d+"</span>").join(" ") : "";
  // 3) TONO por candidato (media móvil)
  _linea("ch-tono",dias,cands.map((c,i)=>({label:c,data:_mm(g.tono_por_candidato[c],3),
    borderColor:COLORES[i],borderWidth:2,pointRadius:1,tension:.3})),
    {plugins:{legend:{labels:{color:"#cdd3dd"}},title:{display:true,color:"#e6e6e6",text:"Tono medio hacia cada candidato (media móvil 3 días)"}}});
  // 4) ENCUADRE (% por día) — usa la serie global (frames no se filtran por medio aquí)
  const fr=g.frames||{}; const frKeys=Object.keys(fr).slice(0,6);
  if(frKeys.length) _linea("ch-frame",dias,frKeys.map((k,i)=>({label:k,data:fr[k],borderColor:COLORES[i%COLORES.length],borderWidth:2,pointRadius:0,tension:.3})),
    {plugins:{legend:{labels:{color:"#cdd3dd"}},title:{display:true,color:"#e6e6e6",text:"Encuadre dominante por día (%)"}}});
}
function dibujarTiempo(){
  if(_tiempoInit){pintarTiempo();return;} _tiempoInit=true;
  const c=$("#t-tiempo"); const LT=D.lineas_tiempo||{};
  if(!LT.global||!(LT.global.dias||[]).length){c.innerHTML="<div class='card mut'>Sin datos temporales (las notas no tienen fecha de publicación).</div>";return;}
  const medios=Object.keys(LT.por_medio||{});
  let chips=medios.map(m=>"<label class='chip'><input type='checkbox' class='selMedio' value='"+m+"' style='margin-right:4px'>"+m+"</label>").join(" ");
  c.innerHTML=
    "<div class='card'><h3>📈 Líneas del tiempo — patrones, picos y cambios de tendencia</h3>"+
    "<div class='mut'>Elige uno o varios medios para ver si <b>cambian su tendencia</b> a favorecer a un candidato. Sin selección = todo el corpus. Ámbito actual: <b id='tiempo-amb'>Todo el corpus</b></div>"+
    "<div class='controles'>"+chips+"</div>"+
    "<div style='margin:6px 0' id='tiempo-picos'></div></div>"+
    "<div class='card'><canvas id='ch-sesgo' class='chart'></canvas></div>"+
    "<div class='card'><canvas id='ch-vol' class='chart'></canvas></div>"+
    "<div class='card'><canvas id='ch-tono' class='chart'></canvas></div>"+
    "<div class='card'><canvas id='ch-frame' class='chart'></canvas></div>";
  c.querySelectorAll(".selMedio").forEach(x=>x.onchange=pintarTiempo);
  pintarTiempo();
}
</script></body></html>"""

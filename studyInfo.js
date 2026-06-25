/* studyInfo.js — Panel permanente de información técnica del estudio.
 *
 * Calcula, EN EL FRONTEND y a partir del objeto de grafo ya cargado en memoria,
 * las métricas estructurales de la red (nodos, aristas, densidad, grado,
 * componentes…) y las muestra en un panel lateral fijo, legible sin interacción.
 *
 * No hace peticiones a servidor ni añade dependencias. Las métricas costosas
 * (clustering, diámetro) se calculan de forma diferida (setTimeout) para no
 * bloquear el render de la visualización 3D/2D.
 *
 * API:  StudyInfo.render(opts)
 *   opts.mount   -> elemento DOM donde montar el panel (obligatorio)
 *   opts.grafo   -> { nodes:[{id,...}], edges:[{source,target,weight?}], directed? }
 *   opts.titulo  -> nombre del estudio (título del panel)
 *   opts.porNota -> objeto/array de notas para corpus (nº docs + rango de fechas)
 *   opts.fuente  -> (opcional) nombre del corpus/fuente si está en metadatos
 *
 * Reentrante: llamarlo de nuevo con otro grafo refresca el panel (soporta
 * "cargar un corpus diferente").
 */
(function (global) {
  "use strict";

  // ---- utilidades de cálculo (grafo no dirigido por defecto) ----------------

  function calcularMetricas(grafo) {
    const nodes = (grafo && grafo.nodes) || [];
    const edges = (grafo && grafo.edges) || (grafo && grafo.links) || [];
    const dirigido = !!(grafo && grafo.directed);
    const N = nodes.length;
    const E = edges.length;

    // ¿hay pesos? (alguna arista con weight numérico != 1 o presente)
    const conPesos = edges.some(e => e.weight != null && e.weight !== 1) ||
                     edges.every(e => e.weight != null) && E > 0;

    // grado por nodo (no dirigido: cada arista suma a sus dos extremos)
    const idSet = new Set(nodes.map(n => n.id));
    const grado = {};
    nodes.forEach(n => { grado[n.id] = 0; });
    const ady = {};            // lista de adyacencia para componentes/clustering
    nodes.forEach(n => { ady[n.id] = new Set(); });
    edges.forEach(e => {
      // ignora aristas hacia nodos inexistentes (defensivo)
      if (!idSet.has(e.source) || !idSet.has(e.target)) return;
      if (e.source === e.target) return;        // ignora bucles para el grado
      grado[e.source] = (grado[e.source] || 0) + 1;
      grado[e.target] = (grado[e.target] || 0) + 1;
      ady[e.source].add(e.target);
      ady[e.target].add(e.source);
    });

    const grados = nodes.map(n => grado[n.id] || 0);
    const sumGrado = grados.reduce((a, b) => a + b, 0);
    const gradoProm = N ? sumGrado / N : 0;

    // grado máximo + nodo que lo tiene
    let nodoMax = null, gMax = -1;
    nodes.forEach(n => { const g = grado[n.id] || 0; if (g > gMax) { gMax = g; nodoMax = n.id; } });

    // grado mínimo excluyendo aislados (grado 0)
    const noAislados = grados.filter(g => g > 0);
    const gMin = noAislados.length ? Math.min.apply(null, noAislados) : 0;
    const nAislados = grados.filter(g => g === 0).length;

    // densidad no dirigida: 2E / (N(N-1));  dirigida: E / (N(N-1))
    let densidad = 0;
    if (N > 1) {
      densidad = dirigido ? E / (N * (N - 1)) : (2 * E) / (N * (N - 1));
    }

    // ¿bipartito? detección por coloreado BFS (2 colores). Solo si no dirigido.
    const bipartito = !dirigido ? esBipartito(nodes, ady) : false;

    // componentes conexos (BFS sobre adyacencia no dirigida)
    const comp = componentes(nodes, ady);

    // top 5 por grado
    const top5 = nodes
      .map(n => [n.id, grado[n.id] || 0])
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5);

    return {
      N, E, densidad, dirigido, conPesos,
      tipoGrafo: dirigido ? "dirigido" : (bipartito ? "no dirigido (bipartito)" : "no dirigido"),
      gradoProm, gMax, nodoMax, gMin, nAislados,
      nComponentes: comp.numero,
      tamMayorComp: comp.tamMayor,
      conexo: comp.numero <= 1 && nAislados === 0,
      top5, ady, idList: nodes.map(n => n.id),
    };
  }

  function esBipartito(nodes, ady) {
    const color = {};
    for (const start of nodes.map(n => n.id)) {
      if (color[start] !== undefined) continue;
      color[start] = 0;
      const cola = [start];
      while (cola.length) {
        const u = cola.shift();
        for (const v of ady[u]) {
          if (color[v] === undefined) { color[v] = 1 - color[u]; cola.push(v); }
          else if (color[v] === color[u]) return false;
        }
      }
    }
    return true;
  }

  function componentes(nodes, ady) {
    const vistos = new Set();
    let numero = 0, tamMayor = 0;
    for (const start of nodes.map(n => n.id)) {
      if (vistos.has(start)) continue;
      numero++;
      let tam = 0;
      const cola = [start]; vistos.add(start);
      while (cola.length) {
        const u = cola.shift(); tam++;
        for (const v of ady[u]) if (!vistos.has(v)) { vistos.add(v); cola.push(v); }
      }
      if (tam > tamMayor) tamMayor = tam;
    }
    return { numero, tamMayor };
  }

  // ---- métricas costosas (diferidas) ----------------------------------------

  // Coeficiente de clustering promedio (Watts-Strogatz, no dirigido, sin peso).
  function clusteringPromedio(idList, ady) {
    let suma = 0, contados = 0;
    for (const u of idList) {
      const vecinos = Array.from(ady[u]);
      const k = vecinos.length;
      if (k < 2) { contados++; continue; }   // C(u)=0 por convención
      let enlaces = 0;
      for (let i = 0; i < k; i++)
        for (let j = i + 1; j < k; j++)
          if (ady[vecinos[i]].has(vecinos[j])) enlaces++;
      suma += (2 * enlaces) / (k * (k - 1));
      contados++;
    }
    return contados ? suma / contados : 0;
  }

  // Diámetro: BFS desde cada nodo (no ponderado). Solo para grafos pequeños.
  function diametro(idList, ady) {
    let diam = 0;
    for (const s of idList) {
      const dist = { [s]: 0 };
      const cola = [s];
      while (cola.length) {
        const u = cola.shift();
        for (const v of ady[u]) if (dist[v] === undefined) {
          dist[v] = dist[u] + 1; cola.push(v);
          if (dist[v] > diam) diam = dist[v];
        }
      }
    }
    return diam;
  }

  // ---- corpus: nº de documentos + rango de fechas ---------------------------

  function infoCorpus(porNota) {
    if (!porNota) return { nDocs: 0, fechaMin: null, fechaMax: null };
    const entradas = Array.isArray(porNota) ? porNota.map(x => x[1] || x)
                                            : Object.values(porNota);
    const nDocs = entradas.length;
    let min = null, max = null;
    entradas.forEach(n => {
      const f = (n && n.fecha) ? String(n.fecha).slice(0, 10) : null;
      if (!f || !/^\d{4}-\d{2}-\d{2}$/.test(f)) return;
      // descarta fechas-basura evidentes (años fuera de rango razonable)
      const a = parseInt(f.slice(0, 4), 10);
      if (a < 2000 || a > 2100) return;
      if (min === null || f < min) min = f;
      if (max === null || f > max) max = f;
    });
    return { nDocs, fechaMin: min, fechaMax: max };
  }

  // ---- render ---------------------------------------------------------------

  const fmt = (x, d) => (typeof x === "number" ? x.toFixed(d == null ? 2 : d) : x);

  function render(opts) {
    const mount = opts.mount;
    if (!mount) return null;
    const m = calcularMetricas(opts.grafo || {});
    const c = infoCorpus(opts.porNota);
    const titulo = opts.titulo || "Estudio";
    const fuente = opts.fuente || null;

    // contenedor del panel (reutiliza si ya existe)
    let panel = mount.querySelector(".study-panel");
    if (!panel) {
      panel = document.createElement("div");
      panel.className = "study-panel";
      mount.appendChild(panel);
    }

    const rango = (c.fechaMin && c.fechaMax)
      ? (c.fechaMin === c.fechaMax ? c.fechaMin : c.fechaMin + " → " + c.fechaMax)
      : "—";

    const filas = [
      ["sec", "Corpus / dataset"],
      ["Fuente", fuente || titulo],
      ["Rango de fechas", rango],
      ["Documentos analizados", c.nDocs.toLocaleString("es")],
      ["sec", "Grafo"],
      ["Nodos", m.N.toLocaleString("es")],
      ["Aristas", m.E.toLocaleString("es")],
      ["Densidad", fmt(m.densidad, 4)],
      ["Tipo", m.tipoGrafo],
      ["Pesos en aristas", m.conPesos ? "Sí" : "No"],
      ["sec", "Grado"],
      ["Grado promedio", fmt(m.gradoProm, 2)],
      ["Grado máximo", m.gMax + (m.nodoMax ? "  (" + m.nodoMax + ")" : "")],
      ["Grado mínimo (no aislados)", m.gMin],
      ["Nodos aislados", m.nAislados],
      ["sec", "Componentes"],
      ["Componentes conexos", m.nComponentes],
      ["Mayor componente (nodos)", m.tamMayorComp],
      ["¿Conexo?", m.conexo ? "Sí" : "No"],
      ["sec", "Avanzadas"],
      ["Clustering promedio", "<span id='si-clust' class='mut'>calculando…</span>"],
      ["Diámetro", "<span id='si-diam' class='mut'>" +
        (m.N > 5000 ? "omitido (N&gt;5000)" : "calculando…") + "</span>"],
    ];

    let rows = "";
    filas.forEach(([k, v]) => {
      if (k === "sec") { rows += "<tr class='si-sec'><td colspan='2'>" + v + "</td></tr>"; }
      else { rows += "<tr><td class='si-k'>" + k + "</td><td class='si-v'>" + v + "</td></tr>"; }
    });

    // top 5 por grado
    let top = "<table class='si-top'><tr><th>Nodo</th><th>Grado</th></tr>";
    m.top5.forEach(([id, g]) => { top += "<tr><td>" + id + "</td><td>" + g + "</td></tr>"; });
    top += "</table>";

    panel.innerHTML =
      "<div class='si-head'>" +
        "<span class='si-titulo' title='" + titulo + "'>📊 " + titulo + "</span>" +
        "<button class='si-copy' type='button'>Copiar métricas</button>" +
      "</div>" +
      "<table class='si-tbl'>" + rows + "</table>" +
      "<div class='si-sec si-toplabel'>Top 5 por grado</div>" + top;

    // botón copiar -> texto plano
    panel.querySelector(".si-copy").onclick = () => {
      const txt = textoPlano(titulo, fuente, rango, c, m, _clustVal, _diamVal);
      copiar(txt, panel.querySelector(".si-copy"));
    };

    // ---- métricas costosas, diferidas (no bloquean el render) ---------------
    let _clustVal = null, _diamVal = null;
    setTimeout(() => {
      try {
        _clustVal = clusteringPromedio(m.idList, m.ady);
        const elc = panel.querySelector("#si-clust");
        if (elc) { elc.textContent = fmt(_clustVal, 3); elc.className = ""; }
      } catch (e) { /* no romper el panel si falla */ }
    }, 30);

    if (m.N <= 5000) {
      setTimeout(() => {
        try {
          _diamVal = diametro(m.idList, m.ady);
          const eld = panel.querySelector("#si-diam");
          if (eld) { eld.textContent = String(_diamVal); eld.className = ""; }
        } catch (e) { /* idem */ }
      }, 60);
    }

    return panel;
  }

  function textoPlano(titulo, fuente, rango, c, m, clust, diam) {
    const L = [];
    L.push("== Información técnica del estudio ==");
    L.push("Estudio: " + titulo);
    L.push("");
    L.push("[Corpus]");
    L.push("Fuente: " + (fuente || titulo));
    L.push("Rango de fechas: " + rango);
    L.push("Documentos analizados: " + c.nDocs);
    L.push("");
    L.push("[Grafo]");
    L.push("Nodos: " + m.N);
    L.push("Aristas: " + m.E);
    L.push("Densidad: " + m.densidad.toFixed(4));
    L.push("Tipo: " + m.tipoGrafo);
    L.push("Pesos en aristas: " + (m.conPesos ? "Sí" : "No"));
    L.push("");
    L.push("[Grado]");
    L.push("Grado promedio: " + m.gradoProm.toFixed(2));
    L.push("Grado máximo: " + m.gMax + (m.nodoMax ? " (" + m.nodoMax + ")" : ""));
    L.push("Grado mínimo (no aislados): " + m.gMin);
    L.push("Nodos aislados: " + m.nAislados);
    L.push("");
    L.push("[Componentes]");
    L.push("Componentes conexos: " + m.nComponentes);
    L.push("Mayor componente (nodos): " + m.tamMayorComp);
    L.push("Conexo: " + (m.conexo ? "Sí" : "No"));
    L.push("");
    L.push("[Avanzadas]");
    L.push("Clustering promedio: " + (clust != null ? clust.toFixed(3) : "n/d"));
    L.push("Diámetro: " + (diam != null ? diam : (m.N > 5000 ? "omitido" : "n/d")));
    L.push("");
    L.push("[Top 5 por grado]");
    m.top5.forEach(([id, g]) => L.push("  " + id + " — " + g));
    return L.join("\n");
  }

  function copiar(txt, btn) {
    const ok = () => { const t = btn.textContent; btn.textContent = "✓ Copiado"; setTimeout(() => { btn.textContent = t; }, 1500); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(txt).then(ok, () => fallback(txt, ok));
    } else { fallback(txt, ok); }
  }
  function fallback(txt, ok) {
    const ta = document.createElement("textarea");
    ta.value = txt; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); ok(); } catch (e) {}
    document.body.removeChild(ta);
  }

  global.StudyInfo = { render: render, _calcular: calcularMetricas };
})(window);

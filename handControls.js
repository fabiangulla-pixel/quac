/* ===========================================================================
 * handControls.js — Control por gestos de mano (webcam) para el grafo 3D de ¡Quac!
 * ---------------------------------------------------------------------------
 * Se engancha al grafo de fuerza 3D ya existente (librería 3d-force-graph, que
 * envuelve Three.js internamente). NO crea la escena ni toca la generación/
 * coloreo de nodos: solo traduce landmarks de la mano en transformaciones de la
 * cámara/escena Three.js que expone 3d-force-graph.
 *
 * API mínima de 3d-force-graph usada:
 *   fg.scene()    -> THREE.Scene      (para escalar el conjunto)
 *   fg.camera()   -> THREE.PerspectiveCamera
 *   fg.controls() -> OrbitControls internos (se habilitan/deshabilitan)
 *
 * Gestos:
 *   - Mano abierta moviéndose  -> rotar (orbitar cámara por azimut/elevación)
 *   - Pellizco pulgar-índice   -> zoom (acerca/aleja la cámara)
 *   - Puño cerrado             -> agarrar y desplazar (pan) la vista
 *   - Dos manos                -> distancia entre muñecas escala la escena
 *
 * Todo client-side. MediaPipe @mediapipe/tasks-vision por CDN. getUserMedia
 * exige HTTPS o localhost; si falla, se hace fallback a OrbitControls (mouse).
 *
 * Uso:
 *   const hc = HandControls.attach({
 *       getGraph: () => _fg3d,          // función que devuelve el grafo 3D vivo
 *       toggleEl: document.getElementById('b-mano'),
 *       statusEl: document.getElementById('hc-status'),
 *   });
 * =========================================================================== */
(function (global) {
  "use strict";

  // CDN del runtime de visión de MediaPipe (Tasks) y del modelo de manos.
  const VISION_CDN = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";
  const WASM_PATH  = VISION_CDN + "/wasm";
  const MODEL_URL  =
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";

  // Landmarks de interés (índices del modelo de MediaPipe Hands)
  const WRIST = 0, THUMB_TIP = 4, INDEX_TIP = 8, MIDDLE_TIP = 12,
        RING_TIP = 16, PINKY_TIP = 20,
        INDEX_PIP = 6, MIDDLE_PIP = 10, RING_PIP = 14, PINKY_PIP = 18;

  // --- utilidades de suavizado / geometría --------------------------------
  function lerp(a, b, t) { return a + (b - a) * t; }
  function dist2D(a, b) { return Math.hypot(a.x - b.x, a.y - b.y); }

  // Filtro de media móvil ligero (lerp exponencial) para matar el jitter.
  function makeSmoother(alpha) {
    let s = null;
    return function (v) {
      if (s === null) { s = v; return s; }
      s = lerp(s, v, alpha);
      return s;
    };
  }

  // --- detección de gestos a partir de los 21 landmarks de una mano -------
  // landmarks: array de {x,y,z} normalizados [0..1] (x espejado por la cámara).
  function clasificarGesto(lm, umbralPinch) {
    umbralPinch = umbralPinch || 0.45;
    // Un dedo está "extendido" si su punta está más arriba (y menor) que su PIP.
    const ext = (tip, pip) => lm[tip].y < lm[pip].y;
    const idx = ext(INDEX_TIP, INDEX_PIP);
    const mid = ext(MIDDLE_TIP, MIDDLE_PIP);
    const rng = ext(RING_TIP, RING_PIP);
    const pky = ext(PINKY_TIP, PINKY_PIP);
    const nExt = [idx, mid, rng, pky].filter(Boolean).length;

    // Pellizco: punta de pulgar e índice muy cerca.
    const pinch = dist2D(lm[THUMB_TIP], lm[INDEX_TIP]);
    // Escala de referencia: tamaño de la mano (muñeca→base del medio aprox).
    const palm = dist2D(lm[WRIST], lm[MIDDLE_PIP]) || 0.0001;
    const pinchNorm = pinch / palm; // ~<0.4 = pellizco claro

    if (pinchNorm < umbralPinch) return { tipo: "pinch", pinch: pinchNorm };
    if (nExt === 0)       return { tipo: "fist" };
    if (nExt >= 3)        return { tipo: "open" };
    return { tipo: "point" }; // 1-2 dedos: estado neutro (no actúa)
  }

  // ========================================================================
  function attach(opts) {
    const getGraph = opts.getGraph;             // () => grafo 3D (3d-force-graph)
    const getNet2d = opts.getNet2d || (() => null); // () => red 2D (vis.Network)
    const getModo  = opts.getModo  || (() => "3d"); // () => "2d" | "3d"
    const toggleEl = opts.toggleEl;
    const statusEl = opts.statusEl;

    // Configuración de sensibilidad (ajustable en vivo desde los sliders).
    // Estos valores son los "por defecto"; el panel de ajustes los modifica.
    const cfg = {
      suavizado: 0.35,   // 0.10 (muy suave/lento) .. 0.70 (responsivo/tiembla)
      rotacion:  3.0,    // velocidad de giro con la mano abierta
      zoom:      0.6,    // cuánto amplifica el pellizco el acercamiento
      pellizco:  0.45,   // umbral de distancia dedos para detectar pellizco
      escala:    1.8,    // cuánto escala la separación de dos manos
    };

    const state = {
      activo: false,
      landmarker: null,
      stream: null,
      raf: null,
      video: null,
      cfg: cfg,
      // suavizadores de la posición de la muñeca (rotación/pan)
      smX: makeSmoother(cfg.suavizado),
      smY: makeSmoother(cfg.suavizado),
      smPinch: makeSmoother(cfg.suavizado),
      prev: null,          // estado del frame anterior {wx,wy,gesto}
      escenaScaleBase: 1,  // escala original de la escena (para restaurar)
    };

    // Cambiar el suavizado en vivo: recrea los filtros con el nuevo alpha.
    function aplicarSuavizado(v) {
      cfg.suavizado = v;
      state.smX = makeSmoother(v); state.smY = makeSmoother(v);
      state.smPinch = makeSmoother(v);
    }

    function setStatus(txt, on) {
      if (!statusEl) return;
      statusEl.textContent = txt;
      statusEl.style.display = "block";
      statusEl.style.borderColor = on ? "#4ea1ff" : "#5a3";
    }
    function hideStatus() { if (statusEl) statusEl.style.display = "none"; }

    // Habilita/inhabilita el control por mouse para no pelear con la mano.
    // En 3D: OrbitControls del grafo. En 2D: drag/zoom de vis-network.
    function setMouseControls(enabled) {
      try {
        const fg = getGraph && getGraph();
        const ctrls = fg && fg.controls && fg.controls();
        if (ctrls) ctrls.enabled = enabled;
      } catch (e) {}
      try {
        const net = getNet2d && getNet2d();
        if (net) net.setOptions({ interaction: {
          dragView: enabled, zoomView: enabled, dragNodes: enabled } });
      } catch (e) {}
    }

    async function ensureLandmarker() {
      if (state.landmarker) return state.landmarker;
      // Import dinámico del módulo ESM de MediaPipe desde CDN.
      const vision = await import(VISION_CDN + "/vision_bundle.mjs");
      const { HandLandmarker, FilesetResolver } = vision;
      const fileset = await FilesetResolver.forVisionTasks(WASM_PATH);
      state.landmarker = await HandLandmarker.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: MODEL_URL, delegate: "GPU" },
        runningMode: "VIDEO",
        numHands: 2,
      });
      return state.landmarker;
    }

    async function activar() {
      // getUserMedia exige contexto seguro (https o localhost).
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        fallar("Tu navegador no permite cámara aquí. Abre el dashboard en "
              + "http://localhost (no como archivo) o por HTTPS.");
        return;
      }
      try {
        setStatus("Cargando modelo de manos…", true);
        await ensureLandmarker();
        state.stream = await navigator.mediaDevices.getUserMedia({
          video: { width: 640, height: 480, facingMode: "user" }, audio: false,
        });
        const v = document.createElement("video");
        v.autoplay = true; v.playsInline = true; v.muted = true;
        v.style.display = "none";          // <video> oculto
        v.srcObject = state.stream;
        document.body.appendChild(v);
        await v.play();
        state.video = v;

        state.activo = true;
        if (toggleEl) toggleEl.classList.add("act");
        setMouseControls(false);           // al activar mano, fuera el mouse
        // recordar la escala original de la escena para poder restaurarla
        const fg = getGraph && getGraph();
        try { state.escenaScaleBase = (fg && fg.scene().scale.x) || 1; } catch (e) {}
        setStatus("✋ Mano: buscando…", true);
        loop();
      } catch (err) {
        const msg = (err && err.name === "NotAllowedError")
          ? "Permiso de cámara denegado. Actívalo para usar el control por mano."
          : "No se pudo iniciar la cámara: " + (err && err.message || err);
        fallar(msg);
      }
    }

    function desactivar() {
      state.activo = false;
      if (state.raf) cancelAnimationFrame(state.raf), state.raf = null;
      if (state.stream) state.stream.getTracks().forEach(t => t.stop()), state.stream = null;
      if (state.video) { state.video.remove(); state.video = null; }
      state.prev = null;
      if (toggleEl) toggleEl.classList.remove("act");
      setMouseControls(true);              // devolver el control al mouse
      hideStatus();
    }

    // Fallback limpio: apaga el modo mano y deja OrbitControls funcionando.
    function fallar(mensaje) {
      desactivar();
      setMouseControls(true);
      setStatus("⚠ " + mensaje, false);
      // el aviso se queda visible unos segundos y luego se oculta
      setTimeout(hideStatus, 6000);
      console.warn("[handControls]", mensaje);
    }

    // ----- aplicación de transformaciones sobre el grafo 3D -----------------
    function orbitar(dx, dy) {
      const fg = getGraph && getGraph();
      if (!fg) return;
      try {
        const cam = fg.camera();
        // Coordenadas esféricas: rotamos la posición de la cámara alrededor del centro.
        const r = Math.hypot(cam.position.x, cam.position.y, cam.position.z) || 1;
        let theta = Math.atan2(cam.position.x, cam.position.z);
        let phi   = Math.acos(Math.max(-1, Math.min(1, cam.position.y / r)));
        theta -= dx * cfg.rotacion;        // azimut
        phi    = Math.max(0.15, Math.min(Math.PI - 0.15, phi - dy * cfg.rotacion)); // elevación
        const x = r * Math.sin(phi) * Math.sin(theta);
        const y = r * Math.cos(phi);
        const z = r * Math.sin(phi) * Math.cos(theta);
        fg.cameraPosition({ x, y, z }, undefined, 0);
      } catch (e) {}
    }

    function zoom(factor) {
      const fg = getGraph && getGraph();
      if (!fg) return;
      try {
        const cam = fg.camera();
        const k = Math.max(0.85, Math.min(1.15, factor));
        fg.cameraPosition({ x: cam.position.x * k, y: cam.position.y * k, z: cam.position.z * k },
                          undefined, 0);
      } catch (e) {}
    }

    function pan(dx, dy) {
      const fg = getGraph && getGraph();
      if (!fg) return;
      try {
        const ctrls = fg.controls();
        const cam = fg.camera();
        const r = Math.hypot(cam.position.x, cam.position.y, cam.position.z) || 1;
        // mover el centro de órbita (target) → efecto de arrastrar la nube
        if (ctrls && ctrls.target) {
          ctrls.target.x += dx * r * 1.2;
          ctrls.target.y += dy * r * 1.2;
          ctrls.update && ctrls.update();
        }
      } catch (e) {}
    }

    function escalarEscena(s) {
      const fg = getGraph && getGraph();
      if (!fg) return;
      try {
        const sc = Math.max(0.3, Math.min(3, state.escenaScaleBase * s));
        fg.scene().scale.set(sc, sc, sc);
      } catch (e) {}
    }

    // ----- transformaciones para la red 2D (vis-network) --------------------
    // En 2D no hay cámara 3D que rotar: la mano abierta DESPLAZA (pan) y el
    // pellizco hace ZOOM. vis-network expone moveTo({position, scale}).
    function pan2d(dx, dy) {
      const net = getNet2d && getNet2d();
      if (!net) return;
      try {
        const pos = net.getViewPosition();   // {x,y} en coords del lienzo
        const sc = net.getScale() || 1;
        // dx/dy vienen normalizados [0..1]; los convertimos a píxeles del lienzo.
        const k = 1200 / sc;                 // sensibilidad de desplazamiento
        net.moveTo({ position: { x: pos.x - dx * k, y: pos.y - dy * k },
                     scale: sc, animation: false });
      } catch (e) {}
    }
    function zoom2d(factor) {
      const net = getNet2d && getNet2d();
      if (!net) return;
      try {
        const sc = net.getScale() || 1;
        const ns = Math.max(0.15, Math.min(4, sc * factor));
        net.moveTo({ scale: ns, animation: false });
      } catch (e) {}
    }

    // ----- dispatchers según el modo activo (2d | 3d) -----------------------
    function es2d() { return getModo && getModo() === "2d"; }
    function rotarG(dx, dy) { if (es2d()) pan2d(-dx, dy); else orbitar(dx, dy); }
    function panG(dx, dy)   { if (es2d()) pan2d(dx, dy);  else pan(dx, dy); }
    function zoomG(factor)  { if (es2d()) zoom2d(factor); else zoom(factor); }
    function escalaG(s)     { if (es2d()) zoom2d(0.5 + s * 0.5); else escalarEscena(s); }

    // ----- bucle principal: HandLandmarker sobre cada frame -----------------
    function loop() {
      if (!state.activo) return;
      // Re-asegurar que el mouse del grafo activo está deshabilitado: al
      // alternar 2D/3D el grafo se recrea con el mouse habilitado por defecto.
      setMouseControls(false);
      const v = state.video, lmk = state.landmarker;
      if (v && lmk && v.readyState >= 2) {
        let res = null;
        try { res = lmk.detectForVideo(v, performance.now()); } catch (e) {}
        const manos = (res && res.landmarks) || [];

        // En 2D el gesto "mano abierta" desplaza (no rota); el texto se adapta.
        const dosD = es2d();
        if (manos.length >= 2) {
          // Dos manos → escalar/zoom por distancia entre muñecas.
          const w1 = manos[0][WRIST], w2 = manos[1][WRIST];
          const d = dist2D(w1, w2);              // 0..~1
          escalaG(0.5 + d * cfg.escala);
          setStatus(dosD ? "🙌 Dos manos · zoom" : "🙌 Dos manos · escalar", true);
          state.prev = null;                      // resetea el seguimiento de 1 mano
        } else if (manos.length === 1) {
          const lm = manos[0];
          const g = clasificarGesto(lm, cfg.pellizco);
          // muñeca suavizada; x espejada para que mover a la derecha gire a la derecha
          const wx = state.smX(1 - lm[WRIST].x);
          const wy = state.smY(lm[WRIST].y);

          if (state.prev && state.prev.gesto === g.tipo) {
            const dx = wx - state.prev.wx;
            const dy = wy - state.prev.wy;
            if (g.tipo === "open") {
              rotarG(dx, dy);
              setStatus(dosD ? "✋ Mano abierta · desplazar" : "✋ Mano abierta · rotar", true);
            }
            else if (g.tipo === "fist") { panG(-dx, dy); setStatus("✊ Puño · arrastrar", true); }
            else if (g.tipo === "pinch") {
              // pellizco: distancia normalizada controla el zoom (menos = más cerca)
              const p = state.smPinch(g.pinch);
              zoomG(1 + (0.35 - p) * cfg.zoom);
              setStatus("🤏 Pellizco · zoom", true);
            } else {
              setStatus("👆 Mano detectada (gesto neutro)", true);
            }
          } else {
            setStatus("✋ Mano detectada", true);
          }
          state.prev = { wx, wy, gesto: g.tipo };
        } else {
          setStatus("✋ Mano: buscando…", true);
          state.prev = null;
        }
      }
      state.raf = requestAnimationFrame(loop);
    }

    // ----- toggle de la UI --------------------------------------------------
    function toggle() {
      if (state.activo) desactivar();
      else activar();
    }
    if (toggleEl) toggleEl.addEventListener("click", toggle);

    return {
      activar, desactivar, toggle,
      get activo() { return state.activo; },
      cfg: cfg,                       // objeto de sensibilidad (mutable en vivo)
      setSuavizado: aplicarSuavizado, // requiere recrear los filtros
    };
  }

  global.HandControls = { attach };
})(window);

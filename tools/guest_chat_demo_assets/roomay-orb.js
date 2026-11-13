/*!
 * ROOMAY voice orb  v1.0
 * <roomay-orb state="idle | listening | speaking"></roomay-orb>
 *
 * Dependency-free canvas web component. Transparent background, crisp on
 * any pixel density, pauses itself when off-screen or in a hidden tab.
 *
 *   el.state = 'speaking'      // or el.setAttribute('state', 'speaking')
 *   el.level = 0.42            // optional live audio level, 0..1 (null = built-in motion)
 *
 * Attributes
 *   state     idle | listening | speaking
 *   compact   crop to the core and its two soft discs (no ripples, halo or
 *             voice ring). Use it below roughly 96 px: avatars, buttons, tab bars.
 *   paused    freeze on the current frame
 *
 * Size it with CSS width (it is always square; default 200px). In the regular
 * layout the core is 38% of the box so the ripples have room; in compact, 60%.
 *
 * Theme with CSS custom properties on the element (all optional):
 *   --orb-core  --orb-core-light  --orb-core-shade
 *   --orb-sage  --orb-mist  --orb-ring  --orb-gold  --orb-glow
 * then call el.refreshColors() if you change them at runtime.
 */
(function (root) {
  'use strict';

  var TAU = Math.PI * 2;
  var LOOP = 4;        // seconds: every motion repeats exactly on this period
  var UNIT = 400;      // design space is 400 x 400, origin at the centre
  var COMPACT_UNIT = 252;  // visible span when the element has the `compact` attribute
  var R = 76;          // core radius in design units
  var WAVE_N = 20;     // bezier vertices per voice ring
  var GILT = R - 7;    // radius of the gilt line inside the core
  var LOBES = 5;       // soft waves around the voice ring

  var PALETTE = {
    core: '#1F4433',       // deep green
    coreLight: '#2F5F48',  // lit side of the core
    coreShade: '#193829',  // far side of the core
    sage: '#A9C3A8',       // inner soft disc
    mist: '#D3E0CD',       // outer soft disc + halo
    ring: '#7FA88C',       // ripple lines + green voice line
    gold: '#C7A866',       // gilt line + gold voice line
    glow: '#86BF9C'        // light inside the core when a voice is present
  };

  /* One parameter set per state. Switching state eases every number
     below towards its new value, so transitions never jump.
       core    resting scale of the core        breath  breathing depth
       glow    light inside the core            halo    halo strength
       out1    first outward ripple             out23   two extra outward ripples
       inn     inward ripples                   grow    how far the discs swell with voice
       wob     wave depth of the voice ring     wave    voice ring opacity
       speak / listen   which built-in voice envelope is active
       arc     length of the gilt arcs (deg)    goldA   gilt opacity */
  var STATES = {
    idle: {
      core: 1.00, breath: 0.034, glow: 0.05, halo: 0.55,
      out1: 0.26, out23: 0.00, inn: 0.00,
      wob: 0.000, grow: 0.00, speak: 0, listen: 0,
      arc: 44, goldA: 0.65, wave: 0
    },
    listening: {
      core: 0.95, breath: 0.012, glow: 0.08, halo: 0.70,
      out1: 0.00, out23: 0.00, inn: 0.36,
      wob: 0.000, grow: 0.06, speak: 0, listen: 1,
      arc: 76, goldA: 0.75, wave: 0
    },
    speaking: {
      core: 1.03, breath: 0.010, glow: 0.10, halo: 0.85,
      out1: 0.26, out23: 0.26, inn: 0.00,
      wob: 0.100, grow: 0.13, speak: 1, listen: 0,
      arc: 104, goldA: 0.9, wave: 0.75
    }
  };

  function clamp01(x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
  function frac(x) { return x - Math.floor(x); }
  function lerp(a, b, k) { return a + (b - a) * k; }
  function smooth(a, b, x) { x = clamp01((x - a) / (b - a)); return x * x * (3 - 2 * x); }

  /* Built-in "voice" envelopes. Sums of whole-number harmonics of the loop,
     so they read as natural speech cadence but still loop perfectly. */
  function speakEnv(t) {
    var phrase = 0.5 + 0.5 * Math.sin(TAU * t - 1.2);
    var syll = 0.55 + 0.25 * Math.sin(TAU * 3 * t + 0.4)
                    + 0.14 * Math.sin(TAU * 5 * t + 1.9)
                    + 0.09 * Math.sin(TAU * 8 * t + 4.2);
    return clamp01(syll * (0.55 + 0.45 * phrase));
  }
  function listenEnv(t) {
    return clamp01(0.5 + 0.30 * Math.sin(TAU * 2 * t + 1.0) + 0.14 * Math.sin(TAU * 3 * t + 2.5));
  }

  /* A ring whose radius ripples as a travelling sine wave:
     r(theta) = r0 + amp * sin(lobes * theta + phase).
     Returned as cubic bezier vertices (Lottie-style: v, i, o). */
  function waveRing(r0, amp, lobes, phase) {
    var v = [], i = [], o = [], h = TAU / WAVE_N / 3;
    for (var k = 0; k < WAVE_N; k++) {
      var th = k * TAU / WAVE_N - Math.PI / 2;
      var r = r0 + amp * Math.sin(lobes * th + phase);
      var dr = amp * lobes * Math.cos(lobes * th + phase);
      var c = Math.cos(th), s = Math.sin(th);
      var tx = (dr * c - r * s) * h, ty = (dr * s + r * c) * h;
      v.push([r * c, r * s]); o.push([tx, ty]); i.push([-tx, -ty]);
    }
    return { v: v, i: i, o: o };
  }

  /* The whole animation is this pure function:
     parameters P + loop time t (1.0 = one 4 s loop) -> what to draw.
     e / e2 are optional live voice levels (fast / slightly lagging). */
  function frame(P, t, e, e2) {
    var voiced = P.speak + P.listen;
    if (e == null) {
      e = P.speak * speakEnv(t) + P.listen * listenEnv(t);
      e2 = P.speak * speakEnv(t - 0.022) + P.listen * listenEnv(t - 0.022);
    } else {
      e = clamp01(e) * clamp01(voiced);
      e2 = clamp01(e2 == null ? e : e2) * clamp01(voiced);
    }
    var breath = Math.sin(TAU * t);
    var breathLate = Math.sin(TAU * t - 0.7);

    var coreScale = P.core + P.breath * breath + (0.045 * P.speak + 0.018 * P.listen) * e;

    var ripples = [], k, p;
    for (k = 0; k < 3; k++) {            // outward: the assistant's voice leaving
      var w = k === 0 ? P.out1 : P.out23;
      p = frac(t - 0.25 + k / 3);
      var po = 1 - Math.pow(1 - p, 2.2);
      ripples.push({
        r: R * lerp(1.22, 2.42, po),
        a: w * smooth(0, 0.16, p) * Math.pow(1 - p, 1.5),
        w: lerp(2.6, 1.4, p)
      });
    }
    for (k = 0; k < 3; k++) {            // inward: the guest's voice arriving
      p = frac(t + k / 3);
      var pi = p * p * (3 - 2 * p) * 0.6 + p * 0.4;
      ripples.push({
        r: R * lerp(2.42, 1.40, pi),
        a: P.inn * smooth(0, 0.4, p) * (1 - smooth(0.82, 1, p)),
        w: lerp(1.4, 2.4, p)
      });
    }

    var rA = R * (1.165 + 0.020 * breath + P.grow * (0.35 + 0.65 * e));
    var rB = R * (1.33 + 0.030 * breathLate + 1.7 * P.grow * (0.35 + 0.65 * e2));
    var rW = R * (1.56 + 0.022 * breathLate + 2.0 * P.grow * (0.35 + 0.65 * e2));
    var amp = R * P.wob * (0.25 + 0.75 * e2);

    return {
      halo: { r: 190 * (0.95 + 0.035 * breathLate + 0.05 * e2), a: P.halo * (0.86 + 0.14 * breathLate) },
      ripples: ripples,
      discB: { r: rB, a: 0.62 },
      discA: { r: rA, a: 0.78 },
      waves: [
        { path: waveRing(rW, amp, LOBES, TAU * t), a: P.wave, w: 2.2, color: 'ring' },
        { path: waveRing(rW, amp, LOBES, TAU * t + Math.PI + 0.5 * Math.sin(TAU * 2 * t)), a: P.wave * 0.9, w: 2.2, color: 'gold' }
      ],
      coreScale: coreScale,
      gold: { a: P.goldA, arc: P.arc, rot: 180 * t },
      glow: { r: R * (0.62 + 0.22 * e + 0.04 * breath), a: P.glow + 0.20 * e + 0.03 * breath }
    };
  }

  /* ---------- canvas renderer ---------- */

  function hexToRgb(hex) {
    var m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})/i.exec(hex);
    return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : [0, 0, 0];
  }
  function rgba(c, a) { return 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + clamp01(a).toFixed(3) + ')'; }

  function tracePath(ctx, path) {
    var v = path.v, i = path.i, o = path.o, n = v.length;
    ctx.beginPath();
    ctx.moveTo(v[0][0], v[0][1]);
    for (var k = 0; k < n; k++) {
      var j = (k + 1) % n;
      ctx.bezierCurveTo(v[k][0] + o[k][0], v[k][1] + o[k][1], v[j][0] + i[j][0], v[j][1] + i[j][1], v[j][0], v[j][1]);
    }
    ctx.closePath();
  }

  /* ctx must already be transformed so the origin is the centre and the
     canvas spans 400 design units. C = palette as [r,g,b] triples. */
  function draw(ctx, F, C) {
    var g, k;

    if (F.halo.a > 0.004) {
      g = ctx.createRadialGradient(0, 0, 0, 0, 0, F.halo.r);
      g.addColorStop(0, rgba(C.mist, F.halo.a));
      g.addColorStop(0.55, rgba(C.mist, F.halo.a * 0.5));
      g.addColorStop(1, rgba(C.mist, 0));
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(0, 0, F.halo.r, 0, TAU); ctx.fill();
    }

    for (k = 0; k < F.ripples.length; k++) {
      var rp = F.ripples[k];
      if (rp.a < 0.004) continue;
      ctx.strokeStyle = rgba(C.ring, rp.a);
      ctx.lineWidth = rp.w;
      ctx.beginPath(); ctx.arc(0, 0, rp.r, 0, TAU); ctx.stroke();
    }

    ctx.fillStyle = rgba(C.mist, F.discB.a);
    ctx.beginPath(); ctx.arc(0, 0, F.discB.r, 0, TAU); ctx.fill();
    ctx.fillStyle = rgba(C.sage, F.discA.a);
    ctx.beginPath(); ctx.arc(0, 0, F.discA.r, 0, TAU); ctx.fill();

    for (k = 0; k < F.waves.length; k++) {
      var wv = F.waves[k];
      if (wv.a < 0.004) continue;
      ctx.strokeStyle = rgba(C[wv.color], wv.a);
      ctx.lineWidth = wv.w;
      tracePath(ctx, wv.path); ctx.stroke();
    }

    ctx.save();
    ctx.scale(F.coreScale, F.coreScale);

    g = ctx.createRadialGradient(-0.36 * R, -0.42 * R, 0, -0.36 * R, -0.42 * R, 1.7 * R);
    g.addColorStop(0, rgba(C.coreLight, 1));
    g.addColorStop(0.55, rgba(C.core, 1));
    g.addColorStop(1, rgba(C.coreShade, 1));
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(0, 0, R, 0, TAU); ctx.fill();

    var rg = GILT;
    ctx.strokeStyle = rgba(C.gold, F.gold.a * 0.42);
    ctx.lineWidth = 1.6;
    ctx.beginPath(); ctx.arc(0, 0, rg, 0, TAU); ctx.stroke();

    ctx.strokeStyle = rgba(C.gold, F.gold.a);
    ctx.lineWidth = 2.6;
    ctx.lineCap = 'round';
    var half = F.gold.arc * Math.PI / 360, rot = F.gold.rot * Math.PI / 180 - Math.PI / 2;
    for (k = 0; k < 2; k++) {
      ctx.beginPath(); ctx.arc(0, 0, rg, rot + k * Math.PI - half, rot + k * Math.PI + half); ctx.stroke();
    }
    ctx.restore();

    g = ctx.createRadialGradient(0, 0, 0, 0, 0, F.glow.r);
    g.addColorStop(0, rgba(C.glow, F.glow.a));
    g.addColorStop(1, rgba(C.glow, 0));
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(0, 0, F.glow.r, 0, TAU); ctx.fill();
  }

  var model = { LOOP: LOOP, UNIT: UNIT, R: R, GILT: GILT, PALETTE: PALETTE, STATES: STATES, frame: frame, draw: draw, hexToRgb: hexToRgb };

  /* ---------- custom element ---------- */

  if (typeof HTMLElement !== 'undefined' && root.customElements && !root.customElements.get('roomay-orb')) {
    var KEYS = Object.keys(STATES.idle);
    var CSS_VARS = {
      core: '--orb-core', coreLight: '--orb-core-light', coreShade: '--orb-core-shade',
      sage: '--orb-sage', mist: '--orb-mist', ring: '--orb-ring', gold: '--orb-gold', glow: '--orb-glow'
    };
    var LABELS = { idle: 'Assistant is ready', listening: 'Assistant is listening', speaking: 'Assistant is speaking' };

    class RoomayOrb extends HTMLElement {
      static get observedAttributes() { return ['state', 'paused', 'compact']; }

      constructor() {
        super();
        this._P = Object.assign({}, STATES.idle);   // parameters currently on screen
        this._target = STATES.idle;                 // parameters being eased towards
        this._t = 0; this._last = 0; this._raf = 0;
        this._level = null; this._lv = 0; this._lv2 = 0;
        this._visible = true; this._calm = false; this._C = null;
        this._tick = this._tick.bind(this);
        this._sync = this._sync.bind(this);
        this.refreshColors = this.refreshColors.bind(this);
        // Keep all presentation in app.css so the local page's strict
        // style-src 'self' policy does not need an inline-style exception.
        this._canvas = document.createElement('canvas');
        this.appendChild(this._canvas);
        try { this._ctx = this._canvas && this._canvas.getContext('2d'); }
        catch (_) { this._ctx = null; }
      }

      get state() { var s = this.getAttribute('state'); return STATES[s] ? s : 'idle'; }
      set state(s) { this.setAttribute('state', s); }

      /* Optional live audio level, 0..1. Set it every frame from your mic or
         TTS analyser and the orb follows the real voice; set null to go back
         to the built-in motion. */
      get level() { return this._level; }
      set level(v) { this._level = (v == null || isNaN(v)) ? null : clamp01(+v); }

      connectedCallback() {
        var self = this;
        if (!this.hasAttribute('role')) this.setAttribute('role', 'img');
        if (!this._ctx) this.setAttribute('data-canvas-unavailable', '');
        this._applyState(true);
        this.refreshColors();
        if (root.ResizeObserver) { this._ro = new ResizeObserver(function () { self._resize(); }); this._ro.observe(this); }
        if (root.IntersectionObserver) {
          this._io = new IntersectionObserver(function (en) { self._visible = en[en.length - 1].isIntersecting; self._sync(); });
          this._io.observe(this);
        }
        if (root.matchMedia) {
          this._mqMotion = root.matchMedia('(prefers-reduced-motion: reduce)');
          this._mqScheme = root.matchMedia('(prefers-color-scheme: dark)');
          this._calm = this._mqMotion.matches;
          this._onMotion = function (ev) { self._calm = ev.matches; };
          this._mqMotion.addEventListener('change', this._onMotion);
          this._mqScheme.addEventListener('change', this.refreshColors);
        }
        document.addEventListener('visibilitychange', this._sync);
        this._resize();
        this._sync();
      }

      disconnectedCallback() {
        cancelAnimationFrame(this._raf); this._raf = 0;
        if (this._ro) this._ro.disconnect();
        if (this._io) this._io.disconnect();
        if (this._mqMotion) {
          this._mqMotion.removeEventListener('change', this._onMotion);
          this._mqScheme.removeEventListener('change', this.refreshColors);
        }
        document.removeEventListener('visibilitychange', this._sync);
      }

      attributeChangedCallback(name) {
        if (name === 'state') this._applyState(false);
        if (name === 'paused' && this.isConnected) {
          // A dialog can be revealed and unpaused in one click task. Its
          // IntersectionObserver callback may still contain the hidden-at-load
          // result, so consult layout immediately instead of waiting for it.
          if (!this.hasAttribute('paused')) this._refreshVisibility();
          this._sync();
        }
        if (name === 'compact' && this.isConnected && !this._raf) this._paint();
      }

      _applyState(snap) {
        var s = this.state;
        this._target = STATES[s];
        if (snap) this._P = Object.assign({}, this._target);
        this.setAttribute('aria-label', LABELS[s]);
      }

      /* Re-read the theme colours. Runs automatically on connect and when the
         OS colour scheme flips; call it yourself after changing the CSS
         variables at runtime (for example an in-app theme toggle). */
      refreshColors() {
        var cs = getComputedStyle(this), C = {}, probe = null;
        try { probe = document.createElement('canvas').getContext('2d'); } catch (_) { probe = null; }
        Object.keys(PALETTE).forEach(function (key) {
          var val = cs.getPropertyValue(CSS_VARS[key]).trim(), rgb = hexToRgb(PALETTE[key]);
          if (val && probe) {             // let the browser parse any CSS colour syntax
            try {
              probe.clearRect(0, 0, 1, 1);
              probe.fillStyle = 'rgba(0,0,0,0)'; probe.fillStyle = val;
              probe.fillRect(0, 0, 1, 1);
              var px = probe.getImageData(0, 0, 1, 1).data;
              if (px[3] > 0) rgb = [px[0], px[1], px[2]];
            } catch (_) { /* Keep the built-in palette when color probing is unavailable. */ }
          }
          C[key] = rgb;
        });
        this._C = C;
        if (!this._raf) this._paint();
      }

      _resize() {
        if (!this._canvas) return;
        var box = this.getBoundingClientRect();
        var dpr = Math.min(root.devicePixelRatio || 1, 3);
        var px = Math.max(1, Math.round(Math.min(box.width, box.height) * dpr));
        if (this._canvas.width !== px || this._canvas.height !== px) { this._canvas.width = px; this._canvas.height = px; }
        this._paint();
      }

      _refreshVisibility() {
        var box = this.getBoundingClientRect();
        var width = box.width || (box.right - box.left), height = box.height || (box.bottom - box.top);
        var inViewport = width > 0 && height > 0;
        if (inViewport && root.innerWidth > 0 && root.innerHeight > 0) {
          inViewport = box.bottom > 0 && box.right > 0 && box.top < root.innerHeight && box.left < root.innerWidth;
        }
        this._visible = inViewport;
        return inViewport;
      }

      /* Run only while it can be seen: on screen, tab visible, not paused. */
      _sync() {
        var run = this.isConnected && !!this._ctx && this._visible && !document.hidden && !this.hasAttribute('paused');
        if (run && !this._raf) { this._last = 0; this._raf = requestAnimationFrame(this._tick); }
        if (!run && this._raf) { cancelAnimationFrame(this._raf); this._raf = 0; }
      }

      _tick(now) {
        var dt = this._last ? Math.min(0.05, (now - this._last) / 1000) : 0;
        this._last = now;
        this._t += dt / LOOP * (this._calm ? 0.5 : 1);

        var P = this._P, T = this._target, k = 1 - Math.exp(-dt / 0.22);
        for (var n = 0; n < KEYS.length; n++) P[KEYS[n]] += (T[KEYS[n]] - P[KEYS[n]]) * k;

        if (this._level != null) {
          this._lv += (this._level - this._lv) * (1 - Math.exp(-dt / 0.06));
          this._lv2 += (this._level - this._lv2) * (1 - Math.exp(-dt / 0.14));
        }
        this._paint();
        this._raf = requestAnimationFrame(this._tick);
      }

      /* Parameters as they should be drawn right now: honours reduced motion
         and the compact layout. */
      _shown(P) {
        if (this._calm) {     // prefers-reduced-motion: slow breathing only, no travelling lines
          P = Object.assign({}, P, { out1: 0, out23: 0, inn: 0, wob: P.wob * 0.3, speak: P.speak * 0.3, listen: P.listen * 0.3 });
        }
        if (this.hasAttribute('compact')) {
          P = Object.assign({}, P, { halo: 0, out1: 0, out23: 0, inn: 0, wave: 0 });
        }
        return P;
      }

      _paint(F) {
        var ctx = this._ctx, px = this._canvas ? this._canvas.width : 0;
        if (!ctx || !this._C || !px) return false;
        if (!F) {
          var P = this._shown(this._P);
          F = this._level != null ? frame(P, this._t, this._lv, this._lv2) : frame(P, this._t);
        }
        try {
          var unit = this.hasAttribute('compact') ? COMPACT_UNIT : UNIT;
          ctx.setTransform(1, 0, 0, 1, 0, 0);
          ctx.clearRect(0, 0, px, px);
          ctx.setTransform(px / unit, 0, 0, px / unit, px / 2, px / 2);
          draw(ctx, F, this._C);
          this.removeAttribute('data-canvas-unavailable');
          return true;
        } catch (_) {
          // The CSS fallback beside this canvas remains visible if a browser
          // lacks a usable 2D context or one of its drawing primitives.
          this.setAttribute('data-canvas-unavailable', '');
          this._ctx = null;
          this._sync();
          return false;
        }
      }

      /* Draw one exact frame of a state's loop (time in seconds). Handy for
         exports, visual tests and poster frames; use together with `paused`. */
      renderAt(seconds, stateName) {
        this._paint(frame(this._shown(STATES[stateName || this.state]), seconds / LOOP));
      }
    }

    RoomayOrb.model = model;
    root.customElements.define('roomay-orb', RoomayOrb);
    root.RoomayOrb = RoomayOrb;
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = model;
})(typeof window !== 'undefined' ? window : globalThis);

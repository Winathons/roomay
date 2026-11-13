// Offline lifecycle/render harness for the actual ROOMAY canvas custom element.
// No network, microphone, Vapi credentials, provider calls, or hotel data.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const source = fs.readFileSync(path.join(__dirname, '..', 'tools', 'guest_chat_demo_assets', 'roomay-orb.js'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, '..', 'tools', 'guest_chat_demo_assets', 'index.html'), 'utf8');
const css = fs.readFileSync(path.join(__dirname, '..', 'tools', 'guest_chat_demo_assets', 'app.css'), 'utf8');
const cases = [];
function test(name, fn) { cases.push([name, fn]); }

function makeOrb({ contextAvailable = true, reducedMotion = false } = {}) {
  let nextFrame = 1;
  const frames = new Map();
  const cancelled = new Set();
  const observers = [];
  const draws = { arcs: 0 };
  const ctx2d = contextAvailable ? {
    setTransform() {}, clearRect() {}, beginPath() {}, moveTo() {}, bezierCurveTo() {},
    closePath() {}, arc() { draws.arcs += 1; }, fill() {}, stroke() {}, save() {}, scale() {}, restore() {},
    fillRect() {}, getImageData() { return { data: [0, 0, 0, 0] }; },
    createRadialGradient() { return { addColorStop() {} }; },
  } : null;
  class Canvas {
    constructor() { this.width = 300; this.height = 150; this.style = {}; }
    getContext(kind) { return kind === '2d' ? ctx2d : null; }
  }
  class FakeHTMLElement {
    constructor() {
      this.attributes = {};
      this.isConnected = false;
      this.rect = { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 };
      this.children = [];
    }
    attachShadow() { return this.shadowRoot; }
    getBoundingClientRect() { return this.rect; }
    appendChild(child) { this.children.push(child); this.canvas = child; return child; }
    hasAttribute(name) { return Object.hasOwn(this.attributes, name); }
    setAttribute(name, value) {
      const oldValue = this.getAttribute(name);
      this.attributes[name] = String(value);
      if (FakeHTMLElement.observed.has(name)) this.attributeChangedCallback(name, oldValue, String(value));
    }
    removeAttribute(name) {
      const oldValue = this.getAttribute(name);
      delete this.attributes[name];
      if (FakeHTMLElement.observed.has(name)) this.attributeChangedCallback(name, oldValue, null);
    }
    getAttribute(name) { return this.attributes[name] ?? null; }
    static observed = new Set(['state', 'paused', 'compact']);
  }
  class ResizeObserverMock { observe() {} disconnect() {} }
  class IntersectionObserverMock {
    constructor(callback) { this.callback = callback; observers.push(this); }
    observe() {}
    disconnect() {}
    emit(isIntersecting) { this.callback([{ isIntersecting }]); }
  }
  const motion = {
    matches: reducedMotion,
    addEventListener() {}, removeEventListener() {},
  };
  const scheme = { matches: false, addEventListener() {}, removeEventListener() {} };
  const customElements = new Map();
  const documentRef = {
    hidden: false,
    addEventListener() {}, removeEventListener() {},
    createElement(tag) { return tag === 'canvas' ? new Canvas() : {}; },
  };
  const windowRef = {
    customElements: { get: name => customElements.get(name), define: (name, value) => customElements.set(name, value) },
    ResizeObserver: ResizeObserverMock, IntersectionObserver: IntersectionObserverMock,
    matchMedia: query => query.includes('reduced-motion') ? motion : scheme,
    devicePixelRatio: 1, innerWidth: 1366, innerHeight: 900,
    requestAnimationFrame(fn) { const id = nextFrame++; frames.set(id, fn); return id; },
    cancelAnimationFrame(id) { cancelled.add(id); frames.delete(id); },
  };
  const context = {
    window: windowRef, globalThis: windowRef, HTMLElement: FakeHTMLElement,
    ResizeObserver: ResizeObserverMock, IntersectionObserver: IntersectionObserverMock,
    document: documentRef, getComputedStyle: () => ({ getPropertyValue: () => '' }),
    requestAnimationFrame: windowRef.requestAnimationFrame,
    cancelAnimationFrame: windowRef.cancelAnimationFrame,
    module: { exports: {} },
  };
  vm.runInNewContext(source, context, { filename: 'roomay-orb.js' });
  const Orb = customElements.get('roomay-orb');
  const orb = new Orb();
  orb.setAttribute('state', 'idle');
  orb.setAttribute('paused', '');
  orb.isConnected = true;
  orb.connectedCallback();
  return {
    orb, windowRef, motion, observers, draws, frames, cancelled,
    frame() {
      const item = [...frames.entries()][0];
      assert(item, 'expected an animation frame');
      frames.delete(item[0]); item[1](1000 + item[0] * 16);
    },
  };
}

test('orb is registered and canvas has a responsive, explicit visible stage', () => {
  assert.match(source, /customElements\.define\('roomay-orb'/);
  assert.match(html, /<roomay-orb id="remi-orb" state="idle" paused/);
  assert.match(html, /class="remi-orb-fallback"/);
  assert.match(css, /\.remi-orb-stage[^\n]*height: min\(224px, 64vw\)/);
  assert.match(css, /\.remi-dialog \.remi-orb-stage[^\n]*height: clamp\(148px, min\(52vw, 250px\), 250px\)/);
  assert.match(css, /\.remi-dialog \.remi-orb-stage[^\n]*height: clamp\(144px, 58vw, 220px\)/);
  assert.match(css, /roomay-orb canvas \{ display: block; width: 100%; height: 100%; \}/);
  assert.match(css, /roomay-orb\[data-canvas-unavailable\] canvas \{ display: none; \}/);
  assert.doesNotMatch(source, /attachShadow|innerHTML|this\._canvas\.style/);
  assert.match(source, /this\.appendChild\(this\._canvas\)/);
  assert.match(css, /\.remi-dialog-overlay[^\n]*overflow-y: auto/);
  assert.match(css, /\.remi-dialog[^\n]*max-height: calc\(100dvh - 32px\)/);
  assert.match(css, /@media \(max-height: 640px\)/);
  assert.match(css, /env\(safe-area-inset-bottom\)/);
});

test('hidden-at-load orb starts rendering immediately when the call modal reveals it', () => {
  const h = makeOrb();
  h.observers[0].emit(false);
  assert.equal(h.frames.size, 0);
  h.orb.rect = { left: 540, top: 200, right: 790, bottom: 450, width: 250, height: 250 };
  h.orb.removeAttribute('paused');
  assert.equal(h.frames.size, 1, 'unpausing rechecks the now-visible layout without waiting on an observer');
  h.frame();
  assert(h.draws.arcs > 0, 'the idle frame paints visible orb shapes');
});

test('listening and speaking states continue to paint and modal close pauses animation', () => {
  const h = makeOrb();
  h.orb.rect = { left: 10, top: 10, right: 260, bottom: 260, width: 250, height: 250 };
  h.orb.removeAttribute('paused');
  h.frame();
  h.orb.setAttribute('state', 'listening'); h.frame();
  h.orb.setAttribute('state', 'speaking'); h.frame();
  assert(h.draws.arcs > 0);
  h.orb.setAttribute('paused', '');
  assert.equal(h.frames.size, 0);
  assert(h.cancelled.size >= 1);
});

test('repeated open and close resumes then stops the animation cleanly', () => {
  const h = makeOrb();
  h.orb.rect = { left: 10, top: 10, right: 230, bottom: 230, width: 220, height: 220 };
  for (let i = 0; i < 3; i += 1) {
    h.orb.removeAttribute('paused'); assert.equal(h.frames.size, 1);
    h.orb.setAttribute('paused', ''); assert.equal(h.frames.size, 0);
  }
});

test('reduced motion keeps a calm painted state without travel ripples', () => {
  const h = makeOrb({ reducedMotion: true });
  h.orb.rect = { left: 10, top: 10, right: 230, bottom: 230, width: 220, height: 220 };
  h.orb.setAttribute('state', 'speaking');
  assert(h.orb._calm);
  assert.equal(orbValues(h.orb._shown(h.orb._target), ['out1', 'out23', 'inn']), 0);
  h.orb.removeAttribute('paused'); h.frame();
  assert(h.draws.arcs > 0);
});

test('missing canvas support does not throw, keeps static fallback and schedules no animation', () => {
  const h = makeOrb({ contextAvailable: false });
  assert(h.orb.hasAttribute('data-canvas-unavailable'));
  assert.equal(h.orb._ctx, null);
  h.orb.rect = { left: 10, top: 10, right: 230, bottom: 230, width: 220, height: 220 };
  h.orb.removeAttribute('paused');
  assert.equal(h.frames.size, 0);
  assert.match(html, /class="remi-orb-fallback"/);
  assert.equal(h.orb.children.length, 1, 'canvas is a normal light-DOM child styled by external CSS');
  assert.match(css, /roomay-orb\[data-canvas-unavailable\] canvas \{ display: none; \}/);
});

test('provider-unavailable state remains independent from the idle visual', () => {
  assert.match(html, /state="idle" paused/);
  assert.match(source, /this\.hasAttribute\('paused'\)/);
  assert.match(fs.readFileSync(path.join(__dirname, '..', 'tools', 'guest_chat_demo_assets', 'vapi_call.js'), 'utf8'),
    /Voice calls are unavailable in this local setup/);
});

function orbValues(parameters, names) { return names.reduce((sum, name) => sum + parameters[name], 0); }

(async () => {
  for (const [name, fn] of cases) {
    try { await fn(); }
    catch (error) { console.error(`FAIL ${name}: ${error.stack}`); process.exitCode = 1; }
  }
  if (!process.exitCode) console.log(`${cases.length} Roomay orb rendering scenarios passed (canvas, observers and provider mocked).`);
})();

// Mocked Vapi Web SDK/browser harness. No Vapi requests, credentials, audio or charges.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const source = fs.readFileSync(path.join(__dirname, '..', 'tools', 'guest_chat_demo_assets', 'vapi_call.js'), 'utf8');
const cases = [];
function test(name, fn) { cases.push([name, fn]); }

class Element {
  constructor(id = '') {
    this.id = id; this.listeners = {}; this.children = []; this.attributes = {};
    this.hidden = false; this.disabled = false; this.textContent = ''; this.scrollHeight = 0;
    this.scrollTop = 0; this.dataset = {};
  }
  addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
  emit(name, event = {}) { for (const fn of this.listeners[name] || []) fn(event); }
  append(...values) { this.children.push(...values); }
  removeChild(child) { this.children.splice(this.children.indexOf(child), 1); }
  setAttribute(key, value) { this.attributes[key] = value; }
}

function harness({ configStatus = 200, startError = null, sdk = true, configGate = null } = {}) {
  const ids = ['remi-call', 'remi-call-overlay', 'call-remi', 'call-remi-label',
    'close-remi', 'remi-call-duration', 'end-remi', 'mute-remi', 'remi-call-status',
    'remi-call-captions', 'use-call-transcript', 'remi-orb'];
  const elements = Object.fromEntries(ids.map(id => [id, new Element(id)]));
  elements['remi-call-overlay'].hidden = true;
  const calls = [];
  const timers = [];
  const intervals = [];
  const listeners = {};
  const documentListeners = {};
  const clientRef = { value: null };
  const fetch = async (url, options) => {
    calls.push({ url, options });
    if (url === '/api/voice/config') {
      if (configGate) await configGate;
      return { ok: configStatus === 200, status: configStatus, json: async () => configStatus === 200
        ? { enabled: true, publicKey: 'pk_public_test_only', assistantId: 'assistant-test-id', assistantLabel: 'Remi', modelProvider: 'openai', modelName: 'gpt-4.1', maxDurationSeconds: 180 }
        : { error: 'not_found' } };
    }
    if (url === '/api/voice/claim') return { ok: true, status: 200, json: async () => ({}) };
    if (url === '/api/voice/release') return { ok: true, status: 200, json: async () => ({ released: true }) };
    throw new Error('unexpected_url');
  };
  class FakeVapi {
    constructor(key) { this.key = key; this.handlers = {}; this.stopped = 0; this.muted = false; clientRef.value = this; }
    on(name, fn) { (this.handlers[name] ||= []).push(fn); }
    emit(name, value) { for (const fn of this.handlers[name] || []) fn(value); }
    start(id, overrides) { this.startArgs = [id, overrides]; if (startError) return Promise.reject(startError); return Promise.resolve({}); }
    stop() { this.stopped += 1; }
    setMuted(muted) { this.muted = muted; }
    isMuted() { return this.muted; }
  }
  const windowRef = {
    fetch,
    RoomayVapiSDK: sdk ? { Vapi: FakeVapi } : undefined,
    setTimeout(fn, duration) { timers.push({ fn, duration }); return timers.length; },
    clearTimeout() {},
    setInterval(fn, duration) { intervals.push({ fn, duration }); return intervals.length; },
    clearInterval() {},
    addEventListener(name, fn) { (listeners[name] ||= []).push(fn); },
  };
  const documentRef = {
    getElementById: id => elements[id],
    createElement: () => new Element(),
    createTextNode: text => ({ textContent: text }),
    addEventListener(name, fn) { (documentListeners[name] ||= []).push(fn); },
  };
  const context = { globalThis: null, windowRef, documentRef };
  context.globalThis = context;
  vm.runInNewContext(source, context);
  const imported = [];
  const orbStates = [];
  const call = context.RoomayVapiCall.attach({
    windowRef, documentRef, onTranscript: text => imported.push(text),
    onState: next => {
      elements['remi-orb'].state = context.RoomayVapiCall.orbStateForCallState(next);
      orbStates.push({ call: next, orb: elements['remi-orb'].state });
    },
  });
  return { elements, calls, timers, intervals, listeners, documentListeners, clientRef, imported, orbStates, call };
}

const tick = () => new Promise(resolve => setImmediate(resolve));

test('does not start a provider call until the guest presses Call Remi', async () => {
  const h = harness();
  assert.equal(h.calls.length, 0);
  assert.equal(h.clientRef.value, null);
  assert.equal(h.elements['remi-call-overlay'].hidden, true);
  assert.equal(h.elements['call-remi'].disabled, false);
  h.elements['call-remi'].emit('click');
  assert.equal(h.elements['remi-call-overlay'].hidden, false);
  await tick();
  assert.deepEqual(h.calls.map(call => call.url), ['/api/voice/config', '/api/voice/claim']);
  assert.equal(h.clientRef.value.startArgs[0], 'assistant-test-id');
  assert.equal(h.clientRef.value.startArgs[1].maxDurationSeconds, 180);
  assert.equal(h.clientRef.value.startArgs[1].model.provider, 'openai');
  assert.equal(h.clientRef.value.startArgs[1].model.model, 'gpt-4.1');
  assert.match(h.clientRef.value.startArgs[1].model.messages[0].content, /Never claim a request was submitted/);
  assert.equal(h.clientRef.value.startArgs[1].artifactPlan.recordingEnabled, false);
  assert.equal(h.clientRef.value.startArgs[1].artifactPlan.loggingEnabled, false);
  assert.equal(h.clientRef.value.startArgs[1].artifactPlan.transcriptPlan.enabled, false);
  assert.equal(h.clientRef.value.key, 'pk_public_test_only');
  assert.equal(JSON.stringify(h.calls).includes('privateKey'), false);
  assert.equal(h.elements['remi-call-status'].textContent.includes('Connecting'), true);
});

test('shows listening, speaking, interruption, captions, mute and end states', async () => {
  const h = harness();
  assert.equal(h.elements['remi-orb'].state, 'idle');
  h.elements['call-remi'].emit('click'); await tick();
  assert.equal(h.elements['remi-orb'].state, 'idle');
  assert.equal(h.orbStates.at(-1).call, 'connecting');
  const client = h.clientRef.value;
  client.emit('call-start');
  assert.equal(h.elements['remi-orb'].state, 'listening');
  assert.match(h.elements['remi-call-status'].textContent, /Connected.*Listening/);
  assert.equal(h.timers[0].duration, 180000);
  assert.equal(h.intervals[0].duration, 1000);
  assert.equal(h.elements['remi-call-duration'].textContent, '00:00');
  client.emit('message', { type: 'assistant.speechStarted' });
  assert.equal(h.elements['remi-orb'].state, 'speaking');
  assert.match(h.elements['remi-call-status'].textContent, /Remi is speaking/);
  h.elements['mute-remi'].emit('click');
  assert.equal(h.elements['remi-orb'].state, 'speaking');
  assert.match(h.elements['remi-call-status'].textContent, /Microphone muted/);
  h.elements['mute-remi'].emit('click');
  assert.equal(h.elements['remi-orb'].state, 'speaking');
  assert.match(h.elements['remi-call-status'].textContent, /Microphone on. Remi is speaking/);
  client.emit('message', { type: 'user-interrupted' });
  assert.equal(h.elements['remi-orb'].state, 'listening');
  assert.match(h.elements['remi-call-status'].textContent, /interrupted/);
  client.emit('message', { type: 'transcript', role: 'user', transcriptType: 'final', transcript: 'Bring two towels' });
  client.emit('message', { type: 'transcript', role: 'assistant', transcriptType: 'final', transcript: 'I can listen.' });
  assert.equal(h.elements['remi-call-captions'].children.length, 2);
  h.elements['use-call-transcript'].emit('click');
  assert.deepEqual(h.imported, ['Bring two towels']);
  h.elements['mute-remi'].emit('click');
  assert.equal(client.isMuted(), true);
  assert.equal(h.elements['remi-orb'].state, 'idle');
  assert.equal(h.elements['mute-remi'].textContent, 'Unmute microphone');
  h.elements['mute-remi'].emit('click');
  assert.equal(client.isMuted(), false);
  assert.equal(h.elements['remi-orb'].state, 'listening');
  h.elements['end-remi'].emit('click');
  assert.equal(client.stopped, 1);
  await tick();
  assert.match(h.elements['remi-call-status'].textContent, /Call ended/);
  assert.equal(h.elements['remi-call-overlay'].hidden, true);
  assert.equal(h.elements['remi-orb'].state, 'idle');
  assert.equal(h.elements['mute-remi'].textContent, 'Mute microphone');
  assert.equal(h.elements['mute-remi'].attributes['aria-pressed'], 'false');
  assert.equal(h.calls.filter(call => call.url === '/api/voice/release').length, 1);
});

test('unsupported local SDK still allows opening the visual preview without a call', () => {
  const h = harness({ sdk: false });
  assert.equal(h.elements['call-remi'].disabled, false);
  assert.equal(h.elements['remi-call-overlay'].hidden, true);
  h.elements['call-remi'].emit('click');
  assert.equal(h.elements['remi-call-overlay'].hidden, false);
  assert.match(h.elements['remi-call-status'].textContent, /Typed chat remains available/);
  assert.equal(h.calls.length, 0);
  h.elements['close-remi'].emit('click');
  assert.equal(h.elements['remi-call-overlay'].hidden, true);
});

test('closing the call dialog ends active audio and keeps late events ignored', async () => {
  const h = harness();
  h.elements['call-remi'].emit('click'); await tick();
  const client = h.clientRef.value;
  client.emit('call-start');
  client.emit('speech-start');
  assert.equal(h.elements['remi-orb'].state, 'speaking');
  h.elements['close-remi'].emit('click');
  assert.equal(h.elements['remi-call-overlay'].hidden, true);
  assert.equal(client.stopped, 1);
  client.emit('speech-start');
  assert.equal(h.elements['remi-orb'].state, 'idle');
});

test('Escape cancels pending setup before provider initiation', async () => {
  let resolveConfig;
  const gate = new Promise(resolve => { resolveConfig = resolve; });
  const h = harness({ configGate: gate });
  h.elements['call-remi'].emit('click');
  await tick();
  assert.equal(h.elements['remi-call-overlay'].hidden, false);
  for (const fn of h.documentListeners.keydown || []) fn({ key: 'Escape', preventDefault() {} });
  assert.equal(h.elements['remi-call-overlay'].hidden, true);
  resolveConfig();
  await tick();
  assert.equal(h.clientRef.value, null);
  assert.equal(h.calls.some(x => x.url === '/api/voice/claim'), false);
});

test('unconfigured voice route fails safely without leaving a call claim', async () => {
  const h = harness({ configStatus: 404 });
  h.elements['call-remi'].emit('click'); await tick();
  assert.match(h.elements['remi-call-status'].textContent, /not configured/);
  assert.equal(h.clientRef.value, null);
  assert.equal(h.calls.some(call => call.url === '/api/voice/claim'), false);
});

test('ending while configuration is pending prevents a later provider call', async () => {
  let resolveConfig;
  const configGate = new Promise(resolve => { resolveConfig = resolve; });
  const h = harness({ configGate });
  h.elements['call-remi'].emit('click');
  await tick();
  h.elements['end-remi'].emit('click');
  resolveConfig();
  await tick();
  await tick();
  assert.equal(h.clientRef.value, null);
  assert.equal(h.calls.some(call => call.url === '/api/voice/claim'), false);
  assert.match(h.elements['remi-call-status'].textContent, /setup stopped/);
  assert.equal(h.elements['remi-orb'].state, 'idle');
});

test('only actual assistant output maps to speaking and every failure maps back to idle', async () => {
  const h = harness();
  assert.equal(h.elements['remi-orb'].state, 'idle');
  h.elements['call-remi'].emit('click'); await tick();
  const client = h.clientRef.value;
  client.emit('call-start');
  client.emit('message', { type: 'transcript', role: 'user', transcriptType: 'final', transcript: 'My AC is broken' });
  assert.equal(h.elements['remi-orb'].state, 'listening');
  client.emit('call-start-failed', { error: 'NotAllowedError' });
  assert.equal(h.elements['remi-orb'].state, 'idle');
  assert.match(h.elements['remi-call-status'].textContent, /Microphone access was not granted/);
});

test('remote speech events drive Remi states, honor mute, and ignore events after end', async () => {
  const h = harness();
  h.elements['call-remi'].emit('click'); await tick();
  const client = h.clientRef.value;
  client.emit('call-start');
  client.emit('message', { type: 'speech-update', role: 'user', status: 'started' });
  assert.equal(h.elements['remi-orb'].state, 'listening');
  client.emit('message', { type: 'speech-update', role: 'assistant', status: 'started' });
  assert.equal(h.elements['remi-orb'].state, 'speaking');
  client.emit('message', { type: 'speech-update', role: 'assistant', status: 'stopped' });
  assert.equal(h.elements['remi-orb'].state, 'listening');
  client.emit('speech-start');
  assert.equal(h.elements['remi-orb'].state, 'speaking');
  assert.match(h.elements['remi-call-status'].textContent, /Remi is speaking/);
  client.emit('speech-end');
  assert.equal(h.elements['remi-orb'].state, 'listening');
  assert.match(h.elements['remi-call-status'].textContent, /Listening/);

  h.elements['mute-remi'].emit('click');
  assert.equal(h.elements['remi-orb'].state, 'idle');
  client.emit('speech-start');
  assert.equal(h.elements['remi-orb'].state, 'speaking');
  client.emit('speech-end');
  assert.equal(h.elements['remi-orb'].state, 'idle');
  assert.match(h.elements['remi-call-status'].textContent, /Microphone muted/);

  h.elements['end-remi'].emit('click');
  assert.equal(h.elements['remi-orb'].state, 'idle');
  const endedStatus = h.elements['remi-call-status'].textContent;
  client.emit('speech-start');
  client.emit('speech-end');
  client.emit('message', { type: 'assistant.speechStarted' });
  client.emit('message', { type: 'speech-update', role: 'assistant', status: 'started' });
  assert.equal(h.elements['remi-orb'].state, 'idle');
  assert.equal(h.elements['remi-call-status'].textContent, endedStatus);
});

test('remote call-end returns the orb to idle and rejects subsequent speech events', async () => {
  const h = harness();
  h.elements['call-remi'].emit('click'); await tick();
  const client = h.clientRef.value;
  client.emit('call-start');
  client.emit('speech-start');
  assert.equal(h.elements['remi-orb'].state, 'speaking');
  client.emit('call-end');
  assert.equal(h.elements['remi-orb'].state, 'idle');
  client.emit('speech-start');
  client.emit('speech-end');
  assert.equal(h.elements['remi-orb'].state, 'idle');
  assert.match(h.elements['remi-call-status'].textContent, /Call ended/);
});

test('microphone denial is sanitized and returns to the typed fallback', async () => {
  const h = harness();
  h.elements['call-remi'].emit('click'); await tick();
  h.clientRef.value.emit('call-start-failed', { error: 'NotAllowedError', errorStack: 'private stack' });
  assert.match(h.elements['remi-call-status'].textContent, /Microphone access was not granted/);
  assert.doesNotMatch(h.elements['remi-call-status'].textContent, /private stack|NotAllowedError/);
  assert.equal(h.elements['call-remi'].hidden, false);
});

test('call-start-failed exposes an allowlisted stage and HTTP status, never provider details', async () => {
  const h = harness();
  h.elements['call-remi'].emit('click'); await tick();
  h.clientRef.value.emit('call-start-failed', {
    stage: 'web-call-creation',
    error: 'Request failed with status code 403. authorization=private-value',
    errorStack: 'private stack and request body',
    context: { callId: 'private-call-id' },
  });
  const status = h.elements['remi-call-status'].textContent;
  assert.match(status, /could not be authorized/);
  assert.match(status, /Reference: VAPI_WEB_CALL_HTTP_403/);
  assert.doesNotMatch(status, /private-value|private stack|request body|private-call-id|status code 403/);
  assert.equal(h.elements['remi-orb'].state, 'idle');
});

test('rejected start promises show a safe diagnostic reference and preserve typed fallback', async () => {
  const h = harness({ startError: Object.assign(new Error('provider token=private-value'), { status: 429 }) });
  h.elements['call-remi'].emit('click'); await tick(); await tick();
  const status = h.elements['remi-call-status'].textContent;
  assert.match(status, /Reference: VAPI_CALL_START_HTTP_429/);
  assert.doesNotMatch(status, /private-value|provider token|Error/);
  assert.equal(h.elements['call-remi'].hidden, false);
  assert.equal(h.elements['remi-orb'].state, 'idle');
});

test('provider errors do not reveal raw exception details', async () => {
  const h = harness();
  h.elements['call-remi'].emit('click'); await tick();
  h.clientRef.value.emit('error', { type: 'network-error', message: 'token=secret' });
  assert.match(h.elements['remi-call-status'].textContent, /connection was interrupted/);
  assert.doesNotMatch(h.elements['remi-call-status'].textContent, /token=secret/);
});

test('3-minute local deadline ends the call even if provider remains connected', async () => {
  const h = harness();
  h.elements['call-remi'].emit('click'); await tick();
  const client = h.clientRef.value;
  client.emit('call-start');
  h.timers[0].fn();
  assert.equal(client.stopped, 1);
  assert.match(h.elements['remi-call-status'].textContent, /3-minute call limit/);
});

(async () => {
  for (const [name, fn] of cases) {
    await fn();
    console.log(`PASS ${name}`);
  }
  console.log(`${cases.length} Vapi Web call scenarios passed (SDK, network and microphone mocked).`);
})().catch(error => { console.error(error); process.exitCode = 1; });

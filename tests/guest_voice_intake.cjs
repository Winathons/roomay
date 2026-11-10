// Offline browser-capability and app-wiring tests. No microphone or network is used.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '..');
const assets = path.join(root, 'tools', 'guest_chat_demo_assets');
const voiceSource = fs.readFileSync(path.join(assets, 'voice_intake.js'), 'utf8');
const appSource = fs.readFileSync(path.join(assets, 'app.js'), 'utf8');
const cases = [];
function test(name, fn) { cases.push([name, fn]); }

class Element {
  constructor(id = '') {
    this.id = id; this.listeners = {}; this.attributes = {}; this.children = [];
    this.textContent = ''; this.value = ''; this.disabled = false; this.hidden = false;
    this.dataset = {}; this.scrollHeight = 0; this.scrollTop = 0;
    this.span = { textContent: '' };
  }
  addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
  emit(name, event = {}) { for (const fn of this.listeners[name] || []) fn(event); }
  setAttribute(name, value) { this.attributes[name] = value; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  querySelector(selector) { return selector === 'span' ? this.span : null; }
  focus() { this.focused = true; }
  requestSubmit() { this.emit('submit', { preventDefault() {} }); }
}

function voiceHarness(Recognition = class {}) {
  const button = new Element('voice-button');
  const input = new Element('guest-message');
  const status = new Element('voice-status');
  const windowRef = Recognition ? { SpeechRecognition: Recognition } : {};
  const api = {};
  vm.runInNewContext(voiceSource, { globalThis: api });
  const voice = api.RoomayVoiceIntake.attachVoiceIntake({ windowRef, button, input, status });
  return { button, input, status, voice };
}

class MockRecognition {
  constructor() { this.processLocally = false; this.results = []; this.startCalls = 0; this.stopCalls = 0; MockRecognition.latest = this; }
  start() { this.startCalls += 1; if (this.onstart) this.onstart(); }
  stop() { this.stopCalls += 1; }
  static available(options) {
    MockRecognition.availabilityOptions = options;
    if (MockRecognition.availabilityError) return Promise.reject(new Error('availability denied'));
    return Promise.resolve(MockRecognition.availabilityResult || 'available');
  }
}
MockRecognition.availabilityResult = 'available';
MockRecognition.availabilityError = false;
MockRecognition.availabilityOptions = null;

test('unsupported browsers keep typed input available', () => {
  const h = voiceHarness(null);
  assert.equal(h.voice.supported, false);
  assert.equal(h.button.disabled, true);
  assert.match(h.status.textContent, /Type your message/);
  h.input.value = 'Please bring towels to room 205';
  assert.equal(h.input.value.length > 0, true);
});

test('cloud-only recognizers are rejected instead of sending audio to a service', () => {
  class RemoteOnly { constructor() { this.startCalls = 0; } start() { this.startCalls += 1; } stop() {} }
  const h = voiceHarness(RemoteOnly);
  assert.equal(h.voice.supported, false);
  assert.equal(h.button.disabled, true);
  h.button.emit('click');
  assert.equal(h.status.textContent.includes('Private on-device'), true);
});

test('microphone start waits for verified local en-NG dictation and a direct button gesture', async () => {
  const h = voiceHarness(MockRecognition);
  assert.equal(h.button.disabled, true, 'voice stays disabled while pack status is checked');
  await h.voice.ready;
  const recognition = MockRecognition.latest;
  assert.equal(recognition.startCalls, 0, 'page initialization must not request microphone access');
  assert.equal(recognition.processLocally, true);
  assert.equal(recognition.lang, 'en-NG');
  assert.equal(Array.from(MockRecognition.availabilityOptions.langs).join(','), 'en-NG');
  assert.equal(MockRecognition.availabilityOptions.processLocally, true);
  assert.equal(MockRecognition.availabilityOptions.quality, 'dictation');
  assert.equal(h.button.disabled, false);
  h.button.emit('click');
  assert.equal(recognition.startCalls, 1);
  assert.equal(h.button.attributes['aria-pressed'], 'true');
  assert.match(h.status.textContent, /Listening on this device/);
});

test('denied microphone access reports a safe typed fallback', async () => {
  const h = voiceHarness(MockRecognition);
  await h.voice.ready;
  h.input.value = 'My typed note stays here';
  h.button.emit('click');
  const recognition = MockRecognition.latest;
  recognition.onerror({ error: 'not-allowed' });
  recognition.onend();
  assert.match(h.status.textContent, /permission was denied/);
  assert.equal(h.input.value, 'My typed note stays here');
  assert.equal(h.voice.voiceDraft, false);
});

test('downloadable, downloading and unavailable packs stay typed-only without installing', async () => {
  for (const [result, expected] of [
    ['downloadable', /not installed.*will not download/i],
    ['downloading', /still downloading.*did not start/i],
    ['unavailable', /dictation is unavailable/i],
  ]) {
    MockRecognition.availabilityResult = result;
    const h = voiceHarness(MockRecognition);
    await h.voice.ready;
    assert.equal(h.button.disabled, true);
    assert.match(h.status.textContent, expected);
    h.button.emit('click');
    assert.equal(MockRecognition.latest.startCalls, 0);
    assert.equal(typeof MockRecognition.latest.install, 'undefined');
  }
  MockRecognition.availabilityResult = 'available';
});

test('missing or failed availability API fails closed to typed input', async () => {
  class NoAvailability extends MockRecognition {}
  NoAvailability.available = undefined;
  const missing = voiceHarness(NoAvailability);
  await missing.voice.ready;
  assert.equal(missing.button.disabled, true);
  assert.match(missing.status.textContent, /cannot verify.*Type your message/i);

  MockRecognition.availabilityError = true;
  const failed = voiceHarness(MockRecognition);
  await failed.voice.ready;
  assert.equal(failed.button.disabled, true);
  assert.match(failed.status.textContent, /could not be verified.*Type your message/i);
  MockRecognition.availabilityError = false;
});

test('unexpected language-pack loss after availability still refuses cloud fallback', async () => {
  const h = voiceHarness(MockRecognition);
  await h.voice.ready;
  h.button.emit('click');
  const recognition = MockRecognition.latest;
  recognition.onerror({ error: 'language-not-supported' });
  recognition.onend();
  assert.equal(h.button.disabled, true);
  assert.match(h.status.textContent, /did not download one/);
  assert.equal(typeof recognition.install, 'undefined');
});

test('interrupted speech keeps partial transcript editable and unsent', async () => {
  const h = voiceHarness(MockRecognition);
  await h.voice.ready;
  h.button.emit('click');
  const recognition = MockRecognition.latest;
  recognition.onresult({ results: [{ isFinal: false, 0: { transcript: 'Abeg towels room 205' } }] });
  recognition.onerror({ error: 'aborted' });
  recognition.onend();
  assert.equal(h.input.value, 'Abeg towels room 205');
  assert.equal(h.voice.voiceDraft, true);
  assert.match(h.status.textContent, /partial transcript/);
  h.input.value = 'Edited text';
  assert.equal(h.input.value, 'Edited text');
});

test('a second recording appends to an edited transcript without replacing it', async () => {
  const h = voiceHarness(MockRecognition);
  await h.voice.ready;
  h.button.emit('click');
  let recognition = MockRecognition.latest;
  recognition.onresult({ results: [{ isFinal: true, 0: { transcript: 'bring towels' } }] });
  recognition.onend();
  h.input.value = 'Please bring two clean towels to my room.';

  h.button.emit('click');
  recognition = MockRecognition.latest;
  assert.equal(recognition.startCalls, 2);
  assert.match(h.status.textContent, /Existing text is being kept/);
  recognition.onresult({ results: [{ isFinal: true, 0: { transcript: 'before dinner' } }] });
  assert.equal(h.input.value, 'Please bring two clean towels to my room. before dinner');
  recognition.onend();
  assert.equal(h.input.value, 'Please bring two clean towels to my room. before dinner');
  assert.equal(h.voice.voiceDraft, true);
});

test('empty recognition leaves no transcript to submit', async () => {
  const h = voiceHarness(MockRecognition);
  await h.voice.ready;
  h.input.value = 'Existing typed request';
  h.button.emit('click');
  MockRecognition.latest.onend();
  assert.equal(h.input.value, 'Existing typed request');
  assert.equal(h.voice.voiceDraft, false);
  assert.match(h.status.textContent, /No clear speech/);
});

test('overlong transcript is shown for editing rather than silently truncated', async () => {
  const h = voiceHarness(MockRecognition);
  await h.voice.ready;
  h.button.emit('click');
  const text = 'x'.repeat(1001);
  MockRecognition.latest.onresult({ results: [{ isFinal: true, 0: { transcript: text } }] });
  MockRecognition.latest.onend();
  assert.equal(h.input.value.length, 1001);
  assert.match(h.status.textContent, /longer than 1,000 characters/);
});

function makeAppHarness({ Recognition = MockRecognition } = {}) {
  const ids = ['messages', 'chat-form', 'guest-message', 'send-button', 'voice-button',
    'voice-status', 'confirmation', 'feedback'];
  const elements = Object.fromEntries(ids.map(id => [id, new Element(id)]));
  const calls = [];
  let releaseMessage;
  const payload = (value) => ({ ok: true, status: 200, json: async () => value });
  const fetchMock = (url, options) => {
    calls.push({ url, options });
    if (url === '/api/session') return Promise.resolve(payload({ messages: [], state: 'ready', pending: null, submitted: false, persisted: false }));
    if (url === '/api/message') return new Promise(resolve => { releaseMessage = () => resolve(payload({ messages: [{ role: 'guest', text: JSON.parse(options.body).text }, { role: 'assistant', text: 'Review this offline proposal.' }], state: 'awaiting_confirmation', pending: null, submitted: false, persisted: false })); });
    throw new Error('unexpected endpoint');
  };
  const document = {
    getElementById: id => elements[id],
    createElement: () => new Element(),
    querySelectorAll: () => [],
  };
  const windowRef = { SpeechRecognition: Recognition };
  const context = { document, fetch: fetchMock, globalThis: null, console, Promise, setTimeout };
  Object.assign(context, windowRef);
  context.globalThis = context;
  vm.runInNewContext(voiceSource, context);
  vm.runInNewContext(appSource, context);
  return { elements, calls, get recognition() { return MockRecognition.latest; }, releaseMessage, getRelease: () => releaseMessage };
}

test('edited transcript is explicitly sent once through the existing typed-intake endpoint', async () => {
  const h = makeAppHarness();
  await new Promise(resolve => setTimeout(resolve, 0));
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(h.recognition.startCalls, 0);
  h.elements['voice-button'].emit('click');
  h.recognition.onresult({ results: [{ isFinal: true, 0: { transcript: 'rough transcript' } }] });
  h.recognition.onend();
  assert.equal(h.calls.filter(call => call.url === '/api/message').length, 0, 'recognition must never auto-submit');
  assert.equal(h.elements['send-button'].span.textContent, 'Send reviewed transcript');
  h.elements['guest-message'].value = 'Please bring extra towels to room 205.';
  h.elements['chat-form'].emit('submit', { preventDefault() {} });
  h.elements['chat-form'].emit('submit', { preventDefault() {} });
  assert.equal(h.calls.filter(call => call.url === '/api/message').length, 1, 'busy gate prevents duplicate submission');
  assert.deepEqual(JSON.parse(h.calls.find(call => call.url === '/api/message').options.body), { text: 'Please bring extra towels to room 205.' });
  h.getRelease()();
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(h.elements['guest-message'].value, '');
  assert.equal(h.elements['messages'].children.length, 2);
});

test('malformed overlong recognized content is blocked before request intake', async () => {
  const h = makeAppHarness();
  await new Promise(resolve => setTimeout(resolve, 0));
  await new Promise(resolve => setTimeout(resolve, 0));
  h.elements['voice-button'].emit('click');
  h.recognition.onresult({ results: [{ isFinal: true, 0: { transcript: 'z'.repeat(1001) } }] });
  h.recognition.onend();
  h.elements['chat-form'].emit('submit', { preventDefault() {} });
  assert.equal(h.calls.filter(call => call.url === '/api/message').length, 0);
  assert.match(h.elements.feedback.textContent, /1,000 characters or fewer/);
});

test('unsupported browser keeps the actual chat composer working', async () => {
  const h = makeAppHarness({ Recognition: null });
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(h.elements['voice-button'].disabled, true);
  assert.match(h.elements['voice-status'].textContent, /Type your message/);
  h.elements['guest-message'].value = 'Please bring extra towels to room 205.';
  h.elements['chat-form'].emit('submit', { preventDefault() {} });
  assert.equal(h.calls.filter(call => call.url === '/api/message').length, 1);
  assert.deepEqual(JSON.parse(h.calls.find(call => call.url === '/api/message').options.body), { text: 'Please bring extra towels to room 205.' });
  h.getRelease()();
  await new Promise(resolve => setTimeout(resolve, 0));
});

(async () => {
  for (const [name, fn] of cases) {
    await fn();
    console.log(`PASS ${name}`);
  }
  console.log(`${cases.length} guest voice intake browser scenarios passed (microphone and network mocked).`);
})().catch(error => { console.error(error); process.exitCode = 1; });

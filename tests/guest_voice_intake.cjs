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
  const cancelButton = new Element('voice-cancel');
  cancelButton.hidden = true;
  const remoteConsent = new Element('voice-remote-consent');
  remoteConsent.checked = false;
  const consentDialog = new Element('voice-remote-dialog');
  consentDialog.hidden = true;
  const consentAllow = new Element('voice-remote-allow');
  const consentCancel = new Element('voice-remote-cancel');
  const windowRef = Recognition ? { SpeechRecognition: Recognition } : {};
  const api = {};
  vm.runInNewContext(voiceSource, { globalThis: api });
  const voice = api.RoomayVoiceIntake.attachVoiceIntake({
    windowRef, button, cancelButton, input, status, remoteConsent,
    consentDialog, consentAllow, consentCancel,
  });
  return { button, cancelButton, input, status, remoteConsent, consentDialog, consentAllow, consentCancel, voice };
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

test('browser speech service stays off until the guest opts in', async () => {
  class RemoteOnly { constructor() { this.startCalls = 0; RemoteOnly.latest = this; } start() { this.startCalls += 1; } stop() {} }
  const h = voiceHarness(RemoteOnly);
  await h.voice.ready;
  assert.equal(h.voice.supported, false);
  assert.equal(h.button.disabled, false, 'microphone remains discoverable');
  assert.equal(RemoteOnly.latest?.startCalls || 0, 0);
  h.button.emit('click');
  assert.equal(h.consentDialog.hidden, false);
  assert.equal(RemoteOnly.latest.startCalls, 0, 'no capture before provider consent');
  h.consentCancel.emit('click');
  assert.equal(h.consentDialog.hidden, true);
  assert.equal(RemoteOnly.latest.startCalls, 0);
  h.button.emit('click');
  h.consentAllow.emit('click');
  assert.equal(h.consentDialog.hidden, true);
  assert.equal(RemoteOnly.latest.startCalls, 1);
  assert.match(h.status.textContent, /browser['’]s speech service/i);
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
  assert.equal(h.remoteConsent.checked, false, 'remote provider consent defaults off');
  h.button.emit('click');
  assert.equal(recognition.startCalls, 1);
  assert.equal(h.button.attributes['aria-pressed'], 'true');
  assert.match(h.status.textContent, /Listening on this device/);
});

test('verified local recognition remains preferred when remote consent is checked', async () => {
  const h = voiceHarness(MockRecognition);
  await h.voice.ready;
  h.remoteConsent.checked = true;
  h.remoteConsent.emit('change');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.button.disabled, false);
  h.button.emit('click');
  assert.equal(MockRecognition.latest.processLocally, true);
  assert.equal(MockRecognition.latest.startCalls, 1);
  assert.match(h.status.textContent, /Listening on this device/i);
  assert.doesNotMatch(h.status.textContent, /audio may be sent to its provider/i);
});

test('legacy remote-only browser with opt-in reports browser-managed processing', async () => {
  class LegacyRemoteRecognition {
    constructor() { this.startCalls = 0; LegacyRemoteRecognition.latest = this; }
    start() { this.startCalls += 1; if (this.onstart) this.onstart(); }
    stop() {}
    static available(options) { return Promise.resolve(options.processLocally ? 'unavailable' : 'available'); }
  }
  const h = voiceHarness(LegacyRemoteRecognition);
  await h.voice.ready;
  assert.equal(h.button.disabled, false);
  h.input.value = 'Please bring towels';
  h.remoteConsent.checked = true;
  h.remoteConsent.emit('change');
  await new Promise(resolve => setImmediate(resolve));
  h.button.emit('click');
  assert.equal(LegacyRemoteRecognition.latest.startCalls, 1);
  assert.match(h.status.textContent, /browser['’]s speech service/i);
  assert.doesNotMatch(h.status.textContent, /Listening on this device/i);
  assert.equal(h.input.value, 'Please bring towels');
});

test('remote consent unchecked or revoked never enables remote-only recognition', async () => {
  class RemoteOnlyRecognition {
    constructor() { this.startCalls = 0; RemoteOnlyRecognition.latest = this; }
    start() { this.startCalls += 1; }
    stop() {}
    static available(options) { return Promise.resolve(options.processLocally ? 'unavailable' : 'available'); }
  }
  const h = voiceHarness(RemoteOnlyRecognition);
  await h.voice.ready;
  h.input.value = 'Keep my typed request';
  h.button.emit('click');
  assert.equal(RemoteOnlyRecognition.latest.startCalls, 0);
  h.remoteConsent.checked = true;
  h.remoteConsent.emit('change');
  await new Promise(resolve => setImmediate(resolve));
  h.remoteConsent.checked = false;
  h.remoteConsent.emit('change');
  h.button.emit('click');
  assert.equal(RemoteOnlyRecognition.latest.startCalls, 0);
  assert.equal(h.consentDialog.hidden, false);
  h.consentCancel.emit('click');
  assert.equal(h.input.value, 'Keep my typed request');
  assert.match(h.status.textContent, /cancelled/i);
});

test('microphone capture failure preserves the typed message', async () => {
  const h = voiceHarness(MockRecognition);
  h.input.value = 'My existing typed request';
  await h.voice.ready;
  h.button.emit('click');
  MockRecognition.latest.onerror({ error: 'audio-capture' });
  MockRecognition.latest.onend();
  assert.equal(h.input.value, 'My existing typed request');
  assert.match(h.status.textContent, /microphone is unavailable/i);
});

test('microphone stays disabled until the opted-in remote availability check completes', async () => {
  const oldAvailable = MockRecognition.available;
  let resolveRemote;
  MockRecognition.available = options => options.processLocally
    ? Promise.resolve('available')
    : new Promise(resolve => { resolveRemote = resolve; });
  const h = voiceHarness(MockRecognition);
  await h.voice.ready;
  h.remoteConsent.checked = true;
  h.remoteConsent.emit('change');
  assert.equal(h.button.disabled, true);
  h.button.emit('click');
  assert.equal(MockRecognition.latest.startCalls, 0);
  resolveRemote('available');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.button.disabled, false);
  h.button.emit('click');
  assert.equal(MockRecognition.latest.processLocally, true, 'verified local mode wins after the remote check completes');
  MockRecognition.available = oldAvailable;
});

test('browser provider unavailable after opt-in keeps typed input and does not start recognition', async () => {
  const oldAvailable = MockRecognition.availabilityResult;
  MockRecognition.availabilityResult = 'unavailable';
  const h = voiceHarness(MockRecognition);
  await h.voice.ready;
  h.remoteConsent.checked = true;
  h.remoteConsent.emit('change');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.button.disabled, false);
  assert.match(h.status.textContent, /browser speech service is unavailable/i);
  h.button.emit('click');
  assert.equal(MockRecognition.latest.startCalls, 0);
  assert.equal(h.consentDialog.hidden, false);
  h.consentCancel.emit('click');
  MockRecognition.availabilityResult = oldAvailable;
});

test('guest can stop recognition and keep its partial transcript for review', async () => {
  const h = voiceHarness(MockRecognition);
  await h.voice.ready;
  h.button.emit('click');
  const recognition = MockRecognition.latest;
  recognition.onresult({ results: [{ isFinal: false, 0: { transcript: 'bring towels please' } }] });
  h.button.emit('click');
  assert.equal(recognition.stopCalls, 1);
  recognition.onend();
  assert.equal(h.input.value, 'bring towels please');
  assert.equal(h.voice.voiceDraft, true);
  assert.match(h.status.textContent, /transcript ready to review/i);
});

test('discarding a voice draft restores the typed text that preceded recording', async () => {
  const h = voiceHarness(MockRecognition);
  h.input.value = 'The AC in my room is not cooling.';
  await h.voice.ready;
  h.button.emit('click');
  MockRecognition.latest.onresult({ results: [{ isFinal: true, 0: { transcript: 'please check it before dinner' } }] });
  MockRecognition.latest.onend();
  assert.equal(h.input.value, 'The AC in my room is not cooling. please check it before dinner');
  h.voice.discardDraft();
  assert.equal(h.input.value, 'The AC in my room is not cooling.');
  assert.equal(h.voice.voiceDraft, false);
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
    assert.equal(h.button.disabled, false);
    assert.match(h.status.textContent, expected);
    h.button.emit('click');
    assert.equal(h.consentDialog.hidden, false);
    assert.equal(MockRecognition.latest.startCalls, 0);
    h.consentCancel.emit('click');
    assert.equal(typeof MockRecognition.latest.install, 'undefined');
  }
  MockRecognition.availabilityResult = 'available';
});

test('missing or failed availability API fails closed to typed input', async () => {
  class NoAvailability extends MockRecognition {}
  NoAvailability.available = undefined;
  const missing = voiceHarness(NoAvailability);
  await missing.voice.ready;
  assert.equal(missing.button.disabled, false);
  assert.match(missing.status.textContent, /Press the microphone/i);

  MockRecognition.availabilityError = true;
  const failed = voiceHarness(MockRecognition);
  await failed.voice.ready;
  assert.equal(failed.button.disabled, false);
  assert.match(failed.status.textContent, /could not be verified.*Press the microphone/i);
  MockRecognition.availabilityError = false;
});

test('unexpected language-pack loss after availability still refuses cloud fallback', async () => {
  const h = voiceHarness(MockRecognition);
  await h.voice.ready;
  h.button.emit('click');
  const recognition = MockRecognition.latest;
  recognition.onerror({ error: 'language-not-supported' });
  recognition.onend();
  assert.equal(h.button.disabled, false);
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
  const ids = ['messages', 'chat-form', 'guest-message', 'send-button', 'voice-button', 'voice-cancel',
    'voice-status', 'voice-remote-consent', 'voice-remote-dialog', 'voice-remote-allow', 'voice-remote-cancel',
    'confirmation', 'feedback'];
  const elements = Object.fromEntries(ids.map(id => [id, new Element(id)]));
  elements['voice-cancel'].hidden = true;
  elements['voice-remote-dialog'].hidden = true;
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

test('composer discard control cancels the recognized addition without sending it', async () => {
  const h = makeAppHarness();
  await new Promise(resolve => setTimeout(resolve, 0));
  await new Promise(resolve => setTimeout(resolve, 0));
  h.elements['guest-message'].value = 'My AC is not cooling.';
  h.elements['voice-button'].emit('click');
  h.recognition.onresult({ results: [{ isFinal: true, 0: { transcript: 'Please check it.' } }] });
  h.recognition.onend();
  assert.equal(h.elements['voice-cancel'].hidden, false);
  h.elements['voice-cancel'].emit('click');
  assert.equal(h.elements['guest-message'].value, 'My AC is not cooling.');
  assert.equal(h.elements['voice-cancel'].hidden, true);
  assert.equal(h.calls.filter(call => call.url === '/api/message').length, 0);
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

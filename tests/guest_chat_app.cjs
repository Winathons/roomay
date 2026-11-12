// Browser-controller regression tests for the real guest chat app.js.
// No network, providers, credentials, or hotel writes are used.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const source = fs.readFileSync(path.join(__dirname, '..', 'tools', 'guest_chat_demo_assets', 'app.js'), 'utf8');
const cases = [];
function test(name, fn) { cases.push([name, fn]); }

class Element {
  constructor(id = '') {
    this.id = id; this.listeners = {}; this.children = []; this.attributes = {};
    this.hidden = false; this.disabled = false; this.checked = false;
    this.textContent = ''; this.value = ''; this.scrollHeight = 48; this.scrollTop = 0;
    this.style = {}; this.dataset = {}; this.className = '';
    this.classList = { add: (...names) => { this.className += ` ${names.join(' ')}`; } };
    this.span = new ElementSpan();
  }
  addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
  async emit(name, event = {}) { for (const fn of this.listeners[name] || []) await fn(event); }
  setAttribute(key, value) { this.attributes[key] = value; }
  append(...values) { this.children.push(...values); }
  replaceChildren(...values) { this.children = [...values]; }
  querySelector(selector) { return selector === 'span' ? this.span : null; }
  dispatchEvent() {}
  focus() {}
}
class ElementSpan { constructor() { this.textContent = ''; } }

function guestView(messages = [{ role: 'assistant', text: 'Welcome to Roomay.' }], overrides = {}) {
  return {
    workspace: 'guest', property_name: 'The Linden House', example_property: true,
    guest: { name: 'Amara Okafor', room: '205', room_type: 'Classic Queen',
      check_in: '2026-11-12', check_out: '2026-11-13', stay_status: 'checked_in',
      reservation_status: 'confirmed' },
    requests: [], reception_contact: { message: 'Contact Reception for help.' },
    chat: { messages, pending: null, state: 'ready', submitted: false, persisted: false,
      ai_chat: { available: false, consented: false, status: 'disabled' } },
    ...overrides,
  };
}

function harness({ failure = null } = {}) {
  const ids = ['feedback', 'messages', 'chat-form', 'guest-message', 'send-button',
    'voice-button', 'voice-cancel', 'voice-status', 'voice-remote-consent', 'confirmation',
    'chat-ai-consent', 'chat-ai-enabled', 'chat-ai-status', 'guest-name', 'guest-room',
    'guest-room-type', 'guest-check-in', 'guest-check-out', 'guest-stay-status',
    'guest-reservation-status', 'reception-contact', 'guest-requests', 'call-remi',
    'remi-call-overlay', 'remi-orb', 'voice-remote-dialog', 'voice-remote-allow'];
  const elements = Object.fromEntries(ids.map(id => [id, new Element(id)]));
  elements['send-button'].span = new ElementSpan();
  elements['remi-call-overlay'].hidden = true;
  const calls = [];
  const documentRef = {
    body: { dataset: { workspace: 'guest' } },
    getElementById: id => elements[id] || null,
    createElement: tag => new Element(tag),
  };
  const fetch = async (url, options) => {
    const body = options?.body ? JSON.parse(options.body) : {};
    calls.push({ url, body });
    if (url === '/api/session') return { ok: true, status: 200, json: async () => guestView() };
    if (url === '/api/message') {
      if (failure === 'network') throw new TypeError('Failed to fetch');
      if (failure === 'http') return { ok: false, status: 503,
        json: async () => ({ error: 'demo_temporarily_unavailable' }) };
      return { ok: true, status: 200, json: async () => guestView([
        { role: 'assistant', text: 'Welcome to Roomay.' },
        { role: 'guest', text: body.text },
        { role: 'assistant', text: 'Hello! I’m here to help with your stay. What would you like to talk about?' },
      ]) };
    }
    throw new Error(`Unexpected endpoint: ${url}`);
  };
  const context = { document: documentRef, fetch, console, Intl, Date, JSON,
    Event: class Event { constructor(type) { this.type = type; } } };
  context.globalThis = context;
  vm.runInNewContext(source, context);
  return { elements, calls };
}

async function settle() { await new Promise(resolve => setImmediate(resolve)); }

test('successful chat renders both messages and clears the composer', async () => {
  const { elements, calls } = harness();
  await settle();
  elements['guest-message'].value = 'Hey Hi';
  await elements['chat-form'].emit('submit', { preventDefault() {} });
  const rendered = elements.messages.children.map(row => row.children[1].textContent);
  assert.deepEqual(calls.map(call => call.url), ['/api/session', '/api/message']);
  assert.equal(calls[1].body.text, 'Hey Hi');
  assert(rendered.includes('Hey Hi'));
  assert(rendered.some(text => text.includes('Hello!')));
  assert.equal(elements['guest-message'].value, '');
  assert.equal(elements.feedback.textContent, '');
});

test('network failure uses message copy and preserves composer contents', async () => {
  const { elements } = harness({ failure: 'network' });
  await settle();
  elements['guest-message'].value = 'Hey Hi';
  await elements['chat-form'].emit('submit', { preventDefault() {} });
  assert.equal(elements['guest-message'].value, 'Hey Hi');
  assert.match(elements.feedback.textContent, /couldn’t send your message/i);
  assert.match(elements.feedback.textContent, /text is still here/i);
  assert.doesNotMatch(elements.feedback.textContent, /update this request/i);
});

test('HTTP failure uses message copy and preserves composer contents', async () => {
  const { elements } = harness({ failure: 'http' });
  await settle();
  elements['guest-message'].value = 'Hey Hi';
  await elements['chat-form'].emit('submit', { preventDefault() {} });
  assert.equal(elements['guest-message'].value, 'Hey Hi');
  assert.match(elements.feedback.textContent, /couldn’t send your message/i);
  assert.match(elements.feedback.textContent, /text is still here/i);
  assert.doesNotMatch(elements.feedback.textContent, /update this request/i);
});

(async () => {
  for (const [name, fn] of cases) {
    try { await fn(); }
    catch (error) { console.error(`FAIL ${name}: ${error.stack}`); process.exitCode = 1; }
  }
  if (!process.exitCode) console.log(`${cases.length} guest chat browser-controller scenarios passed`);
})();

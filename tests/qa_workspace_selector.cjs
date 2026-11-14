// Controller regression for the internal local multi-browser selector.
// This mocks only browser APIs; shared-state semantics are tested over HTTP in Python.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

class Element {
  constructor(dataset = {}) {
    this.dataset = dataset;
    this.listeners = {};
    this.disabled = false;
    this.value = '';
    this.textContent = '';
    this.selected = false;
  }
  addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); }
  async click() { for (const callback of this.listeners.click || []) await callback(); }
  focus() {}
  select() { this.selected = true; }
}

async function main() {
  const feedback = new Element();
  const code = new Element();
  const create = new Element();
  const roles = ['guest', 'reception', 'housekeeping'].map(role =>
    Object.assign(new Element({ role }), { dataset: { role } }));
  const requests = [];
  let navigation = null;
  const document = {
    getElementById(id) {
      return ({ 'qa-feedback': feedback, 'scenario-code': code,
        'create-scenario': create })[id];
    },
    querySelectorAll(selector) { assert.equal(selector, '[data-role]'); return roles; },
  };
  const fetch = async (url, options) => {
    requests.push({ url, body: JSON.parse(options.body) });
    if (url === '/api/qa/scenario')
      return { ok: true, json: async () => ({ scenario_code: 'test-only-code' }) };
    if (url === '/api/qa/select')
      return { ok: true, json: async () => ({ path: '/staff/reception' }) };
    throw new Error('unexpected endpoint');
  };
  const context = { document, fetch, location: { assign: value => { navigation = value; } } };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..',
    'tools', 'guest_chat_demo_assets', 'qa.js'), 'utf8'), context);

  await roles[1].click();
  assert.match(feedback.textContent, /Create a local scenario/);
  assert.equal(requests.length, 0);

  await create.click();
  assert.equal(code.value, 'test-only-code');
  assert.equal(code.selected, true);
  await roles[1].click();
  assert.equal(requests[1].url, '/api/qa/select');
  assert.deepEqual(requests[1].body, { role: 'reception', scenario_code: 'test-only-code' });
  assert.equal(navigation, '/staff/reception');
  console.log('PASS QA selector creates shared code and opens an independent role session');
}

main().catch(error => { console.error(error); process.exitCode = 1; });

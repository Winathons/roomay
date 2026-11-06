// Executes the generated controller and real SDK collection helpers, offline.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
globalThis.window = globalThis;
globalThis.addEventListener = () => {};
globalThis.fetch = () => { throw new Error('NETWORK FORBIDDEN IN TESTS'); };
const output = process.argv[2];
vm.runInThisContext(fs.readFileSync(path.join(output, 'workpeg-runtime.js'), 'utf8'));
vm.runInThisContext(fs.readFileSync(path.join(output, 'app.js'), 'utf8') + '\nglobalThis.Smoke = DevSmoke;');
Workpeg.stateHandler = () => ({}); // rendering is tested separately, no browser DOM here
Workpeg.setInterval = () => {};
const business = '00000000-0000-4000-8000-000000000028';
const tableId = '00000000-0000-4000-8000-000000000201';
Workpeg.routeParam = () => business;
const table = () => ({uuid: tableId, name: 'Roomay Dev Smoke', namespace: 'roomay_smoke',
  permission: '700', columns: [
    {id: 'room_number', type: 'text'}, {id: 'status', type: 'text'},
  ]});
const row = (status = 'ready') => ({id: 201, data: {room_number: '201', status}});
const clone = value => JSON.parse(JSON.stringify(value));
let calls;
function setup(tables = [table()], rows = []) {
  calls = [];
  let remoteTables = clone(tables), remoteRows = clone(rows);
  Workpeg.wpGetTables = async namespace => {
    calls.push(['tables', namespace]); assert.equal(namespace, 'roomay_smoke');
    return clone(remoteTables);
  };
  Workpeg.wpCreateTable = async payload => {
    calls.push(['createTable', clone(payload)]);
    assert.equal(payload.permission, '700');
    assert.equal(payload.alias, 'roomay-dev-smoke-v1');
    remoteTables = [table()]; return table();
  };
  Workpeg.wpGetRows = async (id, paging) => {
    calls.push(['rows', id]); assert.equal(id, tableId);
    assert.deepEqual(paging, {limit: 2, offset: 0}); return clone(remoteRows);
  };
  Workpeg.wpAddRow = async (id, payload) => {
    calls.push(['insert', clone(payload)]); assert.equal(id, tableId);
    remoteRows = [{id: 201, data: clone(payload.data)}]; return clone(remoteRows[0]);
  };
  Workpeg.wpUpdateRow = async (id, rowId, payload) => {
    calls.push(['update', clone(payload)]); assert.equal(id, tableId); assert.equal(rowId, 201);
    remoteRows = [{id: rowId, data: clone(payload.data)}]; return clone(remoteRows[0]);
  };
  const app = new Smoke();
  app.state.expected_business = business;
  app.state.consent = 'Roomay AI single operator';
  return app;
}
const writes = () => calls.filter(c => ['createTable', 'insert', 'update'].includes(c[0]));
const cases = [];
const test = (name, fn) => cases.push([name, fn]);

test('mount and build perform no table calls', async () => {
  const app = setup(); app.on_mount(); app.build(); assert.equal(calls.length, 0);
});
test('missing/mismatched business and missing confirmation fail before any request', async () => {
  const app = setup(); app.state.expected_business = 'other'; await app.create_table();
  assert.equal(calls.length, 0); assert.match(app.state.failure, /context mismatch/);
  app.state.expected_business = business; app.state.consent = ''; await app.check_connection();
  assert.equal(calls.length, 0);
});
test('connection check finds absence without writing', async () => {
  const app = setup([]); await app.check_connection();
  assert.match(app.state.table_status, /No visible/); assert.equal(writes().length, 0);
  assert.match(app.state.context, /Authenticated table read succeeded/);
});
test('table creation has restrictive permissions and verified read-back', async () => {
  const app = setup([]); await app.create_table();
  assert.equal(writes().length, 1); assert.equal(app.state.failure, '');
  assert.match(app.state.last_success, /Table created and read back/);
  await app.create_table(); assert.equal(writes().length, 1);
});
test('duplicate tables stop without choosing one', async () => {
  const app = setup([table(), table()]); await app.create_table();
  assert.match(app.state.failure, /Multiple smoke tables/); assert.equal(writes().length, 0);
});
test('unexpected permissions/schema/namespace fail closed', async () => {
  for (const change of [{permission:'777'}, {columns:[]}, {namespace:'production'}, {uuid:null}, {uuid:'x'.repeat(36)}]) {
    const app = setup([{...table(), ...change}]); await app.create_room();
    assert.ok(app.state.failure); assert.equal(writes().length, 0);
  }
});
test('room create is separate and repeat clicks do not duplicate', async () => {
  const app = setup(); await app.create_room();
  assert.equal(app.state.failure, ''); assert.match(app.state.room_status, /201: ready/);
  await app.create_room(); assert.equal(writes().length, 1);
  assert.equal(writes()[0][1].inherit_individual_permissions, false);
});
test('fresh instance reads remote record, not local state', async () => {
  const app = setup([table()], [row('dirty')]); await app.read_saved();
  assert.match(app.state.room_status, /201: dirty/); assert.equal(writes().length, 0);
});
test('update preserves unrelated nested data and never resets dirty', async () => {
  const existing = row(); existing.data.extra = {fictional: ['keep', 2]};
  const app = setup([table()], [existing]); await app.mark_dirty();
  assert.equal(app.state.failure, ''); assert.match(app.state.room_status, /201: dirty/);
  assert.deepEqual(writes()[0][1].data, {...existing.data, status:'dirty'});
  await app.mark_dirty(); assert.equal(writes().length, 1);
});
test('duplicate or unexpected rows block insertion and update', async () => {
  for (const rows of [[row(), row()], [{id:1,data:{room_number:'999',status:'ready'}}]]) {
    const app = setup([table()], rows); await app.create_room(); await app.mark_dirty();
    assert.ok(app.state.failure); assert.equal(writes().length, 0);
  }
});
test('malformed reads never establish absence', async () => {
  for (const bad of [null, {}, 'bad', [null]]) {
    const app = setup(); Workpeg.wpGetRows = async () => bad;
    await app.create_room(); assert.ok(app.state.failure); assert.equal(writes().length, 0);
  }
  const app = setup(); Workpeg.wpGetTables = async () => ({results: []});
  await app.create_table(); assert.ok(app.state.failure); assert.equal(writes().length, 0);
});
test('401/403 are explicit and raw server text is never displayed', async () => {
  for (const status of [401, 403]) {
    const app = setup(); Workpeg.wpGetTables = async () => { throw new Error(`HTTP ${status}: SECRET_SENTINEL`); };
    await app.check_connection(); assert.ok(app.state.failure.includes(String(status)));
    assert.ok(!JSON.stringify(app.state).includes('SECRET_SENTINEL')); assert.equal(writes().length, 0);
  }
});
test('failed writes lock retries, retain last success and make no success claim', async () => {
  for (const action of ['create_table', 'create_room', 'mark_dirty']) {
    const app = setup(action === 'create_table' ? [] : [table()], action === 'mark_dirty' ? [row()] : []);
    app.state.last_success = 'Earlier read';
    const fail = async () => { throw new Error('HTTP 500 SECRET_SENTINEL'); };
    Workpeg.wpCreateTable = fail; Workpeg.wpAddRow = fail; Workpeg.wpUpdateRow = fail;
    await app[action](); assert.equal(app.state.uncertain, true);
    assert.equal(app.state.last_success, 'Earlier read'); assert.ok(!app.state.failure.includes('SECRET_SENTINEL'));
    const count = calls.length; await app[action](); assert.equal(calls.length, count);
  }
});
test('success response without matching read-back is not success', async () => {
  const app = setup(); Workpeg.wpAddRow = async () => row();
  await app.create_room(); assert.match(app.state.failure, /not confirmed/);
  assert.equal(app.state.uncertain, true); assert.equal(app.state.last_success, 'None');
});
test('malformed write response locks further writes', async () => {
  const app = setup(); Workpeg.wpAddRow = async () => null;
  await app.create_room(); assert.ok(app.state.failure); assert.equal(app.state.uncertain, true);
});
test('busy guard prevents simultaneous clicks and timeout ignores late response', async () => {
  const app = setup([]); let resolve;
  Workpeg.wpGetTables = () => new Promise(r => { resolve = r; });
  const pending = app.create_table(); await app.create_table();
  for (let i = 0; i < 30; i++) app.watch_timeout();
  assert.equal(app.state.timed_out, true); assert.equal(app.state.busy, true);
  resolve([]); await pending;
  assert.equal(writes().length, 0); assert.match(app.state.failure, /Timed out/);
  assert.equal(app.state.last_success, 'None');
});
test('write timeout cannot be treated as cancellation or retried', async () => {
  const app = setup(); let resolve;
  Workpeg.wpAddRow = () => new Promise(r => { resolve = r; });
  const pending = app.create_room();
  await new Promise(r => setImmediate(r));
  for (let i = 0; i < 30; i++) app.watch_timeout();
  resolve(row()); await pending;
  assert.equal(app.state.uncertain, true); assert.equal(app.state.last_success, 'None');
  assert.match(app.state.failure, /Timed out/); assert.equal(app.state.busy, true);
});
(async () => {
  for (const [name, fn] of cases) { await fn(); console.log('PASS ' + name); }
  console.log(`${cases.length} compiled UI scenarios passed (network forbidden).`);
})().catch(error => { console.error(error); process.exitCode = 1; });

// Exercises the generated dev-only controller; all Workpeg responses are mocked.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

globalThis.window = globalThis;
globalThis.document = {getElementById: () => ({})};
let loadHandler;
globalThis.addEventListener = (event, handler) => { if (event === 'load') loadHandler = handler; };
globalThis.fetch = () => { throw new Error('NETWORK FORBIDDEN IN TESTS'); };
const output = process.argv[2];
vm.runInThisContext(fs.readFileSync(path.join(output, 'workpeg-runtime.js'), 'utf8'));
let registeredRoutes;
Workpeg.router = routes => { registeredRoutes = routes; };
vm.runInThisContext(fs.readFileSync(path.join(output, 'app.js'), 'utf8'));
assert.equal(typeof loadHandler, 'function');
loadHandler();
assert.ok(Array.isArray(registeredRoutes), 'compiled dev-only router registers');
const setupRoute = registeredRoutes.find(item => item.path === '/b/[business_id]/dev-table-setup');
assert.ok(setupRoute, 'dedicated route is registered in this isolated build');
const Setup = setupRoute.app;
Workpeg.stateHandler = () => ({});
Workpeg.setInterval = () => {};

const business = '00000000-0000-4000-8000-000000000029';
const tableUuid = '00000000-0000-4000-8000-000000000201';
let routeBusiness = business;
Workpeg.routeParam = () => routeBusiness;
const expectedPayload = {
  name: 'room_types', alias: 'roomay-hotel-v1-room-types',
  namespace: 'roomay_hotel_v1', permission: '700',
  metadata: {extra: {contract: 'roomay.hotel.v1'}},
  columns: [
    {id: 'business_id', name: 'business_id', type: 'uuid', required: true, position: 500},
    {id: 'entity_id', name: 'entity_id', type: 'uuid', required: true, position: 1000},
    {id: 'name', name: 'name', type: 'text', required: true, position: 2000},
    {id: 'capacity', name: 'capacity', type: 'number', required: true, position: 3000},
  ],
};
const table = (overrides = {}) => ({
  uuid: tableUuid, name: 'room_types', namespace: 'roomay_hotel_v1',
  permission: '700', owner: {id: 42}, metadata: {extra: {contract: 'roomay.hotel.v1'}},
  columns: expectedPayload.columns.map(column => ({...column, options: {}, metadata: {}})),
  ...overrides,
});
const clone = value => JSON.parse(JSON.stringify(value));
let calls;
let hotelTables;
let requestTables;
let createdTable;

function setup({hotel = [], requests = []} = {}) {
  routeBusiness = business;
  calls = [];
  hotelTables = clone(hotel);
  requestTables = clone(requests);
  createdTable = null;
  Workpeg.wpGetTables = async namespace => {
    calls.push(['get_tables', namespace]);
    if (namespace === 'roomay_hotel_v1') return clone(hotelTables);
    if (namespace === 'roomay_requests_v1') return clone(requestTables);
    throw new Error('unexpected namespace');
  };
  Workpeg.wpGetTable = async uuid => {
    calls.push(['get_table', uuid]);
    return createdTable ? clone(createdTable) : null;
  };
  Workpeg.wpCreateTable = async payload => {
    calls.push(['create_table', clone(payload)]);
    createdTable = table();
    hotelTables.push(clone(createdTable));
    return clone(createdTable);
  };
  Workpeg.wpAddRow = async () => { throw new Error('TABLE-ONLY FLOW MUST NOT ADD ROWS'); };
  Workpeg.wpUpdateRow = async () => { throw new Error('TABLE-ONLY FLOW MUST NOT UPDATE ROWS'); };
  Workpeg.wpDeleteTable = async () => { throw new Error('TABLE-ONLY FLOW MUST NOT DELETE TABLES'); };
  const app = new Setup();
  app.state.expected_business = business;
  app.state.owner_attestation = 'I VERIFIED ROOMAY AI OWNER CONTEXT';
  app.state.inventory_attestation = 'OWNER VERIFIED NO room_types TABLE';
  app.state.sdk_retry_ack = 'I UNDERSTAND SDK 401/403 REFRESH RETRY';
  app.state.create_confirmation = 'CREATE room_types ONLY';
  return app;
}
const createCalls = () => calls.filter(call => call[0] === 'create_table');
const cases = [];
const test = (name, fn) => cases.push([name, fn]);

test('mount and render make no Workpeg calls', async () => {
  const app = setup(); app.on_mount(); app.build();
  assert.equal(calls.length, 0);
});
test('wrong business and missing owner attestation fail before reads', async () => {
  const app = setup(); app.state.expected_business = '00000000-0000-4000-8000-000000000099';
  await app.inspect(); assert.equal(calls.length, 0); assert.match(app.state.failure, /Business mismatch/);
  app.state.expected_business = business; app.state.owner_attestation = '';
  await app.create_first_table(); assert.equal(calls.length, 0);
  assert.match(app.state.failure, /Owner context is not verified/);
});
test('create is unavailable until the owner reviews a fresh inventory', async () => {
  const app = setup(); await app.create_first_table();
  assert.equal(calls.length, 0);
  assert.match(app.state.failure, /Inspect both namespaces/);
});
test('inspection reads both namespaces and reports native UUID permission and owner id', async () => {
  const app = setup({hotel: [table()], requests: []}); await app.inspect();
  assert.deepEqual(calls, [['get_tables', 'roomay_hotel_v1'], ['get_tables', 'roomay_requests_v1']]);
  assert.match(app.state.inventory_lines[0], new RegExp(tableUuid));
  assert.match(app.state.inventory_lines[0], /permission 700/);
  assert.match(app.state.inventory_lines[0], /owner id 42/);
  assert.match(app.state.context_status, /owner identity is not exposed/);
  assert.equal(createCalls().length, 0);
});
test('one-table creation repeats fresh inventory then validates create, direct GET and fresh lists', async () => {
  const app = setup(); await app.inspect();
  assert.equal(app.state.preflight_ready, true);
  await app.create_first_table();
  assert.equal(createCalls().length, 1);
  assert.deepEqual(createCalls()[0][1], expectedPayload);
  assert.equal(calls.filter(call => call[0] === 'get_table').length, 1);
  assert.equal(calls.filter(call => call[0] === 'get_tables').length, 6);
  assert.match(app.state.last_success, /created and matched create, direct GET, and fresh namespace listing/);
  assert.match(app.state.last_success, /owner id 42/);
  assert.equal(calls.some(call => ['add_row', 'update_row', 'delete_table'].includes(call[0])), false);
});
test('changed inventory after reviewed preflight stops before create', async () => {
  const app = setup(); await app.inspect();
  hotelTables = [table()];
  await app.create_first_table();
  assert.equal(createCalls().length, 0);
  assert.match(app.state.failure, /differs from the reviewed preflight/);
  assert.equal(app.state.preflight_ready, false);
});
test('create requires the exact second confirmation', async () => {
  const app = setup(); await app.inspect();
  app.state.create_confirmation = 'CREATE ALL TABLES';
  let callsBefore = calls.length;
  await app.create_first_table(); assert.equal(calls.length, callsBefore);
  assert.match(app.state.failure, /exact one-table confirmation/);
  app.state.create_confirmation = 'CREATE room_types ONLY';
  app.state.inventory_attestation = '';
  await app.create_first_table(); assert.equal(calls.length, callsBefore);
  assert.match(app.state.failure, /no inaccessible room_types table/);
  app.state.inventory_attestation = 'OWNER VERIFIED NO room_types TABLE';
  app.state.sdk_retry_ack = '';
  await app.create_first_table(); assert.equal(calls.length, callsBefore);
  assert.match(app.state.failure, /may refresh and retry once/);
});
test('existing correct table is not recreated', async () => {
  const app = setup({hotel: [table()]}); await app.inspect();
  assert.equal(createCalls().length, 0);
  assert.match(app.state.last_success, /room_types UUID/);
  assert.equal(app.state.preflight_ready, false);
});
test('duplicate, incompatible or partial inventories stop the create', async () => {
  for (const inventory of [
    {hotel: [table(), table()], requests: []},
    {hotel: [table({permission: '740'})], requests: []},
    {hotel: [table()], requests: [{...table(), name: 'Roomay Service Requests', namespace: 'roomay_requests_v1'}]},
  ]) {
    const app = setup(inventory); await app.inspect();
    assert.equal(createCalls().length, 0); assert.ok(app.state.failure);
  }
});
test('malformed list and HTTP 401/403 fail without leaking response text', async () => {
  const bad = setup(); Workpeg.wpGetTables = async () => ({results: []});
  await bad.inspect(); assert.match(bad.state.failure, /Malformed table-list/);
  for (const status of [401, 403]) {
    const app = setup(); Workpeg.wpGetTables = async () => { throw new Error(`HTTP ${status}: PRIVATE_BODY`); };
    await app.inspect(); assert.match(app.state.failure, new RegExp(String(status)));
    assert.ok(!JSON.stringify(app.state).includes('PRIVATE_BODY'));
  }
});
test('failed direct readback locks create retry and never claims success', async () => {
  const app = setup(); await app.inspect();
  const priorSuccess = app.state.last_success;
  Workpeg.wpGetTable = async () => { throw new Error('HTTP 500 PRIVATE_BODY'); };
  await app.create_first_table();
  assert.equal(app.state.uncertain, true); assert.ok(!app.state.failure.includes('PRIVATE_BODY'));
  assert.equal(app.state.last_success, priorSuccess);
  assert.ok(!app.state.last_success.includes('created'));
  const count = calls.length; await app.create_first_table(); assert.equal(calls.length, count);
});
test('failed create shows sanitized denial and locks application retry', async () => {
  const app = setup(); await app.inspect();
  Workpeg.wpCreateTable = async () => { calls.push(['create_table']); throw new Error('HTTP 403 PRIVATE_BODY'); };
  await app.create_first_table();
  assert.equal(app.state.uncertain, true);
  assert.match(app.state.failure, /403/);
  assert.ok(!app.state.failure.includes('PRIVATE_BODY'));
  assert.equal(app.state.last_success.includes('created'), false);
  const count = calls.length; await app.create_first_table(); assert.equal(calls.length, count);
});
test('write timeout is uncertain and late create response triggers no readback or retry', async () => {
  const app = setup(); await app.inspect(); let resolveCreate;
  const priorSuccess = app.state.last_success;
  Workpeg.wpCreateTable = payload => {
    calls.push(['create_table', clone(payload)]);
    return new Promise(resolve => { resolveCreate = resolve; });
  };
  const pending = app.create_first_table();
  await new Promise(resolve => setImmediate(resolve));
  for (let i = 0; i < 30; i++) app.watch_timeout();
  resolveCreate(table()); await pending;
  assert.equal(app.state.uncertain, true); assert.equal(app.state.last_success, priorSuccess);
  assert.equal(calls.filter(call => call[0] === 'get_table').length, 0);
  assert.match(app.state.failure, /Outcome is unknown/);
});

(async () => {
  for (const [name, fn] of cases) { await fn(); console.log('PASS ' + name); }
  console.log(`${cases.length} compiled first-table scenarios passed (network forbidden).`);
})().catch(error => { console.error(error); process.exitCode = 1; });

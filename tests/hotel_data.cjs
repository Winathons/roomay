// Offline contract tests for the generated Workpeg controller.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

globalThis.window = globalThis;
globalThis.addEventListener = () => {};
globalThis.fetch = () => { throw new Error('NETWORK FORBIDDEN IN TESTS'); };
const output = process.argv[2];
vm.runInThisContext(fs.readFileSync(path.join(output, 'workpeg-runtime.js'), 'utf8'));
vm.runInThisContext(fs.readFileSync(path.join(output, 'app.js'), 'utf8') +
  '\nglobalThis.HotelDataTest = HotelData;');
Workpeg.stateHandler = () => ({});
Workpeg.setInterval = () => {};

const business = '00000000-0000-4000-8000-000000000029';
Workpeg.routeParam = () => business;
const hotelNames = ['room_types', 'rooms', 'guests', 'reservations', 'stays', 'stay_guests', 'room_blocks'];
const requestNames = ['Roomay Service Requests', 'Roomay Service Request Audit'];
const allNames = [...hotelNames, ...requestNames];
const uuid = number => `00000000-0000-4000-8000-${String(number).padStart(12, '0')}`;
const tableId = name => uuid(allNames.indexOf(name) + 1);
const namespace = name => hotelNames.includes(name) ? 'roomay_hotel_v1' : 'roomay_requests_v1';
const schemaApp = new HotelDataTest();
const table = name => ({uuid: tableId(name), name, namespace: namespace(name), permission: '700',
  columns: schemaApp.allowed_fields(name).map(id => ({
    id, type: schemaApp.field_type(id), required: !schemaApp.optional_fields(name).includes(id),
  }))});
const row = (name, number, data) => ({id: number, fingerprint: uuid(5000 + number),
  data: {business_id: business, ...data}});
const roomType = number => row('room_types', number, {
  entity_id: uuid(10000 + number), name: `Type ${number}`, capacity: 2,
});
let calls;
let remoteRows;

function setup() {
  calls = [];
  remoteRows = Object.fromEntries(allNames.map(name => [name, []]));
  Workpeg.wpGetTables = async ns => {
    calls.push(['tables', ns]);
    return allNames.filter(name => namespace(name) === ns).map(table);
  };
  Workpeg.wpGetRows = async (id, paging) => {
    const name = allNames.find(candidate => tableId(candidate) === id);
    calls.push(['rows', name, paging]);
    assert.ok(name);
    return remoteRows[name].slice(paging.offset, paging.offset + paging.limit);
  };
  Workpeg.wpCreateTable = async () => { throw new Error('WRITE FORBIDDEN'); };
  Workpeg.wpAddRow = async () => { throw new Error('WRITE FORBIDDEN'); };
  Workpeg.wpUpdateRow = async () => { throw new Error('WRITE FORBIDDEN'); };
  const app = new HotelDataTest();
  app.state.expected_business = business;
  app.state.confirmation = 'Read Roomay hotel data';
  return app;
}

const cases = [];
const test = (name, fn) => cases.push([name, fn]);

test('mount and render do not read, provision, seed or write', async () => {
  const app = setup(); app.on_mount(); app.build();
  assert.equal(calls.length, 0);
});

test('business and confirmation gates run before the SDK', async () => {
  const app = setup(); app.state.expected_business = uuid(999);
  await app.load_snapshot(); assert.equal(calls.length, 0);
  assert.match(app.state.failure, /context mismatch/);
  app.state.expected_business = business; app.state.confirmation = '';
  await app.load_snapshot(); assert.equal(calls.length, 0);
});

test('empty inventory is truthful and makes no writes', async () => {
  const app = setup(); await app.load_snapshot();
  assert.equal(app.state.failure, '');
  assert.match(app.state.status, /inventory is empty/);
  assert.equal(calls.filter(call => call[0] === 'tables').length, 2);
  assert.equal(calls.filter(call => call[0] === 'rows').length, 9);
  assert.equal(app.state.rooms.length, 0);
});

test('all plain-list pages are fetched with limit and offset', async () => {
  const app = setup(); remoteRows.room_types = Array.from({length: 101}, (_, index) => roomType(index + 1));
  await app.load_snapshot();
  assert.equal(app.state.failure, '');
  assert.equal(app.state.room_types.length, 101);
  assert.deepEqual(calls.filter(call => call[1] === 'room_types').map(call => call[2]),
    [{limit: 100, offset: 0}, {limit: 100, offset: 100}]);
});

test('missing, duplicate and unsafe tables fail closed', async () => {
  for (const mode of ['missing', 'duplicate', 'permission']) {
    const app = setup();
    Workpeg.wpGetTables = async ns => {
      let tables = allNames.filter(name => namespace(name) === ns).map(table);
      if (ns === 'roomay_hotel_v1' && mode === 'missing') tables = tables.filter(item => item.name !== 'rooms');
      if (ns === 'roomay_hotel_v1' && mode === 'duplicate') tables.push(table('rooms'));
      if (ns === 'roomay_hotel_v1' && mode === 'permission') tables.find(item => item.name === 'rooms').permission = '777';
      return tables;
    };
    await app.load_snapshot(); assert.ok(app.state.failure); assert.equal(app.state.rooms.length, 0);
  }
});

test('wrong-business, incomplete and duplicate records are rejected', async () => {
  for (const mode of ['business', 'incomplete', 'duplicate']) {
    const app = setup();
    const first = roomType(1);
    if (mode === 'business') first.data.business_id = uuid(404);
    if (mode === 'incomplete') delete first.data.capacity;
    remoteRows.room_types = mode === 'duplicate' ? [first, {...roomType(2), data: {...roomType(2).data, entity_id: first.data.entity_id}}] : [first];
    await app.load_snapshot(); assert.ok(app.state.failure); assert.equal(app.state.room_types.length, 0);
  }
});

test('malformed table and row response shapes are not absence', async () => {
  const app = setup(); Workpeg.wpGetTables = async () => ({results: []});
  await app.load_snapshot(); assert.match(app.state.failure, /Malformed table-list/);
  const app2 = setup(); Workpeg.wpGetRows = async () => ({results: []});
  await app2.load_snapshot(); assert.match(app2.state.failure, /Malformed row page/);
});

test('400, 401, 403 and network failures are explicit without raw details', async () => {
  for (const status of [400, 401, 403, 500]) {
    const app = setup();
    Workpeg.wpGetTables = async () => { throw new Error(`HTTP ${status}: SECRET_SENTINEL`); };
    await app.load_snapshot();
    assert.ok(app.state.failure); assert.ok(!JSON.stringify(app.state).includes('SECRET_SENTINEL'));
    if (status === 400) assert.match(app.state.failure, /WOR-28/);
  }
});

test('timeout discards a late table response and exposes no snapshot', async () => {
  const app = setup(); let resolve;
  Workpeg.wpGetTables = () => new Promise(done => { resolve = done; });
  const pending = app.load_snapshot();
  await new Promise(done => setImmediate(done));
  for (let index = 0; index < 30; index++) app.watch_timeout();
  resolve(hotelNames.map(table)); await pending;
  assert.equal(app.state.timed_out, true); assert.equal(app.state.rooms.length, 0);
  assert.match(app.state.failure, /timed out/);
});

test('consumer can explicitly invalidate a previously complete snapshot', async () => {
  const app = setup(); await app.load_snapshot(); app.mark_stale();
  assert.match(app.state.freshness, /Stale/);
});

(async () => {
  for (const [name, fn] of cases) { await fn(); console.log('PASS ' + name); }
  console.log(`${cases.length} compiled hotel-data scenarios passed (network and writes forbidden).`);
})().catch(error => { console.error(error); process.exitCode = 1; });

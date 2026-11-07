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
let routeBusiness = business;
Workpeg.routeParam = () => routeBusiness;
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

function validRelationshipSnapshot() {
  return {
    room_types: [{entity_id: uuid(10001), name: 'Standard', capacity: 2}],
    rooms: [
      {entity_id: uuid(10002), number: '201', room_type_id: uuid(10001), enabled: true, housekeeping: 'ready'},
      {entity_id: uuid(10003), number: '202', room_type_id: uuid(10001), enabled: true, housekeeping: 'ready'},
    ],
    guests: [{entity_id: uuid(10004), display_name: 'Synthetic Test Guest'}],
    reservations: [{entity_id: uuid(10005), guest_id: uuid(10004),
      room_type_id: uuid(10001), room_id: uuid(10003), arrival: '2026-11-06',
      departure: '2026-11-09', party_size: 1, source: 'advance', status: 'confirmed'}],
    stays: [{entity_id: uuid(10006), reservation_id: uuid(10005), room_id: uuid(10003),
      checked_in_at: '2026-11-06T15:00:00+00:00', status: 'checked_in'}],
    stay_guests: [{entity_id: uuid(10007), stay_id: uuid(10006), guest_id: uuid(10004),
      joined_at: '2026-11-06T15:00:00+00:00'}],
    room_blocks: [],
    'Roomay Service Requests': [],
    'Roomay Service Request Audit': [],
  };
}

const clone = value => JSON.parse(JSON.stringify(value));
let calls;
let remoteRows;

function setup() {
  routeBusiness = business;
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
  return new HotelDataTest();
}

const cases = [];
const test = (name, fn) => cases.push([name, fn]);

test('mount loads the read-only snapshot and never provisions, seeds or writes', async () => {
  const app = setup(); await app.on_mount(); app.build();
  assert.equal(calls.filter(call => call[0] === 'tables').length, 2);
  assert.equal(calls.filter(call => call[0] === 'rows').length, 9);
});

test('malformed business route is rejected before the SDK', async () => {
  const app = setup(); routeBusiness = 'not-a-business';
  await app.load_snapshot(); assert.equal(calls.length, 0);
  assert.match(app.state.failure, /Business context/);
});

test('empty inventory is truthful and makes no writes', async () => {
  const app = setup(); await app.load_snapshot();
  assert.equal(app.state.failure, '');
  assert.match(app.state.status, /no rooms configured/);
  assert.equal(calls.filter(call => call[0] === 'tables').length, 2);
  assert.equal(calls.filter(call => call[0] === 'rows').length, 9);
  assert.equal(app.state.rooms.length, 0);
  assert.equal(app.state.view_state, 'empty_inventory');
});

test('valid persisted inventory reaches the loaded receptionist state', async () => {
  const app = setup();
  app.state.operational_date = '2026-11-06';
  remoteRows.room_types = [roomType(1)];
  remoteRows.rooms = [row('rooms', 2, {
    entity_id: uuid(10002), number: '201', room_type_id: uuid(10001),
    enabled: true, housekeeping: 'ready',
  })];
  await app.load_snapshot();
  assert.equal(app.state.failure, '');
  assert.equal(app.state.view_state, 'loaded');
  assert.equal(app.state.room_cards.length, 1);
  assert.equal(app.state.metrics.length, 8);
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
    if (status === 401) assert.equal(app.state.view_state, 'authentication_required');
    if (status === 403) assert.equal(app.state.view_state, 'access_denied');
    if (status === 400 || status === 500) assert.equal(app.state.view_state, 'connection_unavailable');
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

test('invalid stay and occupant histories fail closed in the compiled validator', async () => {
  const invalidCases = [
    snapshot => { snapshot.stays[0].status = 'checked_out'; },
    snapshot => {
      snapshot.stays[0].status = 'checked_out';
      snapshot.stays[0].checked_out_at = '2026-11-06T16:00:00+02:00';
      snapshot.stay_guests[0].left_at = '2026-11-06T16:00:00+02:00';
    },
    snapshot => { snapshot.stay_guests[0].joined_at = '2026-11-06T14:59:00+00:00'; },
    snapshot => {
      snapshot.stays[0].status = 'checked_out';
      snapshot.stays[0].checked_out_at = '2026-11-06T17:00:00+00:00';
      snapshot.stay_guests[0].left_at = '2026-11-06T17:01:00+00:00';
    },
    snapshot => {
      snapshot.stays[0].status = 'checked_out';
      snapshot.stays[0].checked_out_at = '2026-11-06T17:00:00+00:00';
    },
    snapshot => { snapshot.stays[0].checked_out_at = '2026-11-06T17:00:00+00:00'; },
    snapshot => { snapshot.reservations[0].status = 'pending'; },
    snapshot => { snapshot.stays.push({...snapshot.stays[0], entity_id: uuid(10008)}); },
  ];
  for (const mutate of invalidCases) {
    const app = setup();
    app.state.view_state = 'loaded';
    const snapshot = clone(validRelationshipSnapshot());
    mutate(snapshot);
    assert.equal(app.validate_relationships(snapshot), false);
    assert.equal(app.state.view_state, 'connection_unavailable');
    assert.ok(app.state.failure);
  }
});

test('historical request keeps its original room after a legitimate room change', async () => {
  const app = setup();
  const snapshot = validRelationshipSnapshot();
  snapshot['Roomay Service Requests'] = [{
    request_id: uuid(10009), stay_id: uuid(10006), guest_id: uuid(10004),
    room_id: uuid(10002), description: 'Original-room request', status: 'resolved',
  }];
  assert.equal(snapshot.stays[0].room_id, uuid(10003));
  assert.equal(snapshot['Roomay Service Requests'][0].room_id, uuid(10002));
  assert.equal(app.validate_relationships(snapshot), true, app.state.failure);
  app.state.operational_date = '2026-11-07';
  app.state.room_types = snapshot.room_types;
  app.state.rooms = snapshot.rooms;
  app.state.guests = snapshot.guests;
  app.state.reservations = snapshot.reservations;
  app.state.stays = snapshot.stays;
  app.state.room_blocks = snapshot.room_blocks;
  app.state.service_requests = snapshot['Roomay Service Requests'];
  app.project_records();
  assert.equal(app.state.request_cards[0].room, '201');
  assert.equal(app.state.room_cards.find(room => room.number === '202').occupancy, 'In house');
});

(async () => {
  for (const [name, fn] of cases) { await fn(); console.log('PASS ' + name); }
  console.log(`${cases.length} compiled hotel-data scenarios passed (network and writes forbidden).`);
})().catch(error => { console.error(error); process.exitCode = 1; });

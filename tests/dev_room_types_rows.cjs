// Compiled controller tests. Network access is deliberately forbidden.
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
let routes;
Workpeg.router = value => { routes = value; };
vm.runInThisContext(fs.readFileSync(path.join(output, 'app.js'), 'utf8'));
loadHandler();
assert.ok(Array.isArray(routes));
const entry = routes.find(item => item.path === '/b/[business_id]/dev-room-types-rows');
assert.ok(entry, 'isolated route exists in standalone build');
const App = entry.app;
Workpeg.stateHandler = () => ({});
Workpeg.setInterval = () => {};
const business = '00000000-0000-4000-8000-000000000058';
const tableUuid = '00000000-0000-4000-8000-000000000581';
const entity = '4a3e15b4-2df4-5a22-93c5-720d4eaa5801';
const data = (extra = {}) => ({business_id: business, entity_id: entity,
  name: 'Roomay TEST Room Type (Fictional)', capacity: 2, ...extra});
const row = (overrides = {}) => ({id: 71, fingerprint: 'fp-71-a', permission:700,
  inherit_business_permission:true, inherit_individual_permissions:false, data:data(), ...overrides});
const clone = value => JSON.parse(JSON.stringify(value));
const calls = [];
let remoteRows;
let tableList;
let directTable;
let addBehavior;
let updateBehavior;
let routeBusiness;
let app;
const table = (overrides = {}) => ({uuid: tableUuid, name: 'room_types',
  namespace: 'roomay_hotel_v1', permission: '700',
  metadata: {extra: {contract: 'roomay.hotel.v1'}},
  columns: [
    {id:'business_id',name:'business_id',type:'uuid',required:true,position:500,options:{},metadata:{}},
    {id:'entity_id',name:'entity_id',type:'uuid',required:true,position:1000,options:{},metadata:{}},
    {id:'name',name:'name',type:'text',required:true,position:2000,options:{},metadata:{}},
    {id:'capacity',name:'capacity',type:'number',required:true,position:3000,options:{},metadata:{}},
  ], ...overrides});
function setup({rows = [], listing = [table()], direct = table()} = {}) {
  calls.length = 0; remoteRows = clone(rows); tableList = clone(listing); directTable = clone(direct);
  addBehavior = null; updateBehavior = null; routeBusiness = business;
  Workpeg.routeParam = () => routeBusiness;
  Workpeg.wpGetTables = async namespace => { calls.push(['tables', namespace]); return clone(tableList); };
  Workpeg.wpGetTable = async uuid => { calls.push(['table', uuid]); return clone(directTable); };
  Workpeg.wpGetRows = async (uuid, options) => {
    calls.push(['rows', uuid, clone(options)]);
    const offset = options.offset || 0, limit = options.limit || 100;
    return clone(remoteRows.slice(offset, offset + limit));
  };
  Workpeg.wpAddRow = async (uuid, payload) => {
    calls.push(['add', uuid, clone(payload)]);
    if (addBehavior) return addBehavior(payload);
    const saved = {id:72, fingerprint:'fp-72-a', permission:700,
      inherit_business_permission:true, inherit_individual_permissions:false, data:clone(payload.data)};
    remoteRows.push(clone(saved)); return clone(saved);
  };
  Workpeg.wpUpdateRow = async (uuid, id, patch) => {
    calls.push(['update', uuid, id, clone(patch)]);
    if (updateBehavior) return updateBehavior(id, patch);
    const index = remoteRows.findIndex(item => item.id === id);
    const saved = {id, fingerprint:'fp-71-b', permission:700,
      inherit_business_permission:true, inherit_individual_permissions:false, data:clone(patch.data)};
    remoteRows[index] = clone(saved); return clone(saved);
  };
  app = new App(); app.on_mount(); app.build();
  app.state.expected_business = business;
  app.state.owner_attestation = 'I VERIFIED ROOMAY AI OWNER CONTEXT';
  app.state.permission_attestation = 'I VERIFIED NO ROW-LEVEL GRANTS';
  app.state.sdk_retry_ack = 'I UNDERSTAND SDK 401/403 REFRESH RETRY';
  app.state.insert_confirmation = 'INSERT ROOMAY TEST ROOM TYPE';
  app.state.update_confirmation = 'UPDATE ROOMAY TEST CAPACITY ONLY';
  return app;
}
const count = kind => calls.filter(call => call[0] === kind).length;
const cases = [];
const test = (name, fn) => cases.push([name, fn]);
async function prepareInsert(target = app) { await target.prepare_insert(); }
async function confirmInsert(target = app) { await target.prepare_insert(); await target.insert_row(); }
async function prepareUpdate(target = app) { await target.prepare_update(); }
async function confirmUpdate(target = app) { await target.prepare_update(); await target.update_row(); }

test('mount and render do not make Workpeg calls', async () => {
  setup(); assert.equal(calls.length, 0);
});
test('correct existing table is discovered and directly read with owner-only schema', async () => {
  setup(); await app.inspect_table();
  assert.equal(count('tables'), 1, JSON.stringify(app.state)); assert.equal(count('table'), 1);
  assert.equal(app.state.table_uuid, tableUuid); assert.match(app.state.table_status, /permission 700/);
});
test('wrong business, missing owner attestation and wrong table permissions fail closed', async () => {
  setup(); routeBusiness = 'bad'; await app.inspect_table(); assert.equal(calls.length, 0);
  setup(); app.state.owner_attestation = ''; await app.inspect_table(); assert.equal(calls.length, 0);
  setup({listing:[table({permission:'740'})]}); await app.inspect_table(); assert.ok(app.state.failure);
  assert.equal(count('add'), 0);
});
test('missing, duplicate, incompatible and direct-GET mismatch tables block access', async () => {
  for (const spec of [{listing:[]}, {listing:[table(),table()]},
    {listing:[table({columns:[]})]}, {direct:table({uuid:'00000000-0000-4000-8000-000000000099'})}]) {
    setup(spec); await app.read_rows(); assert.ok(app.state.failure);
    assert.equal(count('rows'), 0); assert.equal(count('add'), 0);
  }
});
test('row read is explicit and validates complete inventory and pagination', async () => {
  setup({rows:[row()]}); await app.read_rows(); assert.equal(count('rows'), 1);
  assert.match(app.state.rows_summary[0], /row 71 \/ fingerprint fp-71-a/);
  setup({rows:[row({id:0})]}); await app.read_rows(); assert.match(app.state.failure, /Malformed/);
  setup({rows:[row({inherit_business_permission:false})]}); await app.read_rows(); assert.match(app.state.failure, /Malformed/);
  setup({rows:[row({data:data({business_id:'00000000-0000-4000-8000-000000000099'})})]});
  await app.read_rows(); assert.match(app.state.failure, /cross-business/);
  setup({rows:Array.from({length:100}, (_, i) => row({id:i+1, fingerprint:'fp-'+i,
    data:data({entity_id:`00000000-0000-4000-8000-${String(i+1).padStart(12,'0')}`})}))});
  await app.read_rows(); assert.equal(count('rows'), 2);
});
test('insert preparation requires empty complete inventory and separate typed approval', async () => {
  setup({rows:[row()]}); await prepareInsert(); assert.equal(app.state.insert_prepared, false);
  setup(); app.state.permission_attestation = ''; await prepareInsert();
  assert.equal(count('tables'), 0); assert.match(app.state.failure, /row-level permission grants/);
  setup(); await app.insert_row(); assert.equal(count('add'), 0);
  await prepareInsert(); app.state.insert_confirmation = 'no'; await app.insert_row(); assert.equal(count('add'), 0);
});
test('insert writes one synthetic row and verifies fresh readback', async () => {
  setup(); await confirmInsert(); assert.equal(count('add'), 1);
  assert.equal(remoteRows.length, 1); assert.equal(remoteRows[0].data.business_id, business);
  assert.equal(remoteRows[0].data.entity_id, entity); assert.equal(remoteRows[0].data.capacity, 2);
  assert.match(app.state.last_success, /inserted and verified/, JSON.stringify(app.state)); assert.equal(app.state.uncertain, false);
});
test('insert is blocked if prepared inventory changes and duplicate click cannot write twice', async () => {
  setup(); await prepareInsert(); remoteRows.push(row()); await app.insert_row();
  assert.equal(count('add'), 0); assert.match(app.state.failure, /differs/);
  setup(); await prepareInsert();
  let resolve;
  addBehavior = () => new Promise(done => { resolve = done; });
  const pending = app.insert_row(); await new Promise(done => setImmediate(done));
  await app.insert_row(); assert.equal(count('add'), 1);
  resolve({id:72,fingerprint:'fp-72-a',permission:700,inherit_business_permission:true,
    inherit_individual_permissions:false,data:data()}); await pending;
});
test('uncertain insert outcomes lock further writes and never retry', async () => {
  setup(); await prepareInsert(); addBehavior = async () => { throw new Error('HTTP 500 PRIVATE RESPONSE'); };
  await app.insert_row(); assert.equal(app.state.uncertain, true); assert.equal(count('add'), 1);
  const before = calls.length; await app.insert_row(); assert.equal(calls.length, before);
  assert.ok(!JSON.stringify(app.state).includes('PRIVATE RESPONSE'));
});
test('timeout leaves in-flight write locked and prevents late-response races', async () => {
  setup(); await prepareInsert();
  let resolve;
  addBehavior = () => new Promise(done => { resolve = done; });
  const pending = app.insert_row();
  await new Promise(done => setImmediate(done));
  assert.equal(count('add'), 1);
  for (let index = 0; index < 30; index++) app.watch_timeout();
  assert.equal(app.state.timed_out, true);
  assert.equal(app.state.uncertain, true);
  assert.equal(app.state.busy, true, 'do not release busy while a timed-out write is in flight');
  const before = calls.length;
  await app.insert_row();
  await app.read_rows();
  assert.equal(calls.length, before, 'no other request can reset timed_out');
  resolve({id:72,fingerprint:'fp-72-a',permission:700,
    inherit_business_permission:true,inherit_individual_permissions:false,data:data()});
  await pending;
  assert.equal(app.state.uncertain, true);
  assert.equal(app.state.busy, true);
  assert.doesNotMatch(app.state.last_success, /inserted and verified/);
});
test('missing native ID/fingerprint or mismatched readback is uncertain', async () => {
  setup(); await prepareInsert(); addBehavior = async payload => ({data:payload.data}); await app.insert_row();
  assert.equal(app.state.uncertain, true);
  setup(); await prepareInsert(); addBehavior = async payload => {
    const saved={id:72,fingerprint:'fp-72-a',permission:700,inherit_business_permission:true,
      inherit_individual_permissions:false,data:clone(payload.data)};
    remoteRows.push({...saved,data:{...saved.data,capacity:99}}); return saved;
  };
  await app.insert_row(); assert.equal(app.state.uncertain, true);
});
test('update preparation requires exactly the fictional row and correct initial state', async () => {
  setup(); await prepareUpdate(); assert.equal(app.state.update_prepared, false);
  setup({rows:[row({data:data({capacity:3})})]}); await prepareUpdate(); assert.equal(app.state.update_prepared, false);
  setup({rows:[row(), {...row(), id:72, fingerprint:'fp-72', data:data({entity_id:'00000000-0000-4000-8000-000000000072'})}]});
  await prepareUpdate(); assert.equal(app.state.update_prepared, false);
});
test('update preserves unrelated fields and verifies changed fingerprint and readback', async () => {
  const initial = row({data:data({legacy_note:'preserve-me'})}); setup({rows:[initial]}); await confirmUpdate();
  assert.equal(count('update'), 1); assert.equal(remoteRows[0].data.legacy_note, 'preserve-me');
  assert.equal(remoteRows[0].data.capacity, 3); assert.equal(remoteRows[0].fingerprint, 'fp-71-b');
  assert.match(app.state.last_success, /unrelated fields preserved/);
});
test('stale update fingerprint, failed write and wrong response lock out retries', async () => {
  setup({rows:[row()]}); await prepareUpdate(); remoteRows[0].fingerprint='changed'; await app.update_row();
  assert.equal(count('update'), 0); assert.match(app.state.failure, /differs/);
  setup({rows:[row()]}); await prepareUpdate(); updateBehavior=async()=>{throw new Error('timeout');}; await app.update_row();
  assert.equal(app.state.uncertain, true); assert.equal(count('update'),1);
  const before=calls.length; await app.update_row(); assert.equal(calls.length,before);
});
test('authentication and forbidden errors are sanitized', async () => {
  for (const code of [401,403]) {
    setup(); Workpeg.wpGetTables=async()=>{throw new Error(`HTTP ${code}: SECRET_COOKIE`);};
    await app.inspect_table(); assert.match(app.state.failure,new RegExp(String(code)));
    assert.ok(!JSON.stringify(app.state).includes('SECRET_COOKIE'));
  }
});
test('reload-style fresh app reads persisted mock rows without an automatic read', async () => {
  setup(); await confirmInsert(); const saved=clone(remoteRows);
  const callsBefore=calls.length;
  setup({rows:saved}); assert.equal(calls.length,0);
  await app.read_rows(); assert.equal(remoteRows.length,1); assert.match(app.state.last_success,/Rows read/);
});

(async () => {
  for (const [name, fn] of cases) { await fn(); console.log('PASS ' + name); }
  console.log(`${cases.length} compiled WOR-58 scenarios passed (network forbidden).`);
})().catch(error => { console.error(error); process.exitCode = 1; });

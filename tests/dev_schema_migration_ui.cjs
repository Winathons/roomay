// Offline compiled-controller tests. All network access is forbidden.
const fs=require('node:fs'), path=require('node:path'), vm=require('node:vm');
const assert=require('node:assert/strict');
globalThis.window=globalThis;
globalThis.document={getElementById:()=>({})};
let loadHandler;
globalThis.addEventListener=(event,handler)=>{if(event==='load')loadHandler=handler;};
globalThis.fetch=()=>{throw new Error('NETWORK FORBIDDEN IN TESTS');};
const output=process.argv[2], expected=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
vm.runInThisContext(fs.readFileSync(path.join(output,'workpeg-runtime.js'),'utf8'));
let registered;
Workpeg.router=value=>{registered=value;};
vm.runInThisContext(fs.readFileSync(path.join(output,'app.js'),'utf8'));
loadHandler();
assert.ok(Array.isArray(registered));
const routeEntry=registered.find(item=>item.path==='/b/[business_id]/dev-schema-migration');
assert.ok(routeEntry,'standalone migration route compiled');
const App=routeEntry.app;
Workpeg.stateHandler=()=>({}); Workpeg.setInterval=()=>{};
const business='00000000-0000-4000-8000-000000000059';
const typeId='00000000-0000-4000-8000-000000000058';
const typeUuid='00000000-0000-4000-8000-000000000591';
const roomUuid='00000000-0000-4000-8000-000000000592';
let routeBusiness=business, calls=[], hotelTables=[], requestTables=[], created=null;
let createImpl=null;
const clone=value=>JSON.parse(JSON.stringify(value));
Workpeg.routeParam=()=>routeBusiness;
function response(name, uuid){
  const item=clone(expected[name]); delete item.alias; item.uuid=uuid; item.owner={id:900};
  for(const col of item.columns){if(!col.options)col.options={};if(!col.metadata)col.metadata={};}
  return item;
}
function setup({hotel=[response('room_types',typeUuid)], requests=[]}={}){
  calls=[]; routeBusiness=business; hotelTables=clone(hotel); requestTables=clone(requests); created=null; createImpl=null;
  Workpeg.wpGetTables=async namespace=>{
    calls.push(['get_tables',namespace]);
    return namespace==='roomay_hotel_v1'?clone(hotelTables):clone(requestTables);
  };
  Workpeg.wpGetTable=async uuid=>{
    calls.push(['get_table',uuid]);
    const found=[...hotelTables,...requestTables].find(item=>item.uuid===uuid);
    return clone(found||null);
  };
  Workpeg.wpCreateTable=async payload=>{
    calls.push(['create_table',clone(payload)]);
    if(createImpl)return createImpl(payload);
    const made=response(payload.name,'00000000-0000-4000-8000-000000000593');
    if(payload.namespace==='roomay_hotel_v1')hotelTables.push(clone(made));else requestTables.push(clone(made));
    created=clone(made);return clone(made);
  };
  const app=new App(); app.on_mount(); app.build();
  app.state.expected_business=business; app.state.owner_attestation='I VERIFIED ROOMAY AI OWNER CONTEXT';
  return app;
}
const count=kind=>calls.filter(call=>call[0]===kind).length;
const cases=[]; const test=(name,fn)=>cases.push([name,fn]);
async function inspectAndPrepare(app,name='rooms'){
  await app.inspect(); app.set_selected_table(name);
  app.set_missing_attestation('I VERIFIED THIS TABLE IS ABSENT: '+name);
  await app.prepare_selected();
}
async function readyToCreate(app,name='rooms'){
  await inspectAndPrepare(app,name);
  app.set_create_confirmation('CREATE ONLY: '+name);
  app.set_sdk_retry_ack('I UNDERSTAND SDK 401/403 REFRESH RETRY');
}

test('mount and build issue no API requests',async()=>{
  setup(); const app=new App(); app.on_mount(); app.build(); assert.equal(calls.length,0);
});
test('compiled schemas exactly match all nine canonical domain payloads',async()=>{
  const app=setup();
  assert.deepEqual(app.table_names(),Object.keys(expected));
  assert.deepEqual(app.creatable_names(),Object.keys(expected).slice(1));
  for(const name of Object.keys(expected))assert.deepEqual(app.contract_payload(name),expected[name],name);
});
test('inspection verifies existing room_types and lists the eight remaining candidates without writes',async()=>{
  setup(); const app=new App(); app.state.expected_business=business;
  app.state.owner_attestation='I VERIFIED ROOMAY AI OWNER CONTEXT';
  await app.inspect();
  assert.deepEqual(calls.filter(c=>c[0]==='get_tables').map(c=>c[1]),['roomay_hotel_v1','roomay_requests_v1']);
  assert.equal(count('get_table'),1); assert.equal(count('create_table'),0);
  assert.match(JSON.stringify(app.state.table_lines),/room_types \/ existing_compatible/);
  assert.match(JSON.stringify(app.state.table_lines),/rooms \/ missing_or_unreadable/);
  assert.equal(app.state.prepared,false);
});
test('wrong business and absent owner attestation fail before protected reads',async()=>{
  let app=setup(); routeBusiness='00000000-0000-4000-8000-000000000099'; await app.inspect(); assert.equal(calls.length,0);
  app=setup(); app.state.owner_attestation=''; await app.inspect(); assert.equal(calls.length,0);
});
test('one selected table requires the exact owner missing-table check before preparation',async()=>{
  const app=setup(); await app.inspect(); app.set_selected_table('rooms'); await app.prepare_selected();
  assert.equal(app.state.prepared,false); assert.equal(count('create_table'),0);
  app.set_missing_attestation('I VERIFIED THIS TABLE IS ABSENT: guests'); await app.prepare_selected();
  assert.equal(app.state.prepared,false);
});
test('preparation shows exact reviewed schema and performs no writes',async()=>{
  const app=setup(); await inspectAndPrepare(app,'rooms');
  assert.equal(app.state.prepared,true); assert.equal(app.state.prepared_table,'rooms');
  assert.match(app.state.selected_contract,/alias roomay-hotel-v1-rooms \| namespace roomay_hotel_v1 \| permission 700/);
  assert.match(app.state.selected_contract,/housekeeping \/ mutable_select \/ required=true \/ position=5000 \/ choices=ready \(ready\),dirty \(dirty\),cleaning \(cleaning\),inspection \(inspection\)/);
  assert.equal(count('create_table'),0);
});
test('one create requires a separate confirmation and verifies response, direct GET and fresh inventory',async()=>{
  const app=setup(); await inspectAndPrepare(app,'rooms');
  await app.create_selected(); assert.equal(count('create_table'),0);
  app.set_create_confirmation('CREATE ONLY: rooms');
  await app.create_selected(); assert.equal(count('create_table'),0);
  app.set_sdk_retry_ack('I UNDERSTAND SDK 401/403 REFRESH RETRY');
  await app.create_selected();
  assert.equal(count('create_table'),1);
  assert.deepEqual(calls.find(c=>c[0]==='create_table')[1],expected.rooms);
  assert.match(app.state.last_success,/created and verified/);
  assert.equal(app.state.prepared,false);
  const writes=count('create_table'); await app.create_selected(); assert.equal(count('create_table'),writes);
});
test('stale inventory, duplicate, incompatible and unexpected tables block all creation',async()=>{
  let app=setup(); await readyToCreate(app,'rooms');
  hotelTables.push(response('rooms',roomUuid)); await app.create_selected(); assert.equal(count('create_table'),0);
  app=setup({hotel:[response('room_types',typeUuid),response('room_types',roomUuid)]}); await app.inspect();
  app.set_selected_table('rooms'); app.set_missing_attestation('I VERIFIED THIS TABLE IS ABSENT: rooms'); await app.prepare_selected();
  assert.equal(app.state.prepared,false);
  app=setup({hotel:[response('room_types',typeUuid),{...response('rooms',roomUuid),permission:'740'}]}); await app.inspect();
  app.set_selected_table('guests'); app.set_missing_attestation('I VERIFIED THIS TABLE IS ABSENT: guests'); await app.prepare_selected();
  assert.equal(app.state.prepared,false);
  app=setup({hotel:[response('room_types',typeUuid),{name:'mystery',namespace:'roomay_hotel_v1',uuid:roomUuid,permission:'700',columns:[]}]});
  await app.inspect(); app.set_selected_table('rooms'); app.set_missing_attestation('I VERIFIED THIS TABLE IS ABSENT: rooms'); await app.prepare_selected();
  assert.equal(app.state.prepared,false); assert.ok(app.state.unexpected_lines.length>0);
});
test('room_types is never selectable or recreated, including when missing',async()=>{
  let app=setup({hotel:[]}); await app.inspect();
  app.set_selected_table('room_types'); app.set_missing_attestation('I VERIFIED THIS TABLE IS ABSENT: room_types'); await app.prepare_selected();
  assert.equal(app.state.prepared,false); assert.equal(count('create_table'),0);
  app=setup(); app.set_selected_table('room_types'); app.state.missing_attestation='I VERIFIED THIS TABLE IS ABSENT: room_types';
  await app.create_selected(); assert.equal(count('create_table'),0);
});
test('failed and malformed reads fail closed without echoing response bodies',async()=>{
  let app=setup(); Workpeg.wpGetTables=async()=>({data:[]}); app.state.expected_business=business;
  app.state.owner_attestation='I VERIFIED ROOMAY AI OWNER CONTEXT'; await app.inspect(); assert.equal(app.state.prepared,false);
  app=setup(); Workpeg.wpGetTables=async()=>{throw new Error('HTTP 403 PRIVATE_BODY');};
  app.state.expected_business=business; app.state.owner_attestation='I VERIFIED ROOMAY AI OWNER CONTEXT';
  await app.inspect(); assert.match(app.state.failure,/403/); assert.ok(!JSON.stringify(app.state).includes('PRIVATE_BODY'));
});
test('failed create is uncertain, sanitized and cannot retry',async()=>{
  const app=setup(); await readyToCreate(app,'rooms');
  createImpl=async()=>{throw new Error('HTTP 500 PRIVATE_BODY');};
  await app.create_selected(); assert.equal(app.state.uncertain,true); assert.equal(count('create_table'),1);
  assert.ok(!JSON.stringify(app.state).includes('PRIVATE_BODY'));
  const before=calls.length; await app.create_selected(); assert.equal(calls.length,before);
});
test('timed-out in-flight create keeps busy lock and blocks late second request',async()=>{
  const app=setup(); await readyToCreate(app,'rooms'); let resolveCreate;
  createImpl=()=>new Promise(resolve=>{resolveCreate=resolve;});
  const pending=app.create_selected(); await new Promise(resolve=>setImmediate(resolve));
  const readsBeforeTimeout=count('get_table');
  for(let i=0;i<30;i++)app.watch_timeout();
  assert.equal(app.state.busy,true); assert.equal(app.state.uncertain,true);
  const writes=count('create_table'); await app.create_selected(); assert.equal(count('create_table'),writes);
  resolveCreate(response('rooms','00000000-0000-4000-8000-000000000593')); await pending;
  assert.equal(count('get_table'),readsBeforeTimeout,'no readback after timed-out late result');
});

(async()=>{for(const [name,fn] of cases){await fn();console.log('PASS '+name);}
  console.log(`${cases.length} compiled WOR-59 scenarios passed (network forbidden).`);
})().catch(error=>{console.error(error);process.exitCode=1;});

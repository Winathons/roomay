// Offline scenarios for the actual compiled WOR-60 controller.
const fs=require('node:fs'), path=require('node:path'), vm=require('node:vm');
const assert=require('node:assert/strict');
globalThis.window=globalThis;
globalThis.document={getElementById:()=>({})};
let loadHandler;
globalThis.addEventListener=(event,handler)=>{if(event==='load')loadHandler=handler;};
globalThis.fetch=()=>{throw new Error('NETWORK FORBIDDEN IN CI');};
const output=process.argv[2], expected=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
vm.runInThisContext(fs.readFileSync(path.join(output,'workpeg-runtime.js'),'utf8'));
let registered;
Workpeg.router=value=>{registered=value;};
vm.runInThisContext(fs.readFileSync(path.join(output,'app.js'),'utf8'));
loadHandler();
const entry=registered.find(item=>item.path==='/b/[business_id]/dev-vertical-slice');
assert.ok(entry,'isolated vertical-slice route compiled');
const App=entry.app;
Workpeg.stateHandler=()=>({}); Workpeg.setInterval=()=>{};
const business=expected.business, typeUuid='00000000-0000-4000-8000-000000000060';
let routeBusiness=business, calls=[], rowsByKey={}, tableByKey={}, keyByUuid={};
let addBehavior=null, getRowBehavior=null, pendingAdd=null;
const clone=value=>JSON.parse(JSON.stringify(value));
const keyForName=name=>name==='Roomay Service Requests'?'service_requests':name==='Roomay Service Request Audit'?'service_request_audit':name;
const nameForKey=key=>key==='service_requests'?'Roomay Service Requests':key==='service_request_audit'?'Roomay Service Request Audit':key;
const idsForTables={};
function table(app,name,index){
  const key=keyForName(name), contract=app.contract(name);
  const value=clone(contract); delete value.alias;
  value.uuid='00000000-0000-4000-8000-'+String(index).padStart(12,'0');
  value.owner={id:900};
  for(const column of value.columns){if(!column.options)column.options={};if(!column.metadata)column.metadata={};}
  idsForTables[key]=value.uuid; keyByUuid[value.uuid]=key;
  return value;
}
function fixtureRow(data,id,fingerprint){
  return {id,fingerprint,permission:700,inherit_business_permission:true,
    inherit_individual_permissions:false,data:clone(data)};
}
function setup({preserveRemote=false}={}){
  calls=[]; addBehavior=null; getRowBehavior=null; pendingAdd=null;
  routeBusiness=business;
  if(!preserveRemote){
    rowsByKey={room_types:[fixtureRow({business_id:business,...expected.room_type},1,'type-fp-1')]};
    for(const key of ['rooms','guests','reservations','stays','stay_guests','room_blocks','service_requests','service_request_audit'])rowsByKey[key]=[];
  }
  const app=new App(); app.on_mount(); app.build();
  tableByKey={}; keyByUuid={};
  let index=60;
  for(const item of [['room_types'],['rooms'],['guests'],['reservations'],['stays'],['stay_guests'],['room_blocks'],['Roomay Service Requests'],['Roomay Service Request Audit']]){
    const name=item[0], key=keyForName(name); tableByKey[key]=table(app,name,index++);
  }
  const hotel=Object.values(tableByKey).filter(t=>t.namespace==='roomay_hotel_v1');
  const requests=Object.values(tableByKey).filter(t=>t.namespace==='roomay_requests_v1');
  Workpeg.routeParam=()=>routeBusiness;
  Workpeg.wpGetTables=async namespace=>{calls.push(['get_tables',namespace]);return clone(namespace==='roomay_hotel_v1'?hotel:requests);};
  Workpeg.wpGetTable=async uuid=>{calls.push(['get_table',uuid]);const key=keyByUuid[uuid];return clone(key?tableByKey[key]:null);};
  Workpeg.wpGetRows=async(uuid,options)=>{
    calls.push(['get_rows',uuid,clone(options)]);
    if(!keyByUuid[uuid])return null;
    const offset=options.offset||0, limit=options.limit||100;
    return clone(rowsByKey[keyByUuid[uuid]].slice(offset,offset+limit));
  };
  Workpeg.wpGetRow=async(uuid,rowId)=>{
    calls.push(['get_row',uuid,rowId]);
    if(getRowBehavior)return getRowBehavior(uuid,rowId);
    return clone((rowsByKey[keyByUuid[uuid]]||[]).find(row=>row.id===rowId)||null);
  };
  Workpeg.wpAddRow=async(uuid,payload)=>{
    calls.push(['add_row',uuid,clone(payload)]);
    if(addBehavior)return addBehavior(uuid,payload);
    const key=keyByUuid[uuid];
    const nextId=Math.max(1,...rowsByKey[key].map(row=>row.id))+1;
    const saved=fixtureRow(payload.data,nextId,'wor60-fp-'+nextId);
    rowsByKey[key].push(clone(saved));
    return clone(saved);
  };
  app.state.expected_business=business;
  app.state.owner_attestation='I VERIFIED ROOMAY AI OWNER CONTEXT';
  app.state.row_permission_attestation='I VERIFIED OWNER-ONLY ROW ACCESS';
  app.state.operational_date=expected.date;
  app.state.hotel_timezone=expected.zone;
  app.state.authoritative_local_now='2030-02-03T12:00:00';
  app.state.reconciliation_attestation='I RECONCILED ALL PRIOR WRITE OUTCOMES';
  app.state.stay_reload_verified=false;
  app.state.write_started_this_page=false;
  return app;
}
const count=kind=>calls.filter(call=>call[0]===kind).length;
const cases=[]; const test=(name,fn)=>cases.push([name,fn]);
function approveWrite(app){
  app.set_confirmation('CREATE ONE WOR60 ROW: '+app.state.selected_step);
  app.set_retry_ack('I UNDERSTAND SDK 401/403 REFRESH RETRY');
  app.set_reconciliation('I RECONCILED ALL PRIOR WRITE OUTCOMES');
}
async function prepare(app){await app.inspect();await app.prepare_next();}
async function createOne(app){approveWrite(app);await app.create_prepared();}

test('mount/build make no Workpeg calls and route remains isolated',async()=>{
  const app=setup();
  assert.equal(calls.length,0);
  assert.ok(!registered.some(item=>item.path==='/b/[business_id]/reception'));
});
test('all nine compiled schemas exactly match canonical domain contracts',async()=>{
  const app=setup();
  for(const name of app.table_names()){
    const key=keyForName(name), actual=app.contract(name), expectedContract=expected.contracts[key];
    assert.deepEqual(actual,expectedContract,name);
  }
});
test('inspect reads both namespaces, all nine direct schemas and paginated rows without writes',async()=>{
  const app=setup();
  await app.inspect();
  assert.equal(count('get_tables'),2); assert.equal(count('get_table'),9);
  assert.equal(count('get_rows'),9); assert.equal(count('add_row'),0);
  assert.match(app.state.status,/validated/);
  assert.equal(app.state.selected_step,'rooms');
});
test('wrong business and missing owner context fail before requests',async()=>{
  let app=setup(); routeBusiness='00000000-0000-4000-8000-000000000099'; await app.inspect();
  assert.equal(calls.length,0);
  app=setup(); app.state.owner_attestation=''; await app.inspect(); assert.equal(calls.length,0);
  app=setup(); app.state.row_permission_attestation=''; await app.inspect(); assert.equal(calls.length,0);
});
test('pagination reads every page and does not claim completeness after a malformed page',async()=>{
  let app=setup();
  const guests=[];
  for(let i=1;i<=101;i++)guests.push(fixtureRow({business_id:business,entity_id:'00000000-0000-4000-8000-'+String(1000+i).padStart(12,'0'),display_name:'Unexpected synthetic record '+i},i,'guestfp-'+i));
  rowsByKey.guests=guests;
  await app.inspect();
  const guestUuid=idsForTables.guests;
  assert.deepEqual(calls.filter(c=>c[0]==='get_rows'&&c[1]===guestUuid).map(c=>c[2].offset),[0,100]);
  assert.equal(count('add_row'),0); assert.match(app.state.error,/Unexpected|conflicting/);
  app=setup(); Workpeg.wpGetRows=async()=>({results:[]}); await app.inspect();
  assert.match(app.state.error,/Malformed|failed|incomplete/); assert.equal(count('add_row'),0);
});
test('exact room type preview uses preserved entity ID; no preview write occurs',async()=>{
  const app=setup(); await prepare(app);
  assert.equal(app.state.selected_step,'rooms');
  assert.deepEqual(app.state.selected_payload.data,{business_id:business,...expected.records.rooms[0]});
  assert.equal(count('add_row'),0);
  assert.equal(rowsByKey.room_types.length,1);
  await app.create_prepared(); assert.equal(count('add_row'),0,'missing exact typed confirmation cannot write');
});
test('wrong permission, duplicate schema and wrong-business row block all writes',async()=>{
  let app=setup(); tableByKey.rooms.permission='770';
  const hotel=Object.values(tableByKey).filter(t=>t.namespace==='roomay_hotel_v1');
  Workpeg.wpGetTables=async ns=>clone(ns==='roomay_hotel_v1'?hotel:Object.values(tableByKey).filter(t=>t.namespace==='roomay_requests_v1'));
  await app.inspect(); assert.equal(count('add_row'),0); assert.match(app.state.error,/permission|schema/i);
  app=setup(); rowsByKey.room_types[0].data.business_id='00000000-0000-4000-8000-000000000099';
  await app.inspect(); assert.equal(count('add_row'),0);
  app=setup(); rowsByKey.room_types[0].permission=740; await app.inspect();
  assert.equal(count('add_row'),0); assert.match(app.state.error,/permission/i);
  app=setup(); rowsByKey.room_types.push({...clone(rowsByKey.room_types[0]),id:2});
  await app.inspect(); assert.equal(count('add_row'),0); assert.match(app.state.error,/fingerprint|identity/i);
});
test('invalid date/timezone never prepares a row',async()=>{
  const app=setup(); app.state.hotel_timezone='Not/A_Timezone'; await app.inspect(); await app.prepare_next();
  assert.equal(app.state.selected_payload && Object.keys(app.state.selected_payload).length,0);
  assert.equal(count('add_row'),0);
});
test('each explicit create adds one row, verifies direct ID/fingerprint and fresh inventories',async()=>{
  let app=setup();
  for(const step of ['rooms','guests','reservations','stays','stay_guests']){
    await prepare(app); assert.equal(app.state.selected_step,step); await createOne(app);
    assert.equal(count('add_row'),1);
    assert.ok(app.state.last_success.includes(step));
    app=setup({preserveRemote:true});
  }
  assert.equal(rowsByKey.rooms.length,1);
  assert.equal(rowsByKey.stay_guests.length,1);
  assert.equal(rowsByKey.room_types.length,1,'the existing room type is preserved');
  assert.equal(count('get_row'),0,'fresh page has not issued a new write read-back');
});
function RECORD_INDEX(step){return ['rooms','guests','reservations','stays','stay_guests'].indexOf(step);}
test('service request requires a fresh-page stay verification and remains received/routed',async()=>{
  let app=setup();
  for(const step of ['rooms','guests','reservations','stays','stay_guests']){await prepare(app);await createOne(app);app=setup({preserveRemote:true});}
  await app.inspect(); await app.prepare_next();
  assert.equal(app.state.selected_step,'service_requests');
  assert.equal(count('add_row'),0);
  assert.equal(app.state.stay_reload_verified,false,'owner reload attestation is required');
  app.state.stay_reload_attestation='I RELOADED AND VERIFIED THE ACTIVE STAY';
  await app.prepare_next();
  assert.equal(app.state.stay_reload_verified,true);
  const request=app.state.selected_payload.data;
  assert.equal(request.category,'extra_towels'); assert.equal(request.department,'housekeeping');
  assert.equal(request.status,'received'); assert.equal(request.business_id,business);
  await createOne(app); assert.equal(count('add_row'),1);
  assert.equal(app.state.uncertain,false);
});
test('full seven-row fixture resolves only after request and matching audit row',async()=>{
  let app=setup();
  for(const step of ['rooms','guests','reservations','stays','stay_guests']){await prepare(app);await createOne(app);app=setup({preserveRemote:true});}
  app.state.stay_reload_attestation='I RELOADED AND VERIFIED THE ACTIVE STAY';
  await app.inspect(); await app.prepare_next(); assert.equal(app.state.selected_step,'service_requests');
  await createOne(app);
  app=setup({preserveRemote:true}); app.state.stay_reload_attestation='I RELOADED AND VERIFIED THE ACTIVE STAY';
  await app.inspect(); await app.prepare_next(); assert.equal(app.state.selected_step,'service_request_audit');
  await createOne(app);
  app=setup({preserveRemote:true}); app.state.stay_reload_attestation='I RELOADED AND VERIFIED THE ACTIVE STAY';
  await app.inspect();
  assert.equal(rowsByKey.service_requests[0].data.last_event_id,rowsByKey.service_request_audit[0].data.event_id);
  assert.equal(app.state.selected_step,'complete'); assert.equal(count('add_row'),0);
});
test('stale inventory after preparation prevents a write',async()=>{
  const app=setup(); await prepare(app);
  rowsByKey.rooms.push(fixtureRow({business_id:business,...expected.records.rooms[0]},71,'stale-room'));
  await createOne(app);
  assert.equal(count('add_row'),0); assert.match(app.state.error,/Unexpected|changed|prefix/);
});
test('failed or malformed write/readback is uncertain and cannot retry',async()=>{
  const app=setup(); await prepare(app); approveWrite(app);
  addBehavior=async()=>{throw new Error('HTTP 500 SECRET BODY');}; await app.create_prepared();
  assert.equal(app.state.uncertain,true); assert.equal(count('add_row'),1);
  assert.match(app.state.error,/Outcome uncertain; do not retry/);
  assert.doesNotMatch(app.state.error,/No write was attempted/);
  assert.ok(!JSON.stringify(app.state).includes('SECRET BODY'));
  await app.create_prepared(); assert.equal(count('add_row'),1);
  const app2=setup(); await prepare(app2); approveWrite(app2);
  getRowBehavior=async(uuid,rowId)=>fixtureRow({business_id:business,...expected.records.rooms[0]},rowId,'mismatched-readback');
  await app2.create_prepared(); assert.equal(app2.state.uncertain,true);
  assert.match(app2.state.error,/Direct row read-back/);
});
test('authorization errors after a write starts remain uncertain and never claim read-only failure',async()=>{
  const app=setup(); await prepare(app); approveWrite(app);
  addBehavior=async()=>{throw new Error('HTTP 403 provider denied after possible mutation');};
  await app.create_prepared();
  assert.equal(count('add_row'),1);
  assert.equal(app.state.uncertain,true);
  assert.match(app.state.error,/Authorization error during or after row creation/);
  assert.match(app.state.error,/Outcome uncertain; do not retry/);
  assert.doesNotMatch(app.state.error,/No write was attempted/);
  await app.create_prepared();
  assert.equal(count('add_row'),1,'no second write while outcome is unknown');
});
test('timeout keeps the in-flight lock and ignores a late create result',async()=>{
  const app=setup(); await prepare(app); approveWrite(app);
  let resolveAdd; addBehavior=()=>new Promise(resolve=>{resolveAdd=resolve;});
  const pending=app.create_prepared(); await new Promise(resolve=>setImmediate(resolve));
  for(let i=0;i<30;i++)app.watch_timeout();
  assert.equal(app.state.busy,true); assert.equal(app.state.uncertain,true);
  const adds=count('add_row'); await app.create_prepared(); assert.equal(count('add_row'),adds);
  resolveAdd(fixtureRow({business_id:business,...expected.records.rooms[0]},72,'late-room')); await pending;
  assert.equal(count('get_row'),0); assert.equal(count('add_row'),1);
});
test('compiled Workpeg date capability checks IANA boundaries, not arbitrary offsets',async()=>{
  const app=setup();
  app.state.hotel_timezone='Africa/Lagos';
  app.state.operational_date='2030-02-03';
  app.state.authoritative_local_now='2030-02-03T00:30:00';
  assert.equal(app.local_utc(),'2030-02-02T23:30:00+00:00');
  app.state.hotel_timezone='Not/A_Timezone'; assert.equal(app.local_utc(),null);
  app.state.hotel_timezone='Africa/Lagos'; app.state.authoritative_local_now='2030-02-02T23:30:00';
  assert.equal(app.local_utc(),null,'wall time date cannot disagree with operational date');
});

(async()=>{
  for(const [name,fn] of cases){try{await fn();console.log('PASS '+name);}catch(error){console.error('FAIL '+name+'\n'+error.stack);process.exitCode=1;}}
  console.log(cases.length+' compiled WOR-60 scenarios executed (network forbidden).');
})();

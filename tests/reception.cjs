// Exercise the compiled read-only receptionist projection with synthetic test data.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

globalThis.window = globalThis;
let loadHandler;
globalThis.addEventListener = (event, handler) => { if (event === 'load') loadHandler = handler; };
globalThis.fetch = () => { throw new Error('NETWORK FORBIDDEN IN RECEPTION TEST'); };
const output = process.argv[2];
const releaseHtml = fs.readFileSync(path.join(output, 'index.html'), 'utf8');
const compiledApp = fs.readFileSync(path.join(output, 'app.js'), 'utf8');
assert.match(releaseHtml, /fonts\.googleapis\.com\/css2\?family=Plus\+Jakarta\+Sans/);
assert.match(compiledApp, /--color-brand-primary/);
assert.match(compiledApp, /--font-base/);
vm.runInThisContext(fs.readFileSync(path.join(output, 'workpeg-runtime.js'), 'utf8'));
let registeredRoutes;
Workpeg.router = routes => { registeredRoutes = routes; };
vm.runInThisContext(fs.readFileSync(path.join(output, 'app.js'), 'utf8'));
assert.equal(typeof loadHandler, 'function');
loadHandler();
assert.ok(Array.isArray(registeredRoutes), 'generated router registers its compiled routes');
const ReceptionTest = registeredRoutes.find(route => route.path === '/b/[business_id]/reception').app;
assert.equal(typeof ReceptionTest, 'function');
const Home = registeredRoutes.find(route => route.path === '/').app;
const homeTree = JSON.stringify(new Home().build());
assert.match(homeTree, /Roomay reception is available inside an authenticated Workpeg business\./);
Workpeg.stateHandler = () => ({});
Workpeg.routeParam = () => '00000000-0000-4000-8000-000000000034';

const id = n => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const app = new ReceptionTest();
app.state.operational_date = '2026-11-06';
app.state.room_types = [{entity_id: id(1), name: 'Standard', capacity: 2}];
app.state.rooms = [
  {entity_id: id(2), number: '201', room_type_id: id(1), enabled: true, housekeeping: 'ready'},
  {entity_id: id(3), number: '202', room_type_id: id(1), enabled: true, housekeeping: 'dirty'},
  {entity_id: id(6), number: '203', room_type_id: id(1), enabled: true, housekeeping: 'ready'},
];
app.state.guests = [{entity_id: id(4), display_name: 'Synthetic Test Guest'}];
app.state.reservations = [{entity_id: id(5), guest_id: id(4), room_type_id: id(1),
  room_id: id(2), arrival: '2026-11-06', departure: '2026-11-07', party_size: 1,
  source: 'advance', status: 'confirmed'}];
app.state.stays = [];
app.state.room_blocks = [];
app.state.service_requests = [];
app.state.view_state = 'loaded';
app.state.status = 'Records loaded successfully';
app.project_records();

assert.equal(app.state.metrics.length, 8);
assert.equal(app.state.arrival_cards.length, 1);
assert.equal(app.state.in_house_cards.length, 0);
assert.equal(app.state.room_cards.length, 3);
assert.equal(app.state.room_cards[0].occupancy, 'Arriving today');
assert.equal(app.state.room_cards[1].housekeeping, 'dirty');
assert.equal(app.state.metrics.find(item => item.label === 'Maintenance-blocked rooms').value, 0);
app.set_filter('Needs cleaning');
assert.equal(app.state.room_filter, 'Needs cleaning');
app.set_filter('All rooms');

const visit = (node, predicate, found = []) => {
  if (Array.isArray(node)) {
    for (const child of node) visit(child, predicate, found);
  } else if (node && typeof node === 'object') {
    if (predicate(node)) found.push(node);
    visit(node.children, predicate, found);
  }
  return found;
};
const tree = app.build();
const todayMarkup = JSON.stringify(tree);
assert.match(todayMarkup, /Today at a glance/);
for (const label of [
  'In house', 'Arrivals', 'Scheduled departures today', 'Overdue active stays',
  'Ready for check-in', 'Needs cleaning', 'Maintenance-blocked rooms',
  'Open requests',
]) assert.match(todayMarkup, new RegExp(label));
assert.match(todayMarkup, /min-height/);
assert.match(todayMarkup, /min-width/);
const navButtons = visit(tree, node => node.type === 'button' &&
  ['Today', 'Rooms & availability', 'Service requests'].includes(node.props.label));
assert.equal(navButtons.length, 3);
navButtons[1].props.handler();
assert.equal(app.state.active_view, 'Rooms');
app.state.active_view = 'Rooms';
const roomsTree = app.build();
assert.match(JSON.stringify(roomsTree), /Rooms & availability/);
const detailButtons = visit(roomsTree, node => node.type === 'button' && node.props.label === 'View details');
assert.equal(detailButtons.length, 3);
for (const [index, roomNumber] of ['201', '202', '203'].entries()) {
  detailButtons[index].props.handler();
  assert.equal(app.state.selected_room, roomNumber);
}
app.state.active_view = 'Rooms';
const filterButtons = visit(app.build(), node => node.type === 'button' && node.props.label === 'Needs cleaning');
assert.equal(filterButtons.length, 1);
filterButtons[0].props.handler();
assert.equal(app.state.room_filter, 'Needs cleaning');
app.set_filter('All rooms');

const previousMetrics = JSON.stringify(app.state.metrics);
app.set_operational_date('not-a-date');
assert.equal(app.state.operational_date, '2026-11-06');
assert.match(app.state.date_error, /last valid operational date/);
assert.equal(JSON.stringify(app.state.metrics), previousMetrics);
app.set_operational_date('2026-11-07');
assert.equal(app.state.operational_date, '2026-11-07');
assert.equal(app.state.date_error, '');
assert.equal(app.state.arrival_cards.length, 0);

const overdue = new ReceptionTest();
overdue.state.operational_date = '2026-11-08';
overdue.state.room_types = app.state.room_types;
overdue.state.rooms = [app.state.rooms[0]];
overdue.state.guests = app.state.guests;
overdue.state.reservations = [{...app.state.reservations[0], arrival: '2026-11-06', departure: '2026-11-07'}];
overdue.state.stays = [{entity_id: id(7), reservation_id: id(5), room_id: id(2),
  checked_in_at: '2026-11-06T15:00:00+00:00', status: 'checked_in'}];
overdue.state.room_blocks = [];
overdue.state.service_requests = [];
overdue.state.view_state = 'loaded';
overdue.project_records();
assert.equal(overdue.state.in_house_cards.length, 1);
assert.equal(overdue.state.room_cards[0].occupancy, 'In house');
assert.equal(overdue.state.departure_cards.length, 0);
assert.equal(overdue.state.overdue_departure_cards.length, 1);
assert.equal(overdue.state.metrics.find(item => item.label === 'Overdue active stays').value, 1);

const rendered = JSON.stringify(overdue.build());
assert.match(rendered, /Today/);
assert.match(rendered, /WORKPEG RECORDS/);
assert.match(rendered, /OVERDUE/);
assert.match(rendered, /This workspace is read only/);
assert.match(rendered, /Authentication required/);
assert.match(rendered, /Access denied/);
assert.match(rendered, /Connection unavailable/);
assert.doesNotMatch(rendered, /DEMO DATA|Fictional|create_table|add_row|update_row|â|Â/);

// Exercise the compiled projection with the exact relationship shape used by
// the canonical WOR-60 synthetic vertical slice, including persisted audit
// rows. Canary private fields must not enter the rendered receptionist tree.
const sliceApp = new ReceptionTest();
sliceApp.state.operational_date = '2026-11-08';
sliceApp.state.room_types = [{entity_id: id(101), name: 'Roomay TEST Room Type (Fictional)', capacity: 3}];
sliceApp.state.rooms = [{entity_id: id(102), number: '205', room_type_id: id(101),
  enabled: true, housekeeping: 'ready'}];
sliceApp.state.guests = [{entity_id: id(103), display_name: 'WOR-60 Fictional Guest (Synthetic)'}];
sliceApp.state.reservations = [{entity_id: id(104), guest_id: id(103), room_type_id: id(101),
  room_id: id(102), arrival: '2026-11-08', departure: '2026-11-10', party_size: 1,
  source: 'advance', status: 'confirmed'}];
sliceApp.state.stays = [{entity_id: id(105), reservation_id: id(104), room_id: id(102),
  checked_in_at: '2026-11-08T15:00:00+00:00', status: 'checked_in'}];
sliceApp.state.stay_guests = [{entity_id: id(106), stay_id: id(105), guest_id: id(103),
  joined_at: '2026-11-08T15:00:00+00:00'}];
sliceApp.state.room_blocks = [];
sliceApp.state.service_requests = [{request_id: id(107), hotel_id: id(108), stay_id: id(105),
  room_id: id(102), guest_id: id(103), origin: 'reception_desk', category: 'extra_towels',
  description: 'Synthetic WOR-60 extra-towels request for Room 205.', urgency: 'normal',
  department: 'housekeeping', status: 'received', last_event_id: id(109), triage_required: false}];
sliceApp.state.request_audit = [{event_id: id(109), hotel_id: id(108), request_id: id(107),
  sequence: 1, event_type: 'created', from_status: null, to_status: 'received',
  actor_id: 'PRIVATE-ACTOR-CANARY', actor_kind: 'staff', actor_department: 'reception',
  reason: 'PRIVATE-REASON-CANARY', occurred_at: '2026-11-08T15:01:00+00:00',
  commit_state: 'pending', operation_id: 'PRIVATE-OPERATION-CANARY',
  operation_signature: 'PRIVATE-SIGNATURE-CANARY'}];
sliceApp.state.view_state = 'loaded';
sliceApp.state.status = 'Records loaded successfully';
sliceApp.project_records();
assert.equal(sliceApp.state.in_house_cards[0].guest, 'WOR-60 Fictional Guest (Synthetic)');
assert.equal(sliceApp.state.in_house_cards[0].reservation_status, 'confirmed');
assert.equal(sliceApp.state.in_house_cards[0].stay_status, 'checked_in');
assert.equal(sliceApp.state.request_cards[0].room, '205');
assert.equal(sliceApp.state.request_cards[0].department, 'housekeeping');
assert.equal(sliceApp.state.request_cards[0].status, 'received');
assert.match(sliceApp.state.request_cards[0].audit_status, /delivery is not represented/);
sliceApp.state.active_view = 'Rooms';
const roomsSliceTree = JSON.stringify(sliceApp.build());
assert.match(roomsSliceTree, /Roomay TEST Room Type/);
assert.match(roomsSliceTree, /WOR-60 Fictional Guest \(Synthetic\)/);
assert.match(roomsSliceTree, /Reservation: confirmed/);
sliceApp.state.active_view = 'Requests';
const sliceTree = JSON.stringify(sliceApp.build());
assert.match(sliceTree, /extra_towels - housekeeping/);
assert.match(sliceTree, /received/);
assert.match(sliceTree, /Audit 1: created - start/);
assert.match(sliceTree, /delivery is not represented/);
assert.doesNotMatch(sliceTree, /PRIVATE-ACTOR-CANARY|PRIVATE-REASON-CANARY|PRIVATE-OPERATION-CANARY|PRIVATE-SIGNATURE-CANARY/);

console.log('compiled reception controller: Room 205 vertical slice, audit privacy, dates, overdue stays and three room callbacks passed');

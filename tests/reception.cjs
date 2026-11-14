// Exercise the compiled read-only receptionist projection with synthetic test data.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

globalThis.window = globalThis;
let loadHandler;
globalThis.addEventListener = (event, handler) => { if (event === 'load') loadHandler = handler; };
globalThis.fetch = () => { throw new Error('NETWORK FORBIDDEN IN RECEPTION TEST'); };
let routeWorkspace = '';
let navigationTarget = '';
const output = process.argv[2];
const releaseHtml = fs.readFileSync(path.join(output, 'index.html'), 'utf8');
const compiledApp = fs.readFileSync(path.join(output, 'app.js'), 'utf8');
const compiledIcons = fs.readFileSync(path.join(output, 'icons.css'), 'utf8');
assert.match(releaseHtml, /fonts\.googleapis\.com\/css2\?family=Inter/);
assert.match(compiledApp, /--color-brand-primary/);
assert.match(compiledApp, /--font-base/);
for (const icon of ['layout-dashboard', 'bed', 'clipboard-list', 'eye', 'refresh', 'brush']) {
  assert.match(compiledIcons, new RegExp(`\\.ti-${icon}(?:\\s|\\{)`));
}
vm.runInThisContext(fs.readFileSync(path.join(output, 'workpeg-runtime.js'), 'utf8'));
let registeredRoutes;
Workpeg.router = routes => { registeredRoutes = routes; };
vm.runInThisContext(fs.readFileSync(path.join(output, 'app.js'), 'utf8'));
assert.equal(typeof loadHandler, 'function');
loadHandler();
assert.ok(Array.isArray(registeredRoutes), 'generated router registers its compiled routes');
const ReceptionTest = registeredRoutes.find(route => route.path === '/b/[business_id]/reception').app;
assert.equal(typeof ReceptionTest, 'function');
assert.ok(registeredRoutes.some(route =>
  route.path === '/b/[business_id]/reception/[workspace]' && route.app === ReceptionTest),
  'housekeeping workspace is business scoped and uses the same validated reader');
const Home = registeredRoutes.find(route => route.path === '/').app;
const homeTree = JSON.stringify(new Home().build());
assert.match(homeTree, /Roomay reception is available inside an authenticated Workpeg business\./);
Workpeg.stateHandler = () => ({});
Workpeg.routeParam = name => name === 'workspace' ? routeWorkspace :
  '00000000-0000-4000-8000-000000000034';
Workpeg.navigate = target => { navigationTarget = target; };

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
assert.match(todayMarkup, /600px/);
assert.match(todayMarkup, /max-width/);
assert.match(todayMarkup, /outline-gray/);
assert.doesNotMatch(todayMarkup, /outline-color/);
assert.match(todayMarkup, /font-size/);
assert.match(todayMarkup, /38px/);
assert.match(todayMarkup, /#f8f9f7/);
const navButtons = visit(tree, node => node.type === 'button' &&
  ['Today', 'Rooms & availability', 'Service requests'].includes(node.props.label));
assert.equal(navButtons.length, 3);
assert.deepEqual(navButtons.map(node => node.props.icon),
  ['layout-dashboard', 'bed', 'clipboard-list']);
for (const [index, button] of navButtons.entries()) {
  assert.equal(button.props.variant, 'ghost-gray');
  assert.equal(button.props.style[':rest'].color, index === 0 ? '#181a1a' : '#515653');
  assert.equal(button.props.style[':rest']['background-color'], index === 0 ? '#f0f1ef' : 'transparent');
  assert.equal(button.props.style[':hover'].color, '#181a1a');
  assert.equal(button.props.style[':hover']['background-color'], index === 0 ? '#e8eae7' : '#f0f1ef');
  assert.equal(button.props.style[':focus-visible'].color, '#181a1a');
  assert.equal(button.props.style[':focus-visible']['background-color'], index === 0 ? '#e8eae7' : '#f0f1ef');
  assert.equal(button.props.style[':focus-visible'].outline, '2px solid #181a1a');
  assert.equal(button.props.style[':active'].color, '#181a1a');
}
assert.match(todayMarkup, /WORKPEG SNAPSHOT/);
assert.match(todayMarkup, /READ ONLY/);
assert.doesNotMatch(todayMarkup, /WORKPEG SNAPSHOT - READ ONLY/);
const businessId = Workpeg.routeParam();
assert.doesNotMatch(todayMarkup, new RegExp(businessId), 'business ID is collapsed by default');
const showBusinessId = visit(tree, node => node.type === 'button' && node.props.label === 'Show ID');
assert.equal(showBusinessId.length, 1);
assert.equal(showBusinessId[0].props.handler, 'toggle_business_id');
app.toggle_business_id();
assert.match(JSON.stringify(app.build()), new RegExp(businessId), 'business scope can be inspected without removing route validation');
app.toggle_business_id();
const housekeepingLink = visit(app.build(), node => node.type === 'button' &&
  node.props.label === 'Housekeeping');
assert.equal(housekeepingLink.length, 1);
assert.equal(housekeepingLink[0].props.handler, 'open_housekeeping');
app.open_housekeeping();
assert.equal(navigationTarget,
  '/b/00000000-0000-4000-8000-000000000034/reception/housekeeping');
navButtons[1].props.handler();
assert.equal(app.state.active_view, 'Rooms');
app.state.active_view = 'Rooms';
const roomsTree = app.build();
assert.match(JSON.stringify(roomsTree), /Rooms & availability/);
assert.match(JSON.stringify(roomsTree), /Room board/);
assert.match(JSON.stringify(roomsTree), /Select a room to inspect details/);
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
assert.match(rendered, /WORKPEG SNAPSHOT/);
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
sliceApp.state.room_types = [{entity_id: id(101), name: 'Roomay TEST Room Type (Fictional) Presidential Family Suite With A Long Label', capacity: 3}];
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
  department: 'housekeeping', status: 'received', last_event_id: id(109),
  version: 1, updated_at: '2026-11-08T15:01:00+00:00',
  last_operation_signature: 'PRIVATE-SIGNATURE-CANARY', triage_required: false},
  {request_id: id(113), hotel_id: id(108), stay_id: id(105), room_id: id(102),
   guest_id: id(103), origin: 'reception_desk', category: 'plumbing',
   description: 'Synthetic WOR-60 plumbing request for Room 205.', urgency: 'high',
   department: 'maintenance', status: 'in_progress', last_event_id: id(114),
   version: 2, updated_at: '2026-11-08T15:02:00+00:00',
   last_operation_signature: 'PRIVATE-SECOND-SIGNATURE-CANARY', triage_required: false}];
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
assert.equal(sliceApp.state.request_cards[0].audit_tone, 'warning');
assert.equal(sliceApp.state.request_cards[0].department_label, 'Housekeeping');
assert.equal(sliceApp.state.request_cards[0].category_label, 'Extra towels');
assert.equal(sliceApp.state.request_cards[0].status_label, 'Received');
assert.match(sliceApp.state.request_cards[0].audit_status, /delivery is not represented/);
assert.deepEqual(sliceApp.state.request_summary.map(item => [item.label, item.value]), [
  ['Open requests', 2], ['New requests', 1], ['In progress', 1], ['Resolved today', 0],
]);
const overviewTree = sliceApp.build();
const overviewMarkup = JSON.stringify(overviewTree);
assert.match(overviewMarkup, /Recent guest requests/);
assert.match(overviewMarkup, /Latest requests from the validated WorkPeg snapshot/);
const overviewRequests = visit(overviewTree, node => node.type === 'button' &&
  node.props.label.includes('Synthetic WOR-60') && node.props.label.includes('request for Room 205.'));
assert.equal(overviewRequests.length, 2, 'overview preview links to both existing requests');
overviewRequests[1].props.handler();
assert.equal(sliceApp.state.selected_request, id(113), 'each row opens its own request');
assert.equal(sliceApp.state.active_view, 'Requests');
sliceApp.clear_selected_request();
sliceApp.state.active_view = 'Rooms';
const roomsSliceTree = JSON.stringify(sliceApp.build());
assert.match(roomsSliceTree, /Roomay TEST Room Type/);
assert.match(roomsSliceTree, /overflow-wrap/);
assert.match(roomsSliceTree, /Presidential Family Suite With A Long Label/);
assert.match(roomsSliceTree, /Room details/);
assert.match(roomsSliceTree, /WOR-60 Fictional Guest \(Synthetic\)/);
assert.match(roomsSliceTree, /Reservation/);
assert.match(roomsSliceTree, /confirmed/);
assert.match(roomsSliceTree, /Room guidance is not included in the authorized hotel table contract/);
sliceApp.state.active_view = 'Requests';
const requestsTree = sliceApp.build();
const requestsMarkup = JSON.stringify(requestsTree);
assert.match(requestsMarkup, /Guest requests/);
assert.match(requestsMarkup, /REQUEST/);
assert.match(requestsMarkup, /DEPARTMENT/);
assert.match(requestsMarkup, /Search requests, rooms or guests/);
assert.match(requestsMarkup, /Synthetic WOR-60 extra-towels request for Room 205/);
assert.match(requestsMarkup, /Staff assignment not configured/);
assert.match(requestsMarkup, /Open requests/);
assert.match(requestsMarkup, /Resolved today/);
const requestButton = visit(requestsTree, node => node.type === 'button' &&
  node.props.label === 'Synthetic WOR-60 extra-towels request for Room 205.');
assert.equal(requestButton.length, 1, 'request can be opened from the native table');
requestButton[0].props.handler();
assert.equal(sliceApp.state.selected_request, id(107));
const selectedRequestTree = sliceApp.build();
const selectedRequestMarkup = JSON.stringify(selectedRequestTree);
assert.match(selectedRequestMarkup, /Request details/);
assert.match(selectedRequestMarkup, /Issue details/);
assert.match(selectedRequestMarkup, /Audit history/);
assert.match(selectedRequestMarkup, /delivery is not represented/);
assert.match(selectedRequestMarkup, /Assignment, acknowledgement, status changes and guest messaging are unavailable/);
assert.doesNotMatch(selectedRequestMarkup, /PRIVATE-ACTOR-CANARY|PRIVATE-REASON-CANARY|PRIVATE-OPERATION-CANARY|PRIVATE-SIGNATURE-CANARY/);
const requestDetailBack = visit(selectedRequestTree, node => node.type === 'button' &&
  node.props.label === 'Back to requests');
assert.equal(requestDetailBack.length, 1);
assert.equal(requestDetailBack[0].props.handler, 'clear_selected_request');
sliceApp.clear_selected_request();
assert.equal(sliceApp.state.selected_request, '');
assert.doesNotMatch(JSON.stringify(sliceApp.build()), /Save changes|Send guest update|Acknowledge request|Mark resolved/,
  'request actions remain unavailable without an authorized write path');
sliceApp.state.rooms.push({entity_id: id(111), number: '206', room_type_id: id(101),
  enabled: true, housekeeping: 'dirty'});
sliceApp.state.room_blocks.push({entity_id: id(112), room_id: id(111),
  start: '2026-11-08', end: '2026-11-10', reason: 'test fixture', status: 'active'});
sliceApp.project_records();
routeWorkspace = 'housekeeping';
const housekeepingTree = JSON.stringify(sliceApp.build());
assert.match(housekeepingTree, /Housekeeping/);
assert.match(housekeepingTree, /Room readiness/);
assert.match(housekeepingTree, /Owner-only preview/);
assert.match(housekeepingTree, /Housekeeping staff are not authorized/);
assert.match(housekeepingTree, /Readiness overview/);
assert.match(housekeepingTree, /Housekeeping request activity/);
assert.match(housekeepingTree, /Extra towels/);
assert.match(housekeepingTree, /Room 205/);
assert.match(housekeepingTree, /Room 206/);
assert.match(housekeepingTree, /Dirty/);
assert.match(housekeepingTree, /Maintenance blocked/);
assert.match(housekeepingTree, /#fbfcf9/);
assert.match(housekeepingTree, /flex/);
assert.match(housekeepingTree, /box-shadow/);
assert.match(housekeepingTree, /#103a30/);
assert.equal(sliceApp.state.housekeeping_metrics.find(item => item.label === 'Needs cleaning').value, 1);
assert.match(housekeepingTree, /Received/);
assert.match(housekeepingTree, /Audit: Latest audit event pending commit/);
assert.match(housekeepingTree, /Guest message withheld/);
assert.doesNotMatch(housekeepingTree, /WOR-60 Fictional Guest|Synthetic WOR-60 extra-towels request/);
const housekeepingButtons = visit(sliceApp.build(), node => node.type === 'button');
assert.deepEqual(housekeepingButtons.map(node => node.props.label).sort(),
  ['Reception workspace', 'Refresh records', 'Show ID'].sort(),
  'Housekeeping preview exposes no operational action controls');
assert.match(housekeepingTree, /actions are unavailable/);
assert.match(housekeepingTree, /Authentication required/);
assert.match(housekeepingTree, /Access denied/);
assert.match(housekeepingTree, /Connection unavailable/);
const receptionLink = visit(sliceApp.build(), node => node.type === 'button' &&
  node.props.label === 'Reception workspace');
assert.equal(receptionLink.length, 1);
assert.equal(receptionLink[0].props.handler, 'open_reception');
sliceApp.open_reception();
assert.equal(navigationTarget, '/b/00000000-0000-4000-8000-000000000034/reception');
routeWorkspace = 'unknown';
sliceApp.load_snapshot();
assert.equal(sliceApp.state.view_state, 'connection_unavailable');
assert.equal(sliceApp.state.failure, 'This Roomay staff workspace is not available.');
assert.equal(sliceApp.state.freshness, 'No complete snapshot');
routeWorkspace = '';
sliceApp.state.request_audit[0].commit_state = 'committed';
sliceApp.project_records();
assert.equal(sliceApp.state.request_cards[0].audit_tone, 'neutral');
assert.match(sliceApp.state.request_cards[0].audit_status, /delivery is not represented/);

// A committed latest event cannot make a broken sequence look reconciled.
const sliceRequest = sliceApp.state.service_requests[0];
sliceRequest.status = 'in_progress';
sliceRequest.version = 3;
sliceRequest.last_event_id = id(110);
sliceRequest.updated_at = '2026-11-08T15:03:00+00:00';
sliceRequest.last_operation_signature = 'PRIVATE-SIGNATURE-GAP-CANARY';
sliceApp.state.request_audit.push({event_id: id(110), hotel_id: id(108), request_id: id(107),
  sequence: 3, event_type: 'status_changed', from_status: 'acknowledged', to_status: 'in_progress',
  actor_id: 'PRIVATE-SECOND-ACTOR-CANARY', actor_kind: 'staff', actor_department: 'housekeeping',
  reason: null, occurred_at: '2026-11-08T15:03:00+00:00', commit_state: 'committed',
  operation_id: 'PRIVATE-SECOND-OPERATION-CANARY',
  operation_signature: 'PRIVATE-SIGNATURE-GAP-CANARY'});
sliceApp.project_records();
assert.equal(sliceApp.state.request_cards[0].audit_tone, 'warning');
assert.match(sliceApp.state.request_cards[0].audit_status, /incomplete or mismatched/);
assert.doesNotMatch(sliceApp.state.request_cards[0].audit_status, /marked committed/);

// Restore a complete single-event chain, then catch a stale request signature.
sliceRequest.status = 'received';
sliceRequest.version = 1;
sliceRequest.last_event_id = id(109);
sliceRequest.updated_at = '2026-11-08T15:01:00+00:00';
sliceRequest.last_operation_signature = 'not-the-audit-signature';
sliceApp.state.request_audit = [sliceApp.state.request_audit[0]];
sliceApp.project_records();
assert.equal(sliceApp.state.request_cards[0].audit_tone, 'warning');
assert.match(sliceApp.state.request_cards[0].audit_status, /incomplete or mismatched/);

console.log('compiled reception controller: hotel projection, complete audit matching, privacy, dates, overdue stays and room callbacks passed');

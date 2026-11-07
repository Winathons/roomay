// Exercise the compiled read-only receptionist projection with synthetic test data.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

globalThis.window = globalThis;
globalThis.addEventListener = () => {};
globalThis.fetch = () => { throw new Error('NETWORK FORBIDDEN IN RECEPTION TEST'); };
const output = process.argv[2];
vm.runInThisContext(fs.readFileSync(path.join(output, 'workpeg-runtime.js'), 'utf8'));
vm.runInThisContext(fs.readFileSync(path.join(output, 'app.js'), 'utf8') +
  '\nglobalThis.ReceptionTest = HotelData;');
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
const detailButtons = visit(tree, node => node.type === 'button' && node.props.label === 'View details');
assert.equal(detailButtons.length, 3);
for (const [index, roomNumber] of ['201', '202', '203'].entries()) {
  detailButtons[index].props.handler();
  assert.equal(app.state.selected_room, roomNumber);
}

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
assert.match(rendered, /Reception workspace/);
assert.match(rendered, /WORKPEG RECORDS/);
assert.match(rendered, /OVERDUE/);
assert.match(rendered, /No mutation controls are enabled/);
assert.match(rendered, /Authentication required/);
assert.match(rendered, /Access denied/);
assert.match(rendered, /Connection unavailable/);
assert.doesNotMatch(rendered, /DEMO DATA|Fictional|create_table|add_row|update_row|â|Â/);

console.log('compiled reception controller: dates, overdue stays and three room callbacks passed');

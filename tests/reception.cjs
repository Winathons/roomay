// Exercise the real compiled receptionist controller with all network forbidden.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

globalThis.window = globalThis;
globalThis.addEventListener = () => {};
globalThis.fetch = () => { throw new Error('NETWORK FORBIDDEN IN RECEPTION DEMO'); };

const output = process.argv[2];
vm.runInThisContext(fs.readFileSync(path.join(output, 'workpeg-runtime.js'), 'utf8'));
vm.runInThisContext(fs.readFileSync(path.join(output, 'app.js'), 'utf8') + '\nglobalThis.Reception = ReceptionDemo;');
Workpeg.stateHandler = () => ({});

const app = new Reception();
assert.equal(app.state.room_filter, 'All rooms');
assert.equal(app.state.selected_room, '202');
assert.equal(app.state.metrics.length, 7);
assert.equal(app.state.rooms.length, 10);
assert.equal(app.state.requests.length, 4);

const rendered = JSON.stringify(app.build());
assert.match(rendered, /DEMO DATA — NOT CONNECTED TO LIVE WORKPEG/);
assert.doesNotMatch(rendered, /â|Â/);
app.set_filter('Blocked');
assert.equal(app.state.room_filter, 'Blocked');
assert.match(app.state.feedback, /only filters demo data/);
app.select_room('205');
assert.equal(app.state.selected_room, '205');
assert.match(app.state.feedback, /read-only demo data/);
app.preview_action('Guest check-in');
assert.match(app.state.failure, /unavailable in this demo/);
assert.match(app.state.failure, /No Workpeg write was attempted/);
app.set_filter('All rooms');
assert.equal(app.state.failure, '');

console.log('compiled reception controller: 1 offline scenario passed');

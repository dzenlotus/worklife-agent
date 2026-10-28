import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {NeighborPolicy, networkGroup} from '../src/worklife/p2p_transport/neighbors.mjs';

const key = number => BigInt(number).toString(16).padStart(64, '0');
const source = number => `10.${number >> 8}.${number % 256}.1`;
const badHost = '192.0.2.7';
const badGroup = networkGroup(badHost);
const make = (seed, saved = []) => new NeighborPolicy({seed, maxPeers: 32, now: () => 1_000_000, saved});
const failures = [], results = {};
function check(name, run) {
  try { run(); }
  catch (error) { failures.push({name, message: error.message}); }
}

const totals = {one_key: {selected: 0, probe: 0}, thousand_keys: {selected: 0, probe: 0}};
let unequalSeeds = 0;
for (let round = 0; round < 128; round++) {
  const seed = createHash('sha256').update(`worklife-neighbor-simulation/${round}`).digest();
  const draws = [];
  for (const badKeys of [1, 1000]) {
    const policy = make(seed), sources = new Map();
    for (let index = 1; index <= 16; index++) {
      policy.remember(key(index), source(index));
      sources.set(key(index), networkGroup(source(index)));
    }
    for (let index = 0; index < badKeys; index++) {
      const peer = key(100_000 + index);
      policy.remember(peer, badHost);
      sources.set(peer, badGroup);
    }
    const draw = {selected: 0, probe: 0};
    for (const peer of policy.tick().connect) {
      if (sources.get(peer.key) === badGroup) draw[peer.role]++;
    }
    draws.push(draw);
    const total = totals[badKeys === 1 ? 'one_key' : 'thousand_keys'];
    total.selected += draw.selected;
    total.probe += draw.probe;
  }
  if (draws[0].selected !== draws[1].selected || draws[0].probe !== draws[1].probe) unequalSeeds++;
}
results.selection = {seeds: 128, honest_source_groups: 16, hostile_source_groups: 1,
  hostile_keys: [1, 1000], endpoint_hosts_initially_known: false, draws: totals, unequal_seeds: unequalSeeds};
check('source-group draws are independent of key count in this model', () => assert.equal(unequalSeeds, 0));

const seed = createHash('sha256').update('worklife-neighbor-reservations').digest();
const reserved = make(seed);
let admitted = 0;
for (let index = 0; index < 1000; index++) {
  if (reserved.admit(key(200_000 + index), badHost)) admitted++;
}
for (let index = 1; index <= 16; index++) reserved.remember(key(index), source(index));
const local = reserved.tick().connect;
results.reservations = {unsolicited_attempts: 1000, admitted,
  selected_choices: local.filter(peer => peer.role === 'selected').length,
  probe_choices: local.filter(peer => peer.role === 'probe').length};
check('unsolicited peers preserve the local reservations', () => {
  assert.equal(admitted, 22);
  assert.equal(results.reservations.selected_choices, 8);
  assert.equal(results.reservations.probe_choices, 2);
});

const saved = Array.from({length: 32}, (_, index) => ({key: key(index + 1),
  source: source(index + 1), host: source(index + 1), verifiedAt: 900_000 + index}));
const knownKeys = new Set(saved.map(peer => peer.key));
const poisoned = make(seed, saved);
for (let index = 0; index < 1000; index++) poisoned.remember(key(300_000 + index), badHost);
const unverifiedRetained = poisoned.snapshot().filter(peer => knownKeys.has(peer.key)).length;
results.unverified_history_flood = {advertised_keys: 1000, saved_before: 32, saved_retained: unverifiedRetained,
  candidate_count: poisoned.status().candidates};
check('unverified advertisements preserve all saved useful history', () => assert.equal(unverifiedRetained, 32));

const verified = make(seed, saved);
for (let index = 0; index < 1000; index++) {
  const peer = key(400_000 + index);
  assert.equal(verified.admit(peer, badHost), 'incoming');
  assert.equal(verified.verified(peer), true);
  verified.closed(peer);
}
const retained = verified.snapshot().filter(peer => knownKeys.has(peer.key));
results.verified_history_flood = {sequential_incoming_keys: 1000, saved_before: 32,
  saved_retained: retained.length, retained_saved_groups: new Set(retained.map(peer => networkGroup(peer.host))).size,
  history_count: verified.snapshot().length};
check('same-endpoint verified churn preserves independent useful history', () => {
  assert.ok(retained.length > 0);
  assert.ok(new Set(retained.map(peer => networkGroup(peer.host))).size > 1);
  assert.ok(verified.snapshot().length <= 32);
});

const nat = make(seed);
for (let index = 1; index <= 16; index++) nat.remember(key(index), source(index));
for (const peer of nat.tick().connect) {
  assert.equal(nat.admit(peer.key, badHost), peer.role);
  nat.verified(peer.key);
}
results.shared_nat = {roles: nat.status().roles, degraded: nat.status().degraded,
  observed_selected_groups: nat.status().groups.selected.length};
check('shared NAT stays usable and reports limited diversity', () => {
  assert.equal(nat.status().roles.selected, 8);
  assert.equal(nat.status().roles.probe, 2);
  assert.equal(nat.status().degraded, true);
});

process.stdout.write(`${JSON.stringify({model: 'synthetic bounded neighbor policy; no network traffic',
  results, failures}, null, 2)}\n`);
if (failures.length) process.exitCode = 1;

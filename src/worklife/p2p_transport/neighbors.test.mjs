import test from 'node:test';
import assert from 'node:assert/strict';

const neighbors = await import('./neighbors.mjs').catch(() => null);
const key = n => n.toString(16).padStart(64, '0');
function policy(options = {}) {
  assert.ok(neighbors, 'the neighbor policy must exist');
  return new neighbors.NeighborPolicy({seed: Buffer.alloc(32, 7), ...options});
}
function candidates(p, count = 40, start = 1) {
  for (let i = start; i < start + count; i++) p.remember(key(i), `198.18.${i}.1`);
}

test('groups actual IPs by /24 and /48, normalizing mapped IPv4 without claiming unknown hosts', () => {
  policy();
  const {networkGroup} = neighbors;
  assert.equal(networkGroup('192.0.2.7'), networkGroup('::ffff:192.0.2.8'));
  assert.equal(networkGroup('::ffff:c000:0208'), networkGroup('192.0.2.7'));
  assert.equal(networkGroup('2001:db8:3:4::1'), networkGroup('2001:0db8:0003:ffff::2'));
  assert.notEqual(networkGroup('2001:db8:3::1'), networkGroup('2001:db8:4::1'));
  for (const host of [null, 'unknown', 'relay', 'example.test', 'not an IP']) assert.equal(networkGroup(host), null);
});

test('candidate floods are bounded globally and per observed discovery source', () => {
  const p = policy();
  for (let i = 1; i <= 1000; i++) p.remember(key(i), '203.0.113.8');
  assert.ok(p.status().candidates <= 8);
  for (let i = 1001; i <= 2000; i++) p.remember(key(i), `198.18.${i % 256}.1`);
  assert.ok(p.status().candidates <= 256);
});

test('reserves selected and probe capacity before accepting unsolicited peers', () => {
  const p = policy();
  for (let i = 1000; i < 1032; i++) p.admit(key(i), '203.0.113.1');
  assert.equal(p.status().roles.incoming, 22);
  candidates(p);
  const next = p.tick();
  assert.equal(next.connect.filter(peer => peer.role === 'selected').length, 8);
  assert.equal(next.connect.filter(peer => peer.role === 'probe').length, 2);
  for (const peer of next.connect) assert.equal(p.admit(peer.key, '192.0.2.1'), peer.role);
  assert.equal(p.status().active, 32);
  assert.equal(p.admit(key(9000), '192.0.2.2'), null);
});

test('a two-peer node retains one inbound slot and can choose one local neighbor', () => {
  const p = policy({maxPeers: 2});
  candidates(p);
  const next = p.tick();
  assert.equal(next.connect.length, 1);
  assert.equal(p.admit(key(1000), '203.0.113.4'), 'incoming');
  assert.equal(p.admit(next.connect[0].key, '198.51.100.5'), 'selected');
  assert.equal(p.admit(key(1001), '203.0.113.5'), null);
});

test('source-group selection is private-seeded and is not weighted by advertised key count', () => {
  const p = policy();
  for (let i = 1; i <= 8; i++) p.remember(key(i), '203.0.113.1');
  for (let i = 10; i < 20; i++) p.remember(key(i), `198.18.${i}.1`);
  assert.ok(p.tick().connect.filter(peer => Number.parseInt(peer.key, 16) <= 8).length <= 1);
  const other = policy({seed: Buffer.alloc(32, 8)});
  candidates(other);
  const same = policy();
  candidates(same);
  assert.notDeepEqual(other.tick().connect, same.tick().connect);
});

test('only protocol-verified active peers enter bounded successful history, protected against floods', () => {
  const p = policy();
  candidates(p);
  const first = p.tick().connect[0];
  assert.equal(p.verified(first.key), false);
  assert.deepEqual(p.snapshot(), []);
  p.admit(first.key, '192.0.2.9');
  p.verified(first.key);
  assert.deepEqual(p.snapshot().map(peer => peer.key), [first.key]);
  for (let i = 2000; i < 4000; i++) p.remember(key(i), `198.19.${i % 256}.1`);
  assert.ok(p.snapshot().some(peer => peer.key === first.key));
  assert.ok(p.status().candidates <= 256);
  const restored = policy({saved: p.snapshot()});
  assert.deepEqual(restored.snapshot(), p.snapshot());
});

test('successful same-endpoint churn cannot erase diverse prior useful history', () => {
  let time = 1000000;
  const saved = Array.from({length: 32}, (_, index) => ({key: key(index + 1),
    source: `198.18.${index}.1`, host: `198.18.${index}.1`, verifiedAt: index}));
  const p = policy({saved, now: () => time});
  for (let index = 1000; index < 2000; index++) {
    const peer = key(index);
    assert.equal(p.admit(peer, '203.0.113.9'), 'incoming');
    assert.equal(p.verified(peer), true);
    p.closed(peer);
    time++;
  }
  const retained = p.snapshot().filter(peer => saved.some(old => old.key === peer.key));
  assert.ok(retained.length >= 30, 'one endpoint group erased diverse working history');
  assert.ok(p.snapshot().length <= 32);
  assert.ok(p.status().candidates <= 256);
});

test('local requested roles survive duplicate admission and close/open replacement', () => {
  let time = 0;
  const p = policy({now: () => time});
  candidates(p);
  const first = p.tick().connect[0];
  assert.equal(p.admit(first.key, '192.0.2.1'), first.role);
  assert.equal(p.admit(first.key, '192.0.2.1'), first.role);
  assert.equal(p.status().active, 1);
  p.closed(first.key);
  time += 100;
  assert.equal(p.admit(first.key, '192.0.2.2'), first.role);
  assert.equal(p.status().active, 1);
});

test('a replacement stream refreshes its observed endpoint without consuming another slot', () => {
  const p = policy();
  candidates(p);
  const selected = p.tick().connect.filter(peer => peer.role === 'selected');
  p.admit(selected[0].key, null);
  p.admit(selected[1].key, '192.0.2.1');
  assert.equal(p.status().degraded, true);
  assert.equal(p.admit(selected[0].key, '198.51.100.1'), 'selected');
  assert.equal(p.status().active, 2);
  assert.equal(p.status().degraded, false);
});

test('failed pending requests expire into cooldown before fresh candidates are tried', () => {
  let time = 0;
  const p = policy({now: () => time});
  candidates(p);
  const first = p.tick().connect;
  time += 30001;
  const next = p.tick();
  assert.equal(next.disconnect.length, 10);
  assert.equal(next.connect.length, 10);
  assert.ok(next.connect.every(peer => !first.some(old => old.key === peer.key)));
  assert.equal(p.status().pending, 10);
});

test('probe rotation explores new candidates while stable selected peers remain', () => {
  let time = 0;
  const p = policy({now: () => time});
  candidates(p);
  const first = p.tick().connect;
  for (const peer of first) p.admit(peer.key, '192.0.2.1');
  time += 60001;
  const next = p.tick();
  assert.deepEqual(new Set(next.disconnect), new Set(first.filter(peer => peer.role === 'probe').map(peer => peer.key)));
  assert.equal(next.connect.length, 2);
  assert.ok(next.connect.every(peer => peer.role === 'probe'));
  assert.equal(p.status().roles.selected, 8);
});

test('verified diverse probes replace one overrepresented selected peer and preserve diverse selections', () => {
  const p = policy();
  candidates(p);
  const first = p.tick().connect;
  const selected = first.filter(peer => peer.role === 'selected');
  const probe = first.find(peer => peer.role === 'probe');
  for (const peer of selected) p.admit(peer.key, '192.0.2.1');
  p.admit(probe.key, '198.51.100.1');
  p.verified(probe.key);
  const next = p.tick();
  assert.equal(next.disconnect.length, 1);
  assert.ok(selected.some(peer => peer.key === next.disconnect[0]));
  assert.equal(p.admit(probe.key, '198.51.100.1'), 'selected');
  assert.equal(p.status().groups.selected.length, 2);
  assert.equal(p.status().degraded, false);
});

test('shared NAT remains usable and reports degraded diversity; unknown hosts never count', () => {
  const p = policy();
  candidates(p);
  for (const peer of p.tick().connect) p.admit(peer.key, '192.0.2.1');
  assert.equal(p.status().active, 10);
  assert.equal(p.status().degraded, true);
  assert.equal(p.status().groups.selected.length, 1);
  const unknown = policy();
  candidates(unknown);
  for (const peer of unknown.tick().connect) unknown.admit(peer.key, 'relay');
  assert.equal(unknown.status().groups.selected.length, 0);
  assert.equal(unknown.status().degraded, true);
});

test('rejected malicious peers are removed from candidate history and requests', () => {
  const p = policy();
  candidates(p);
  const first = p.tick().connect[0];
  p.admit(first.key, '192.0.2.1');
  p.verified(first.key);
  p.rejected(first.key);
  assert.ok(!p.snapshot().some(peer => peer.key === first.key));
  assert.ok(!p.tick().connect.some(peer => peer.key === first.key));
});

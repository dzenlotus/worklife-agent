import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, readFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawn} from 'node:child_process';
import {createSocket} from 'node:dgram';
import {once} from 'node:events';
import DHT from 'hyperdht';
import Hyperswarm from 'hyperswarm';
import {NeighborPolicy, networkGroup} from './neighbors.mjs';

const key = number => BigInt(number).toString(16).padStart(64, '0');
const host = number => `10.${number >> 8}.${number % 256}.1`;

function policy(saved = [], seed = Buffer.alloc(32, 11)) {
  let clock = 1_000_000;
  return {
    value: new NeighborPolicy({seed, maxPeers: 32, now: () => clock, saved}),
    advance(milliseconds) { clock += milliseconds; }
  };
}

function candidates(value, count, start = 1) {
  for (let index = 0; index < count; index++) {
    assert.equal(value.remember(key(start + index), host(start + index)), true);
  }
}

test('a thousand identities from one discovery network cannot own the candidate pool', () => {
  const {value} = policy();
  for (let index = 0; index < 1000; index++) {
    value.remember(key(index + 1), `192.0.2.${1 + index % 254}`);
  }
  assert.ok(value.status().candidates <= 8, 'one IPv4 /24 exceeded its candidate allowance');
  candidates(value, 40, 2000);
  const plan = value.tick().connect;
  assert.equal(plan.length, 10, 'independent candidates still need the reserved attempts');
  assert.ok(plan.some(peer => BigInt(`0x${peer.key}`) >= 2000n));

  const ipv6 = policy().value;
  for (let index = 0; index < 1000; index++) {
    ipv6.remember(key(index + 1), `2001:db8:1234:${index.toString(16)}::1`);
  }
  assert.ok(ipv6.status().candidates <= 8, 'one IPv6 /48 exceeded its candidate allowance');
});

test('candidate floods do not replace saved peers that passed protocol validation', () => {
  const saved = Array.from({length: 32}, (_, index) => ({
    key: key(index + 1), source: host(index + 1), host: host(index + 1), verifiedAt: 900_000 + index
  }));
  const {value} = policy(saved);
  for (let index = 0; index < 1000; index++) value.remember(key(index + 1000), host(index + 1000));
  assert.ok(value.status().candidates <= 256, 'discovery memory must remain bounded');
  assert.deepEqual(new Set(value.snapshot().map(peer => peer.key)), new Set(saved.map(peer => peer.key)));

  const unverified = key(20_000);
  assert.equal(value.admit(unverified, '198.51.100.7'), 'incoming');
  assert.equal(value.snapshot().some(peer => peer.key === unverified), false,
    'an open transport alone must not enter useful history');
  assert.equal(value.verified(unverified), true);
  assert.equal(value.snapshot().some(peer => peer.key === unverified), true);
  assert.ok(value.snapshot().length <= 32);
});

test('a thousand unsolicited keys cannot consume selected and probe reservations', () => {
  const {value} = policy();
  const accepted = [];
  for (let index = 0; index < 1000; index++) {
    if (value.admit(key(index + 10_000), '192.0.2.55')) accepted.push(key(index + 10_000));
  }
  assert.equal(accepted.length, 22);
  assert.equal(value.status().roles.incoming, 22);
  candidates(value, 24);
  const plan = value.tick().connect;
  assert.equal(plan.filter(peer => peer.role === 'selected').length, 8);
  assert.equal(plan.filter(peer => peer.role === 'probe').length, 2);
  for (const peer of plan) assert.equal(value.admit(peer.key, host(Number(BigInt(`0x${peer.key}`)))), peer.role);
  assert.equal(value.status().active, 32);
  assert.equal(value.admit(key(50_000), host(500)), null);
});

test('reserved roles come from local attempts and survive replacement streams', () => {
  const {value} = policy();
  candidates(value, 24, 100);
  const plan = value.tick().connect;
  // Small/large Noise keys cannot choose the role granted by a duplicate tie-break.
  assert.equal(value.admit('00'.repeat(32), '198.51.100.1'), 'incoming');
  assert.equal(value.admit('ff'.repeat(32), '198.51.100.2'), 'incoming');
  for (const peer of plan) {
    assert.equal(value.admit(peer.key, '203.0.113.8'), peer.role);
    const count = value.status().active;
    assert.equal(value.admit(peer.key, '203.0.113.8'), peer.role);
    assert.equal(value.status().active, count, 'replacement stream consumed another slot');
  }
  assert.equal(value.status().roles.selected, 8);
  assert.equal(value.status().roles.probe, 2);
});

test('known endpoint diversity is preferred while peers behind one NAT remain usable', () => {
  const saved = Array.from({length: 32}, (_, index) => ({
    key: key(index + 1), source: host(index + 1),
    host: index === 31 ? '198.51.100.3' : '192.0.2.5', verifiedAt: 900_000
  }));
  const diverse = policy(saved).value;
  const selected = diverse.tick().connect.filter(peer => peer.role === 'selected');
  assert.ok(selected.some(peer => peer.key === key(32)), 'available independent endpoint was not selected');

  const {value} = policy();
  candidates(value, 24);
  for (const peer of value.tick().connect) {
    assert.equal(value.admit(peer.key, '192.0.2.5'), peer.role);
    value.verified(peer.key);
  }
  assert.equal(value.status().roles.selected, 8, 'shared NAT must not prevent useful local connections');
  assert.equal(value.status().degraded, true, 'shared endpoint diversity must be reported honestly');
  assert.equal(value.snapshot().length, 10);
});

test('probes continue with selected peers connected and rotate without evicting them', () => {
  const clock = policy();
  const {value} = clock;
  candidates(value, 64);
  const initial = value.tick().connect;
  for (const peer of initial) {
    assert.equal(value.admit(peer.key, host(Number(BigInt(`0x${peer.key}`)))), peer.role);
    value.verified(peer.key);
  }
  assert.equal(value.status().degraded, false);
  const selected = new Set(initial.filter(peer => peer.role === 'selected').map(peer => peer.key));
  const firstProbes = new Set(initial.filter(peer => peer.role === 'probe').map(peer => peer.key));
  clock.advance(60_001);
  const rotation = value.tick();
  assert.equal(rotation.disconnect.length, 2);
  assert.ok(rotation.disconnect.every(peer => firstProbes.has(peer)));
  assert.ok(rotation.disconnect.every(peer => !selected.has(peer)));
  for (const peer of rotation.disconnect) value.closed(peer);
  const replacement = [...rotation.connect, ...value.tick().connect];
  assert.equal(replacement.filter(peer => peer.role === 'probe').length, 2);
  assert.ok(replacement.every(peer => !firstProbes.has(peer.key)), 'a probe must discover another candidate');
  assert.equal(value.status().roles.selected, 8);
});

test('failed attempts release reservations and missing endpoint information stays unknown', () => {
  const clock = policy();
  const {value} = clock;
  candidates(value, 24);
  const attempted = value.tick().connect;
  for (const peer of attempted) value.rejected(peer.key);
  const replacement = value.tick().connect;
  assert.equal(replacement.length, 10);
  assert.ok(replacement.every(peer => !attempted.some(previous => previous.key === peer.key)));
  for (const peer of replacement) assert.equal(value.admit(peer.key, null), peer.role);
  assert.equal(value.status().degraded, true);
  assert.deepEqual(value.status().groups.selected, []);
  assert.equal(networkGroup('not-an-ip'), null);
  assert.equal(networkGroup(null), null);
  assert.equal(networkGroup('::ffff:192.0.2.8'), networkGroup('192.0.2.9'));
  assert.equal(networkGroup('2001:db8:1234:1::1'), networkGroup('2001:db8:1234:ffff::2'));
  assert.notEqual(networkGroup('2001:db8:1234::1'), networkGroup('2001:db8:1235::1'));
});

test('unreachable candidates cannot hold the reserved slots indefinitely', () => {
  const clock = policy();
  const {value} = clock;
  candidates(value, 32);
  const first = value.tick().connect;
  assert.equal(first.length, 10);
  clock.advance(30_001);
  const retry = value.tick();
  assert.equal(retry.connect.length, 10);
  assert.ok(retry.connect.every(peer => !first.some(previous => previous.key === peer.key)));
  assert.ok(first.every(peer => retry.disconnect.includes(peer.key)),
    'expired attempts must also be cancelled in the underlying swarm');
});

function sidecar(args) {
  const child = spawn(process.execPath, [new URL('./swarm.mjs', import.meta.url).pathname, ...args],
    {stdio: ['pipe', 'pipe', 'pipe']});
  const events = [], waiting = new Set();
  let buffer = '', stderr = '';
  child.stderr.on('data', chunk => { stderr = (stderr + chunk).slice(-2000); });
  child.stdout.on('data', chunk => {
    buffer += chunk;
    for (let end; (end = buffer.indexOf('\n')) !== -1;) {
      events.push(JSON.parse(buffer.slice(0, end)));
      buffer = buffer.slice(end + 1);
      for (const check of waiting) check();
    }
  });
  return {
    events, child,
    send(message) { child.stdin.write(`${JSON.stringify(message)}\n`); },
    wait(predicate, start = 0) {
      return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
          waiting.delete(check);
          reject(new Error(`Sidecar timed out: ${JSON.stringify(events)} ${stderr}`));
        }, 10_000);
        const check = () => {
          const found = events.slice(start).find(predicate);
          if (found) { clearTimeout(timer); waiting.delete(check); resolve(found); }
        };
        waiting.add(check);
        check();
      });
    },
    async close() {
      if (child.exitCode !== null || child.signalCode !== null) return;
      const exited = once(child, 'exit');
      child.stdin.write('{"type":"shutdown"}\n');
      const timer = setTimeout(() => child.kill('SIGKILL'), 4000);
      const [code, signal] = await exited;
      clearTimeout(timer);
      assert.deepEqual([code, signal], [0, null], stderr);
    }
  };
}

test('an authenticated replacement stream keeps its locally selected role', {timeout: 35_000}, async t => {
  const directory = await mkdtemp(join(tmpdir(), 'worklife-neighbor-'));
  const portSocket = createSocket('udp4');
  portSocket.bind(0, '127.0.0.1');
  await once(portSocket, 'listening');
  const port = portSocket.address().port;
  await new Promise(resolve => portSocket.close(resolve));
  const bootstrap = DHT.bootstrapper(port, '127.0.0.1', {host: '127.0.0.1'});
  const dht = new DHT({bootstrap: [`127.0.0.1:${port}`], port: [0, 0], host: '0.0.0.0'});
  const native = new Hyperswarm({dht, seed: Buffer.alloc(32, 71), maxPeers: 2});
  native.on('connection', socket => socket.on('error', () => {}));
  let victim, duplicate;
  t.after(async () => {
    duplicate?.destroy();
    if (victim) await victim.close();
    await native.destroy();
    await bootstrap.destroy({force: true});
    await rm(directory, {recursive: true, force: true});
  });
  await bootstrap.ready();
  await native.listen();
  victim = sidecar(['--topic', 'b7'.repeat(32), '--key-file', join(directory, 'victim.seed'),
    '--bootstrap', `127.0.0.1:${port}`, '--isolated']);
  const ready = await victim.wait(event => event.type === 'ready');
  const peer = native.keyPair.publicKey.toString('hex');
  const connected = once(native, 'connection');
  victim.send({type: 'join_peer', peer});
  await victim.wait(event => event.type === 'connected' && event.peer === peer);
  victim.send({type: 'send', peer, message: {type: 'open-selected-stream'}});
  const [socket] = await connected;
  socket.on('error', () => {});
  await victim.wait(event => event.type === 'connected' && event.peer === peer);
  const stats = async () => {
    const start = victim.events.length;
    victim.send({type: 'stats'});
    return victim.wait(event => event.type === 'stats', start);
  };
  assert.equal((await stats()).neighbors.roles.selected, 1);
  socket.write('{"type":"before-replacement"}\n');
  await victim.wait(event => event.type === 'message' &&
    Buffer.from(event.payload, 'base64').toString().includes('before-replacement'));
  const reply = once(socket, 'data');
  victim.send({type: 'send', peer, message: {type: 'reply-before-replacement'}});
  await reply;

  const start = victim.events.length;
  duplicate = dht.connect(Buffer.from(ready.public_key, 'hex'), {keyPair: native.keyPair});
  duplicate.on('error', () => {});
  await once(duplicate, 'open');
  await victim.wait(event => event.type === 'connected' && event.peer === peer, start);
  const after = await stats();
  assert.equal(after.peers.length, 1, 'replacement stream consumed a second connection slot');
  assert.equal(after.neighbors.roles.selected, 1, 'incoming replacement lost the local selected role');
  assert.equal(after.neighbors.roles.incoming, 0, 'peerInfo.client changed policy ownership');
  duplicate.write('{"type":"after-replacement"}\n');
  await victim.wait(event => event.type === 'message' &&
    Buffer.from(event.payload, 'base64').toString().includes('after-replacement'), start);
  assert.equal(victim.child.exitCode, null);
});

test('22 native unsolicited peers leave room for a useful locally selected peer', {timeout: 30_000}, async t => {
  const directory = await mkdtemp(join(tmpdir(), 'worklife-neighbor-full-'));
  const portSocket = createSocket('udp4');
  portSocket.bind(0, '127.0.0.1');
  await once(portSocket, 'listening');
  const port = portSocket.address().port;
  await new Promise(resolve => portSocket.close(resolve));
  const bootstrap = DHT.bootstrapper(port, '127.0.0.1', {host: '127.0.0.1'});
  const attackers = [];
  const honestDht = new DHT({bootstrap: [`127.0.0.1:${port}`], port: [0, 0], host: '0.0.0.0'});
  const honest = new Hyperswarm({dht: honestDht, seed: Buffer.alloc(32, 151), maxPeers: 2});
  honest.on('connection', socket => socket.on('error', () => {}));
  const sockets = [];
  let victim;
  t.after(async () => {
    for (const socket of sockets) socket.destroy();
    const results = await Promise.allSettled([
      victim?.close(), honest.destroy(), ...attackers.map(client => client.destroy())
    ]);
    await bootstrap.destroy({force: true});
    await rm(directory, {recursive: true, force: true});
    for (const result of results) if (result.status === 'rejected') throw result.reason;
  });
  await bootstrap.ready();
  await honest.listen();
  victim = sidecar(['--topic', 'b8'.repeat(32), '--key-file', join(directory, 'victim.seed'),
    '--bootstrap', `127.0.0.1:${port}`, '--isolated']);
  const ready = await victim.wait(event => event.type === 'ready');
  const target = Buffer.from(ready.public_key, 'hex');
  const stats = async () => {
    const start = victim.events.length;
    victim.send({type: 'stats'});
    return victim.wait(event => event.type === 'stats', start);
  };
  for (let index = 1; index <= 22; index++) {
    const keyPair = DHT.keyPair(Buffer.alloc(32, index));
    const dht = new DHT({bootstrap: [`127.0.0.1:${port}`], port: [0, 0], host: '0.0.0.0', keyPair});
    const attacker = new Hyperswarm({dht, keyPair, maxPeers: 1});
    attacker.on('connection', socket => socket.on('error', () => {}));
    attackers.push(attacker);
    await attacker.listen();
    const connection = once(attacker, 'connection');
    attacker.joinPeer(target);
    const [socket] = await connection;
    attacker.leavePeer(target);
    sockets.push(socket);
    socket.on('error', () => {});
    socket.write('{"type":"native-unsolicited"}\n');
    await victim.wait(event => event.type === 'connected' && event.peer === keyPair.publicKey.toString('hex'));
  }
  const full = await stats();
  assert.equal(full.neighbors.roles.incoming, 22);
  assert.equal(full.peers.length, 22);
  for (let index = 23; index <= 24; index++) {
    const keyPair = DHT.keyPair(Buffer.alloc(32, index));
    const dht = new DHT({bootstrap: [`127.0.0.1:${port}`], port: [0, 0], host: '0.0.0.0', keyPair});
    const attacker = new Hyperswarm({dht, keyPair, maxPeers: 1});
    attacker.on('connection', socket => socket.on('error', () => {}));
    attackers.push(attacker);
    await attacker.listen();
    const connection = once(attacker, 'connection');
    attacker.joinPeer(target);
    const [socket] = await connection;
    attacker.leavePeer(target);
    sockets.push(socket);
    socket.on('error', () => {});
    await new Promise(resolve => socket.once('close', resolve));
  }
  const rejected = await stats();
  assert.equal(rejected.neighbors.roles.incoming, 22);
  assert.equal(rejected.peers.length, 22);

  const peer = honest.keyPair.publicKey.toString('hex');
  const connection = once(honest, 'connection');
  victim.send({type: 'join_peer', peer});
  await victim.wait(event => event.type === 'connected' && event.peer === peer);
  victim.send({type: 'send', peer, message: {type: 'open-selected-stream'}});
  const [socket] = await connection;
  socket.on('error', () => {});
  await victim.wait(event => event.type === 'connected' && event.peer === peer);
  const selected = await stats();
  assert.equal(selected.neighbors.roles.incoming, 22);
  assert.equal(selected.neighbors.roles.selected, 1);
  assert.equal(selected.peers.length, 23);
  const marker = Buffer.from('{"type":"selected-after-native-saturation"}');
  socket.write(Buffer.concat([marker, Buffer.from('\n')]));
  await victim.wait(event => event.type === 'message' && event.peer === peer && event.payload === marker.toString('base64'));
  assert.equal(victim.child.exitCode, null);
});

test('explicit rejection and malformed native frames erase useful history before restart', {timeout: 30_000}, async t => {
  const directory = await mkdtemp(join(tmpdir(), 'worklife-neighbor-rejected-'));
  const portSocket = createSocket('udp4');
  portSocket.bind(0, '127.0.0.1');
  await once(portSocket, 'listening');
  const port = portSocket.address().port;
  await new Promise(resolve => portSocket.close(resolve));
  const bootstrap = DHT.bootstrapper(port, '127.0.0.1', {host: '127.0.0.1'});
  const victims = [], sockets = [], clients = [];
  t.after(async () => {
    for (const socket of sockets) socket.destroy();
    const closed = await Promise.allSettled(victims.map(victim => victim.close()));
    await Promise.all(clients.map(client => client.destroy({force: true})));
    await bootstrap.destroy({force: true});
    await rm(directory, {recursive: true, force: true});
    for (const result of closed) if (result.status === 'rejected') throw result.reason;
  });
  await bootstrap.ready();
  for (const reason of ['disconnect', 'malformed']) await t.test(reason, async () => {
    const topic = (reason === 'disconnect' ? 'b9' : 'ba').repeat(32);
    const keyFile = join(directory, `${reason}.seed`);
    const args = ['--topic', topic, '--key-file', keyFile, '--bootstrap', `127.0.0.1:${port}`, '--isolated'];
    const victim = sidecar(args);
    victims.push(victim);
    const ready = await victim.wait(event => event.type === 'ready');
    const client = new DHT({bootstrap: [`127.0.0.1:${port}`], port: [0, 0], host: '0.0.0.0'});
    clients.push(client);
    const keyPair = DHT.keyPair(Buffer.alloc(32, reason === 'disconnect' ? 152 : 153));
    const peer = keyPair.publicKey.toString('hex');
    const socket = client.connect(Buffer.from(ready.public_key, 'hex'), {keyPair});
    sockets.push(socket);
    socket.on('error', () => {});
    await once(socket, 'open');
    socket.write('{"type":"history-test-peer"}\n');
    await victim.wait(event => event.type === 'connected' && event.peer === peer);
    victim.send({type: 'peer_verified', peer});
    victim.send({type: 'stats'});
    await victim.wait(event => event.type === 'stats');
    const cachePath = `${keyFile}.neighbors-${topic}.json`;
    assert.equal(JSON.parse(await readFile(cachePath, 'utf8')).peers.some(saved => saved.key === peer), true);
    const start = victim.events.length;
    if (reason === 'disconnect') victim.send({type: 'disconnect', peer});
    else socket.write('{bad-json}\n');
    if (reason === 'malformed') await victim.wait(event => event.code === 'invalid_peer_frame' && event.peer === peer, start);
    await victim.wait(event => event.type === 'disconnected' && event.peer === peer, start);
    assert.equal(JSON.parse(await readFile(cachePath, 'utf8')).peers.some(saved => saved.key === peer), false,
      `${reason} left a rejected peer in the persisted useful history`);
    await victim.close();
    const restarted = sidecar(args);
    victims.push(restarted);
    await restarted.wait(event => event.type === 'ready');
    restarted.send({type: 'stats'});
    assert.equal((await restarted.wait(event => event.type === 'stats')).neighbors.history, 0);
    await restarted.close();
  });
});

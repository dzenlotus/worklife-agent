import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, readFile, stat, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawn} from 'node:child_process';
import {createSocket} from 'node:dgram';
import {once} from 'node:events';
import DHT from 'hyperdht';
import Hyperswarm from 'hyperswarm';

const transport = await import('./swarm.mjs').catch(() => null);

test('decodes split UTF-8 and multiple newline-delimited JSON objects', () => {
  assert.ok(transport, 'the transport module must exist');
  const messages = [], errors = [];
  const decode = transport.jsonLines(value => messages.push(value), error => errors.push(error));
  const frame = Buffer.from('{"text":"мир"}\n{"type":"shutdown"}\n');
  decode(frame.subarray(0, 10));
  decode(frame.subarray(10));
  assert.deepEqual(messages, [{text: 'мир'}, {type: 'shutdown'}]);
  assert.deepEqual(errors, []);
});

test('rejects oversized, malformed, and non-object peer frames', () => {
  assert.ok(transport, 'the transport module must exist');
  for (const frame of ['x'.repeat(17), '{bad}\n', '[]\n', 'null\n']) {
    const errors = [], messages = [];
    transport.jsonLines(value => messages.push(value), error => errors.push(error), 16)(Buffer.from(frame));
    assert.equal(errors.length, 1);
    assert.equal(messages.length, 0);
  }
});

test('accepts the exact frame boundary and rejects an oversized outgoing message', () => {
  assert.ok(transport, 'the transport module must exist');
  const messages = [];
  transport.jsonLines(value => messages.push(value), assert.fail, 8)(Buffer.from('{"a":12}\n'));
  assert.deepEqual(messages, [{a: 12}]);
  assert.throws(() => transport.encodeMessage({text: 'x'.repeat(transport.MAX_FRAME)}), /large/i);
  assert.throws(() => transport.encodeMessage([]), /object/i);
});

test('preserves raw JSON integer bytes while validating the frame boundary', () => {
  const raw = Buffer.from('{"n":1152921504606846977}');
  assert.deepEqual(transport.encodeRawMessage(raw.toString('base64')), Buffer.concat([raw, Buffer.from('\n')]));
  for (const invalid of [Buffer.from('[]'), Buffer.from('{"n":1}\n'), Buffer.from([123, 34, 120, 34, 58, 34, 255, 34, 125]), Buffer.from('x'.repeat(transport.MAX_FRAME + 1))]) {
    assert.throws(() => transport.encodeRawMessage(invalid.toString('base64')));
  }
  assert.throws(() => transport.encodeRawMessage('not-base64'));
});

test('persists a separate 32-byte transport seed with private permissions', async t => {
  assert.ok(transport, 'the transport module must exist');
  const directory = await mkdtemp(join(tmpdir(), 'worklife-seed-'));
  t.after(() => rm(directory, {recursive: true, force: true}));
  const path = join(directory, 'transport.seed');
  const first = transport.loadSeed(path);
  assert.equal(first.length, 32);
  assert.deepEqual(transport.loadSeed(path), first);
  assert.deepEqual(await readFile(path), first);
  assert.equal((await stat(path)).mode & 0o777, 0o600);
});

test('neighbor history is private, bounded and bound to its swarm topic', async t => {
  assert.equal(typeof transport.saveNeighborHistory, 'function', 'neighbor persistence must exist');
  const directory = await mkdtemp(join(tmpdir(), 'worklife-neighbors-'));
  t.after(() => rm(directory, {recursive: true, force: true}));
  const path = join(directory, 'neighbors.json'), topic = 'a'.repeat(64);
  const peers = [{key: 'b'.repeat(64), source: '192.0.2.1', host: '198.51.100.2', verifiedAt: 1}];
  transport.saveNeighborHistory(path, topic, peers);
  assert.deepEqual(transport.loadNeighborHistory(path, topic), peers);
  assert.deepEqual(transport.loadNeighborHistory(path, 'c'.repeat(64)), []);
  assert.equal((await stat(path)).mode & 0o777, 0o600);
  assert.throws(() => transport.saveNeighborHistory(path, topic, Array(33).fill(peers[0])));
  assert.deepEqual(transport.loadNeighborHistory(join(directory, 'missing'), topic), []);
});

test('stalled native dials cannot accumulate an uncancellable per-key queue', async t => {
  assert.equal(typeof transport.dispatchDials, 'function', 'bounded dial dispatch must exist');
  const dht = new DHT({bootstrap: [], port: [0, 0]});
  const swarm = new Hyperswarm({dht, maxPeers: Infinity, maxParallel: 0});
  t.after(() => swarm.destroy({force: true}));
  const waiting = new Set();
  for (let round = 0; round < 100; round++) {
    waiting.clear();
    for (let i = 1; i <= 10; i++) waiting.add(BigInt(round * 10 + i).toString(16).padStart(64, '0'));
    transport.dispatchDials(swarm, waiting);
    assert.equal(swarm.peers.size, 0, 'blocked native slots retained expired queued keys');
  }
  swarm.maxParallel = 3;
  transport.dispatchDials(swarm, waiting);
  assert.equal(waiting.size, 7);
  assert.equal(swarm.connecting, 3);
  assert.equal(swarm.peers.size, 3);
  assert.equal(swarm.explicitPeers.size, 0, 'upstream retries outlived locally owned attempts');
  assert.ok([...swarm.peers.values()].filter(peer => peer.queued).length <= swarm.connecting,
    'native queue contains more than the bounded in-flight attempts');
});

test('validates local CLI options and keeps public bootstrap opt-in by omission', () => {
  assert.ok(transport, 'the transport module must exist');
  const base = ['--topic', 'aa'.repeat(32), '--key-file', '/tmp/test.seed'];
  assert.equal(transport.parseOptions(base).bootstrap, undefined);
  assert.deepEqual(transport.parseOptions([...base, '--isolated']).bootstrap, []);
  assert.deepEqual(transport.parseOptions([...base, '--bootstrap', 'localhost:1234', '--isolated']).bootstrap, ['localhost:1234']);
  assert.deepEqual(transport.parseOptions([...base, '--peer', 'bb'.repeat(32)]).peer, ['bb'.repeat(32)]);
  for (const invalid of [[], [...base, '--port', '-1'], [...base, '--max-peers', '0'], [...base, '--bootstrap', 'missing-port'], [...base, '--bootstrap', '[::1]:1234'], [...base, '--unknown']]) {
    assert.throws(() => transport.parseOptions(invalid));
  }
});

async function freePort() {
  const socket = createSocket('udp4');
  socket.bind(0, '127.0.0.1');
  await once(socket, 'listening');
  const port = socket.address().port;
  await new Promise(resolve => socket.close(resolve));
  return port;
}

function sidecar(args, initialMessage = null) {
  const child = spawn(process.execPath, [new URL('./swarm.mjs', import.meta.url).pathname, ...args], {stdio: ['pipe', 'pipe', 'pipe']});
  const events = [], waiters = new Set();
  let stderr = '', buffer = '';
  child.stderr.on('data', chunk => { stderr += chunk; });
  child.stdout.on('data', chunk => {
    buffer += chunk;
    for (let index; (index = buffer.indexOf('\n')) !== -1;) {
      const event = JSON.parse(buffer.slice(0, index));
      buffer = buffer.slice(index + 1);
      events.push(event);
      if (event.type === 'connected' && initialMessage) {
        // Native streams open lazily; BlockSwarm also sends hello on every connection.
        child.stdin.write(`${JSON.stringify({type: 'send', peer: event.peer, message: initialMessage})}\n`);
      }
      for (const check of waiters) check();
    }
  });
  return {
    child, events,
    send: message => child.stdin.write(`${JSON.stringify(message)}\n`),
    wait(predicate, timeout = 20000, label = 'event') {
      return new Promise((resolve, reject) => {
        const timer = setTimeout(() => { waiters.delete(check); reject(new Error(`Sidecar timed out waiting for ${label}: ${JSON.stringify(events)} ${stderr}`)); }, timeout);
        const check = () => {
          const found = events.find(predicate);
          if (found) { clearTimeout(timer); waiters.delete(check); resolve(found); }
        };
        waiters.add(check);
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
      assert.equal(signal, null, 'shutdown must complete without forced termination');
      assert.equal(code, 0, `sidecar shutdown failed: ${stderr}`);
    }
  };
}

test('three isolated local peers exchange objects without executing payload control messages', {timeout: 40000}, async t => {
  assert.ok(transport, 'the transport module must exist');
  const directory = await mkdtemp(join(tmpdir(), 'worklife-swarm-'));
  const bootstrap = DHT.bootstrapper(await freePort(), '127.0.0.1');
  const peers = [];
  t.after(async () => {
    const results = await Promise.allSettled(peers.map(peer => peer.close()));
    await bootstrap.destroy({force: true});
    await rm(directory, {recursive: true, force: true});
    for (const result of results) if (result.status === 'rejected') throw result.reason;
  });
  await bootstrap.ready();
  const topic = '42'.repeat(32);
  const initialMessage = {type: 'transport-test-hello'};
  for (let index = 0; index < 3; index++) {
    const peer = sidecar(['--topic', topic, '--key-file', join(directory, `${index}.seed`), '--bootstrap', `127.0.0.1:${bootstrap.address().port}`, '--isolated'], initialMessage);
    peers.push(peer);
    const ready = await peer.wait(event => event.type === 'ready');
    assert.match(ready.public_key, /^[0-9a-f]{64}$/);
    assert.equal(ready.bootstrap_mode, 'custom');
    assert.ok(ready.address.port > 0);
  }
  const keys = peers.map(peer => peer.events.find(event => event.type === 'ready').public_key);
  await Promise.all(peers.flatMap((peer, index) => keys.filter(key => key !== keys[index]).map(key => peer.wait(event => event.type === 'connected' && event.peer === key, 20000, `initial mesh peer ${index} to ${key}`))));
  const ordinary = {type: 'shutdown', arbitrary: 'ordinary peer payload'};
  peers[0].send({type: 'send', peer: keys[1], message: ordinary});
  const ordinaryPayload = Buffer.from(JSON.stringify(ordinary)).toString('base64');
  const received = await peers[1].wait(event => event.type === 'message' && event.peer === keys[0] && event.payload === ordinaryPayload, 20000, 'ordinary payload at peer 1');
  assert.deepEqual(JSON.parse(Buffer.from(received.payload, 'base64')), ordinary);
  const raw = Buffer.from('{"n":1152921504606846977}');
  peers[0].send({type: 'send_raw', peer: keys[1], payload: raw.toString('base64')});
  const exact = await peers[1].wait(event => event.type === 'message' && event.payload === raw.toString('base64'), 20000, 'raw payload at peer 1');
  assert.deepEqual(Buffer.from(exact.payload, 'base64'), raw);
  assert.equal('message' in exact, false);
  const hello = {type: 'hello', blocks: []};
  peers[1].send({type: 'send', peer: keys[2], message: hello});
  const helloPayload = Buffer.from(JSON.stringify(hello)).toString('base64');
  assert.deepEqual(JSON.parse(Buffer.from((await peers[2].wait(event => event.type === 'message' && event.peer === keys[1] && event.payload === helloPayload, 20000, 'hello payload at peer 2')).payload, 'base64')), hello);
  peers[0].send({type: 'disconnect', peer: keys[1]});
  await peers[0].wait(event => event.type === 'disconnected' && event.peer === keys[1]);
  await peers[0].close();
  const restarted = sidecar(['--topic', '99'.repeat(32), '--key-file', join(directory, '0.seed'), '--bootstrap', `127.0.0.1:${bootstrap.address().port}`, '--peer', keys[2]], initialMessage);
  peers.push(restarted);
  assert.equal((await restarted.wait(event => event.type === 'ready')).public_key, keys[0]);
  await restarted.wait(event => event.type === 'connected' && event.peer === keys[2], 20000, 'restart explicit peer 2');
  restarted.send({type: 'join_peer', peer: keys[1]});
  await restarted.wait(event => event.type === 'connected' && event.peer === keys[1], 20000, 'restart joined peer 1');
});

test('peer shuts down promptly when its only bootstrap router has gone offline', {timeout: 15000}, async t => {
  const directory = await mkdtemp(join(tmpdir(), 'worklife-offline-'));
  const bootstrap = DHT.bootstrapper(await freePort(), '127.0.0.1');
  await bootstrap.ready();
  const peer = sidecar(['--topic', '37'.repeat(32), '--key-file', join(directory, 'peer.seed'), '--bootstrap', `127.0.0.1:${bootstrap.address().port}`]);
  t.after(async () => {
    if (peer.child.exitCode === null) peer.child.kill('SIGKILL');
    await bootstrap.destroy({force: true});
    await rm(directory, {recursive: true, force: true});
  });
  await peer.wait(event => event.type === 'ready');
  await bootstrap.destroy({force: true});
  await peer.close();
});

test('an explicit UDP port is bound exactly as requested', {timeout: 10000}, async t => {
  const directory = await mkdtemp(join(tmpdir(), 'worklife-port-'));
  const bootstrap = DHT.bootstrapper(await freePort(), '127.0.0.1');
  await bootstrap.ready();
  const port = await freePort();
  const peer = sidecar(['--topic', '56'.repeat(32), '--key-file', join(directory, 'peer.seed'),
    '--bootstrap', `127.0.0.1:${bootstrap.address().port}`, '--port', String(port)]);
  t.after(async () => {
    await peer.close();
    await bootstrap.destroy({force: true});
    await rm(directory, {recursive: true, force: true});
  });
  await peer.wait(event => event.type === 'ready');
  const probe = createSocket('udp4');
  const failed = once(probe, 'error');
  probe.bind(port, '0.0.0.0');
  assert.equal((await failed)[0].code, 'EADDRINUSE');
  probe.close();
});

test('standalone bootstrapper remains alive after stdin EOF and stops on SIGTERM', {timeout: 10000}, async t => {
  const router = sidecar(['--bootstrapper', '--port', String(await freePort()), '--bootstrap-host', '127.0.0.1']);
  t.after(() => { if (router.child.exitCode === null) router.child.kill('SIGKILL'); });
  assert.equal((await router.wait(event => event.type === 'ready')).bootstrap_mode, 'bootstrapper');
  router.child.stdin.end();
  await new Promise(resolve => setTimeout(resolve, 200));
  assert.equal(router.child.exitCode, null, 'Docker router must survive closed stdin');
  const exited = once(router.child, 'exit');
  router.child.kill('SIGTERM');
  assert.deepEqual(await exited, [0, null]);
});

test('startup EOF shuts down before unreachable DHT discovery finishes', {timeout: 6000}, async t => {
  const directory = await mkdtemp(join(tmpdir(), 'worklife-startup-'));
  const peer = sidecar(['--topic', '38'.repeat(32), '--key-file', join(directory, 'peer.seed'), '--bootstrap', '127.0.0.1:1']);
  t.after(async () => {
    if (peer.child.exitCode === null) peer.child.kill('SIGKILL');
    await rm(directory, {recursive: true, force: true});
  });
  const exited = once(peer.child, 'exit');
  peer.child.stdin.end();
  const status = await Promise.race([exited, new Promise(resolve => setTimeout(() => resolve('timeout'), 4000))]);
  assert.deepEqual(status, [0, null]);
});

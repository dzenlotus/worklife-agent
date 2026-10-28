import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawn} from 'node:child_process';
import {createSocket} from 'node:dgram';
import {once} from 'node:events';
import DHT from 'hyperdht';
import Hyperswarm from 'hyperswarm';

const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function bounded(promise, ms = 8000) {
  let timer;
  try {
    return await Promise.race([promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error('Local transport test timed out')), ms);
    })]);
  } finally { clearTimeout(timer); }
}

test('a bounded peer flood with a stalled parent preserves the transport and another peer', {timeout: 40000}, async t => {
  const directory = await mkdtemp(join(tmpdir(), 'worklife-flood-'));
  const portSocket = createSocket('udp4');
  portSocket.bind(0, '127.0.0.1');
  await once(portSocket, 'listening');
  const port = portSocket.address().port;
  await new Promise(resolve => portSocket.close(resolve));
  const bootstrap = DHT.bootstrapper(port, '127.0.0.1', {host: '127.0.0.1'});
  const swarms = [];
  let victim, exited;
  t.after(async () => {
    if (victim && victim.exitCode === null && victim.signalCode === null) {
      victim.stdout.resume();
      victim.stdin.write('{"type":"shutdown"}\n');
      await bounded(exited, 4000).catch(() => victim.kill('SIGKILL'));
    }
    await Promise.allSettled(swarms.map(swarm => swarm.destroy()));
    await bootstrap.destroy({force: true});
    await rm(directory, {recursive: true, force: true});
  });
  await bootstrap.ready();
  victim = spawn(process.execPath, [new URL('./swarm.mjs', import.meta.url).pathname,
    '--topic', '53'.repeat(32), '--key-file', join(directory, 'victim.seed'),
    '--bootstrap', `127.0.0.1:${port}`, '--isolated'], {stdio: ['pipe', 'pipe', 'pipe']});
  exited = once(victim, 'exit');
  let buffer = '', stderr = '', publicKey, frames = 0, markerReceived = false;
  const marker = Buffer.from('{"type":"good-peer-after-flood"}');
  victim.stderr.on('data', chunk => { stderr = (stderr + chunk).slice(-1000); });
  victim.stdout.on('data', chunk => {
    buffer += chunk;
    for (let end; (end = buffer.indexOf('\n')) !== -1;) {
      const event = JSON.parse(buffer.slice(0, end));
      buffer = buffer.slice(end + 1);
      if (event.type === 'ready') publicKey = event.public_key;
      if (event.type === 'message') {
        frames++;
        if (event.payload === marker.toString('base64')) markerReceived = true;
      }
    }
  });
  async function waitFor(predicate, description) {
    const deadline = Date.now() + 8000;
    while (!predicate() && Date.now() < deadline) await pause(20);
    assert.ok(predicate(), `${description}; stderr: ${stderr}`);
  }
  await waitFor(() => publicKey, 'victim did not become ready');
  async function connect(seed) {
    const dht = new DHT({bootstrap: [`127.0.0.1:${port}`], port: [0, 0], host: '0.0.0.0'});
    const swarm = new Hyperswarm({dht, seed: Buffer.alloc(32, seed), maxPeers: 2});
    // Reconnects and duplicate streams can also reset when the victim shuts down.
    swarm.on('connection', socket => socket.on('error', () => {}));
    swarms.push(swarm);
    await swarm.listen();
    const connection = once(swarm, 'connection');
    swarm.joinPeer(Buffer.from(publicKey, 'hex'));
    const [socket] = await bounded(connection);
    return socket;
  }
  const attacker = await connect(91), good = await connect(92);
  let goodClosed = false, sentBytes = 0;
  good.on('close', () => { goodClosed = true; });
  const frame = Buffer.from(JSON.stringify({type: 'ordinary_peer_data', padding: 'x'.repeat(900000)}) + '\n');
  async function flood(count) {
    for (let i = 0; i < count && !attacker.destroyed; i++) {
      sentBytes += frame.length;
      if (!attacker.write(frame)) await bounded(new Promise((resolve, reject) => {
        const clear = () => { attacker.off('drain', done); attacker.off('close', done); attacker.off('error', fail); };
        const done = () => { clear(); resolve(); };
        const fail = error => { clear(); reject(error); };
        attacker.once('drain', done); attacker.once('close', done); attacker.once('error', fail);
      }), 2500);
    }
  }

  // A draining parent accepts the same traffic. The whole test sends under 20 MiB.
  await flood(4);
  await waitFor(() => frames >= 4, 'control frames were not delivered');
  assert.equal(victim.exitCode, null);
  assert.equal(goodClosed, false);

  victim.stdout.pause();
  const flooding = flood(16).catch(() => {}); // Disconnecting the offending connection is acceptable.
  await pause(700);
  victim.stdout.resume();
  await flooding;
  await pause(200);
  assert.ok(sentBytes <= 20 * 1024 * 1024);
  assert.equal(victim.exitCode, null, `one peer stopped the transport: ${stderr}`);
  assert.equal(goodClosed, false, 'one peer disconnected the healthy peer');
  good.write(Buffer.concat([marker, Buffer.from('\n')]));
  await waitFor(() => markerReceived, 'healthy peer could not send after the flood');
});

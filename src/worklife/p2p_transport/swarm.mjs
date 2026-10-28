import Hyperswarm from 'hyperswarm';
import DHT from 'hyperdht';
import {parseArgs} from 'node:util';
import {randomBytes, randomInt} from 'node:crypto';
import {readFileSync, writeFileSync, chmodSync, statSync, renameSync} from 'node:fs';
import {lookup} from 'node:dns/promises';
import {pathToFileURL} from 'node:url';
import {NeighborPolicy} from './neighbors.mjs';

export const MAX_FRAME = 1024 * 1024;
const MAX_PENDING = 4 * MAX_FRAME;
const isObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const parseFrame = frame => {
  const value = JSON.parse(new TextDecoder('utf-8', {fatal: true, ignoreBOM: true}).decode(frame));
  if (!isObject(value)) throw new Error('Message must be a JSON object');
  return value;
};

export function encodeMessage(message) {
  if (!isObject(message)) throw new Error('Message must be a JSON object');
  const frame = Buffer.from(JSON.stringify(message));
  if (frame.length > MAX_FRAME) throw new Error('Message frame is too large');
  return Buffer.concat([frame, Buffer.from('\n')]);
}

export function encodeRawMessage(payload) {
  if (typeof payload !== 'string') throw new Error('Raw payload must be base64');
  const frame = Buffer.from(payload, 'base64');
  if (frame.toString('base64') !== payload) throw new Error('Raw payload must be canonical base64');
  if (frame.length > MAX_FRAME) throw new Error('Message frame is too large');
  if (frame.includes(10)) throw new Error('Raw JSON frame must occupy one line');
  try { parseFrame(frame); } catch { throw new Error('Invalid UTF-8 JSON object frame'); }
  return Buffer.concat([frame, Buffer.from('\n')]);
}

// Count bytes before decoding, preserving UTF-8 split across network chunks.
export function jsonLines(onMessage, onError, limit = MAX_FRAME) {
  let pending = Buffer.alloc(0), failed = false;
  return chunk => {
    if (failed) return;
    for (let offset = 0; offset < chunk.length;) {
      const newline = chunk.indexOf(10, offset);
      const end = newline === -1 ? chunk.length : newline;
      const piece = chunk.subarray(offset, end);
      if (pending.length + piece.length > limit) {
        failed = true;
        onError(new Error('JSON frame is too large'));
        return;
      }
      pending = Buffer.concat([pending, piece]);
      if (newline === -1) return;
      let value;
      try {
        value = parseFrame(pending);
      } catch {
        failed = true;
        onError(new Error('Invalid JSON object frame'));
        return;
      }
      const frame = pending;
      pending = Buffer.alloc(0);
      onMessage(value, frame);
      offset = newline + 1;
    }
  };
}

export function loadSeed(path) {
  let seed;
  try { seed = readFileSync(path); }
  catch (error) {
    if (error.code !== 'ENOENT') throw error;
    seed = randomBytes(32);
    writeFileSync(path, seed, {mode: 0o600, flag: 'wx'});
  }
  if (seed.length !== 32) throw new Error('Transport key file must contain exactly 32 bytes');
  chmodSync(path, 0o600);
  return seed;
}

export function loadNeighborHistory(path, topic) {
  try {
    if (statSync(path).size > 32768) return [];
    const value = JSON.parse(readFileSync(path, 'utf8'));
    return value?.version === 1 && value.topic === topic && Array.isArray(value.peers) && value.peers.length <= 32
      ? value.peers : [];
  } catch { return []; }
}

export function saveNeighborHistory(path, topic, peers) {
  if (!Array.isArray(peers) || peers.length > 32) throw new Error('Neighbor history limit exceeded');
  const value = JSON.stringify({version: 1, topic, peers});
  if (Buffer.byteLength(value) > 32768) throw new Error('Neighbor history limit exceeded');
  const temporary = `${path}.tmp-${process.pid}`;
  writeFileSync(temporary, value, {mode: 0o600});
  chmodSync(temporary, 0o600);
  renameSync(temporary, path);
}

export function dispatchDials(swarm, waiting) {
  for (const key of waiting) {
    if (swarm.connecting >= swarm.maxParallel) break;
    waiting.delete(key);
    const publicKey = Buffer.from(key, 'hex');
    swarm.joinPeer(publicKey);
    // Retry and expiry belong to our bounded policy, not Hyperswarm's explicit queue.
    swarm.leavePeer(publicKey);
  }
}

export function parseOptions(args) {
  const {values} = parseArgs({args, options: {
    topic: {type: 'string'}, 'key-file': {type: 'string'},
    bootstrap: {type: 'string', multiple: true}, isolated: {type: 'boolean'}, peer: {type: 'string', multiple: true},
    port: {type: 'string', default: '0'}, 'max-peers': {type: 'string', default: '32'},
    bootstrapper: {type: 'boolean'}, 'bootstrap-host': {type: 'string', default: '127.0.0.1'}
  }});
  const port = Number(values.port), maxPeers = Number(values['max-peers']);
  if (!Number.isInteger(port) || port < 0 || port > 65535) throw new Error('Port must be between 0 and 65535');
  if (!Number.isInteger(maxPeers) || maxPeers < 1 || maxPeers > 32) throw new Error('Max peers must be between 1 and 32');
  if (values.bootstrapper && !port) throw new Error('Bootstrapper requires a nonzero UDP port');
  if (!values.bootstrapper && (!/^[0-9a-f]{64}$/i.test(values.topic || '') || !values['key-file'])) {
    throw new Error('--topic (64 hex characters) and --key-file are required');
  }
  for (const address of values.bootstrap || []) {
    const match = /^[a-zA-Z0-9.-]+:([0-9]+)$/.exec(address);
    if (!match || Number(match[1]) < 1 || Number(match[1]) > 65535) throw new Error('Bootstrap must be host:port');
  }
  if ((values.peer || []).some(peer => !/^[0-9a-f]{64}$/i.test(peer))) throw new Error('Peer must be a 64-character Noise public key');
  return {...values, port, maxPeers, bootstrap: values.bootstrap || (values.isolated ? [] : undefined)};
}

export async function main(args = process.argv.slice(2)) {
  const options = parseOptions(args);
  const peers = new Map();
  const waitingDials = new Set();
  let swarm, dht, discoveryTimer, policyTimer, lookupQuery, policy, historyPath;
  let closing = false, outputPaused = false, looking = false;
  const emit = event => {
    const frame = `${JSON.stringify(event)}\n`;
    if (process.stdout.writableLength + Buffer.byteLength(frame) > 8 * MAX_FRAME) return false;
    if (!process.stdout.write(frame) && !outputPaused) {
      outputPaused = true;
      for (const {socket} of peers.values()) socket.pause();
    }
    return true;
  };
  process.stdout.on('drain', () => {
    outputPaused = false;
    if (!closing) for (const {socket} of peers.values()) socket.resume();
  });
  const report = (code, error, peer) => emit({type: 'error', code, message: String(error.message || error).slice(0, 200), ...(peer ? {peer} : {})});
  const neighborStatus = () => {
    const status = policy.status();
    // Addresses remain in the private peer cache; status exposes diversity counts only.
    return {...status, dial_queue: waitingDials.size, dialing: swarm.connecting,
      groups: Object.fromEntries(Object.entries(status.groups).map(([role, groups]) => [role, groups.length]))};
  };
  const drop = peer => {
    waitingDials.delete(peer);
    swarm.leavePeer(Buffer.from(peer, 'hex'));
    const state = peers.get(peer);
    if (state) state.socket.destroy();
  };
  const persistHistory = () => {
    try { saveNeighborHistory(historyPath, options.topic, policy.snapshot()); }
    catch (error) { report('neighbor_cache_error', error); }
  };
  const reject = peer => {
    const remembered = policy.snapshot().some(record => record.key === peer);
    policy.rejected(peer);
    if (remembered) persistHistory();
    drop(peer);
  };
  const maintain = () => {
    if (closing || !policy) return;
    const actions = policy.tick();
    for (const peer of actions.disconnect) drop(peer);
    for (const {key} of actions.connect) waitingDials.add(key);
    dispatchDials(swarm, waitingDials);
  };
  async function shutdown(code = 0) {
    if (closing) return;
    closing = true;
    clearInterval(discoveryTimer);
    clearInterval(policyTimer);
    lookupQuery?.destroy();
    process.exitCode = code;
    // Offline DHT unannounces can wait on unreachable routers; bound our own exit.
    const deadline = setTimeout(() => {
      process.stderr.write('DHT unannounce exceeded the shutdown deadline\n');
      process.exit(code);
    }, 3000).unref();
    process.stdin.destroy();
    for (const {socket} of peers.values()) socket.destroy();
    if (swarm) await swarm.destroy();
    else if (dht) await dht.destroy({force: true});
    clearTimeout(deadline);
  }
  process.once('SIGINT', () => void shutdown());
  process.once('SIGTERM', () => void shutdown());
  process.stdout.on('error', () => void shutdown(1));
  process.stdin.on('data', jsonLines(command => {
    try {
      if (command.type === 'shutdown') { void shutdown(); return; }
      if (command.type === 'stats') { emit({type: 'stats', peers: [...peers.keys()], ...(policy ? {neighbors: neighborStatus()} : {})}); return; }
      if (typeof command.peer !== 'string' || !/^[0-9a-f]{64}$/.test(command.peer)) throw new Error('Invalid peer key');
      if (command.type === 'join_peer' && policy) { policy.remember(command.peer, null); maintain(); return; }
      if (command.type === 'peer_verified' && policy) {
        policy.verified(command.peer);
        persistHistory();
        return;
      }
      if (command.type === 'disconnect' && policy) { reject(command.peer); return; }
      const state = peers.get(command.peer);
      if (!state) throw new Error('Peer is not connected');
      if (command.type !== 'send' && command.type !== 'send_raw') throw new Error('Unknown control command');
      const frame = command.type === 'send_raw' ? encodeRawMessage(command.payload) : encodeMessage(command.message);
      if (state.pending + frame.length > MAX_PENDING) {
        state.socket.destroy();
        throw new Error('Peer write queue limit exceeded');
      }
      state.pending += frame.length;
      state.socket.write(frame, () => { state.pending -= frame.length; });
    } catch (error) { report('invalid_command', error); }
  }, error => { report('invalid_control_frame', error); void shutdown(1); }, 2 * MAX_FRAME + 4096));
  if (!options.bootstrapper) process.stdin.on('end', () => void shutdown());
  process.stdin.resume();
  try {
    if (options.bootstrapper) {
      const {address} = await lookup(options['bootstrap-host'], {family: 4});
      if (closing) return;
      dht = DHT.bootstrapper(options.port, address, {host: '0.0.0.0'});
      await dht.ready();
    } else {
      const seed = loadSeed(options['key-file']);
      historyPath = `${options['key-file']}.neighbors-${options.topic.toLowerCase()}.json`;
      policy = new NeighborPolicy({seed, maxPeers: options.maxPeers,
        saved: loadNeighborHistory(historyPath, options.topic)});
      // HyperDHT defaults numeric zero to 49737; ranges have an exclusive upper bound.
      dht = new DHT({bootstrap: options.bootstrap, port: [options.port, options.port ? options.port + 1 : 0], host: '0.0.0.0'});
      // Our policy owns the admitted cap. Disable upstream's per-key capacity gate,
      // which can otherwise retain uncancellable queued explicit attempts.
      swarm = new Hyperswarm({dht, seed, maxPeers: Infinity, maxParallel: 3});
      swarm.on('connection', socket => {
        const peer = socket.remotePublicKey.toString('hex');
        if (closing || !policy.admit(peer, socket.rawStream?.remoteHost)) {
          socket.on('error', () => {});
          drop(peer);
          return socket.destroy();
        }
        // Automatic upstream retries never own admission or protected capacity.
        swarm.leavePeer(socket.remotePublicKey);
        const previous = peers.get(peer);
        if (previous) {
          previous.socket.destroy();
          emit({type: 'disconnected', peer});
        }
        const state = {socket, pending: 0, overloaded: false};
        peers.set(peer, state); // Hyperswarm resolves duplicate streams using its Noise key tie-break.
        if (outputPaused) socket.pause();
        socket.on('error', error => report('peer_error', error, peer));
        socket.on('close', () => {
          if (peers.get(peer) !== state) return;
          peers.delete(peer);
          policy.closed(peer);
          swarm.leavePeer(socket.remotePublicKey);
          emit({type: 'disconnected', peer});
        });
        socket.on('data', jsonLines((_, frame) => {
          if (closing || state.overloaded || peers.get(peer) !== state) return;
          if (!emit({type: 'message', peer, payload: frame.toString('base64')})) {
            state.overloaded = true;
            socket.destroy();
          }
        }, error => {
          report('invalid_peer_frame', error, peer);
          reject(peer);
        }));
        emit({type: 'connected', peer});
      });
      dht.on('error', error => report('dht_error', error));
      await swarm.listen();
      if (closing) return;
      const topic = Buffer.from(options.topic, 'hex');
      // Candidate selection belongs to our policy, not an unbounded per-key upstream queue.
      const discovery = swarm.join(topic, {server: true, client: false});
      const discover = async () => {
        if (closing || looking) return;
        looking = true;
        let deadline;
        try {
          await discovery.refresh();
          if (closing) return;
          lookupQuery = dht.lookup(topic);
          deadline = setTimeout(() => lookupQuery?.destroy(), 15000).unref();
          for await (const result of lookupQuery) {
            if (closing) break;
            for (const candidate of result.peers) {
              if (candidate.publicKey.equals(swarm.keyPair.publicKey)) continue;
              policy.remember(candidate.publicKey.toString('hex'), result.from?.host);
            }
          }
          maintain();
        } catch (error) {
          if (!closing) report('discovery_error', error);
        } finally { clearTimeout(deadline); lookupQuery = null; looking = false; }
      };
      for (const peer of options.peer || []) policy.remember(peer, null);
      policyTimer = setInterval(() => { maintain(); emit({type: 'neighbors', status: neighborStatus()}); }, 1000).unref();
      const scheduleDiscovery = delay => {
        discoveryTimer = setTimeout(async () => {
          await discover();
          if (!closing) scheduleDiscovery(30000 + randomInt(5000));
        }, delay).unref();
      };
      // A first lookup can precede the other devices' announcements.
      scheduleDiscovery(5000);
      maintain();
      void discover();
      await discovery.flushed();
    }
    if (closing) return;
    emit({type: 'ready', public_key: swarm?.keyPair.publicKey.toString('hex') || null,
      topic: options.topic?.toLowerCase() || null, address: dht.address(),
      bootstrap_mode: options.bootstrapper ? 'bootstrapper' : options.bootstrap?.length ? 'custom' : options.isolated ? 'isolated' : 'public'});
  } catch (error) {
    if (closing) return;
    report('startup_error', error);
    await shutdown(1);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(error => {
    process.stdout.write(`${JSON.stringify({type: 'error', code: 'startup_error', message: String(error.message).slice(0, 200)})}\n`);
    process.exitCode = 1;
  });
}

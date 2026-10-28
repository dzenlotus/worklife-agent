import {createHmac} from 'node:crypto';
import {isIP} from 'node:net';

const CANDIDATES = 256, SOURCE_CAPACITY = 8, HISTORY = 32;
const PENDING_MS = 30000, COOLDOWN_MS = 30000, PROBE_MS = 60000;
const validKey = key => typeof key === 'string' && /^[a-f0-9]{64}$/i.test(key);

// These are observed address groups, not identities or proof of independent operators.
export function networkGroup(host) {
  if (typeof host !== 'string') return null;
  host = host.replace(/^\[|\]$/g, '').split('%')[0].toLowerCase();
  const family = isIP(host);
  if (family === 4) return `v4:${host.split('.').slice(0, 3).join('.')}.0/24`;
  if (family !== 6) return null;
  if (host.includes('.')) {
    const colon = host.lastIndexOf(':'), bytes = host.slice(colon + 1).split('.').map(Number);
    host = `${host.slice(0, colon)}:${((bytes[0] << 8) | bytes[1]).toString(16)}:${((bytes[2] << 8) | bytes[3]).toString(16)}`;
  }
  const halves = host.split('::');
  const left = halves[0] ? halves[0].split(':') : [];
  const right = halves[1] ? halves[1].split(':') : [];
  const words = (halves.length === 2 ? [...left, ...Array(8 - left.length - right.length).fill('0'), ...right] : left).map(word => Number.parseInt(word, 16));
  if (words.slice(0, 5).every(word => word === 0) && words[5] === 0xffff) {
    return networkGroup(`${words[6] >> 8}.${words[6] & 255}.${words[7] >> 8}.${words[7] & 255}`);
  }
  return `v6:${words.slice(0, 3).map(word => word.toString(16).padStart(4, '0')).join(':')}::/48`;
}

export class NeighborPolicy {
  #seed;
  #book = new Map();
  #history = new Map();
  #active = new Map();
  #intents = new Map();
  #disconnect = new Set();
  #round = 0;

  constructor({seed, maxPeers = 32, now = Date.now, saved = []} = {}) {
    if (!(seed instanceof Uint8Array) || seed.length !== 32) throw new Error('Neighbor selection needs a private 32-byte seed');
    if (!Number.isInteger(maxPeers) || maxPeers < 1 || maxPeers > 32) throw new Error('Max peers must be between 1 and 32');
    this.#seed = Buffer.from(seed);
    this.now = now;
    let incoming = maxPeers === 1 ? 0 : Math.max(1, Math.floor(maxPeers * 22 / 32));
    if (maxPeers >= 3) incoming = Math.min(incoming, maxPeers - 2);
    const local = maxPeers - incoming;
    const probe = local > 1 ? Math.min(2, Math.max(1, Math.floor(local / 5))) : 0;
    this.limits = {candidates: CANDIDATES, sourceGroup: SOURCE_CAPACITY, history: HISTORY,
      selected: local - probe, probe, incoming, maxPeers};
    for (const savedPeer of Array.isArray(saved) ? saved.slice(-HISTORY) : []) {
      if (!savedPeer || !validKey(savedPeer.key) || !Number.isFinite(savedPeer.verifiedAt)) continue;
      const record = this.#record(savedPeer.key.toLowerCase(), savedPeer.source);
      record.host = networkGroup(savedPeer.host) ? savedPeer.host : null;
      record.verifiedAt = savedPeer.verifiedAt;
      this.#book.set(record.key, record);
      this.#history.set(record.key, record);
    }
  }

  #record(key, source) {
    return {key, source: networkGroup(source) ? source : 'unknown', host: null, verifiedAt: null, cooldownUntil: 0};
  }

  #rank(value) {
    return createHmac('sha256', this.#seed).update(value).digest('hex');
  }

  #protected(key) {
    return this.#history.has(key) || this.#active.has(key) || this.#intents.has(key);
  }

  #worst(records) {
    return records.reduce((worst, record) => !worst || this.#rank(`book/${record.key}`) > this.#rank(`book/${worst.key}`) ? record : worst, null);
  }

  #trimHistory() {
    if (this.#history.size <= HISTORY) return;
    const records = [...this.#history.values()], groups = new Map();
    for (const record of records) {
      const group = networkGroup(record.host);
      groups.set(group, (groups.get(group) || 0) + 1);
    }
    const unselected = records.filter(record => this.#active.get(record.key)?.role !== 'selected');
    const victims = unselected.length ? unselected : records;
    victims.sort((a, b) => groups.get(networkGroup(b.host)) - groups.get(networkGroup(a.host)) || a.verifiedAt - b.verifiedAt);
    this.#history.delete(victims[0].key);
  }

  remember(key, sourceHost) {
    if (!validKey(key)) return false;
    key = key.toLowerCase();
    if (this.#book.has(key)) return true;
    const record = this.#record(key, sourceHost);
    const group = networkGroup(record.source);
    const sameSource = [...this.#book.values()].filter(peer => peer.verifiedAt === null && networkGroup(peer.source) === group);
    let victim;
    if (sameSource.length >= SOURCE_CAPACITY) {
      victim = this.#worst([...sameSource.filter(peer => !this.#protected(peer.key)), record]);
      if (!victim || victim === record) return false;
    } else if (this.#book.size >= CANDIDATES) {
      victim = this.#worst([...this.#book.values()].filter(peer => !this.#protected(peer.key)).concat(record));
      if (!victim || victim === record) return false;
    }
    if (victim) this.#book.delete(victim.key);
    this.#book.set(key, record);
    return true;
  }

  #slots(role) {
    const keys = new Set([...this.#active].filter(([, peer]) => peer.role === role).map(([key]) => key));
    for (const [key, intent] of this.#intents) if (intent.role === role) keys.add(key);
    return keys.size;
  }

  #drop(key, now) {
    this.#active.delete(key);
    this.#intents.delete(key);
    const record = this.#book.get(key);
    if (record) record.cooldownUntil = now + COOLDOWN_MS;
    this.#disconnect.add(key);
  }

  #promote(key, now) {
    const peer = this.#active.get(key);
    if (!peer || peer.role !== 'probe' || !this.#history.has(key)) return;
    if (this.#slots('selected') >= this.limits.selected) {
      const group = networkGroup(peer.host);
      if (!group) return;
      const selected = [...this.#active].filter(([, other]) => other.role === 'selected');
      if (selected.some(([, other]) => networkGroup(other.host) === group)) return;
      const counts = new Map();
      for (const [, other] of selected) {
        const otherGroup = networkGroup(other.host);
        if (otherGroup) counts.set(otherGroup, (counts.get(otherGroup) || 0) + 1);
      }
      const victims = selected.filter(([, other]) => (counts.get(networkGroup(other.host)) || 0) > 1);
      if (!victims.length) return;
      victims.sort(([a], [b]) => this.#rank(`replace/${a}`).localeCompare(this.#rank(`replace/${b}`)));
      this.#drop(victims[0][0], now);
    }
    peer.role = 'selected';
    const intent = this.#intents.get(key);
    if (intent) intent.role = 'selected';
  }

  #choose(now) {
    const groups = new Map(), counts = new Map(), actual = new Map();
    const localKeys = new Set(this.#intents.keys());
    for (const [key, peer] of this.#active) {
      if (peer.role !== 'incoming') localKeys.add(key);
      if (peer.role === 'selected') {
        const group = networkGroup(peer.host);
        if (group) actual.set(group, (actual.get(group) || 0) + 1);
      }
    }
    for (const [key, intent] of this.#intents) {
      if (intent.role !== 'selected' || this.#active.has(key)) continue;
      const group = networkGroup(this.#book.get(key)?.host);
      if (group) actual.set(group, (actual.get(group) || 0) + 1);
    }
    for (const key of localKeys) {
      const group = networkGroup(this.#book.get(key)?.source);
      counts.set(group, (counts.get(group) || 0) + 1);
    }
    for (const record of this.#book.values()) {
      if (this.#active.has(record.key) || this.#intents.has(record.key) || record.cooldownUntil > now) continue;
      const group = networkGroup(record.source);
      if (!groups.has(group)) groups.set(group, []);
      groups.get(group).push(record);
    }
    if (!groups.size) return null;
    // Draw source groups first; advertising more keys does not buy more group draws.
    const preference = record => {
      const group = networkGroup(record.host);
      return group ? (actual.get(group) || 0) * 2 : 1;
    };
    const round = this.#round++;
    const groupPreference = group => Math.min(...groups.get(group).map(preference));
    const chosen = [...groups.keys()].sort((a, b) => (counts.get(a) || 0) - (counts.get(b) || 0) ||
      groupPreference(a) - groupPreference(b) ||
      this.#rank(`${round}/source/${a}`).localeCompare(this.#rank(`${round}/source/${b}`)))[0];
    return groups.get(chosen).sort((a, b) => preference(a) - preference(b) ||
      this.#rank(`${round}/peer/${a.key}`).localeCompare(this.#rank(`${round}/peer/${b.key}`)))[0];
  }

  tick() {
    const now = this.now(), connect = [];
    for (const [key, intent] of this.#intents) {
      if (intent.expiresAt > now) continue;
      this.#intents.delete(key);
      if (intent.pending && !this.#active.has(key)) this.#drop(key, now);
    }
    for (const [key, peer] of this.#active) this.#promote(key, now);
    for (const [key, peer] of this.#active) {
      if (peer.role === 'probe' && now - peer.started >= PROBE_MS) this.#drop(key, now);
    }
    for (const role of ['selected', 'probe']) {
      while (this.#slots(role) < this.limits[role]) {
        const record = this.#choose(now);
        if (!record) break;
        this.#intents.set(record.key, {role, expiresAt: now + PENDING_MS, pending: true});
        connect.push({key: record.key, role});
      }
    }
    const disconnect = [...this.#disconnect];
    this.#disconnect.clear();
    return {connect, disconnect};
  }

  admit(key, host) {
    if (!validKey(key)) return null;
    key = key.toLowerCase();
    const existing = this.#active.get(key);
    if (existing) {
      existing.host = networkGroup(host) ? host : null;
      const record = this.#book.get(key);
      if (record) record.host = existing.host;
      return existing.role;
    }
    const now = this.now(), intent = this.#intents.get(key);
    const role = intent && intent.expiresAt > now ? intent.role : 'incoming';
    if (this.#active.size >= this.limits.maxPeers || (role === 'incoming' && this.#slots(role) >= this.limits.incoming)) return null;
    const actualHost = networkGroup(host) ? host : null;
    this.#active.set(key, {role, host: actualHost, started: now});
    if (intent) intent.pending = false;
    const record = this.#book.get(key);
    if (record) record.host = actualHost;
    return role;
  }

  verified(key) {
    if (!validKey(key)) return false;
    key = key.toLowerCase();
    const peer = this.#active.get(key);
    if (!peer) return false;
    const now = this.now();
    let record = this.#book.get(key);
    if (!record) {
      record = this.#record(key, 'unknown');
      if (this.#book.size >= CANDIDATES) {
        const victim = this.#worst([...this.#book.values()].filter(other => !this.#protected(other.key)));
        if (victim) this.#book.delete(victim.key);
      }
      this.#book.set(key, record);
    }
    record.host = peer.host;
    record.verifiedAt = now;
    this.#history.delete(key);
    this.#history.set(key, record);
    this.#trimHistory();
    this.#promote(key, now);
    return true;
  }

  closed(key) {
    if (!validKey(key)) return;
    key = key.toLowerCase();
    const now = this.now(), peer = this.#active.get(key), intent = this.#intents.get(key);
    if (peer && peer.role !== 'incoming') {
      // Keep local intent across Hyperswarm's duplicate stream replacement.
      this.#intents.set(key, {role: peer.role, expiresAt: now + PENDING_MS, pending: false});
    } else if (intent) intent.pending = false;
    this.#active.delete(key);
    const record = this.#book.get(key);
    if (record) record.cooldownUntil = now + COOLDOWN_MS;
  }

  rejected(key) {
    if (!validKey(key)) return;
    key = key.toLowerCase();
    if (this.#active.has(key) || this.#intents.has(key)) this.#disconnect.add(key);
    this.#book.delete(key);
    this.#history.delete(key);
    this.#active.delete(key);
    this.#intents.delete(key);
  }

  snapshot() {
    return [...this.#history.values()].map(({key, source, host, verifiedAt}) => ({key, source, host, verifiedAt}));
  }

  status() {
    const roles = {selected: 0, probe: 0, incoming: 0};
    const groups = {selected: new Set(), probe: new Set(), incoming: new Set()};
    for (const peer of this.#active.values()) {
      roles[peer.role]++;
      const group = networkGroup(peer.host);
      if (group) groups[peer.role].add(group);
    }
    return {candidates: this.#book.size, history: this.#history.size, active: this.#active.size,
      pending: [...this.#intents.values()].filter(intent => intent.pending).length, intents: this.#intents.size,
      roles, groups: Object.fromEntries(Object.entries(groups).map(([role, values]) => [role, [...values]])),
      degraded: groups.selected.size < Math.min(2, this.limits.selected), limits: {...this.limits}};
  }
}

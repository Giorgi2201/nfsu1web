#!/usr/bin/env node
// Smoke nfsu1-server /lan hello/welcome + binary unicast. No game runtime.
import { spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';
import process from 'node:process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const port = Number(process.env.NFSU1_LAN_SMOKE_PORT || 18765);
const serverBin = process.env.NFSU1_SERVER
  || path.join(ROOT, 'server/target/release/nfsu1-server');
const dist = path.join(ROOT, 'work/upstream/nfsu2-web/web/dist');
const wasm = path.join(ROOT, 'work/upstream/nfsu2-web/out/web/nfsu1.wasm');
const meta = path.join(ROOT, 'work/upstream/nfsu2-web/out/web/nfsu1.json');
const data = path.join(ROOT, 'work/data');

function be32(n) {
  const b = Buffer.alloc(4);
  b.writeUInt32BE(n >>> 0, 0);
  return b;
}

async function waitHealth(ms = 8000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/healthz`);
      if (r.ok) return;
    } catch { /* retry */ }
    await sleep(100);
  }
  throw new Error('server healthz timeout');
}

function openPeer(name) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`ws://127.0.0.1:${port}/lan`);
    const timer = setTimeout(() => { ws.close(); reject(new Error(`welcome timeout for ${name}`)); }, 5000);
    const ctrl = [];
    let welcome = null;
    ws.binaryType = 'arraybuffer';
    ws.addEventListener('open', () => {
      ws.send(JSON.stringify({ t: 'hello', name, deltas: 1, lan: 1, bundle: 1 }));
    });
    ws.addEventListener('message', (ev) => {
      if (typeof ev.data === 'string') {
        const m = JSON.parse(ev.data);
        ctrl.push(m);
        if (m.t === 'welcome') {
          welcome = m;
          clearTimeout(timer);
          resolve({ ws, welcome, ctrl });
        }
      }
    });
    ws.addEventListener('error', () => reject(new Error(`ws error for ${name}`)));
  });
}

function onceBinary(ws, ms = 2000) {
  return new Promise((resolve, reject) => {
    const onMsg = (ev) => {
      if (typeof ev.data === 'string') return;
      cleanup();
      resolve(Buffer.from(ev.data));
    };
    const onErr = () => { cleanup(); reject(new Error('ws error waiting binary')); };
    const timer = setTimeout(() => { cleanup(); reject(new Error('binary timeout')); }, ms);
    const cleanup = () => {
      clearTimeout(timer);
      ws.removeEventListener('message', onMsg);
      ws.removeEventListener('error', onErr);
    };
    ws.addEventListener('message', onMsg);
    ws.addEventListener('error', onErr);
  });
}

const child = spawn(serverBin, [
  '--host', '127.0.0.1', '--port', String(port),
  '--dist', dist, '--wasm', wasm, '--metadata', meta, '--data', data,
], { cwd: ROOT, stdio: ['ignore', 'pipe', 'pipe'] });

let out = '';
child.stdout.on('data', (c) => { out += c; });
child.stderr.on('data', (c) => { out += c; });

try {
  await waitHealth();
  const empty = await (await fetch(`http://127.0.0.1:${port}/players`)).json();
  if (empty.players !== 0) throw new Error(`expected 0 players, got ${JSON.stringify(empty)}`);

  const a = await openPeer('Alpha');
  const b = await openPeer('Bravo');
  if (a.welcome.vip === b.welcome.vip) throw new Error('duplicate VIP');
  if (a.welcome.bundle !== 1) throw new Error('expected bundle:1');
  if (a.welcome.mask !== '255.255.248.0') throw new Error('expected /21 network');

  const frame = Buffer.alloc(24);
  frame[0] = 3;
  be32(0).copy(frame, 4);
  be32(b.welcome.vip).copy(frame, 8);
  frame.writeUInt16BE(3658, 12);
  frame.writeUInt16BE(3658, 14);
  frame.write('ping-lan', 16);
  const pending = onceBinary(b.ws);
  a.ws.send(frame);
  const got = await pending;
  if (got[0] !== 3) throw new Error(`kind ${got[0]}`);
  const src = got.readUInt32BE(4);
  if (src !== (a.welcome.vip >>> 0)) throw new Error(`src rewrite ${src} != ${a.welcome.vip}`);
  if (got.subarray(16, 24).toString() !== 'ping-lan') throw new Error('payload mismatch');

  // An upstream bundle containing two reliable frames must arrive in order,
  // whether the writer combines them or emits separate WebSocket messages.
  const frames = [];
  const takeFrames = (ev) => {
    if (typeof ev.data === 'string') return;
    const bytes = Buffer.from(ev.data);
    if (bytes[0] !== 32) { frames.push(bytes); return; }
    for (let at = 4; at < bytes.length;) {
      const start = at + 4 + bytes[at] * 4, end = start + bytes.readUInt16BE(at + 2);
      frames.push(bytes.subarray(start, end));
      at = end;
    }
  };
  b.ws.addEventListener('message', takeFrames);
  const bundle = Buffer.alloc(4 + 2 * (4 + frame.length));
  bundle[0] = 32;
  for (let n = 0; n < 2; n++) {
    const at = 4 + n * (4 + frame.length);
    bundle.writeUInt16BE(frame.length, at + 2);
    frame.copy(bundle, at + 4);
    bundle[at + 4 + 23] = n;
  }
  a.ws.send(bundle);
  const until = Date.now() + 3000;
  while (frames.length < 2 && Date.now() < until) await sleep(10);
  b.ws.removeEventListener('message', takeFrames);
  if (frames.length !== 2 || frames[0][23] !== 0 || frames[1][23] !== 1
      || frames.some(f => f.readUInt32BE(4) !== (a.welcome.vip >>> 0))) {
    throw new Error('bundle order/source mismatch');
  }

  const peers = [a, b];
  const target = Number(process.env.NFSU1_LAN_SMOKE_PEERS || 2);
  for (let i = 2; i < target; i++) peers.push(await openPeer(`Peer${i}`));
  if (new Set(peers.map(p => p.welcome.vip)).size !== peers.length) throw new Error('duplicate VIP');

  const counts = await (await fetch(`http://127.0.0.1:${port}/players`)).json();
  if (counts.players !== peers.length) throw new Error(`expected ${peers.length} players, got ${JSON.stringify(counts)}`);

  for (const peer of peers) peer.ws.close();
  console.log(`lan_switch_smoke ok: ${peers.length} peers, unicast source rewrite, ordered bundles`);
} catch (err) {
  console.error(String(err));
  if (out.trim()) console.error(out.trim().split('\n').slice(-20).join('\n'));
  process.exitCode = 1;
} finally {
  child.kill('SIGTERM');
  await Promise.race([
    new Promise((r) => child.on('exit', r)),
    sleep(2000),
  ]);
}

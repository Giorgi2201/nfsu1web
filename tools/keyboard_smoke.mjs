#!/usr/bin/env node
// Exercise the overlaid input adapter and its real mailbox protocol with Node host stubs.
// This does not operate a browser or establish game compatibility.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const upstream = path.resolve(process.argv[2] ?? path.join(root, 'work/upstream/nfsu2-web'));
const inputPath = path.join(upstream, 'web/src/input/index.ts');
let source = await readFile(inputPath, 'utf8');
if (!source.includes('import { translateKeyboardEvent }')) {
  const { mkdtempSync, writeFileSync, readFileSync, rmSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const dir = mkdtempSync(path.join(tmpdir(), 'nfsu1-kbd-'));
  try {
    const dest = path.join(dir, 'web/src/input');
    execFileSync('mkdir', ['-p', dest]);
    writeFileSync(path.join(dest, 'index.ts'), source);
    execFileSync('patch', ['-p1', '-i', path.join(root, 'patches/nfsu2-web/web/src/input/index.ts.patch')], { cwd: dir });
    source = readFileSync(path.join(dest, 'index.ts'), 'utf8');
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}
const require = createRequire(path.join(upstream, 'web/build.mjs'));
const esbuild = require('esbuild');
const result = await esbuild.build({
  stdin: { contents: `${source}\nexport { toggleKeyboardAliases, translateKeyboardEvent } from '../app/keyboard';\nexport { INPUT_MAGIC, INPUT_VERSION, IM_MAGIC, IM_VERSION, IM_EV_W, IM_EV_R, IM_OFF_EV, IEV_KEY_DOWN, IEV_KEY_UP, IEV_RELEASE_ALL, IEV_FOCUS };`, loader: 'ts', resolveDir: path.dirname(inputPath) },
  bundle: true, write: false, platform: 'node', format: 'cjs', target: 'es2022',
  plugins: [{ name: 'tracked-keyboard', setup(build) {
    build.onResolve({ filter: /\/app\/keyboard$/ }, () => ({ path: path.join(root, 'browser/keyboard.ts') }));
  } }],
});

class Target {
  listeners = new Map();
  addEventListener(type, fn) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(fn);
  }
  removeEventListener(type, fn) { this.listeners.get(type)?.delete(fn); }
  dispatchEvent(e) { for (const fn of [...(this.listeners.get(e.type) ?? [])]) fn(e); return true; }
}
class Element extends Target {
  style = {};
  tagName = 'CANVAS';
  isContentEditable = false;
  tabIndex = 0;
  ui = false;
  closest() { return this.ui; }
}
const window = new Target(), document = new Target();
Object.assign(document, { hidden: false, fullscreenElement: null, hasFocus: () => true, querySelector: () => null });
const storage = new Map([['nfsu1-keyboard-v1', JSON.stringify({ ArrowUp: 'KeyW', ArrowDown: 'KeyS', ArrowLeft: 'KeyA', ArrowRight: 'KeyD', Space: 'KeyH', AltLeft: 'KeyN', ShiftLeft: 'KeyE', ControlLeft: 'KeyX' })]]);
const context = vm.createContext({
  module: { exports: {} }, console, document, window, HTMLElement: Element, Event,
  navigator: { platform: 'Linux' }, performance,
  localStorage: { getItem: k => storage.get(k) ?? null, setItem: (k, v) => storage.set(k, v) },
  addEventListener: window.addEventListener.bind(window), removeEventListener: window.removeEventListener.bind(window),
  dispatchEvent: window.dispatchEvent.bind(window), requestAnimationFrame: () => 1, cancelAnimationFrame() {},
  setInterval: () => 1, clearInterval() {},
});
vm.runInContext(result.outputFiles[0].text, context);
const p = context.module.exports;
const defaults = vm.createContext({ module: { exports: {} }, localStorage: { getItem: () => '{}' } });
vm.runInContext(result.outputFiles[0].text, defaults);
for (const [code, destination] of [['ShiftRight', undefined], ['Space', undefined], ['Insert', undefined], ['Delete', undefined]]) {
  assert.equal(defaults.module.exports.translateKeyboardEvent({ code }), destination);
}
const buffer = new SharedArrayBuffer(32768), ptr = 64;
const header = new Int32Array(buffer, ptr, 64), bytes = new Uint8Array(buffer);
header[p.IM_MAGIC] = p.INPUT_MAGIC;
header[p.IM_VERSION] = p.INPUT_VERSION;
const canvas = new Element();
const input = p.attachInput({ memory: { buffer }, registered: async () => ({ ptr }) }, canvas, { gamepads: false, mac: false, log() {} });
await Promise.resolve();
await Promise.resolve();
assert.equal(input.status().attached, true);

function events() {
  const rows = [];
  for (let i = header[p.IM_EV_R]; i < header[p.IM_EV_W]; i++) {
    const at = ptr + p.IM_OFF_EV + (i & 1023) * 16;
    const raceDik = new DataView(buffer).getInt32(at + 8, true);
    rows.push({ type: bytes[at], dik: bytes[at + 1], vk: bytes[at + 2], chars: [...bytes.slice(at + 5, at + 5 + bytes[at + 4])],
      ...(raceDik ? { raceDik } : {}) });
  }
  header[p.IM_EV_R] = header[p.IM_EV_W];
  return rows;
}
function key(type, code, extra = {}) {
  window.dispatchEvent({ type, code, key: code.startsWith('Key') ? code.slice(3).toLowerCase() : code,
    target: canvas, keyCode: 0, repeat: false, isComposing: false, metaKey: false, ctrlKey: false, altKey: false,
    shiftKey: false, isTrusted: true, getModifierState: () => false, preventDefault() {}, ...extra });
}
// Existing saved row IDs must route to NFSU1 keys, rather than NFSU2 guesses.
for (const [code, physicalDik, raceDik] of [['KeyH', 0x23, 0x36], ['KeyN', 0x31, 0x39], ['KeyE', 0x12, 0xd2], ['KeyX', 0x2d, 0xd3]]) {
  key('keydown', code);
  assert.deepEqual(events().map(e => [e.type, e.dik, e.raceDik, e.chars]),
    [[p.IEV_KEY_DOWN, physicalDik, raceDik, [code.charCodeAt(3) + 32]]]);
  key('keyup', code);
  assert.deepEqual(events().map(e => [e.type, e.dik, e.raceDik]), [[p.IEV_KEY_UP, physicalDik, raceDik]]);
}
key('keydown', 'KeyW');
assert.deepEqual(events(), [{ type: p.IEV_KEY_DOWN, dik: 0x11, vk: 0x57, chars: [0x77], raceDik: 0xc8 }]);
key('keydown', 'ArrowUp'); assert.equal(events()[0].dik, 0xc8);
key('keydown', 'KeyW', { repeat: true });
assert.deepEqual(events()[0].chars, [0x77], 'Overlapping driving keys must preserve independent text repeats');
key('keyup', 'KeyW'); assert.equal(events()[0].dik, 0x11);
key('keyup', 'ArrowUp'); assert.deepEqual(events().map(e => [e.type, e.dik]), [[p.IEV_KEY_UP, 0xc8]]);
key('keydown', 'KeyW', { ctrlKey: true });
assert.equal(events()[0].raceDik, 0xc8, 'Ctrl held during driving must preserve the WASD binding');
key('keyup', 'KeyW', { ctrlKey: false }); assert.equal(events()[0].dik, 0x11);
assert.equal(p.toggleKeyboardAliases(), false);
assert.equal(events()[0].type, p.IEV_RELEASE_ALL);
key('keydown', 'KeyW');
assert.deepEqual(events(), [{ type: p.IEV_KEY_DOWN, dik: 0x11, vk: 0x57, chars: [0x77] }], 'F10 disables only the driving binding');
key('keyup', 'KeyW'); events();
assert.equal(p.toggleKeyboardAliases(), true); events();
key('keydown', 'KeyQ'); assert.deepEqual(events()[0].chars, [0x71], 'Unmapped text preserves WM_CHAR');
key('keyup', 'KeyQ'); events();
key('keydown', 'KeyW'); events();
window.dispatchEvent(new Event('nfsu1-keyboard-change'));
assert.equal(events()[0].type, p.IEV_RELEASE_ALL);
key('keyup', 'KeyW'); assert.equal(events().length, 0, 'A late release cannot release a different mapping');
key('keydown', 'KeyW'); events();
window.dispatchEvent(new Event('blur')); assert.equal(events()[0].type, p.IEV_FOCUS);
key('keyup', 'KeyW'); assert.equal(events().length, 0);
window.dispatchEvent(new Event('focus')); events();
key('keydown', 'KeyW'); events();
const ui = new Element(); ui.ui = true;
document.dispatchEvent({ type: 'focusin', target: ui }); assert.equal(events()[0].type, p.IEV_RELEASE_ALL);
key('keyup', 'KeyW'); assert.equal(events().length, 0);
key('keydown', 'KeyW', { target: ui }); assert.equal(events().length, 0, 'Page controls keep their keyboard events');
input.detach(); events();
assert.equal(window.listeners.get('nfsu1-keyboard-change').size, 0);
assert.equal(document.listeners.get('focusin').size, 0);
key('keydown', 'KeyW'); assert.equal(events().length, 0);
console.log('Keyboard mailbox smoke passed: physical text/VK/DIK, separate driving destinations, overlapping keys, repeats, driving toggle, map changes, blur, UI focus and detach. No browser/game validation.');

#!/usr/bin/env python3
"""Exercise actual WebGPU pipeline descriptors without creating a GPU/browser.

Checks persistent scene depth across smaller Z-disabled effect targets and a
later Z-enabled draw on the same target. Uses fake GPU objects to inspect the
actual encodeFrame passes, plus all render-state pipeline combinations.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

from depth_state_overlay import encoder

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
const { Encoder } = await import(pathToFileURL(process.argv[2]));
const context = Object.create(Encoder.prototype);
Object.assign(context, {
  vsMods: new Map(), psMods: new Map(), tvertMod: {}, ffMod: {}, ffCubeMod: {},
  pl2d: {}, plCube: {},
});
// No GPU API is invoked. These objects record actual encodeFrame decisions;
// a single synthetic pixel models whether a later car is behind a wall.
globalThis.GPUBufferUsage = { STORAGE: 1, COPY_DST: 2, UNIFORM: 4 };
globalThis.GPUTextureUsage = { RENDER_ATTACHMENT: 1 };
function texture(label, width, height) {
  return { label, width, height, depth: 1, createView() { return { texture: this }; }, destroy() {} };
}
function frame(records, initialZid = 1) {
  const e = Object.create(Encoder.prototype);
  const memory = new ArrayBuffer(65536), u32 = new Uint32Array(memory), f32 = new Float32Array(memory);
  const screen = texture('screen', 800, 600), small = texture('small', 128, 128);
  const depthTextures = [], passes = [], visibility = [];
  Object.assign(e, {
    views() {}, u32, i32: new Int32Array(memory), f32, u8: new Uint8Array(memory), ctlW: 0,
    device: {
      createTexture(desc) { const t = texture(desc.label, desc.size[0], desc.size[1]); depthTextures.push(t); return t; },
      createBindGroup() { return {}; },
    },
    queue: { writeBuffer() {} }, log() {}, tex: [], zTex: [], zView: [],
    zpend: new Uint8Array(64), zpendV: new Float32Array(64), scratchZ: new Map(),
    destroyLater: [], traceSeq: new Set(), traceDumps: false, pStage: new Float32Array(8192),
    b1: new Int32Array(9), dyn: new Uint32Array(2), bg1: new Map(), pipes: new Map(),
    vsMods: new Map(), psMods: new Map(), tvertMod: {}, ffMod: {}, ffCubeMod: {},
    pl2d: {}, plCube: {}, totalDraws: 0, totalPasses: 0, zMismatch: 0,
    calls: { pass: 0, bg0: 0, bg1: 0, bg1New: 0, pipe: 0, blend: 0, draw: 0 },
    grow(old) { return old ?? {}; }, group0() { return {}; },
    texFor() { return { serial: 1, view: {} }; }, sampler() { return {}; },
    pipeline(key, blend, ps, vs, cull, dm, nd) {
      const desc = this.pipeDesc(key, blend, ps, vs, cull, dm, nd);
      this.pipes.set(key, desc); return desc;
    },
  });
  e.tex[2] = { rt: true, w: 128, h: 128, rtViews: [small.createView()] };
  if (initialZid !== 1) {
    const z = texture(`existing-z${initialZid}`, 800, 600);
    e.zTex[initialZid] = z; e.zView[initialZid] = z.createView();
  }
  const fw = 24, draws = 256;
  u32[fw + 1] = records.length; u32[fw + 6] = draws * 4;
  u32[fw + 10] = 8192; u32[fw + 12] = 800; u32[fw + 13] = 600;
  records.forEach((r, i) => {
    const w = draws + i * 38;
    u32[w] = r.first ?? i; u32[w + 1] = r.clear ? 0 : 3;
    u32[w + 3] = r.target ?? 0; u32[w + 4] = r.clear ? 1 : 0;
    u32[w + 7] = (initialZid << 8) | (r.depth ?? 19);
    u32[w + 26] = 1;
    if (r.clear) { u32[w + 32] = 2; f32[w + 33] = r.clearValue ?? 1; }
  });
  const enc = {
    beginRenderPass(desc) {
      passes.push(desc);
      const z = desc.depthStencilAttachment.view.texture;
      if (desc.depthStencilAttachment.depthLoadOp === 'clear') z.depth = desc.depthStencilAttachment.depthClearValue;
      let pipe;
      return {
        end() {}, setBindGroup() {}, setBlendConstant() {}, setPipeline(p) { pipe = p; },
        draw(_count, _instances, first) {
          const incoming = [0.25, 0.9, 0.75][first] ?? 0.75;
          const state = pipe.depthStencil;
          const visible = state.depthCompare === 'always' || incoming <= z.depth;
          visibility.push(visible);
          if (visible && state.depthWriteEnabled) z.depth = incoming;
        },
      };
    },
  };
  e.encodeFrame(0, enc, screen);
  return { e, depthTextures, passes, visibility };
}
for (const zid of [1, 2]) {
  const r = frame([{ depth: 19 }, { target: 2, depth: 18 }, { depth: 19 }], zid);
  const a = r.passes[0].depthStencilAttachment, b = r.passes[1].depthStencilAttachment, c = r.passes[2].depthStencilAttachment;
  assert.equal(c.view, a.view, `z${zid}: smaller Z-disabled target replaced scene depth`);
  assert.notEqual(b.view, a.view, `z${zid}: effect needs scratch depth`);
  assert.equal(c.depthLoadOp, 'load', `z${zid}: scene depth must load`);
  assert.equal(r.visibility[2], false, `z${zid}: traffic behind wall must remain rejected`);
  assert.equal(r.e.zMismatch, 0, `z${zid}: Z-disabled target must not test surface size`);
}
const enabling = frame([{ depth: 18 }, { depth: 19 }]);
assert.equal(enabling.passes.length, 2, 'enabling Z on the same target must reopen scratch-only pass');
assert.notEqual(enabling.passes[0].depthStencilAttachment.view, enabling.passes[1].depthStencilAttachment.view);
const clearing = frame([{ depth: 19 }, { depth: 0, clear: true }, { depth: 19, first: 2 }]);
assert.equal(clearing.visibility[1], true, 'explicit depth clear must work even with Z disabled');
assert.equal(clearing.passes[1].depthStencilAttachment.depthLoadOp, 'clear');
console.log('PASS: actual frame encoder preserves scene depth across smaller Z-disabled targets, reopens for Z enable, honors depth clears');
const comparison = ['always', 'never', 'less', 'equal', 'less-equal', 'greater',
                    'not-equal', 'greater-equal'];
for (let z = 0; z < 2; z++) {
  for (let write = 0; write < 2; write++) {
    for (let fn = 0; fn < 8; fn++) {
      const dm = z | (write << 1) | (fn << 2);
      const desc = context.pipeDesc(1, 0, 0, 0, 1, dm, true).depthStencil;
      assert.equal(desc.depthWriteEnabled, Boolean(z && write), `mode ${dm}`);
      assert.equal(desc.depthCompare, z ? comparison[fn] : 'always', `mode ${dm}`);
    }
  }
}
console.log('PASS: actual pipeline disables depth writes with Z disabled; read-only and normal depth states preserved');
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=ROOT / "work/upstream/nfsu2-web")
    parser.add_argument("--original", action="store_true", help="run unmodified pinned source (expected to fail)")
    args = parser.parse_args()
    upstream = args.upstream.resolve()
    source_path = upstream / "web/src/gpu/encoder.ts"
    # Always start from the reversible overlay's pristine backup when available.
    backup = upstream / ".nfsu1-browser-profile/web/src/gpu/encoder.ts"
    source = (backup if backup.is_file() else source_path).read_text()
    if not args.original:
        source = encoder(source)
    esbuild = ROOT / "work/toolchain/web-bundler/node_modules/.bin/esbuild"
    with tempfile.TemporaryDirectory(prefix="nfsu1-depth-state-") as directory:
        temporary = Path(directory)
        bundle = temporary / "encoder.mjs"
        harness = temporary / "check.mjs"
        subprocess.run([str(esbuild), "--bundle", "--platform=node", "--format=esm", "--loader=ts",
                        f"--outfile={bundle}"], input=source, text=True, cwd=source_path.parent, check=True)
        harness.write_text(HARNESS)
        subprocess.run(["node", str(harness), str(bundle)], check=True)


if __name__ == "__main__":
    main()

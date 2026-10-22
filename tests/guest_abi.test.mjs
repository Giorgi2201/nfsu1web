import test from 'node:test';
import assert from 'node:assert/strict';
import { CPU, createFixture } from '../poc/guest_abi.mjs';

function setup(view, cpu, stack, a, b, ret = 0x12345678) {
  view.setUint32(cpu + CPU.esp, stack, true);
  view.setUint32(cpu + 4, 0xcafe, true); // ecx: must remain unchanged
  for (const [offset, value] of [[0, ret], [4, a], [8, b]]) {
    view.setUint32(stack + offset, value, true);
  }
}

test('cdecl preserves arguments for caller cleanup and reads return slot', async () => {
  const { view, dispatch } = await createFixture();
  const cpu = 0x8000, stack = 0x1001; // deliberately unaligned
  setup(view, cpu, stack, 17, 25);
  dispatch(cpu, 0);
  assert.equal(view.getUint32(cpu + CPU.eax, true), 42);
  assert.equal(view.getUint32(cpu + CPU.eip, true), 0x12345678);
  assert.equal(view.getUint32(cpu + CPU.esp, true), stack + 4);
  assert.equal(view.getUint32(stack + 4, true), 17);
  assert.equal(view.getUint32(cpu + 4, true), 0xcafe);
});

test('stdcall callee removes return slot and eight argument bytes', async () => {
  const { view, dispatch } = await createFixture();
  setup(view, 0x8000, 0x1000, 0xffffffff, 2);
  dispatch(0x8000, 1);
  assert.equal(view.getUint32(0x8000 + CPU.eax, true), 1);
  assert.equal(view.getUint32(0x8000 + CPU.esp, true), 0x100c);
});

test('alternating CPU pointers retain separate register state', async () => {
  const { view, dispatch } = await createFixture();
  setup(view, 0x8000, 0x1000, 2, 3);
  setup(view, 0x8100, 0x2000, 20, 30);
  dispatch(0x8000, 0);
  dispatch(0x8100, 1);
  assert.equal(view.getUint32(0x8000, true), 5);
  assert.equal(view.getUint32(0x8100, true), 50);
  assert.equal(view.getUint32(0x8000 + CPU.esp, true), 0x1004);
  assert.equal(view.getUint32(0x8100 + CPU.esp, true), 0x200c);
});

test('unknown indirect targets trap instead of silently returning', async () => {
  const { dispatch } = await createFixture();
  assert.throws(() => dispatch(0x8000, 2), WebAssembly.RuntimeError);
});

test('out-of-memory guest access traps', async () => {
  const { view, dispatch } = await createFixture();
  view.setUint32(0x8000 + CPU.esp, 0xfffc, true);
  assert.throws(() => dispatch(0x8000, 0), WebAssembly.RuntimeError);
});

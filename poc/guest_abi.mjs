// Original synthetic WebAssembly module, hand-encoded without game code.
// CPU offsets match the leading fields of nfsu2-web runtime/cpu.h at
// 31da468582c3de14fd6f4233831f62816e2df83d. This is NOT a full CPU model.
export const CPU = { eax: 0, esp: 16, eip: 32, bytes: 36 };

function uleb(value) {
  const out = [];
  do {
    const byte = value & 127;
    value >>>= 7;
    out.push(byte | (value ? 128 : 0));
  } while (value);
  return out;
}
const vec = items => [...uleb(items.length), ...items.flat()];
const str = value => {
  const bytes = [...new TextEncoder().encode(value)];
  return [...uleb(bytes.length), ...bytes];
};
const section = (id, data) => [id, ...uleb(data.length), ...data];
const local = i => [0x20, i];
const constant = n => [0x41, n]; // all constants below are positive and < 64
const load = offset => [0x28, 0, offset]; // align=1 allows unaligned guest words
const store = offset => [0x36, 0, offset];
const add = [0x6a];

function addBody(cleanup) {
  // void add(CPU *c): eax=arg1+arg2, eip=return slot, esp+=4(+8).
  const stack = () => [...local(0), ...load(CPU.esp)];
  const instructions = [
    ...local(0), ...stack(), ...load(4), ...stack(), ...load(8),
    ...add, ...store(CPU.eax),
    ...local(0), ...stack(), ...load(0), ...store(CPU.eip),
    ...local(0), ...stack(), ...constant(cleanup), ...add, ...store(CPU.esp),
    0x0b,
  ];
  const body = [0, ...instructions]; // no additional locals
  return [...uleb(body.length), ...body];
}

export function syntheticModule() {
  const types = vec([
    [0x60, ...vec([[0x7f]]), 0], // (i32 CPU*) -> void
    [0x60, ...vec([[0x7f], [0x7f]]), 0], // (CPU*, table index) -> void
  ]);
  const imports = vec([[...str('env'), ...str('memory'), 2, 3, 1, 2]]);
  const functions = vec([[0], [0], [1]]);
  const table = vec([[0x70, 0, 2]]);
  const exports = vec([[...str('dispatch'), 0, 2]]);
  const elements = vec([[0, ...constant(0), 0x0b, ...vec([[0], [1]])]]);
  const dispatch = [0, ...local(0), ...local(1), 0x11, 0, 0, 0x0b];
  const code = vec([addBody(4), addBody(12), [...uleb(dispatch.length), ...dispatch]]);
  return new Uint8Array([
    0, 97, 115, 109, 1, 0, 0, 0,
    ...section(1, types), ...section(2, imports), ...section(3, functions),
    ...section(4, table), ...section(7, exports), ...section(9, elements),
    ...section(10, code),
  ]);
}

export async function createFixture() {
  // Small shared memory fixture, not the production 640 MiB guest arena.
  const memory = new WebAssembly.Memory({ initial: 1, maximum: 2, shared: true });
  const { instance } = await WebAssembly.instantiate(syntheticModule(), { env: { memory } });
  const view = new DataView(memory.buffer);
  return { memory, view, dispatch: instance.exports.dispatch };
}

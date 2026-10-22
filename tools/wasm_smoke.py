#!/usr/bin/env python3
"""Compile the existing real-lifter synthetic fixture to freestanding Wasm.

No game input is used. This needs LLVM with wasm32 and wasm-ld, not a WASI SDK.
It runs the native smoke first, then reuses exactly its emitted synthetic bodies.
The declaration-only headers below are sufficient for this integer-only fixture;
they are not libc replacements for the runtime.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--cc", required=True, help="Wasm-capable clang")
    parser.add_argument("--native-cc", default="clang")
    parser.add_argument("--output-dir", type=Path, default=Path("out/wasm-smoke"))
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name("run_lifter_smoke.py")),
                    "--upstream", str(args.upstream.resolve()), "--cc", args.native_cc,
                    "--output-dir", str(output / "native")], check=True)
    source = (output / "native/synthetic.c").read_text()
    if source.count("uint8_t *g_mem;") != 1 or source.count("int main(void) {") != 1:
        raise RuntimeError("native fixture layout changed; review Wasm adaptation")
    source = source.replace("#include <stdio.h>\n#include <stdlib.h>\n", "")
    source = source.replace("uint8_t *g_mem;", "")
    source = source.split("int main(void) {")[0] + r'''
/* Host C stack/data live above GUEST_END, as in the upstream browser build. */
int smoke_check(void) {
    return check(sub_00001000, 17, 25, 42) |
           (check(sub_00001000, 0xffffffff, 2, 1) << 1) |
           (check(sub_00002000, 0, 0, 9) << 2) |
           (check(sub_00002000, 1, 0, 7) << 3);
}
void *memset(void *dst, int value, __SIZE_TYPE__ n) {
    unsigned char *p = dst;
    for (__SIZE_TYPE__ i = 0; i < n; ++i) p[i] = (unsigned char)value;
    return dst;
}
'''
    headers = output / "fixture-headers"
    headers.mkdir(exist_ok=True)
    (headers / "math.h").write_text(
        "double nearbyint(double); double floor(double); "
        "double ceil(double); double trunc(double);\n")
    (headers / "string.h").write_text(
        "typedef __SIZE_TYPE__ size_t;\n"
        "void *memcpy(void *, const void *, size_t);\n"
        "void *memset(void *, int, size_t);\n")
    path = output / "synthetic-wasm.c"
    path.write_text(source)
    wasm = output / "synthetic.wasm"
    command = [args.cc, "--target=wasm32-unknown-unknown", "-std=c11", "-O2",
               "-ffreestanding", "-fno-builtin", "-fno-delete-null-pointer-checks",
               "-nostdlib", "-isystem", str(headers), "-I",
               str(args.upstream.resolve() / "runtime"), str(path),
               "-Wl,--no-entry", "-Wl,--export=smoke_check", "-Wl,--export-memory",
               "-Wl,--global-base=671088640", "-Wl,--initial-memory=671350784",
               "-o", str(wasm)]
    subprocess.run(command, check=True)
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js is required to execute the compiled Wasm")
    subprocess.run([node, "--input-type=module", "-e", """
import { readFileSync } from 'node:fs';
const { instance } = await WebAssembly.instantiate(readFileSync(process.argv[1]), {});
const result = instance.exports.smoke_check();
if (result !== 15) throw new Error(`compiled Wasm check failed: ${result}`);
console.log('PASS: upstream lifted synthetic C -> Wasm, arithmetic/branches, CPU ABI');
console.log(`Wasm memory: ${instance.exports.memory.buffer.byteLength} bytes`);
""", str(wasm)], check=True)
    print(f"Synthetic Wasm: {wasm}")


if __name__ == "__main__":
    main()

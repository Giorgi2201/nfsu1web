#!/usr/bin/env python3
"""Focused paddq/psubq/unpck* check: synthetic native run plus real-body emission.

Uses authored x86 bytes for value semantics and the cached NFSU1 catalog for the
known SSE helpers that previously stopped on those mnemonics. Compiles emitted
bodies with the WASI SDK when --wasi is set. Not a browser or game validation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from catalog_bridge import attach_catalog, load_web_lifter
from lift_catalog import verify_emitter

_SUB_RE = re.compile(r"\bsub_([0-9a-f]{8})\b")
_TERMINATORS = frozenset(
    ("ret", "retf", "jmp", "int3", "hlt", "ud2", "iret", "iretd")
)

# paddq xmm0,xmm1; ret  /  psubq xmm0,xmm1; ret (0F FB, not 0F F9=psubw)
# unpcklpd xmm0,xmm1; ret  /  unpckhpd xmm0,xmm1; ret  /  paddq mm0,mm1; ret
SYNTH = {
    0x1000: bytes.fromhex("660fd4c1c3"),
    0x1010: bytes.fromhex("660ffbc1c3"),
    0x1020: bytes.fromhex("660f14c1c3"),
    0x1030: bytes.fromhex("660f15c1c3"),
    0x1040: bytes.fromhex("0fd4c1c3"),
}
SYNTH_MNEMONICS = {
    0x1000: "paddq", 0x1010: "psubq", 0x1020: "unpcklpd",
    0x1030: "unpckhpd", 0x1040: "paddq",
}

HARNESS = r'''
#include "cpu.h"
#include <stdio.h>
#include <string.h>
uint8_t *g_mem;
/* BODIES */

static int fail(const char *msg) {
    fputs(msg, stderr); fputc('\n', stderr); return 0;
}

int main(void) {
    CPU c = {0};
    g_mem = (uint8_t[0x1000]){0};
    c.xmm[0].u64[0] = UINT64_C(0xffffffffffffffff);
    c.xmm[0].u64[1] = UINT64_C(0xffffffffffffffff);
    c.xmm[1].u64[0] = 1; c.xmm[1].u64[1] = 2;
    sub_00001000(&c);
    if (c.xmm[0].u64[0] || c.xmm[0].u64[1] != 1)
        return fail("paddq xmm wrap");
    c.xmm[0].u64[0] = 0; c.xmm[0].u64[1] = 5;
    c.xmm[1].u64[0] = 1; c.xmm[1].u64[1] = 6;
    sub_00001010(&c);
    if (c.xmm[0].u64[0] != UINT64_C(0xffffffffffffffff) ||
        c.xmm[0].u64[1] != UINT64_C(0xffffffffffffffff))
        return fail("psubq xmm wrap");
    c.xmm[0].u64[0] = 0x1111; c.xmm[0].u64[1] = 0x2222;
    c.xmm[1].u64[0] = 0x3333; c.xmm[1].u64[1] = 0x4444;
    sub_00001020(&c);
    if (c.xmm[0].u64[0] != 0x1111 || c.xmm[0].u64[1] != 0x3333)
        return fail("unpcklpd");
    c.xmm[0].u64[0] = 0x1111; c.xmm[0].u64[1] = 0x2222;
    c.xmm[1].u64[0] = 0x3333; c.xmm[1].u64[1] = 0x4444;
    sub_00001030(&c);
    if (c.xmm[0].u64[0] != 0x2222 || c.xmm[0].u64[1] != 0x4444)
        return fail("unpckhpd");
    c.mm[0] = UINT64_C(0xffffffffffffffff); c.mm[1] = 1;
    sub_00001040(&c);
    if (c.mm[0]) return fail("paddq mm wrap");
    puts("PASS: paddq/psubq/unpck* synthetic native");
    return 0;
}
'''

SSE_HELPERS = (0x67cfa9, 0x67d026, 0x67d834, 0x67ded8, 0x67dede)


def lift_synth(module):
    base = min(SYNTH)
    end = max(address + len(code) for address, code in SYNTH.items())
    image = bytearray(end - base)
    for address, code in SYNTH.items():
        image[address - base:address - base + len(code)] = code
    catalog = {
        "image_base": base,
        "code_start": base,
        "code_end": end,
        "functions": [
            {
                "address": address,
                "calls_to": [],
                "jump_targets": [],
                "blocks": [[address, address + len(code), [], 1]],
            }
            for address, code in SYNTH.items()
        ],
    }
    lifter = module.RawLifter(bytes(image), base=base)
    attach_catalog(lifter, catalog, route_catalog_tails=True)
    bodies = []
    for address in SYNTH:
        lifter.traps = 0
        lifter.truncated = 0
        code, targets = lifter.lift(address)
        mnemonic = SYNTH_MNEMONICS[address]
        if lifter.traps or lifter.truncated or targets or "unsupported_insn(" in code:
            raise RuntimeError(f"synthetic 0x{address:x} lift failed")
        if mnemonic not in code or "_nfsu1_" not in code:
            raise RuntimeError(
                f"synthetic 0x{address:x} missed nfsu1 {mnemonic} emission"
            )
        bodies.append(code)
    return "\n\n".join(bodies)


def lift_helpers(module, image_path, catalog_path, profile_path):
    profile = json.loads(profile_path.read_text())
    image = image_path.read_bytes()
    digest = hashlib.sha256(image).hexdigest()
    if digest != profile["identity"]["sha256"]:
        raise ValueError("image SHA-256 does not match the selected profile")
    catalog = json.loads(catalog_path.read_text())
    lifter = module.Lifter(str(image_path.resolve()), comments=False)
    attach_catalog(lifter, catalog, route_catalog_tails=True)
    results, bodies = [], []
    for address in SSE_HELPERS:
        lifter.traps = 0
        lifter.truncated = 0
        try:
            decoded, _ = lifter.discover(address)
            for instructions in decoded.values():
                last = instructions[-1]
                if last.mnemonic not in _TERMINATORS:
                    fallthrough = last.address + last.size
                    if fallthrough not in decoded:
                        raise ValueError(
                            f"missing fallthrough block 0x{fallthrough:08x}"
                        )
            code, targets = lifter.lift(address)
            if lifter.traps or lifter.truncated:
                raise ValueError(
                    f"traps={lifter.traps}, truncated={lifter.truncated}"
                )
            if "unsupported_insn(" in code:
                raise ValueError("emitted unsupported instruction/branch site")
            bodies.append(code)
            results.append({
                "address": f"0x{address:08x}",
                "status": "ok",
                "unresolved_targets": [
                    f"0x{target:08x}" for target in sorted(targets)
                ],
            })
        except Exception as error:
            results.append({
                "address": f"0x{address:08x}",
                "status": "failed",
                "error": str(error),
            })
    return results, bodies


def run_native_smoke(compiler, upstream, output, bodies):
    source = output / "synthetic.c"
    executable = output / "synthetic-smoke"
    source.write_text(HARNESS.replace("/* BODIES */", bodies))
    subprocess.run(
        [
            compiler,
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Wno-unused-label",
            "-I",
            str(upstream / "runtime"),
            str(source),
            "-o",
            str(executable),
            "-lm",
        ],
        check=True,
    )
    subprocess.run([str(executable)], check=True)


def compile_wasi_object(wasi, upstream, output, bodies_c):
    clang = wasi.resolve() / "bin/clang"
    obj = output / "bodies.o"
    obj.unlink(missing_ok=True)
    command = [
        str(clang), "--target=wasm32-wasip1-threads", "-pthread", "-O3",
        "-msimd128", "-mbulk-memory", "-mnontrapping-fptoint", "-mtail-call",
        "-mexception-handling", "-mllvm", "-wasm-enable-sjlj",
        "-mllvm", "-wasm-use-legacy-eh=false",
        "-D_WASI_EMULATED_MMAN", "-D_WASI_EMULATED_SIGNAL",
        "-D_WASI_EMULATED_PROCESS_CLOCKS",
        "-fno-delete-null-pointer-checks",
        "-include", str(upstream / "runtime/web/compat/wasm_plat.h"),
        "-I", str(upstream / "runtime/web/compat"),
        "-I", str(upstream / "runtime"), "-I", str(output),
        "-DNFSU2_GUEST_OBJ", "-Wno-unused-label", "-Wno-parentheses-equality",
        "-c", str(bodies_c), "-o", str(obj),
    ]
    result = subprocess.run(command, text=True, capture_output=True)
    (output / "bodies-compile.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        sys.stderr.write(result.stderr or result.stdout)
        raise SystemExit(result.returncode)
    return obj


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--image", type=Path,
                        default=Path("work/analysis/Speed.analysis.exe"))
    parser.add_argument("--catalog", type=Path,
                        default=Path("work/analysis/catalog.json"))
    parser.add_argument("--profile", type=Path,
                        default=Path("profiles/nfsu1-pc.json"))
    parser.add_argument("--output-dir", type=Path,
                        default=Path("out/simd-integration"))
    parser.add_argument("--cc", default="clang")
    parser.add_argument("--wasi", type=Path,
                        help="WASI SDK root; compile bodies.o when set")
    args = parser.parse_args()
    upstream = args.upstream.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    verify_emitter(upstream)
    # X87PC is read at lift.py import time; FLAGOPT is read per lift.
    os.environ["FLAGOPT"] = "0"
    os.environ["X87PC"] = "1"
    module = load_web_lifter(upstream)
    run_native_smoke(args.cc, upstream, output, lift_synth(module))

    results, bodies = lift_helpers(module, args.image, args.catalog, args.profile)
    failed = [result for result in results if result["status"] != "ok"]
    report = {
        "kind": "simd-helper-emission",
        "helpers": results,
        "emitted": len(bodies),
        "failed": len(failed),
    }
    (output / "lift-report.json").write_text(json.dumps(report, indent=2) + "\n")
    if failed:
        print(json.dumps(report, indent=2))
        raise SystemExit(1)
    joined = "\n\n".join(bodies)
    referenced = {int(m.group(1), 16) for m in _SUB_RE.finditer(joined)}
    decls = [
        "#ifndef NFSU1_SIMD_DECLS_H",
        "#define NFSU1_SIMD_DECLS_H",
        '#include "cpu.h"',
    ]
    decls.extend(
        f"void sub_{address:08x}(CPU *);" for address in sorted(referenced)
    )
    decls.append("#endif")
    (output / "decls.h").write_text("\n".join(decls) + "\n")
    bodies_c = output / "bodies.c"
    bodies_c.write_text(
        "/* GAME-DERIVED: local output, DO NOT DISTRIBUTE. */\n"
        '#include "cpu.h"\n#include "decls.h"\n#include <math.h>\n\n'
        + joined + "\n")
    print(f"Emitted {len(bodies)} SSE helpers -> {bodies_c}")

    if args.wasi:
        obj = compile_wasi_object(args.wasi, upstream, output, bodies_c)
        print(f"WASI object: {obj}")
        report["wasi_object"] = str(obj)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

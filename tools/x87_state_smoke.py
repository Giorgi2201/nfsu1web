#!/usr/bin/env python3
"""Focused fnsave/frstor check: synthetic native run plus real-body emission.

Uses authored x86 bytes for the 108-byte protected-mode image round trip and
reset, then re-lifts the catalog entries that share the entry-reachable
0x6738ed helper. Optional WASI object compile. Not a browser or game validation.
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

# fnsave [ecx]; ret  /  frstor [ecx]; ret
SYNTH = {
    0x1000: bytes.fromhex("dd31c3"),
    0x1010: bytes.fromhex("dd21c3"),
}
SYNTH_MARKERS = {
    0x1000: ("fnsave",),
    0x1010: ("frstor",),
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
    c.ecx = 0x100;
    c.top = 6;
    c.fcw = 0x027f;
    c.fsw = 0x0400;
    c.st[6] = 1.5;
    c.st[7] = -2.25;
    c.st[0] = 8.0;
    sub_00001000(&c);
    if (c.top != 0 || c.fcw != 0x037f || c.fsw != 0)
        return fail("fnsave reset");
    for (int i = 0; i < 8; i++)
        if (c.st[i] != 0.0) return fail("fnsave cleared st");
    uint16_t cw, sw, tw;
    memcpy(&cw, g_mem + 0x100, 2);
    memcpy(&sw, g_mem + 0x104, 2);
    memcpy(&tw, g_mem + 0x108, 2);
    if (cw != 0x027f || tw != 0 || ((sw >> 11) & 7) != 6)
        return fail("fnsave header");
    if (f80_load(g_mem + 0x100 + 28) != 1.5 ||
        f80_load(g_mem + 0x100 + 38) != -2.25 ||
        f80_load(g_mem + 0x100 + 48) != 8.0)
        return fail("fnsave stack order");
    memset(&c, 0, sizeof c);
    c.ecx = 0x100;
    c.fcw = 0x037f;
    sub_00001010(&c);
    if (c.top != 6 || c.fcw != 0x027f || (c.fsw & 0x0400) == 0)
        return fail("frstor env");
    if (c.st[6] != 1.5 || c.st[7] != -2.25 || c.st[0] != 8.0)
        return fail("frstor st");
    puts("PASS: fnsave/frstor synthetic native");
    return 0;
}
'''

# start + aliases that share fnsave/frstor at [ecx+8]
X87_HELPERS = (0x6738ed, 0x673984, 0x6739b0, 0x6739b4, 0x6739ca)


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
        if lifter.traps or lifter.truncated or targets or "unsupported_insn(" in code:
            raise RuntimeError(f"synthetic 0x{address:x} lift failed")
        if "_nfsu1_" not in code or any(
                marker not in code for marker in SYNTH_MARKERS[address]):
            raise RuntimeError(
                f"synthetic 0x{address:x} missed nfsu1 x87 emission"
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
    for address in X87_HELPERS:
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
            if "_nfsu1_p" not in code or "f80_store" not in code or "f80_load" not in code:
                raise ValueError("expected nfsu1 fnsave/frstor emission")
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
                "error": f"{type(error).__name__}: {error}",
            })
    return results, bodies


def run_native_smoke(compiler, upstream, output, bodies):
    source = output / "synthetic.c"
    executable = output / "synthetic-smoke"
    source.write_text(HARNESS.replace("/* BODIES */", bodies))
    subprocess.run(
        [
            compiler, "-std=c11", "-O2", "-Wall", "-Wextra",
            "-Wno-unused-label", "-I", str(upstream / "runtime"),
            str(source), "-o", str(executable), "-lm",
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
                        default=Path("out/x87-state"))
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
        "kind": "x87-state-helper-emission",
        "helpers": results,
        "emitted": len(bodies),
        "failed": len(failed),
    }
    (output / "lift-report.json").write_text(json.dumps(report, indent=2) + "\n")
    if failed:
        print(json.dumps(report, indent=2))
        raise SystemExit(1)
    joined = "\n\n".join(bodies)
    referenced = {int(match.group(1), 16) for match in _SUB_RE.finditer(joined)}
    decls = [
        "#ifndef NFSU1_X87_DECLS_H",
        "#define NFSU1_X87_DECLS_H",
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
    print(f"Emitted {len(bodies)} x87 helpers -> {bodies_c}")

    if args.wasi:
        obj = compile_wasi_object(args.wasi, upstream, output, bodies_c)
        print(f"WASI object: {obj}")
        report["wasi_object"] = str(obj)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Lift original synthetic x86, compile against upstream CPU ABI, execute natively.

No game binary or game-derived code is read. This is a focused integration
check, not a new general test framework or proof of Wasm/browser compatibility.
"""
import argparse
from pathlib import Path
import subprocess

from catalog_bridge import attach_catalog, load_web_lifter, upstream_smoke


HARNESS = r'''
#include "cpu.h"
#include <stdio.h>
#include <stdlib.h>
uint8_t *g_mem;

/* GENERATED_SYNTHETIC_BODIES */

static int check(void (*fn)(CPU *), uint32_t a, uint32_t b, uint32_t expected) {
    CPU cpu = {0};
    cpu.esp = 0x3000;
    cpu.ecx = 0xcafe;
    MR32(cpu.esp) = 0x12345678;
    MR32(cpu.esp + 4) = a;
    MR32(cpu.esp + 8) = b;
    fn(&cpu);
    return cpu.eax == expected && cpu.esp == 0x3004 &&
           cpu.eip == 0x12345678 && cpu.ecx == 0xcafe;
}

int main(void) {
    g_mem = calloc(1, 0x4000);
    if (!g_mem) return 2;
    int ok = check(sub_00001000, 17, 25, 42) &&
             check(sub_00001000, 0xffffffff, 2, 1) &&
             check(sub_00002000, 0, 0, 9) &&
             check(sub_00002000, 1, 0, 7);
    free(g_mem);
    if (!ok) { fputs("synthetic lifted-code smoke failed\n", stderr); return 1; }
    puts("PASS: real upstream lift, arithmetic/wraparound, both branch paths, CPU ABI");
    return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("out/lifter-smoke"))
    parser.add_argument("--cc", default="clang")
    args = parser.parse_args()
    checkout = args.upstream.resolve()
    arithmetic = upstream_smoke(checkout)
    module = load_web_lifter(checkout)
    # Authored fixture: mov eax,[esp+4]; cmp eax,0; je zero;
    # mov eax,7; ret; padding; zero: mov eax,9; ret.
    data = bytes.fromhex("8b44240483f8007408b807000000c39090b809000000c3")
    catalog = {
        "image_base": 0x2000, "code_start": 0x2000, "code_end": 0x2017,
        "functions": [{"address": 0x2000, "calls_to": [],
                       "jump_targets": [0x2011], "blocks": [
                           [0x2000, 0x2009, [0x2009, 0x2011], 0],
                           [0x2009, 0x200f, [], 1],
                           [0x2011, 0x2017, [], 1]]}],
    }
    lifter = module.RawLifter(data, base=0x2000)
    attach_catalog(lifter, catalog)
    branch, targets = lifter.lift(0x2000)
    if lifter.traps or getattr(lifter, "truncated", 0) or targets:
        raise RuntimeError("synthetic branch lift has traps or unresolved edges")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = output / "synthetic.c"
    executable = output / "synthetic-smoke"
    source.write_text(HARNESS.replace("/* GENERATED_SYNTHETIC_BODIES */",
                                      arithmetic + "\n" + branch))
    command = [args.cc, "-std=c11", "-O2", "-Wall", "-Wextra",
               "-Wno-unused-label", "-I", str(checkout / "runtime"),
               str(source), "-o", str(executable), "-lm"]
    subprocess.run(command, check=True)
    subprocess.run([str(executable)], check=True)
    print(f"Synthetic C: {source}")


if __name__ == "__main__":
    main()

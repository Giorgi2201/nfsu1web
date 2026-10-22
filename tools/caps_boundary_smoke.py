#!/usr/bin/env python3
"""Check the actual upstream fill_caps writer against a 304-byte D3DCAPS9.

Microsoft layout: https://learn.microsoft.com/en-us/windows/win32/api/d3d9caps/ns-d3d9caps-d3dcaps9
This native synthetic boundary check reads no game data and does not validate
capability values or game/browser compatibility.
"""
import argparse
from pathlib import Path
import subprocess


HARNESS = r'''
#include "cpu.h"
#include <stdio.h>
#include <stdlib.h>

uint8_t *g_mem;
void mem_commit(uint32_t address, uint32_t size) {
    (void)address;
    (void)size;
}
#define ENVC(name) ((const char *)0)

/* ACTUAL_FILL_CAPS */

int main(void) {
    enum { TOTAL = 1024, TARGET = 256, CAPS_SIZE = 304 };
    g_mem = malloc(TOTAL);
    if (!g_mem) return 2;
    memset(g_mem, 0xa5, TARGET);
    memset(g_mem + TARGET, 0xcc, CAPS_SIZE);
    memset(g_mem + TARGET + CAPS_SIZE, 0x5a, TOTAL - TARGET - CAPS_SIZE);
    fill_caps(TARGET);
    int failed = 0;
    for (unsigned i = 0; i < TOTAL; i++) {
        if (i >= TARGET && i < TARGET + CAPS_SIZE) continue;
        unsigned expected = i < TARGET ? 0xa5 : 0x5a;
        if (g_mem[i] != expected) {
            fprintf(stderr, "FAIL: fill_caps changed canary at target%+d: %02x != %02x\n",
                    (int)i - TARGET, g_mem[i], expected);
            failed = 1;
            break;
        }
    }
    if (MR32(TARGET) != 1) {
        fputs("FAIL: fill_caps did not populate the target\n", stderr);
        failed = 1;
    }
    free(g_mem);
    if (failed) return 1;
    puts("PASS: actual fill_caps preserves all bytes around 304-byte D3DCAPS9, including next 32 bytes");
    return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--source", type=Path,
                        help="alternate com.c for checking an unmodified baseline")
    parser.add_argument("--output-dir", type=Path, default=Path("out/caps-boundary"))
    parser.add_argument("--cc", default="clang")
    args = parser.parse_args()
    checkout = args.upstream.resolve()
    source = args.source or checkout / "runtime/com.c"
    contents = source.read_text()
    signature = "static void fill_caps(uint32_t p){"
    start = contents.rfind(signature)
    if start < 0:
        raise ValueError(f"fill_caps definition not found in {source}")
    # In this pinned runtime fill_caps is the last function. Keep its exact
    # implementation; fail visibly if the expected extraction boundary changes.
    function = contents[start:].strip()
    if not function.endswith("}") or function.count("{") != function.count("}"):
        raise ValueError("expected a complete fill_caps definition at end of source")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    harness = output / "caps-boundary.c"
    executable = output / "caps-boundary"
    harness.write_text(HARNESS.replace("/* ACTUAL_FILL_CAPS */", function))
    subprocess.run([args.cc, "-std=c11", "-O1", "-Wall", "-Wextra",
                    "-I", str(checkout / "runtime"), str(harness),
                    "-o", str(executable), "-lm"], check=True)
    return subprocess.run([str(executable)], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())

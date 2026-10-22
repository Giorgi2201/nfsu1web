#!/usr/bin/env python3
"""Focused native smoke for NFSU1 loaded-bank content dispatch."""
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_RUNTIME = ROOT / "work/upstream/nfsu2-web/runtime"

HARNESS = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "nfs_abk.h"

#undef assert
#define assert(expr) do { if (!(expr)) { \
    fprintf(stderr, "ABK smoke assertion failed: %s\\n", #expr); \
    return __LINE__; \
} } while (0)

uint8_t *g_mem;
uint8_t g_cbits[1u << 15];

static const uint8_t raw_code[] = {0xe8, 0, 0, 0, 0, 0xc3, 0xc3};
static const uint8_t other_code[] = {0xc3, 0xc3};
static const uint16_t relocs[] = {1};
const nfs_abk_block_t nfs_abk_blocks[] = {
    {0x1000u, raw_code, sizeof raw_code, relocs, 1},
    {0x2000u, other_code, sizeof other_code, NULL, 0}
};
const unsigned nfs_abk_block_count = 2;

static int bad;
static void nested(CPU *c) {
    if (nfsu1_abk_return_address(0x1006u) != 0x3006u) bad = 1;
    c->ebx++;
}
static void other_nested(CPU *c) {
    if (nfsu1_abk_return_address(0x2001u) != 0x5001u) bad = 1;
    c->edx++;
}
static void outer(CPU *c) {
    if (nfsu1_abk_return_address(0x1005u) != 0x3005u) bad = 1;
    if (!nfsu1_abk_dispatch(c, 0x3006u)) bad = 1;
    if (nfsu1_abk_return_address(0x1005u) != 0x3005u) bad = 1;
    if (!nfsu1_abk_dispatch(c, 0x1006u)) bad = 1; /* canonical same-block call */
    if (nfsu1_abk_dispatch(c, 0x2000u)) bad = 1; /* reject other-block canonical */
    if (!nfsu1_abk_dispatch(c, 0x5000u)) bad = 1; /* loaded cross-block callback */
    if (nfsu1_abk_return_address(0x1005u) != 0x3005u) bad = 1;
    c->eax++;
}
const Nfsu1AbkFunction nfsu1_abk_functions[] = {
    {0x1000u, outer}, {0x1006u, nested}, {0x2000u, other_nested}
};
const unsigned nfsu1_abk_function_count = 3;
const uint32_t nfsu1_abk_call_targets[] = {0x00401000u};
const unsigned nfsu1_abk_call_target_count = 1;

static void store_disp(uint32_t at, int32_t value) {
    uint32_t bits = (uint32_t)value;
    g_mem[at] = (uint8_t)bits;
    g_mem[at + 1] = (uint8_t)(bits >> 8);
    g_mem[at + 2] = (uint8_t)(bits >> 16);
    g_mem[at + 3] = (uint8_t)(bits >> 24);
}

int main(void) {
    CPU cpu = {0};
    g_mem = calloc(0x8000u, 1);
    assert(g_mem);
    g_cbits[0] = 3; /* guest pages [0, 0x8000) committed */
    memcpy(g_mem + 0x3000u, raw_code, sizeof raw_code);
    store_disp(0x3001u, (int32_t)(0x00401000u - 0x3005u));
    memcpy(g_mem + 0x5000u, other_code, sizeof other_code);

    assert(nfsu1_abk_dispatch(&cpu, 0x3000u));
    assert(cpu.eax == 1 && cpu.ebx == 2 && cpu.edx == 1 && bad == 0);
    assert(nfsu1_abk_return_address(0x1005u) == 0x1005u);

    g_mem[0x3005u] = 0x90;
    assert(!nfsu1_abk_dispatch(&cpu, 0x3000u));
    g_mem[0x3005u] = 0xc3;

    store_disp(0x3001u, (int32_t)(0x00401001u - 0x3005u));
    assert(!nfsu1_abk_dispatch(&cpu, 0x3000u));
    store_disp(0x3001u, (int32_t)(0x00401000u - 0x3005u));

    g_cbits[0] = 0;
    assert(!nfsu1_abk_dispatch(&cpu, 0x3000u));
    free(g_mem);
    return 0;
}
'''


def main():
    compiler = shutil.which("clang") or shutil.which("cc")
    if not compiler:
        raise SystemExit("clang or cc is required")
    if not (UPSTREAM_RUNTIME / "cpu.h").is_file():
        raise SystemExit("pinned runtime checkout is missing; see docs/toolchain.md")
    with tempfile.TemporaryDirectory(prefix="nfsu1-abk-smoke-") as tmp:
        source = Path(tmp) / "abk_smoke.c"
        binary = Path(tmp) / "abk_smoke"
        source.write_text(HARNESS)
        subprocess.run([
            compiler, "-std=c11", "-O2",
            "-I", str(UPSTREAM_RUNTIME), "-I", str(ROOT / "runtime"),
            str(ROOT / "runtime/nfsu1_abk.c"), str(source), "-o", str(binary),
        ], check=True)
        subprocess.run([str(binary)], check=True)
    print("NFSU1 ABK content dispatch smoke passed")


if __name__ == "__main__":
    main()

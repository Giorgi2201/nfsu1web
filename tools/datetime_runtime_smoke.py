#!/usr/bin/env python3
"""Compile and run focused synthetic tests for the NFSU1 date/time HLE.

The native build is always run. If a WASI SDK is present (or passed with
--wasi-sdk), the same harness is also compiled to Wasm and run with Node's
WASI host. No game executable, assets, or generated game code are used.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_RUNTIME = ROOT / "work/upstream/nfsu2-web/runtime"
GUEST_END = 0x28000000

HARNESS = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cpu.h"

int nfsu1_win32_call(CPU *, const char *, uint32_t *);
void win32_set_last_error(CPU *, uint32_t);

#ifndef __wasm__
uint8_t *g_mem;
#endif
uint8_t g_cbits[1u << 15];

static CPU *error_cpus[8];
static uint32_t errors[8];
static unsigned error_count;

void win32_set_last_error(CPU *cpu, uint32_t error) {
    unsigned i;
    for (i = 0; i < error_count; ++i) {
        if (error_cpus[i] == cpu) {
            errors[i] = error;
            return;
        }
    }
    if (error_count < 8) {
        error_cpus[error_count] = cpu;
        errors[error_count++] = error;
    }
}

static uint32_t last_error(CPU *cpu) {
    unsigned i;
    for (i = 0; i < error_count; ++i)
        if (error_cpus[i] == cpu) return errors[i];
    return 0;
}

void mem_commit(uint32_t address, uint32_t size) {
    uint32_t first, last, page;
    if (!size) return;
    first = address >> 14;
    last = (address + size - 1u) >> 14;
    for (page = first; page <= last; ++page)
        g_cbits[page >> 3] |= (uint8_t)(1u << (page & 7u));
}

static void put32(uint32_t address, uint32_t value) {
    g_mem[address] = (uint8_t)value;
    g_mem[address + 1] = (uint8_t)(value >> 8);
    g_mem[address + 2] = (uint8_t)(value >> 16);
    g_mem[address + 3] = (uint8_t)(value >> 24);
}

static void put16(uint32_t address, uint16_t value) {
    g_mem[address] = (uint8_t)value;
    g_mem[address + 1] = (uint8_t)(value >> 8);
}

static void put_string(uint32_t address, const char *value) {
    size_t n = strlen(value) + 1;
    mem_commit(address, (uint32_t)n);
    memcpy(g_mem + address, value, n);
}

static uint32_t get32(uint32_t address) {
    return (uint32_t)g_mem[address] |
           ((uint32_t)g_mem[address + 1] << 8) |
           ((uint32_t)g_mem[address + 2] << 16) |
           ((uint32_t)g_mem[address + 3] << 24);
}

static void set_system_time(uint32_t address) {
    memset(g_mem + address, 0, 16);
    put16(address, 2026);       /* wYear */
    put16(address + 2, 10);     /* wMonth */
    put16(address + 4, 4);      /* wDayOfWeek */
    put16(address + 6, 22);     /* wDay */
    put16(address + 8, 15);     /* wHour */
    put16(address + 10, 4);     /* wMinute */
    put16(address + 12, 5);     /* wSecond */
}

static uint32_t call6(CPU *cpu, const char *name, uint32_t a0, uint32_t a1,
                      uint32_t a2, uint32_t a3, uint32_t a4, uint32_t a5) {
    uint32_t result = 0xdeadbeefu;
    put32(cpu->esp, a0);
    put32(cpu->esp + 4, a1);
    put32(cpu->esp + 8, a2);
    put32(cpu->esp + 12, a3);
    put32(cpu->esp + 16, a4);
    put32(cpu->esp + 20, a5);
    if (!nfsu1_win32_call(cpu, name, &result)) return 0xbad00001u;
    return result;
}

static int check(int condition, const char *label) {
    if (condition) return 0;
    fprintf(stderr, "datetime smoke failed: %s\n", label);
    return 1;
}

int main(void) {
    CPU cpu = {0}, other = {0};
    const uint32_t stack = 0x1000, system_time = 0x2000;
    const uint32_t date_format = 0x2100, time_format = 0x2140;
    const uint32_t out = 0x2200;
    uint32_t n, failed = 0;

#ifndef __wasm__
    g_mem = (uint8_t *)calloc(0x8000u, 1);
    if (!g_mem) return 2;
#endif
    mem_commit(0, 0x8000u);
    cpu.esp = stack;
    other.esp = stack + 0x40;
    set_system_time(system_time);
    put_string(date_format, "yyyy-MM-dd");
    put_string(time_format, "HH':'mm");

    n = call6(&cpu, "GetDateFormatA", 0x0800u, 1u, system_time,
              0, 0, 0);
    failed |= check(n == sizeof("10/22/2026"), "date size query includes NUL");
    n = call6(&cpu, "GetDateFormatA", 0x0800u, 1u, system_time,
              0, out, 12);
    failed |= check(n == sizeof("10/22/2026") &&
                    strcmp((const char *)g_mem + out, "10/22/2026") == 0,
                    "DATE_SHORTDATE formatting");

    n = call6(&cpu, "GetTimeFormatA", 0x0800u, 2u, system_time,
              0, 0, 0);
    failed |= check(n == sizeof("3:04 PM"), "time size query includes NUL");
    memset(g_mem + out, 0xa5, 32);
    n = call6(&cpu, "GetTimeFormatA", 0x0800u, 2u, system_time,
              0, out, 12);
    failed |= check(n == sizeof("3:04 PM") &&
                    strcmp((const char *)g_mem + out, "3:04 PM") == 0,
                    "TIME_NOSECONDS formatting");

    /* Custom patterns and the supported locale aliases stay deterministic. */
    n = call6(&cpu, "GetDateFormatA", 0x0409u, 0, system_time,
              date_format, out, 32);
    failed |= check(n == sizeof("2026-10-22") &&
                    strcmp((const char *)g_mem + out, "2026-10-22") == 0,
                    "custom yyyy-MM-dd pattern");
    n = call6(&cpu, "GetTimeFormatA", 0x0400u, 2u, system_time,
              time_format, out, 32);
    failed |= check(n == sizeof("15:04") &&
                    strcmp((const char *)g_mem + out, "15:04") == 0,
                    "custom time pattern and user-default locale");

    /* A short buffer must stay untouched and set only the calling CPU error. */
    memset(g_mem + out, 0xa5, 32);
    win32_set_last_error(&cpu, 0xfeedu);
    n = call6(&cpu, "GetDateFormatA", 0x0800u, 1u, system_time,
              0, out, (uint32_t)sizeof("10/22/2026") - 1u);
    failed |= check(n == 0, "short date buffer returns failure");
    failed |= check(g_mem[out] == 0xa5 && g_mem[out + 1] == 0xa5 &&
                    g_mem[out + 10] == 0xa5, "short buffer preserves canaries");
    failed |= check(last_error(&cpu) == 122 && last_error(&other) == 0,
                    "last error is associated with calling CPU");

    /* A NULL SYSTEMTIME requests the current clock; check a valid NUL string. */
    n = call6(&other, "GetDateFormatA", 0x0800u, 1u, 0,
              0, out, 12);
    failed |= check(n > 1 && g_mem[out + n - 1] == 0,
                    "NULL SYSTEMTIME uses current clock");
    n = call6(&cpu, "GetDateFormatA", 0x0800u, 16u, system_time,
              date_format, out, 32);
    failed |= check(n == 0 && last_error(&cpu) == 1004,
                    "invalid flags set ERROR_INVALID_FLAGS");

    if (!failed) puts("PASS: synthetic NFSU1 date/time native runtime smoke");
#ifndef __wasm__
    free(g_mem);
#endif
    return failed ? 1 : 0;
}
'''


def find_wasi_sdk(explicit):
    if explicit:
        return explicit.resolve()
    candidates = sorted((ROOT / "work/toolchain").glob("wasi-sdk-*"))
    for candidate in candidates:
        if (candidate / "bin/clang").is_file():
            return candidate
    return None


def run_wasi(wasi_sdk, source, output_dir, node):
    compiler = wasi_sdk / "bin/clang"
    wasm = output_dir / "datetime-runtime-smoke.wasm"
    subprocess.run([
        str(compiler), "--target=wasm32-wasip1-threads", "-pthread",
        "-O2", "-fno-delete-null-pointer-checks", "-include",
        str(UPSTREAM_RUNTIME / "web/compat/wasm_plat.h"),
        "-I", str(UPSTREAM_RUNTIME / "web/compat"), "-I", str(UPSTREAM_RUNTIME),
        "-I", str(ROOT / "runtime"), str(ROOT / "runtime/nfsu1_win32.c"),
        str(UPSTREAM_RUNTIME / "web/tz.c"), str(source),
        f"-Wl,--global-base={GUEST_END}",
        f"-Wl,--initial-memory={GUEST_END + 0x100000}",
        "-Wl,--max-memory=2147483648", "-o", str(wasm),
    ], check=True)
    runner = r'''
import fs from 'node:fs';
import { WASI } from 'node:wasi';
const wasi = new WASI({ version: 'preview1', args: [], env: {}, preopens: {} });
const { instance } = await WebAssembly.instantiate(fs.readFileSync(process.argv[1]), {
  wasi_snapshot_preview1: wasi.wasiImport,
});
wasi.start(instance);
'''
    subprocess.run([node, "--input-type=module", "-e", runner, str(wasm)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=ROOT / "work/upstream/nfsu2-web",
                        help="pinned nfsu2-web source snapshot")
    parser.add_argument("--native-cc", default="clang")
    parser.add_argument("--wasi-sdk", type=Path,
                        help="WASI SDK root; auto-detected under work/toolchain if omitted")
    parser.add_argument("--output-dir", type=Path,
                        default=Path("out/datetime-runtime-smoke"))
    args = parser.parse_args()

    global UPSTREAM_RUNTIME
    UPSTREAM_RUNTIME = args.upstream.resolve() / "runtime"
    if not (UPSTREAM_RUNTIME / "cpu.h").is_file():
        parser.error("upstream runtime/cpu.h is missing; fetch the pinned source snapshot first")
    node = shutil.which("node")
    if not node:
        parser.error("Node.js is required for the optional compiled-Wasm run")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    wasi_sdk = find_wasi_sdk(args.wasi_sdk)

    with tempfile.TemporaryDirectory(prefix="nfsu1-datetime-smoke-") as tmp:
        source = Path(tmp) / "datetime_runtime_smoke.c"
        native = Path(tmp) / "datetime_runtime_smoke"
        source.write_text(HARNESS)
        subprocess.run([
            args.native_cc, "-std=c11", "-O2", "-I", str(UPSTREAM_RUNTIME),
            "-I", str(ROOT / "runtime"), str(ROOT / "runtime/nfsu1_win32.c"),
            str(source), "-o", str(native),
        ], check=True)
        subprocess.run([str(native)], check=True)
        if wasi_sdk:
            run_wasi(wasi_sdk, source, output, node)
            print(f"Compiled Wasm smoke: {output / 'datetime-runtime-smoke.wasm'}")
        else:
            print("WASI SDK not found; compiled-Wasm smoke skipped")


if __name__ == "__main__":
    main()

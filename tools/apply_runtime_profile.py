#!/usr/bin/env python3
"""Apply a reversible NFSU1 bring-up overlay to the pinned web runtime.

Pinned upstream runtime excerpts are used under the MIT license in
patches/nfsu2-web.LICENSE (copyright 2026 th0mk).
Only hand-written runtime files are touched. No game input or generated game
code is read. Re-run is idempotent; --revert restores the original files.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "31da468582c3de14fd6f4233831f62816e2df83d"
PINNED = {
    "runtime/cpu.h": "7a6d17d2f76f8f096b3c9e13bc18b42a925e2529",
    "runtime/dispatch.c": "f1e586523c71773d5146b9dd3455efbea3474a18",
    "runtime/web/main_web.c": "df20ec27b2cde6b049feb8be29e0adbef3a6d0f8",
    "runtime/win32.c": "267984c79ac5ec9dfc0aeee98689e4c3abded572",
    "runtime/web/gcpu.c": "eb39bed5cd7cc86d7b08bd45a6a46f2848a6bf17",
    "runtime/com.c": "f32cbf8b5d568b8fcc206ee253397d52bd6ec18a",
    "runtime/dinput_pad.c": "bfa162cdf129e14f652fc5cf1ff85adefed0e45d",
}


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f"expected one anchored occurrence: {old[:70]!r}")
    return source.replace(old, new, 1)


def edits(name, source):
    if name == "runtime/cpu.h":
        source = replace(source, '#include <math.h>', '#include "nfsu1_profile.h"\n#include <math.h>')
        source = replace(source, '#define DISPATCH_TEXT_BASE 0x00401000u\n#define DISPATCH_TEXT_SIZE 0x00381af1u', '/* Dispatch bounds come from nfsu1_profile.h. */')
        source = replace(source, 'va >= 0x00401000u && va < 0x00401000u + (3676913u)', 'va - DISPATCH_TEXT_BASE < DISPATCH_TEXT_SIZE')
        return replace(source, 'g_cov[va - 0x00401000u]++;', 'g_cov[va - DISPATCH_TEXT_BASE]++;')
    if name == "runtime/dispatch.c":
        source = replace(source, '    extern int g_efx_stat;\n    return (g_icall_want && a == g_icall_want) || (g_efx_stat && a - 0x650000u < 0x40000u);', '    return g_icall_want && a == g_icall_want;')
        source = replace(source, '{ extern int g_efx_stat; const char *e = getenv("ICALL");', '{ const char *e = getenv("ICALL");')
        source = replace(source, 'g_diag = g_icall_want || g_efx_stat;', 'g_diag = g_icall_want != 0;')
        begin = source.index('    /* EFXSTAT: inventory')
        end = source.index('    uint32_t off = addr - TEXT_BASE;', begin)
        source = source[:begin] + '    /* NFSU2 effect-address diagnostics and epoch writes disabled. */\n' + source[end:]
        begin = source.index('    /* No lifted counterpart.')
        end = source.index('\nvoid cpuid_shim', begin)
        source = source[:begin] + '''#ifdef NFSU1_HAS_ABK
    { extern int nfsu1_abk_dispatch(CPU *, uint32_t);
      if (nfsu1_abk_dispatch(c, addr)) return; }
#endif
    g_stat_indirect_miss++;
    fprintf(stderr, "NFSU1 unresolved dispatch: target=%08x eip=%08x esp=%08x\\n",
            addr, c->eip, c->esp);
    { extern void nfsu1_diagnostics_dispatch(CPU *, uint32_t);
      nfsu1_diagnostics_dispatch(c, addr); }
    /* No interpreter fallback and no fabricated guest return value. */
    abort();
}

void unsupported_insn(CPU *c, uint32_t addr, const char *mn){
    g_stat_unsupported++;
    fprintf(stderr, "NFSU1 unsupported instruction: %08x %s eip=%08x\\n",
            addr, mn ? mn : "?", c->eip);
    abort();
}
''' + source[end:]
        source = replace(source, '    genexec_report();', '    /* Generic generated-code interpretation is disabled for NFSU1. */')
        # Out-of-range catalog entries must not silently vanish from dispatch.
        source = replace(source, '    patch_apply();\n    fprintf(stderr, "dispatch:', '    if (dup || oob){ fprintf(stderr, "NFSU1 invalid dispatch catalog\\n"); abort(); }\n    patch_apply();\n    fprintf(stderr, "dispatch:')
        return source
    if name == "runtime/web/main_web.c":
        begin = source.index('    fprintf(stderr, "\\n  CRT heap:')
        end = source.index('    dispatch_report();', begin)
        source = source[:begin] + '    com_report(); win32_report();\n' + source[end:]
        source = replace(source, 'sub_0075bcc7(&cpu);', 'NFSU1_ENTRY_POINT(&cpu);')
        source = replace(source, '"/data/SPEED2.EXE"', 'NFSU1_EXE_PATH')
        source = replace(source, '    { extern void autotest_early(void); autotest_early(); }   /* NFSU2_LOG, NFSU2_TIMEOUT */', '''#ifndef NFSU1_ALLOW_EXPERIMENTAL_BOOT
    fprintf(stderr, "NFSU1 runtime overlay installed; full runtime audit and catalog build required.\\n");
    return 1;
#endif''')
        for line in source.splitlines():
            if 'autotest_init();' in line or 'stackprobe_on();' in line:
                source = replace(source, line + '\n', '')
        source = source.replace('NFSU2_SAVEDIR', 'NFSU1_SAVEDIR').replace('NFSU2_READONLY_DATA', 'NFSU1_READONLY_DATA')
        source = replace(source, '    fileio_set_root(exe);', '    fileio_set_root(exe);\n    fileio_set_write_root("/save/nfsu1");\n    fileio_set_readonly_root(1);')
        source = replace(source, '    dispatch_init(); win32_init();',
                         '    dispatch_init(); win32_init();\n'
                         '    { extern void nfsu1_diagnostics_start(void); nfsu1_diagnostics_start(); }')
        source = replace(source, '    MR32(PEB_BASE+0x08) = 0x00400000u;', '    MR32(PEB_BASE+0x08) = NFSU1_IMAGE_BASE;')
        source = replace(source, '"\\n=== running the entry point: 0x0075bcc7 ===\\n"', '"\\n=== NFSU1 entry point: 0x%08x ===\\n", NFSU1_ENTRY_VA')
        return source
    if name == "runtime/win32.c":
        source = source.replace('"speed2.exe"', '"speed.exe"').replace('"speed2"', '"speed"').replace('"SPEED2.EXE"', 'NFSU1_EXE_NAME')
        source = replace(source, 'C:\\\\\\\\NFSU2\\\\\\\\SPEED2.EXE', 'C:\\\\\\\\NFSU1\\\\\\\\Speed.exe')
        source = replace(source, '    if (idx >= g_nimps) return 0;',
                         '    if (idx >= g_nimps){ fprintf(stderr, "NFSU1 invalid import token: %u\\n", idx); abort(); }')
        old = '''           { extern void autotest_note_unimpl(const char*,const char*,uint32_t);
             autotest_note_unimpl(e->dll, n, c->eip); }'''
        new = '''           fprintf(stderr, "NFSU1 unresolved import: %s!%s eip=%08x\\n", e->dll, n, c->eip);
           abort();'''
        source = replace(source, old, new)
        source = replace(source, 'int win32_ext_call(CPU*, const char*, uint32_t*);',
                         'int win32_ext_call(CPU*, const char*, uint32_t*);\nint nfsu1_win32_call(CPU*, const char*, uint32_t*);')
        source = replace(source,
                         '    else if (win32_ext_call(c, n, &r)) { /* second-round layer */ }\n'
                         '    else { handled = 0; g_win32_unimpl++; stat_[idx].unimpl++;',
                         '    else if (win32_ext_call(c, n, &r)) { /* second-round layer */ }\n'
                         '    else if (nfsu1_win32_call(c, n, &r)) { /* NFSU1 bring-up HLE */ }\n'
                         '    else { handled = 0; g_win32_unimpl++; stat_[idx].unimpl++;')
        # This build has no lifted server.dll. Avoid its import-table linkage.
        source = replace(source, 'extern const ImpEnt g_srv_imp[]; extern const uint32_t g_srv_imp_count;', 'static const ImpEnt g_srv_imp[1];\nstatic const uint32_t g_srv_imp_count = 0;')
        return source
    if name == "runtime/web/gcpu.c":
        return replace(source, 'mem_is_committed(0x8654a4u) ? MR32(0x8654a4u) : 0u', '0u /* NFSU2 game-flow address is invalid for NFSU1 */')
    if name == "runtime/com.c":
        # D3DCAPS9 is 304 bytes in the 32-bit guest ABI. The upstream 336-byte
        # clear overwrites NFSU1's adjacent RECT and four mode-availability words.
        source = replace(source, '    mem_commit(p,0x150); memset(g_mem+p,0,0x150);',
                         '    mem_commit(p,0x130); memset(g_mem+p,0,0x130); /* sizeof(D3DCAPS9) */')
        # NFSU2 mode labels are addresses in a different game image. Keep the
        # enumerated legacy modes and the requested backing resolution intact.
        source = replace(source, 'static int modemap_on(void){ return !ENVC("NOWIDE"); }',
                         'static int modemap_on(void){ return 0; } /* NFSU1: no NFSU2 menu writes. */')
        source = replace(source, 'static int rdone = 0, pinned = 0;',
                         'static int rdone = 0, pinned = 1; /* NFSU1: native size unless NFSRES is explicit. */')
        source = replace(source, '                           MR32(pm+12)= fmt; }',
                         '                           MR32(pm+12)= fmt;\n'
                         '                           if (g_com_trace) fprintf(stderr,\n'
                         '                               "[nfsu1 modes] index=%u output=%08x %ux%u format=%u\\n",\n'
                         '                               mode, pm, MR32(pm), MR32(pm+4), fmt);\n'
                         '                           if (g_com_trace){ void nfsu1_diagnostics_words(void);\n'
                         '                               nfsu1_diagnostics_words(); } }')
        return source
    if name == "runtime/dinput_pad.c":
        # The NFSU2 hotplug rescan flag is not part of the NFSU1 image. Keep
        # DirectInput enumeration and connection-state behavior, but omit the
        # write to NFSU2's 0x8364e8 global.
        source = replace(source,
                         '        if (mem_is_committed(0x8364e8u)) MR32(0x8364e8u) = mode == MODE_HOTPLUG || !s.connected;\n',
                         '')
        # Front-end key synthesis and collision jolt sampling both read
        # NFSU2-only globals. Preserve pad state tracking and DirectInput
        # rumble; disable only these optional NFSU2 integrations.
        source = replace(source,
                         '    int fe = MR32(0x8654a4u) == 3u;\n',
                         '    int fe = 0; /* NFSU2 GameFlow is not present in NFSU1. */\n')
        source = replace(source,
                         'static void ff_jolt(void){\n',
                         'static void ff_jolt(void){\n'
                         '    g_jolt = 0.f; g_jolt_car = 0;\n'
                         '    return; /* NFSU2 physics globals are not present in NFSU1. */\n')
        return source
    raise ValueError(name)


def header(profile):
    ident = profile['identity']['structural_values']
    lifting = profile['lifting']
    entry = profile['runtime']['entry_symbol']
    values = {
        'NFSU1_IMAGE_BASE': ident['image_base'],
        'NFSU1_IMAGE_SIZE': ident['size_of_image'],
        'NFSU1_ENTRY_VA': ident['entry_va'],
        'DISPATCH_TEXT_BASE': lifting['dispatch_text_base'],
        'DISPATCH_TEXT_SIZE': lifting['dispatch_text_size'],
    }
    result = '/* Original NFSU1 integration configuration; see docs/source-permissions.md. */\n#ifndef NFSU1_PROFILE_H\n#define NFSU1_PROFILE_H\n'
    for key, value in values.items():
        result += f'#define {key} 0x{int(value, 16):08x}u\n'
    result += f'#define NFSU1_ENTRY_POINT {entry}\n'
    result += f'#define NFSU1_EXE_SHA256 "{profile["identity"]["sha256"]}"\n'
    result += '#define NFSU1_EXE_PATH "/data/Speed.exe"\n#define NFSU1_EXE_NAME "Speed.exe"\n#endif\n'
    return result


OVERRIDES = '''/* Original CPU* implementations of PC NFSU1 override contracts.
 * Sites/contracts: codepdbh/nfsu1-recompiled, src/runtime/overrides.c.
 * Integration/runtime: th0mk/nfsu2-web. See docs/source-permissions.md.
 * No translated game instructions are included. */
#include "cpu.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern void dispatch_patch(uint32_t, guest_fn_t);
extern uint64_t g_hook_hits, g_gs_fail;

static void move_guest(CPU *c){
    uint32_t dst = MR32(c->esp + 4u), src = MR32(c->esp + 8u);
    uint32_t n = MR32(c->esp + 12u);
    /* Limit arithmetic before forming host/linear-memory pointers. Page
     * commitment faults remain the memory subsystem's responsibility. */
    if ((uint64_t)dst + n > NFSU1_GUEST_LIMIT ||
        (uint64_t)src + n > NFSU1_GUEST_LIMIT){
        fprintf(stderr, "NFSU1 memmove outside guest memory\\n"); abort();
    }
    if (n) memmove(g_mem + dst, g_mem + src, n);
    c->eax = dst;
    POP32(c->eip); /* cdecl: caller owns the three arguments. */
}
void sub_00643a39(CPU *c){ c->eax = 0; POP32(c->eip); }
void sub_00672630(CPU *c){ move_guest(c); }
void sub_00678d30(CPU *c){ move_guest(c); }
void overrides_install(void){
    dispatch_patch(0x00643a39u, sub_00643a39);
    dispatch_patch(0x00672630u, sub_00672630);
    dispatch_patch(0x00678d30u, sub_00678d30);
}
void overrides_report(void){ /* No NFSU2 hooks are installed. */ }
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--profile', type=Path, default=ROOT / 'profiles/nfsu1-pc.json')
    parser.add_argument('--verify-exe', type=Path, help='optional read-only identity check before applying')
    parser.add_argument('--revert', action='store_true')
    args = parser.parse_args()
    upstream = args.upstream.resolve()
    state_dir = upstream / '.nfsu1-profile'
    state_path = state_dir / 'state.json'
    if args.revert:
        state = json.loads(state_path.read_text())
        for name, info in state['files'].items():
            target = upstream / name
            if hashlib.sha256(target.read_bytes()).hexdigest() != info['applied_sha256']:
                raise ValueError(f'refusing to discard later edits: {name}')
        for name, info in state['files'].items():
            target = upstream / name
            if info['existed']:
                target.write_bytes((state_dir / name).read_bytes())
            else:
                target.unlink()
        state_path.unlink()
        print('Restored original runtime files; backups retained in .nfsu1-profile/.')
        return
    profile = json.loads(args.profile.read_text())
    if profile['upstreams']['runtime']['commit'] != COMMIT:
        raise ValueError('unsupported upstream runtime revision')
    if args.verify_exe:
        digest = hashlib.sha256(args.verify_exe.read_bytes()).hexdigest()
        if digest != profile['identity']['sha256']:
            raise ValueError('executable SHA-256 does not match profile')
        print('Read-only executable SHA-256 matches profile.')
    if state_path.exists():
        state = json.loads(state_path.read_text())
        if state['profile_sha256'] != hashlib.sha256(args.profile.read_bytes()).hexdigest():
            raise ValueError('profile changed; revert before reapplying')
        for name, info in state['files'].items():
            if hashlib.sha256((upstream / name).read_bytes()).hexdigest() != info['applied_sha256']:
                raise ValueError(f'overlay has later edits: {name}')
        print('NFSU1 runtime overlay already applied and unchanged.')
        return
    license_data = (upstream / 'LICENSE').read_bytes()
    if blob(license_data) != 'fe8858826d9da7b52561037421aa85c68960d18e':
        raise ValueError('expected pinned MIT license; source tree needs review')
    outputs = {}
    for name, sha in PINNED.items():
        data = (upstream / name).read_bytes()
        if blob(data) != sha:
            raise ValueError(f'upstream source differs from pinned Git blob: {name}')
        outputs[name] = edits(name, data.decode()).encode()
    outputs['runtime/nfsu1_profile.h'] = header(profile).replace('#endif\n', f'#define NFSU1_GUEST_LIMIT {int(profile["runtime"]["guest_end"], 16)}ull\n#endif\n').encode()
    outputs['runtime/overrides.c'] = OVERRIDES.encode()
    original_override = upstream / 'runtime/overrides.c'
    if original_override.exists() and blob(original_override.read_bytes()) != '5165ce16f071bb5a6991d1e92b87736979a49a31':
        raise ValueError('unexpected existing runtime/overrides.c')
    # Validate everything before changing any upstream file.
    state = {'upstream_commit': COMMIT, 'profile_sha256': hashlib.sha256(args.profile.read_bytes()).hexdigest(), 'files': {}}
    for name, data in outputs.items():
        target = upstream / name
        existed = target.exists()
        backup = state_dir / name
        if existed:
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(target.read_bytes())
        state['files'][name] = {'existed': existed, 'applied_sha256': hashlib.sha256(data).hexdigest()}
    for name, data in outputs.items():
        (upstream / name).write_bytes(data)
    state_path.write_text(json.dumps(state, indent=2) + '\n')
    print(f'Applied NFSU1 profile to {len(outputs)} runtime files. Original backups: {state_dir}')
    print('This overlay is guarded: full runtime build/browser boot remains unvalidated.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        raise SystemExit(str(error))

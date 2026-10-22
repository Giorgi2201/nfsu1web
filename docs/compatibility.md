# NFSU1 → nfsu2-web: technical compatibility assessment

## Recommendation

**Feasible as a runtime port, not a drop-in replacement.** The simplest strategy
is to keep PC NFSU1's known function set and CFG catalog, re-decode its saved
blocks, and emit the web lifter's `void function(CPU *)` ABI. Reuse the browser
Win32/COM/D3D9/WebGPU/audio host behind a new NFSU1 game profile. This avoids
repeating function discovery and avoids maintaining two incompatible CPU models.

The Xbox/Switch project is useful corroboration and a source of platform-specific
knowledge, but choosing its XBE pipeline would require porting Xbox kernel,
NV2A graphics and APU behavior as well. It is the larger integration.

This conclusion is an engineering inference from the pinned sources below.
Neither this assessment nor the synthetic proof of concept establishes race
completion, gameplay parity, or a browser frame budget.

## Revisions and evidence

All inspections were read-only, on 2026-10-21:

| Project | Inspected commit | Relevant primary sources |
| --- | --- | --- |
| PC NFSU1 | `58d9d4f63d59c941031f91973ae48c2cdb1a42b1` | [lift/catalog driver](https://github.com/codepdbh/nfsu1-recompiled/blob/58d9d4f63d59c941031f91973ae48c2cdb1a42b1/scripts/run_lift.py), [runtime](https://github.com/codepdbh/nfsu1-recompiled/blob/58d9d4f63d59c941031f91973ae48c2cdb1a42b1/android/app/src/main/cpp/guest_runtime.cpp), [audit](https://github.com/codepdbh/nfsu1-recompiled/blob/58d9d4f63d59c941031f91973ae48c2cdb1a42b1/docs/AUDIT.md) |
| Browser NFSU2 | `31da468582c3de14fd6f4233831f62816e2df83d` | [CPU ABI](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/runtime/cpu.h), [lifter](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/tools/lift.py), [web build](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/web/build.sh) |
| Xbox NFSU1 | `d597e08f88e3f415eb44366b22e75054f2dfd15d` | [regeneration driver](https://github.com/antoxa2584x/nfsu1-sw/blob/d597e08f88e3f415eb44366b22e75054f2dfd15d/tools/regen.sh), [CPU helpers](https://github.com/antoxa2584x/nfsu1-sw/blob/d597e08f88e3f415eb44366b22e75054f2dfd15d/xboxrecomp/templates/runtime/recomp_types.h), [project overview](https://github.com/antoxa2584x/nfsu1-sw/blob/d597e08f88e3f415eb44366b22e75054f2dfd15d/README.md) |

Sources show implementation, not independently reproduced game behavior.
PC NFSU1's README reports 22,751 functions, 191 vtables, 254 imports and no
relocations or RTTI. These are upstream counts, not measurements performed here.
Its status table also says races are untested; use newer code and validation
notes when assessing specific features rather than treating the status table as
a complete description. [PC overview](https://github.com/codepdbh/nfsu1-recompiled/blob/58d9d4f63d59c941031f91973ae48c2cdb1a42b1/README.md)

## Compatibility matrix

“Reusable” below means a candidate after profile separation and validation,
not demonstrated game compatibility.

| Area | PC NFSU1 recompilation | nfsu2-web | Xbox/Switch NFSU1 | Integration consequence |
| --- | --- | --- | --- | --- |
| Input/pipeline | PC patch 1.4 PE → patched pcrecomp disasm32/lift32 → C → MSVC or Android native code | PC NFSU2 v1.2 NA PE → custom Python/Capstone lifter → C shards → wasi-sdk Wasm | NTSC-U `default.xbe` → disasm → function identification → ABI analysis → recomp → native C | Use PC analysis; replace emission/build, not discovery. [Drivers above; web generator](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/tools/genall.py) |
| Discovery artifacts | Local catalog holds entry addresses, entry kinds, thunk markers, calls, jump targets and `[start,end,successors,is_exit]` blocks | Default generator discovers entries from PE entry/relocation references and call closure; lifter discovers per-function blocks | Seed JSON plus disassembly/function/ABI outputs; seeds include runtime-discovered indirect targets | Feed the PC catalog directly. Passing entries as seeds alone retains only part of the analysis. Xbox addresses are not PC addresses. [PC driver](https://github.com/codepdbh/nfsu1-recompiled/blob/58d9d4f63d59c941031f91973ae48c2cdb1a42b1/scripts/run_lift.py) |
| General CPU state | `g_eax`…`g_ebp` globals; Android saves/restores a State under a machine lock | Explicit `CPU *`; GPR array/fields, EIP, FS/GS bases | TLS globals; EBP has local/global/SEH handling in helpers | Generated C cannot link unchanged. Re-lift to one CPU representation. [PC runtime; CPU headers above] |
| Flags/FPU/SIMD | Lazy flag tuple (`g_flag_k/a/b/cf`), x87 state/control, MMX/XMM, MXCSR and segment selectors | Explicit arithmetic flags and system bits; double x87 stack with TOP/FCW/FSW; MMX/XMM; no matching MXCSR/selector fields | Separate TLS flag/FPU/SIMD helpers | A struct memcpy or symbol rename is insufficient. Verify flag, x87 precision/rounding and SSE behavior; re-lifting uses the web semantics. [CPU headers; PC State above] |
| Calling convention | `void(void)` host ABI; guest stack arguments at ESP+4, EAX result, `ret N` stack cleanup | `void(CPU *)`; guest stack plus explicit EIP; typed indirect calls and Wasm musttail dispatch | `void(void)` over guest stack and TLS registers | Preserve cdecl/stdcall/thiscall/fastcall guest behavior, return slots and callbacks. Host ABIs differ even when the guest convention matches. [PC overrides](https://github.com/codepdbh/nfsu1-recompiled/blob/58d9d4f63d59c941031f91973ae48c2cdb1a42b1/src/runtime/overrides.c), [web CPU ABI above] |
| Guest memory | Windows reserves original image range; Android uses base+VA and mmap/mprotect; full 4 GiB reservation on 64-bit hosts | Guest offsets equal linear addresses below `0x28000000` (640 MiB); host data above; initial 1 GiB, maximum 4 GiB | Offset-based Xbox VA mappings plus kernel/MMIO aliases | Keep original PC image VAs. Replace OS virtual-memory protection with browser metadata/checks. Synthetic high-address dispatch tokens must be resolved, not dereferenced. [PC memory](https://github.com/codepdbh/nfsu1-recompiled/blob/58d9d4f63d59c941031f91973ae48c2cdb1a42b1/android/app/src/main/cpp/guest_memory.h), [web CPU/build above], [Xbox memory](https://github.com/antoxa2584x/nfsu1-sw/blob/d597e08f88e3f415eb44366b22e75054f2dfd15d/xboxrecomp/templates/runtime/xbox_memory.h) |
| Imports/Win32 | Windows native32 forwards to native APIs; Android implements imports/COM as guest shims | Win32, filesystem, input, COM and WASI/browser host layers | Xbox kernel ordinals, XAPI and device behavior | Reuse web PC shims by name, then audit actual NFSU1 IAT entries and signatures. Upstream's 87% overlap concerns its native NFSU2 project, not a measured web-runtime coverage percentage. [PC audit above], [web Win32](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/runtime/win32.c) |
| Overrides/hooks | Three CPU-probe/memmove overrides; PC-specific widescreen and input sites | NFSU2-specific overrides, hooks, D3DX replacements, gameplay enhancements | Xbox-specific manual replacements in `src/recomp_manual.c` | New NFSU1 profile; keep reasons and discovered PC addresses. Disable NFSU2 gameplay/online enhancements initially. [PC overrides above], [hook sites](https://github.com/codepdbh/nfsu1-recompiled/blob/58d9d4f63d59c941031f91973ae48c2cdb1a42b1/config/hooks.txt), [web overrides](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/runtime/overrides.c) |
| Direct3D | **D3D9**, native on Windows; guest COM bridge to DXVK/Vulkan on Android | D3D9 guest COM → recorded draw/resources → shared-memory queues → WebGPU/WGSL | Xbox D3D8/LTCG and NV2A, Vulkan/OpenGL backends | PC path shares the useful API boundary. DXVK/Vulkan is not the browser backend. Audit resource/state/shader coverage; same API does not imply complete support. [PC D3D bridge](https://github.com/codepdbh/nfsu1-recompiled/blob/58d9d4f63d59c941031f91973ae48c2cdb1a42b1/android/app/src/main/cpp/d3d9_bridge.cpp), [web COM](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/runtime/com.c), [web GPU producer](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/runtime/web/gpu_web.c) |
| Threading | Android host threads serialize guest execution, saving/restoring global registers when yielding | Pthreads backed by workers, per-thread CPU/TLS, shared memory and guest lock released during host waits | TLS register model and native Xbox kernel thread emulation | Follow web scheduling. Validate waits, events, critical sections, timer callbacks and audio handoff; neither source proves safe parallel guest execution. [PC runtime above], [web threads](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/runtime/win32_ext.c) |
| Audio output | PC/Android DirectSound-style shims and host mixer | DirectSound buffer mixer → audio pump pthread → shared float ring → AudioWorklet; cursors advance even with suspended output | Xbox MCPX APU/DSP and stereo downmix | PC DirectSound output is the closer fit. Validate cursor timing, rate, starvation and suspended AudioContext behavior. Xbox APU reuse is a separate port. [web audio](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/runtime/web/audio_web.c), [Xbox overview above] |
| Code outside main image | EA `.abk` banks contain x86 routines; tool builds separate module, runtime matches relocated copies | `genexec.c` interprets a subset of runtime-generated render/material x86; optional server.dll module pipeline | Kernel/MMIO and XBE-specific runtime mechanisms | Reuse NFSU1's separate ABK analysis plan and port its dispatch into `CPU *`; don't assume web genexec handles bank routines. No browser JIT is required for the AOT approach. [ABK builder](https://github.com/codepdbh/nfsu1-recompiled/blob/58d9d4f63d59c941031f91973ae48c2cdb1a42b1/scripts/abk_module.py), [ABK lookup](https://github.com/codepdbh/nfsu1-recompiled/blob/58d9d4f63d59c941031f91973ae48c2cdb1a42b1/src/runtime/abk_code.c), [web generated-code fallback](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/runtime/genexec.c) |
| Browser support | No web target supplied | Custom WASI host, wasm32-wasip1-threads; SIMD, bulk memory, tail calls and exception handling enabled | Switch/Linux native target | Reuse web build/host, feature checks and deployment headers; native binaries cannot be loaded directly. [Web build above; browser checks](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/web/src/app/checks.ts) |
| Licensing/reuse | Root license not found; user reports maintainer permission with attribution | MIT with named upstream portions | Root permission user-reported; vendored toolkit MIT with LGPL exceptions | Proceed within reported permission, retain attribution and component notices. [Permission record](source-permissions.md) |

## Preserve analysis before changing code generation

The committed PC repository supplies tooling/configuration, **not the actual
local catalog**. Since no saved copy was obtainable, the original upstream
seed/catalog pipeline was run locally and cached; see [current progress](progress.md).
Subsequent read-only
Downloads inspection identified an executable matching the source-verified
loader checks and published abbreviated hash; [local findings](game-inputs.md)
record its full measured fingerprint and section bounds.
Prefer a matching saved catalog when available. Otherwise generate it once with
the existing upstream scripts and known seed/fix passes; do not ask the user to
obtain an unavailable artifact or hand-repeat function analysis. Cache the
catalog together with its own hash, executable SHA-256, tool revisions and image
bounds. The original catalog schema itself lacks a binary digest. The README abbreviates the game
hash, so that abbreviation cannot serve as a complete identity check.

Preserve the saved CFG, exclusions, override list, hook sites, import names,
indirect targets, and ABK catalogs separately. Re-decoding known block extents
is necessary for target instruction semantics; it is not repeating discovery.
Compare counts, per-function block ranges and dispatch coverage after the lift.
Only investigate differences or unresolved targets rather than restarting the
22k-function analysis. [Catalog writer/rebuilder](https://github.com/codepdbh/nfsu1-recompiled/blob/58d9d4f63d59c941031f91973ae48c2cdb1a42b1/scripts/run_lift.py)

## Concrete runtime changes

1. **Introduce a game profile.** PC loader checks identify image base
   `0x00400000`, image size `0x00394368`, entry RVA `0x00270cb5` (VA
   `0x00670cb5`). These are structural checks, not a hash. In contrast,
   `runtime/web/main_web.c` directly calls `sub_0075bcc7`, names `SPEED2.EXE`,
   and reads NFSU2 CRT addresses during reporting. Replace all three behaviors;
   selecting a different input filename alone cannot work. Keep identity, entry,
   text bounds, save roots and enabled hooks in one profile.
   [PC loader](https://github.com/codepdbh/nfsu1-recompiled/blob/58d9d4f63d59c941031f91973ae48c2cdb1a42b1/android/app/src/main/cpp/guest_runtime.cpp),
   [web entry point](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/runtime/web/main_web.c)
2. **Replace generator discovery with catalog input.** Web `genall.py`
   Phase 1 expects relocation-derived references, whereas PC NFSU1 lacks
   relocations. Add a catalog input path, retain exact entries/blocks, and make
   unknown edges explicit. Generate `g_fn_*` tables, declarations and NFSU1
   import argument metadata; adapt generator stamps too. Do not run NFSU2's
   `reloc2.py`, hot-inline list or whole-program flag table unchanged.
   [Web generator](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/tools/genall.py),
   [generation wrapper](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/web/gen.sh)
3. **Separate shared runtime from game-specific behavior.** Review
   `overrides.c`, `d3dx_hle.c`, `widescreen.c`, `framerate.c`, `autotest.c`,
   `gcpu.c`, COM resolution handling, game audio helpers, and online/career
   code. For example `gcpu.c` reads flow at `0x8654a4`; leaving that enabled
   would inspect unrelated NFSU1 memory. Disable features pending a mapped
   NFSU1 implementation, including optional server.dll/LAN paths.
   [Concrete flow read](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/runtime/web/gcpu.c),
   [COM game assumptions](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/runtime/com.c)
4. **Keep web memory and scheduling contracts.** Derive the dispatch text
   range from NFSU1; the web CPU header's present range is NFSU2-specific.
   Audit guest heaps/stacks and synthetic tokens against `GUEST_END` before
   running. Preserve `musttail` for indirect tail dispatch to avoid engine-stack
   accumulation. Do not emulate mmap/mprotect as real browser page protection.
   [CPU/dispatch contract](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/runtime/cpu.h),
   [Wasm memory implementation](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/runtime/mem.c)
5. **Bring up graphics and sound incrementally.** First log the NFSU1
   import/COM methods and unsupported shaders. Confirm device creation,
   texture uploads/locks, viewport/depth/blend states, fixed-function and shader
   paths, then draw/present. Bring ABK code dispatch and DirectSound timing up
   before declaring audio complete. The PC ABK builder identifies 23 distinct
   blocks and a separate synthetic analysis module; keep outputs private.
   [ABK builder](https://github.com/codepdbh/nfsu1-recompiled/blob/58d9d4f63d59c941031f91973ae48c2cdb1a42b1/scripts/abk_module.py)

## Alternatives and tradeoffs

| Strategy | Advantage | Additional cost | Verdict |
| --- | --- | --- | --- |
| Re-lift known PC catalog using web CPU ABI | One CPU/dispatch/host model; retains discovery and CFG work | Catalog-to-lifter adapter plus game profile/runtime audit | **Recommended minimum total integration** |
| Compile existing PC generated C with a compatibility shim | Retains existing instruction emission | Lazy flags vs explicit flags, x87 conventions, state swaps at every callback, globals across workers, tail-call guarantees | Useful for an isolated experiment; likely a more complex maintained port |
| Port PC Android runtime wholesale | Existing PC game-specific fixes | Replace DXVK, AAudio, native virtual memory, JNI, thread integration and filesystem assumptions | More browser backend work |
| Port Xbox/Switch runtime | Existing NFSU1 Xbox experience | XBE identity/assets, kernel ordinals, MMIO/NV2A shaders and APU/DSP, browser backends | Longest route for this PC-browser objective |

These relative costs are qualitative judgments, not measured schedules.

## Browser acceptance and validation gates

Use the upstream runtime's feature checks, not just browser name/version:
secure context, cross-origin isolation and SharedArrayBuffer, shared Wasm memory,
Atomics.waitAsync, and an actual WebGPU adapter. Its UI currently names Chrome
140 and Firefox 145 as tested minima, but those constants do not guarantee
support on every platform. Reuse its server isolation headers. Verify all build
features, 1 GiB initial allocation and growth limits on the actual target.
The GPU path can decode BC textures when hardware compression is unavailable,
at extra memory cost. [Checks](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/web/src/app/checks.ts),
[build flags](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/web/build.sh)

Acceptance should progress through:

1. Matching identity/catalog → zero decoding gaps, unexplained lost functions,
   unresolved required edges, or silent unsupported-instruction stubs.
2. Synthetic ABI/flags/x87/SSE, callbacks, tail-loop and guest-thread tests in
   the actual compiled Wasm runtime, including bad addresses and lock handoffs.
3. Private local boot → Win32 startup, first D3D9 Present, front end and input.
4. Audio bank dispatch, music and movie timing; paused/resumed audio, tab focus,
   loading and save persistence. Check real cursors and buffer underruns.
5. A repeatable race against the native PC recompilation: state/physics drift,
   rendering differences, memory growth and frame times in Chrome and Firefox.

A strict linked Wasm module now sustains guest execution under Node. The main
catalog emits 22,944 bodies with 675 abort stubs. The ABK adapter emits 28
routines from 106 banks and 23 unique blocks, translating 1,053 call-return
sites with no ABK stubs; the strict module is about 101 MiB. Runtime diagnostics
matched the loaded callback at `0x092031dc` to canonical routine `0x10016000`
(108-byte block) eight times. A 180-second Node run recorded 9,657 Presents and
ended at the host deadline without a guest trap, after resolving the movie-thread
starvation and the former `0x00647e82` switch stop. A separate 30-second run
with the current DirectInput guards recorded 1,131 Presents and exited at its
host deadline without a guest trap. These checks establish callback dispatch
and sustained guest execution only.

The pinned browser host has been overlaid, bundled and checked for JavaScript
syntax and local server inputs. In-process HTTP handler checks cover the actual
static assets, manifest, byte ranges and isolation headers. The user reports
that the browser played intro clips with sound, created a profile that remained
after reload, and then loaded that profile and started a race. These are useful
initial observations, not a completed-race or parity result; rendering, input,
and broader gameplay behavior still need validation.

A startup regression check executes the overlaid `startGame()` with stubbed host
dependencies. Reintroducing the removed NFSU2 `autosaved` reference reproduces a
`ReferenceError`; the current overlay passes. The branch ran after session
creation, so this confirms and fixes a real startup error without establishing
that it alone caused the reported black screen. The adapter's synthetic checks
passed native and compiled-Wasm execution against the CPU header. The cached
game catalog and WASI SDK are already available locally; do not repeat discovery
or compiler setup. [Setup and result](toolchain.md),
[current startup and emission status](progress.md)

## Deliverables and next step

The workspace contains pinned-source setup, catalog and sound-bank adapters,
reversible runtime/browser overlays, local Wasm build and serving tools,
focused checks, an executable synthetic Wasm ABI fixture, and an
attribution/permission record.
The adapter consumes saved block ranges and call targets, retaining other CFG
metadata. Optional typed tail routing only targets already catalogued entries;
full runtime behavior of those paths remains unvalidated.
See [proof-of-concept details](../poc/README.md) and [commands](../README.md).

The [NFSU1 configuration](../profiles/nfsu1-pc.json) is wired into a private
runtime-source overlay, and the catalog is generated locally. The initial
user-reported browser milestones are documented above; complete game
compatibility remains unverified. Follow the [build guide](building.md)
and [browser test instructions](browser-testing.md). Original archives remain
unchanged and all game-derived output remains local and ignored.

# NFSU1 runtime profile integration

[`profiles/nfsu1-pc.json`](../profiles/nfsu1-pc.json) is an original, machine-readable
configuration consumed by `tools/apply_runtime_profile.py`, which now overlays
the pinned hand-written runtime sources. It is not a complete game port.
`null` fields are unresolved. Read-only Downloads inspection now supplies a
local executable digest, exact loader-field matches and `.text` section bounds;
the digest also matches upstream's published prefix/suffix. The full upstream
reference digest is unavailable. See [input findings](game-inputs.md).
The matching catalog is now generated locally with the original seeded analysis
pipeline and cached for subsequent builds. A strict linked module sustains
execution under Node, and the pinned browser host has been bundled with an
isolated NFSU1 profile. The user reports that the browser played intro clips
with sound, created a profile that persisted through reload, then loaded that
profile and started a race. This is an initial browser observation; no completed
race, parity or playable-port claim has been established.

The checklist targets `th0mk/nfsu2-web` at
`31da468582c3de14fd6f4233831f62816e2df83d`, with PC analysis from
`codepdbh/nfsu1-recompiled` at `58d9d4f63d59c941031f91973ae48c2cdb1a42b1`.
Paths below refer to that upstream source snapshot. The overlay parses the
profile's hexadecimal strings as unsigned 32-bit addresses.

## Original integration plan

The checklist below preserves the original design. The runtime and browser
overlays and local build tools now implement the startup path, dispatch bounds,
import binding, storage isolation and game-specific guards. Use the
[build guide](building.md) for current commands and
[progress](progress.md) for completed fixes and remaining limitations.

1. **Generate a build configuration from the profile.** The overlay generates
   `runtime/nfsu1_profile.h`. The local executable and generated catalog digests
   are now recorded. Check the PE image base,
   image size and entry against the source-verified values. Extract executable
   section bounds; do not reuse NFSU2's text range or substitute SizeOfImage.
   Preserve saved blocks and metadata through the existing catalog adapter.
   `tools/lift_catalog.py` supplies catalog-based emission and declarations;
   clean full emission is required before publishing tables. Make `web/gen.sh` skip
   NFSU2 relocations, flags/inline tables and server generation; update generation
   stamps and `web/build.sh`'s unconditional `gen/server` requirement.

2. **Select the NFSU1 entry and process identity.** In
   [`runtime/web/main_web.c`](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/runtime/web/main_web.c),
   replace `/data/SPEED2.EXE`, the direct `sub_0075bcc7` call and its diagnostic
   string with profile values (`sub_00670cb5`). Remove NFSU2 CRT reads at
   `0x008ba4a4`/`0x008ba4a8` and gate game-specific initialization/reports.
   In `runtime/win32.c`, replace the hard-coded module filename and command
   line. Namespace browser persistence and save paths for NFSU1; `/save` alone
   does not establish isolation. Retain the web CPU/TLS/guest-lock setup until
   actual memory-layout validation justifies changes.

3. **Replace dispatch bounds and address-sensitive behavior.** Generate
   `DISPATCH_TEXT_BASE`/`DISPATCH_TEXT_SIZE` in `runtime/cpu.h`; update its
   coverage range too. Keep `void(CPU *)` and Wasm `musttail` dispatch intact.
   In [`runtime/dispatch.c`](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/runtime/dispatch.c),
   gate NFSU2 effect diagnostics/epoch mutations in `0x00650000..0x00690000`,
   which overlap NFSU1 code. Stop on missing targets and unsupported instructions
   during bring-up: upstream currently swallows unresolved calls and only counts
   unsupported instructions. Disable generic generated-code interpretation until
   needed; separately port ABK relocation-aware dispatch before enabling audio.

4. **Bind imports and port only required overrides.** Generate NFSU1
   `{iat,dll,name,nargs}` records from its own PE; audit ordinals and stack cleanup
   against the shared Win32 shims. Preserve `0xf0000000 + import_index` and COM
   tokens in the `0xe...` range as dispatch tokens. Provide empty server tables
   or conditionally remove their references. Replace NFSU2 override/hook lists
   and direct-call wrappers with the three profile sites; port their semantics
   into `CPU *`, including return EIP and cdecl argument ownership. Retain
   attribution and notices if source is copied later.

5. **Gate remaining NFSU2 features before first boot.** Audit `runtime/com.c`,
   `d3dx_hle.c`, `widescreen.c`, `framerate.c`, `autotest.c`, audio helpers,
   career/online/roam modules and their build-time dependencies. Disable the
   `runtime/web/gcpu.c` flow read at `0x008654a4`. Empty hook enablement is
   intentional. Keep generic D3D9/WebGPU/input/DirectSound plumbing, then report
   unsupported methods rather than assuming NFSU2 feature coverage transfers.

## Focused validation

Profile parsing, entry arithmetic, runtime syntax and override execution have
been checked. Synthetic C emission, native compilation and compiled Wasm
execution in Node passed against the real CPU header. The main catalog emits
22,944 bodies with 675 abort stubs. The ABK adapter emits 28 routines from 106
banks and 23 unique blocks, translating 1,053 call-return sites with no ABK
stubs; the strict linked module is about 101 MiB. Diagnostics matched loaded
callback `0x092031dc` to canonical routine `0x10016000` (108-byte block) eight
times. After resolving movie-thread starvation and the former
`0x00647e82` switch stop, a 180-second Node run recorded 9,657 Presents and
ended at the host deadline without a guest trap. A separate 30-second run with
the current DirectInput guards recorded 1,131 Presents and exited at its host
deadline without a guest trap. These checks verify guest dispatch and sustained
execution, not front-end or rendered output.

The experimental browser bundle passes JavaScript syntax checks; in-process
requests through the actual local HTTP handler pass the static asset, manifest,
range and isolation-header checks. A focused startup smoke executes the
overlaid `startGame()` with stubbed host dependencies. Reintroducing the removed
NFSU2 `autosaved` reference makes it fail with `ReferenceError`; the current
overlay passes. This branch runs after session creation, which confirms the
startup bug without proving it alone caused the reported black screen. The
browser observations above came from the user, not an agent-operated browser.
They provide early positive evidence for clips, sound and save persistence;
broader rendering, input and gameplay validation remains open. The host uses
isolated NFSU1 save/cache namespaces and filters unsupported NFSU2 environment
options. Follow the [browser test instructions](browser-testing.md) for further
checks.

Sources are linked above and in the
[compatibility assessment](compatibility.md). Override contracts come from
[PC runtime overrides](https://github.com/codepdbh/nfsu1-recompiled/blob/58d9d4f63d59c941031f91973ae48c2cdb1a42b1/src/runtime/overrides.c);
image structure comes from the
[PC loader](https://github.com/codepdbh/nfsu1-recompiled/blob/58d9d4f63d59c941031f91973ae48c2cdb1a42b1/android/app/src/main/cpp/guest_runtime.cpp).
These files contain metadata and an original checklist, with no reused source,
binary, real catalog or game-derived generated code.

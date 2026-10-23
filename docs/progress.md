# Integration progress — 2026-10-23

## Current bring-up checkpoint

### Drag loading: internal switch dispatch

The user reports a drag-race loading abort at unresolved dispatch `0x00482f48`
with `sub_00483080` on the stack. The private caller audit identifies the
switch in its callee `sub_00482f00`: the selector is reloaded from an ESP spill,
and the jump has no saved successor edges. Its three distinct case targets
are already saved local blocks, but are not standalone dispatch entries.
The previous guard-based table recovery missed this form and emitted an
indirect tail dispatch into an internal block.

`tools/catalog_bridge.py` now also recovers direct indexed tables whose
contiguous words match the function's complete saved `jump_targets` set and
whose arms all have saved local blocks. This conservative fallback needs no
new analysis, executable changes or guessed callback bodies. The upstream
emitter checks each live table word before entering its label and retains
indirect dispatch for changed words and other indices. The same recovery
applies to the saved aliases of this switch. Functions with multiple unrelated
tables may still need separate recovery; this does not claim full switch coverage.

The focused authored-byte smoke covers an ESP reload without a guard or
successors, repeated table entries, missing blocks and incomplete tables.
Existing split-guard and frame-spill checks and five catalog unit checks pass.
An additional native execution of the synthetic lift passes all five table
indices, an index beyond the recovered prefix and a changed live table word;
the latter two reach the original indirect fallback. Its private harness is
under `out/saved-switch-smoke/`.
The full re-lift recovers seven additional guarded switch sites across five
shards, including the reported owner and both aliases, with unchanged emission
successes, failures, 675 abort stubs and unresolved direct targets. The selected
private emission is `gen/nfsu1-saved-switch` via `gen/nfsu1-current`; lift and
build logs use the `out/saved-switch-` prefix.
The private Wasm link, browser bundle, stubbed startup, JavaScript syntax and
in-process server checks pass. Restart the server and reload the same origin
to retry the failing drag event with the repaired module; keep existing saves.
Browser drag loading and race completion remain pending user validation.

### Startup movie controls

The browser now exposes **Startup movies: Skippable / Original / Off**.
Skippable is the default and adds Escape, Space, Enter and controller A/B/Start
to the startup movie screens. The adapter hooks three verified NFSU1
notification handlers and invokes the original guest handlers for normal
screen transitions and player teardown. Story/tutorial handlers are untouched.
Off finishes each startup screen on its first update, so a brief frame can
appear. See [implementation and browser checks](movie-skipping.md).

The focused synthetic native adapter smoke passes mode selection, guest stack
and argument preservation, input baselining and controller disabling. The
private Wasm module and browser bundles are rebuilt; startup/syntax and
in-process server checks pass. Browser skip behavior and audio teardown remain
pending user validation. No agent operated a browser. Restart the local server
and reload the same origin to pick up the new module and settings; keep saves.

### First profile creation: date/time imports

A later user log establishes the first-profile crash: after creating
`Profiles.usr` and the profile's `_autosave.ugd`, the runtime aborts on
`KERNEL32.dll!GetDateFormatA` at guest EIP `0x0041d90c`. This explains how files
can exist after a failed creation attempt; successful loading after reload does
not establish that the initial creation path completed.

The private caller audit found two successive six-argument stdcall imports:
`GetDateFormatA(LOCALE_SYSTEM_DEFAULT, DATE_SHORTDATE, NULL, NULL, out, 12)`
and `GetTimeFormatA(LOCALE_SYSTEM_DEFAULT, TIME_NOSECONDS, NULL, format, out, 12)`.
The time picture is either the locale default or `HH':'mm`. Both imports now
have original implementations in `runtime/nfsu1_win32.c`. They use the current
clock, the existing browser timezone adapter, and the runtime's English (US)
locale. They preserve NUL-inclusive size queries, check guest buffer bounds,
and set per-thread last-error on failure. This is focused formatting support,
not complete Windows locale/calendar emulation.

`tools/datetime_runtime_smoke.py` executes the actual helper with synthetic
guest memory, both natively and compiled with the WASI runtime's compatibility
header and timezone source. Both pass date/time formatting, the game's custom
picture, size queries, short-buffer canaries, and error handling. The game
module has been relinked, and the user subsequently confirmed that profile
creation works. No original executable or generated guest functions were changed.

The user also supplied a race screenshot showing the rendered world, car and
HUD. Two issues remain deferred at the user's request: main-menu option labels
appear about one second after their container, and minimap roads are absent in
both 2D and 3D modes while player markers remain visible. Their causes are
unconfirmed. No experimental menu/map tracing or rendering changes are retained.

The `C:\NFSU2` prefix in the pasted write log is inherited virtual filesystem
identity. Those requests resolve into `/save/nfsu1/NFS Underground/`, as the log
shows; it does not identify the date-format abort or a write into NFSU2 saves.
The movie `MAD_FRAME` warning is retained for investigation. Its origin in the
original decoder and lack of an accompanying trap distinguish it from this
explicit unresolved-import failure; its host-versus-game cause is not proven.

### Earlier browser and Node observations

The user reports that the browser plays clips with sound, creates a profile
which survives a reload, loads that profile and starts a race. This is a
user-observed browser milestone; no agent operated the browser, and race
completion or compatibility with all content is not established.

The reported page error `ReferenceError: autosaved is not defined` is fixed.
The browser overlay removed NFSU2 autosave setup but left its later toast branch;
that branch threw after a session had started and before exit tracking attached.
It now shows the generic startup hint. The focused startup smoke executes the
actual overlaid function with host stubs and is part of every browser build.
Reintroducing the old reference in an ignored regression fixture reproduces the
error; the fixed source passes. This establishes the JavaScript fault, not the
cause of every first-run black screen. The rebuilt page needs a reload.

The module now sustains a guest frame loop: the latest **180-second Node run
records 9,657 Presents** and ends at the host deadline (exit 124), with no
unresolved-dispatch or unsupported-instruction stop. Movie-thread starvation,
interior switch dispatch `0x00647e82`, and the music bank callback have been
resolved. All 28 bank routines emit cleanly and link through a content-matched
`CPU *` adapter; repeated execution of the previously failing callback is logged.
Graphics and audio output are dropped by the minimal Node host. This is guest
execution progress, not visible rendering validation.
The next browser check is startup/stop behavior with the repaired shell; see
the [local test instructions](browser-testing.md).

The other pasted messages are classified as follows:

- `.js.map` 404: optional debugging data was stored in `dist-dev`, outside the
  served page directory. The builder now retains those maps locally without
  advertising unavailable public map URLs.
- `ConnectionResetError`: a browser closed an HTTP connection. The local server
  now quietly handles reset/aborted connections and broken pipes during reads
  and writes; its in-process disconnect smoke passes.
- `RCMP:: Warning: in ~MAD_FRAME() m_ReferenceCount >= 1`: an original game
  movie-frame cleanup diagnostic (the strings are present in the original
  executable). It is not by itself a fatal error; retain it for later movie
  lifetime investigation if symptoms recur.
- Missing `NFSUNDER/ZDIR.BIN` and `Config.bin`: also present in successful Node
  bring-up logs and absent from the selected archive. No placeholder files have
  been fabricated; these messages alone do not establish the profile failure.
- Network-off/`WSASYSNOTREADY`: expected with online integration disabled.

Downloaded logs now use the `nfsu1-` filename prefix. Restart the local Python
server to use its disconnect fix, then reload the page to use the new bundle;
the isolated profile storage is not cleared.

## Startup diagnostics and first stall fixed

The former quiet stall after D3D9 device creation was caused by a host
write overrun: `fill_caps` cleared 336 bytes, but the guest `D3DCAPS9` occupies
304 bytes. With the caps at `0x0071b670`, the extra clear erased the adjacent
rectangle and four display-mode availability flags. Enumeration correctly set
all five flags before the later capabilities query erased them. The game then
entered a very long display-mode scan. The overlay now limits the clear to
304 bytes; the executable and generated game code remain unchanged.

The size follows the [Microsoft D3DCAPS9 layout](https://learn.microsoft.com/en-us/windows/win32/api/d3d9caps/ns-d3d9caps-d3dcaps9)
and its nested [vertex](https://learn.microsoft.com/en-us/windows/win32/api/d3d9caps/ns-d3d9caps-d3dvshadercaps2_0)
and [pixel](https://learn.microsoft.com/en-us/windows/win32/api/d3d9caps/ns-d3d9caps-d3dpshadercaps2_0)
caps. `tools/caps_boundary_smoke.py` executes the actual host writer on synthetic
memory with canaries. It passes with the overlay; the unchanged upstream backup
fails at byte 304. This establishes the write boundary, not complete caps semantics.

The Node host now passes an explicit allowlist of diagnostic environment
variables into WASI, consistently across pthread workers. An actual compiled
Wasm smoke checked main/worker `getenv` and exclusion of unrelated host variables.
Previously the WASI environment was always empty. `runtime/nfsu1_diagnostics.c`
adds repeated frame-count, thread-state and guest-stack snapshots before the
first Present. Registers and heuristic stack scans are approximate concurrent
observations, not an instruction-precise debugger stop.

```sh
python3 tools/caps_boundary_smoke.py --upstream work/upstream/nfsu2-web
NFSU1_DIAGNOSTICS=5 TRACE_MAX=350 \
  perl -e 'alarm 25; exec @ARGV' node tools/run_wasm_node.mjs \
  work/upstream/nfsu2-web/out/web/nfsu1.wasm
```

Optional `NFSU1_DIAGNOSTIC_WORDS=0x700e70,0x71b7b4` prints up to 16 aligned
guest words when diagnostics are enabled. `COMTRACE=1` traces COM calls and
display-mode outputs, including word snapshots at enumeration checkpoints.
The overlay disables NFSU2 mode-label writes and automatic backing-resolution
remapping; an explicit `NFSRES` remains available.

The next observed stop was unresolved dispatch `0x0040df3e`, a saved switch
arm. The adapter now recognizes an immediate comparison and conditional branch
split across adjacent saved blocks, including aliases whose comparison is
retained by a canonical owner. It uses a unique predecessor range recorded with
the branch in the catalog and checks flag/index preservation. No new entries
or block ranges are discovered. `tools/split_switch_smoke.py` checks real-lifter
synthetic emission and rejects flag/index clobbers and unrelated adjacent ranges.
Targeted real-image emission recovers all six arms for the owner and aliases.
The fresh full pass at `gen/nfsu1-split-guards/` completes with 22,942 bodies,
672 rejected entries, three unresolved direct targets and 675 abort stubs.
It emits 1,275 switch occurrences (previously 1,272). This is still a
`linkable_with_stubs` bring-up emission, not a clean full lift.

Build hardening renames three colliding NFSU2 wrapper symbols in the runtime
objects and removes blanket duplicate-definition suppression. The link input
list now follows current sources so stale objects cannot be pulled in through
wildcards; guest-object cache hashes also include the generated profile header.
The complete module links successfully with duplicate-definition errors enabled.
Select the current emission explicitly when rebuilding:

```sh
J=4 bash tools/build_nfsu1_wasm.sh
```

Private diagnostic evidence is under `out/`: `startup-mode-checkpoints.log`
captures successful enumeration before the corrupting clear, and
`caps-fix-node.log` records startup advancing into input/audio initialization.
`split-guards-node.log` records the recovered switch path, draw submission and
14 Presents. The bounded launch terminates after 30 seconds (exit 142);
the guest had already aborted on the missing callback, while host workers and
diagnostics remained alive. Counter stability after that abort is not a running
frame loop.
Rendering, audio output, front-end interaction and races remain unvalidated.

### Callback catalog repair

The next observed stop was `target=0x00448a40`, `eip=0x004483fe`. This address is
absent as both an entry and a block in the cached catalog. It is a code-address
immediate assigned by callback `0x00448ac0`: that parent is absent from the
initial catalog but present after the single code-seed pass. The callback chain
therefore exposes a gap beyond the one-pass seed scan.

A focused invocation of the pinned original `Disassembler` accepts the target
as a function body and produces five blocks. Its two direct callees are already
catalogued. Diagnostic output and input/tool/output fingerprints are cached at
`work/analysis/callback-00448a40-diagnostic.json` and the adjacent
`.metadata.json`. The baseline catalog and executable are unchanged.

`tools/repair_catalog_callbacks.py` now performs that focused analysis with the
pinned original disassembler. It preserves every baseline record and follows
only missing direct callees. Optional `--follow-code-immediates` applies the
original mov/push probe rule only to newly added bodies, so the callback chain
does not require repeated whole-program discovery. Input, source/tool and output
hashes govern reuse; conflicting instruction boundaries or incomplete analysis
withhold the augmented catalog.

The closure adds exactly `0x00448a40` (five blocks) and `0x00448a10` (three
blocks). The latter is introduced by a push at `0x00448a79` in the former.
All 23,617 baseline records remain unchanged. Re-running the repair reuses its
cache; a known-code interior entry is rejected. Both added bodies pass focused
real-emitter checks with resolved direct calls and no traps or missing fallthroughs.

```sh
export PYTHONPATH="$PWD/work/toolchain/capstone/bindings/python:$PWD/work/toolchain/pefile"
export LIBCAPSTONE_PATH="$PWD/work/toolchain/capstone"
python3 tools/repair_catalog_callbacks.py \
  --image work/analysis/Speed.analysis.exe --catalog work/analysis/catalog.json \
  --entry 0x00448a40 --follow-code-immediates \
  --output-dir work/analysis/callback-closure
python3 tools/lift_catalog.py \
  --image work/analysis/Speed.analysis.exe \
  --catalog work/analysis/callback-closure/catalog.json \
  --base-catalog work/analysis/catalog.json \
  --upstream work/upstream/nfsu2-web \
  --output-dir gen/nfsu1-callback-closure --link-stubs
```

Use an empty destination for emission. `--base-catalog` verifies the profile's
parent hash, exact baseline records and repair provenance. Added functions are
appended in emission order while dispatch arrays stay sorted. The object cache
hashes only referenced generated prototypes plus all other header content, so
an unused declaration addition does not invalidate unchanged shards. Existing
objects migrate only after matching the previous complete-input cache hash.

The Node host now runs Wasm in a supervised worker. A trap or process exit in
any guest worker terminates the entire Node run and preserves its failure code.
`NFSU1_TIMEOUT_MS=30000` bounds execution/startup after module compilation and
returns 124 at the deadline. Synthetic checks cover main return, nested-worker
process exit, worker trap, busy-loop deadline and environment forwarding. The
old real-game artifact exits 134 at its known missing callback rather than
leaving worker threads running.

### Data staging and the next scheduler gap

The repaired callback module at `gen/nfsu1-callback-closure/` emits 22,944
bodies and retains 675 abort stubs. It linked with only `fntab.c` and the last
shard recompiled; all other guest shards reused validated cache objects.
The first bounded launch passed the former callback stop and reached 22
Presents, then stalled while sound registration/lookup repeatedly failed to
load missing local assets.

The selected archive's `Sound`, `Movies`, `SNDSTREAMS` and `SpeechStreams`
directories have now been extracted under ignored `work/data/`: 150 files,
524,253,876 bytes. `work/data-extraction.metadata.json` records the source
archive hash and extracted-file hashes. No original executable, archive or
native plugin was modified or run. The executable and previously staged game
directories are retained. Do not repeat extraction on every build.

With these assets present, the callback module reaches 39 Presents and the
sound-data open failures disappear. It then spins in the movie stream poll
`sub_00645a77` / callback pump `sub_0063f0a0`, while reader threads wait for the
guest lock. Guest stack remnants initially pointed at allocation code; a V8
CPU profile confirms the polling path. Evidence is private under
`out/callback-closure-assets-node.log` and `out/wasm-cpu-profile/`.

The emitter now supports an explicit `--cooperative-yield-entry 0x0063f0a0`.
It calls the existing runtime `guest_fair_yield` before the selected function's
first real instruction. The helper already respects critical sections and
no-yield regions and, every 1,024 calls, hands the FIFO guest lock to queued
threads. Synthetic tails are not hooked; default emission is unchanged.
This is a scheduling integration point, not a fabricated stream-completion
result. The resulting `gen/nfsu1-cooperative/` module recompiles only
`shard_0088.c` and links successfully. Its bounded Node run clears the polling
stall, reaches sound-thread restart, then exits 134 at unresolved dispatch
`0x00647e82`. Evidence is in `out/cooperative-node.log`.

That address is already a case label of `sub_00647cb0`, not a missing catalog
entry. Its guard compares `dword [ebp-0x2c]` with 7, then the dispatch block
loads the same slot into EAX before the indirect jump. The adapter now recognizes
this narrow stack-spill form: adjacent comparison/guard, first-in-block matching
dword EBP-relative load, and the existing index-preservation, table-range and
target checks. It retains the runtime table-value checks and dispatcher fallback.
The real image emits all eight arms without traps; the authored smoke rejects
different slots, a changed frame pointer, a store between comparison and guard,
and a clobbered loaded index. The full pass retains 22,944 main-image bodies and
675 abort stubs. Only three shards changed, adding 28 switches with 283 checked
cases; the remaining emitted bodies are unchanged. Strict linking recompiles
those three shards. The 30-second Node run reaches 1,367 Presents and exits 124
at the host deadline, without a guest trap. The 120-second run reaches a last
snapshot of 6,427 Presents, then exits 134 at dynamic audio target `0x092031dc`.
`[guest] done` is guest `WriteFile` output, not host/main completion.

```sh
python3 tools/lift_catalog.py \
  --image work/analysis/Speed.analysis.exe \
  --catalog work/analysis/callback-closure/catalog.json \
  --base-catalog work/analysis/catalog.json \
  --upstream work/upstream/nfsu2-web \
  --output-dir gen/nfsu1-spilled-switch \
  --cooperative-yield-entry 0x0063f0a0 --link-stubs
GEN="$PWD/gen/nfsu1-spilled-switch" J=4 bash tools/build_nfsu1_wasm.sh
NFSU1_DIAGNOSTICS=3 NFSU1_TIMEOUT_MS=30000 \
  node tools/run_wasm_node.mjs work/upstream/nfsu2-web/out/web/nfsu1.wasm
```

The build defaults to ignored `gen/nfsu1-current`, a symlink selecting the
latest verified emission. `GEN=...` still selects an explicit directory.

### Loaded sound-bank callbacks

The dynamic target is read from a callback list in the audio worker, outside
the executable. A bounded dispatch diagnostic captures its registers and 64
target bytes in ignored `out/dynamic-audio-node.log`. All non-relocation bytes
match the unique 108-byte block shared by `STRM_Music_UG0_MB.abk` and its PCD
variant, at routine offset zero. Three complete relocated calls also resolve
to the expected original table entries (indices 0, 1 and 27). The private match
record is `work/analysis/dynamic-audio-match.json`. This confirms ABK code rather
than another missing executable entry. File tracing also shows progression
through `PSA.mad` and `E3_TITLE.mad`; front-end arrival is still unverified.

`tools/prepare_abk_catalog.py` invokes the pinned original bank module builder
and recursive-descent analysis only at its routine seeds. It hashes the image,
all 106 banks, upstream sources, wrapper, catalog adapter and toolchain. Repeat
runs verify output hashes and reuse the saved results. Private outputs under
`work/analysis/abk/` contain 23 unique blocks (18,508 code bytes), 28 routines,
40 CFG blocks and 22 external main-image call targets.

`tools/lift_abk_catalog.py` emits all 28 routines without stubs using the pinned
web emitter. Its instruction adapter translates 1,053 guest return-slot pushes
to the actual loaded bank addresses. `runtime/nfsu1_abk.c` accepts only full
content matches with every relocated call checked against the original static
function table, and validates guest bounds and committed pages. Nested callbacks
save and restore a thread-local mapping; canonical internal calls are confined
to the active block. No interpreter or fabricated callback return is used.
The authored runtime smoke covers matching, code/call mutation rejection,
uncommitted memory and nested loaded/canonical callback mapping.

```sh
python3 tools/prepare_abk_catalog.py --image work/analysis/Speed.analysis.exe
python3 tools/lift_abk_catalog.py --image work/analysis/Speed.analysis.exe
python3 tools/abk_runtime_smoke.py
J=4 bash tools/build_nfsu1_wasm.sh
NFSU1_DIAGNOSTICS=10 NFSU1_TIMEOUT_MS=180000 \
  node tools/run_wasm_node.mjs work/upstream/nfsu2-web/out/web/nfsu1.wasm
```

Use the Python dependency environment from the catalog commands above and an
empty bank emission destination. The build consumes `gen/nfsu1-abk/` by default
when its complete report and output hashes validate; `ABK_GEN=...` selects an
explicit bank emission. This adds three bank objects and the CPU-ABI matcher
to the strict link without recompiling unchanged main-image shards. The module
links at about 101 MiB. The real run in `out/abk-node.log` matches loaded address
`0x092031dc` to canonical bank entry `0x10016000` repeatedly and continues to
9,657 Presents at the last diagnostic snapshot. It exits 124 at the configured
180-second host deadline, with no unresolved dispatch or unsupported-instruction
stop. All 22 main-image targets called by the bank module have emitted bodies,
not abort stubs. This validates this observed callback path, not every bank or
audible output. The main executable still has 675 abort stubs.
Diagnostics and bank-derived outputs must stay local.

### Local browser host and next check

`tools/apply_browser_profile.py` now applies a reversible seven-file overlay to
the pinned page and browser host. It selects `/data/Speed.exe`, isolates OPFS
saves (`save-nfsu1`) and data (`cache-nfsu1`) and uses a dedicated service-worker
cache (`nfsu1-offline-1`). A host-option allowlist preserves the shared GPU,
audio and input interfaces while excluding unsupported NFSU2 options. NFSU2
profile edits, online features, front-end pad synthesis and UI compatibility
claims are disabled. The page's Stop experiment action terminates its workers.

`tools/build_nfsu1_browser.py` bundles the page, game/I/O/preload workers, service
worker and audio worklet with the isolated cached esbuild 0.27.4 installation.
All required assets exist and pass JavaScript syntax checks. It uses the
existing linked module and data; catalog discovery and extraction are not run.
The original upstream package/lockfile remains unchanged; the isolated bundler
has its own integrity lockfile and retained MIT license under `work/toolchain/`.

`tools/serve_nfsu1.py` replaces the unavailable upstream Rust-server launch path
for this experiment. It serves the page, `/game.json`, `/game.wasm`, a 507-entry
`/data-manifest` and range-readable `/data/*` on loopback. It supplies the Wasm
MIME type, COOP/COEP, SHA-256 module revision URLs and immutable private caching
for matching hashes. Stale module requests receive 409. Game files are read-only;
only the expected private Speed.exe symlink is accepted outside the data root.
The file manifest and module identity are fixed for one server run; restart
following a rebuild or data change.

The runtime overlay now additionally pins `dinput_pad.c` and disables its NFSU2
rescan-flag store, front-end state read/key injection and physics-derived jolt
path. Generic DirectInput state/enumeration and force-feedback APIs remain.
The updated module links without recompiling main-image shards; a 30-second
Node check records 1,131 Presents at its last five-second snapshot and exits
124 at the host deadline, without a guest trap.

Actual HTTP-handler checks pass in process, including real module/PE ranges,
isolation headers, metadata revision, manifest, HEAD, 206/416, stale hashes and
path/symlink rejection. This agent sandbox denies socket binding, so no listening
server or browser result is claimed. The current build report is
`out/browser-build.json`; other evidence is in `out/browser-serving-check.json`,
`out/browser-runtime-build.log` and `out/browser-runtime-node.log`.

The next step is the [exact user-run browser check](browser-testing.md): start
`python3 tools/serve_nfsu1.py` in a terminal and open
`http://127.0.0.1:8765/`. No browser was operated. Visible graphics, input,
front-end arrival, audio output and races remain unvalidated. Do not repeat
catalog discovery, data extraction or compiler setup.

## Catalog generated locally

The catalog is a generated analysis artifact, not a prerequisite the user must
obtain from someone else. With no saved copy available, we ran the original
NFSU1 seed and catalog pipeline against an unchanged private copy of the matching
executable. Both original archives remain untouched.

The pipeline preserves aligned-data seeds, callback/code immediates, switch-arm
seeds and `restore_seeds` repairs. It produced **23,617 entries**: 15,362 starts
and 8,255 aliases. This differs from the historical README's 22,751 because the
available pcrecomp revision is newer; it is not claimed to reproduce the missing
historical catalog byte for byte.

Local artifacts:

- `work/analysis/Speed.analysis.exe`: unchanged private executable copy.
- `work/analysis/catalog.json`: cached function/block catalog.
- `work/analysis/catalog.metadata.json`: input, source and tool fingerprints.
- `gen/nfsu1-first-full/`: private initial emission output and diagnostics.

These files must stay ignored and local. No binary or generated game code is
included in distributable project sources.

With the source-built Python dependencies from [toolchain notes](toolchain.md):

```sh
export PYTHONPATH="$PWD/work/toolchain/capstone/bindings/python:$PWD/work/toolchain/pefile"
export LIBCAPSTONE_PATH="$PWD/work/toolchain/capstone"
python3 tools/prepare_game_catalog.py --image work/analysis/Speed.analysis.exe
```

The wrapper checks the binary and pinned source blobs. An unchanged rerun reuses
all four stages rather than repeating discovery. Current source pins are PC
NFSU1 `58d9d4f63d59c941031f91973ae48c2cdb1a42b1` and pcrecomp
`8c92919a99aaf9e129af5787776bca84863468cc`. Source licenses and notices are retained
beside the ignored source snapshots.

## Runtime configuration wired

```sh
python3 tools/apply_runtime_profile.py --upstream work/upstream/nfsu2-web
# Restore the original hand-written runtime files:
python3 tools/apply_runtime_profile.py --upstream work/upstream/nfsu2-web --revert
```

The overlay verifies pinned runtime blobs, retains backups, generates the NFSU1
header and connects entry/identity/text bounds. It supplies the three NFSU1
`CPU *` overrides, disables known NFSU2 address-based diagnostics and mutations,
uses a separate save subdirectory and defaults game files to read-only.
Unknown dispatch/imports and unsupported instructions stop visibly.

Native syntax checks and focused override execution passed. This is a bring-up
overlay, not a complete runtime port. A module now links for Node bring-up with
abort stubs; browser storage isolation and remaining game-specific modules are
unfinished. The `NFSU1_ALLOW_EXPERIMENTAL_BOOT` compile guard remains the overlay
default, and the explicit bring-up build enables it.

## Actual catalog-fed emission

```sh
python3 tools/lift_catalog.py \
  --image work/analysis/Speed.analysis.exe \
  --catalog work/analysis/catalog.json \
  --upstream work/upstream/nfsu2-web \
  --output-dir gen/nfsu1-next
```

Use an empty destination. This emitter reads saved block extents, preserves
alternate overlapping x86 decode contexts, and routes transfers to already
catalogued entries through typed tail dispatch. It never discovers additional
functions. Import metadata uses the upstream signature table with an explicit
[NFSU1 supplement](../profiles/nfsu1-imports.json).

Missing fallthrough edges, truncated targets, unsupported instructions and
unreviewed external transfers are reported instead of hidden behind no-op
stubs. Failed/partial lifts withhold function/import tables. Even clean C emission
would not establish game or browser readiness.

The first complete pass emitted **22,932 bodies**, selected the three external
overrides and rejected **682 entries**. It also reported three unresolved direct
targets. The entry point emitted successfully. Rejections included 478 missing
fallthrough blocks, 20 truncated branches, 23 external transfers and 161 other
instruction/emitter cases. Most have no direct callers, but indirect reachability
prevents declaring them all dead or silently dropping them.

The entry point's static direct-call closure contains 3,305 entries and initially
encountered `fnsave`, `psubq` and `unpcklpd` gaps. `tools/nfsu1_instructions.py`
now covers `psubq`, `paddq`, `unpcklpd`, `unpckhpd`, `fnsave`/`fsave` and
`frstor` (108-byte protected-mode image, stack-order ST via `f80_store`/`f80_load`,
tag word 0, FNINIT reset after save). After these emitters, a full-catalog trap
scan found **no remaining unsupported mnemonics inside the entry closure**.
Outside it, `fnstenv`/`fldenv` and `pswapd` are the next real instruction gaps.

`tools/simd_integration_smoke.py` and `tools/x87_state_smoke.py` check the SIMD
and x87 additions with synthetic native execution, re-lift the known helper/alias
entries (including entry-reachable `0x67dede` and `0x6738ed`), and compile
emitted bodies to WASI objects. Object compile is not a linked module or game
run. The initial full-pass counts above precede these additions; no clean full
lift is claimed (CFG fallthroughs and other rejections remain).

## Wasm compiler and user testing

The installed Android NDK's LLVM19 **does compile real upstream-lifted synthetic
C to Wasm**, which ran successfully in Node. The fixture retains the upstream
guest/runtime memory boundary. This is separate from the older hand-encoded
Wasm experiment and is not a browser or game test.

```sh
python3 tools/wasm_smoke.py --upstream work/upstream/nfsu2-web \
  --cc "$HOME/Library/Android/sdk/ndk/28.0.12674087/toolchains/llvm/prebuilt/darwin-x86_64/bin/clang"
```

The official WASI SDK 34 arm64 macOS archive is unpacked at
`work/toolchain/wasi-sdk-34.0-arm64-macos` (published SHA-256
`9c59398106b417f8f14913380fdf0097a8cc0ff4af9eb3ce0065a859e88d49e9`).
`tools/compile_runtime.py` compiled 55 handwritten runtime objects with it.
The SIMD and x87 smokes compile helper bodies to
`out/simd-integration/bodies.o` and `out/x87-state/bodies.o`. Neither step
links a game module or proves browser readiness.

```sh
PYTHONPATH="$PWD/work/toolchain/capstone/bindings/python:$PWD/work/toolchain/pefile" \
LIBCAPSTONE_PATH="$PWD/work/toolchain/capstone" \
python3 tools/simd_integration_smoke.py --upstream work/upstream/nfsu2-web \
  --wasi work/toolchain/wasi-sdk-34.0-arm64-macos
python3 tools/x87_state_smoke.py --upstream work/upstream/nfsu2-web \
  --wasi work/toolchain/wasi-sdk-34.0-arm64-macos
```

## Current Node bring-up launch

The minimal Node host exercises guest execution with graphics/audio output
dropped. The browser test instructions are separate above. Reuse the selected
main-image and bank emissions:

```sh
J=4 bash tools/build_nfsu1_wasm.sh
NFSU1_DIAGNOSTICS=10 NFSU1_TIMEOUT_MS=180000 \
  node tools/run_wasm_node.mjs work/upstream/nfsu2-web/out/web/nfsu1.wasm
```

The supervisor terminates all workers on a guest failure; exit 124 means the
explicit host deadline was reached. `USER32.dll!CharUpperA` and related bring-up
HLEs live in `runtime/nfsu1_win32.c`, copied into the upstream tree by the build.
The selected main catalog emits 22,944 bodies with 675 abort stubs, and the bank
module emits 28 routines without stubs. The latest detailed findings and private
log names are recorded at the top of this document. No game compatibility is
inferred from synthetic fixtures or frame counts.

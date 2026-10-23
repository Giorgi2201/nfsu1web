# Building and running locally

This is a private bring-up build for the PC NFSU1 1.4 executable. It combines
the pinned `nfsu2-web` runtime/emitter with locally generated code based on
`nfsu1-recompiled` and its pinned `pcrecomp` analysis dependency. It is still
experimental: the user's browser report covers intro clips with sound, profile
creation and reload, profile loading, and starting a race. It does not establish
a completed race or general game compatibility. Synthetic checks and Node
guest runs are separate from browser/game validation.

If this workspace is already built, start it with
`python3 tools/serve_nfsu1.py`; rebuilding or repeating emission is unnecessary.
The steps below describe a fresh setup. Both lift tools require empty output
directories and deliberately refuse to overwrite earlier emissions.

## Prerequisites and source setup

Use Python 3.10 or newer, Node.js, npm, and a C toolchain. The source-only
tests work with Node.js 20+, but the full Wasm Node host was tested with Node.js
25.9. Do not infer full-module support on Node 20 from the test prerequisite.
A full game-module build also needs a WASI SDK with threads, SIMD, exception
handling and tail-call support. The tested workspace used WASI SDK 34; see
[toolchain notes](toolchain.md) for exact flags and setup.

Install the SDK separately from the
[official WASI SDK 34 release](https://github.com/WebAssembly/wasi-sdk/releases/tag/wasi-sdk-34),
choosing the archive for your host. For the tested Apple Silicon macOS setup,
download `wasi-sdk-34.0-arm64-macos.tar.gz`, verify its SHA-256, and extract it:

```sh
shasum -a 256 /path/to/wasi-sdk-34.0-arm64-macos.tar.gz
# Expected: 9c59398106b417f8f14913380fdf0097a8cc0ff4af9eb3ce0065a859e88d49e9
mkdir -p work/toolchain
tar -xzf /path/to/wasi-sdk-34.0-arm64-macos.tar.gz -C work/toolchain
```

The SDK root must contain `bin/clang`, `bin/llvm-objdump` and `share/wasi-sysroot/`.
The build defaults to `work/toolchain/wasi-sdk-34.0-arm64-macos`; use
`WASI=/path/to/sdk` for another location. Other host platforms are unverified.

The three required upstream source snapshots live outside tracked project files.
From the repository root, fetch the fixed revisions:

```sh
python3 tools/fetch_upstreams.py
```

This materializes the selected source and license files for `nfsu2-web`,
`nfsu1-recompiled`, and `pcrecomp` in ignored `work/upstream/`. Each file is
checked against its pinned Git blob hash in `profiles/upstreams.json`; the
source revision is recorded there as well. This is a sparse source snapshot,
not a full repository clone. No upstream repo is added as a submodule or copied
into tracked project files. Verify the snapshot, including local overlay
backups, without network access with:

```sh
python3 tools/fetch_upstreams.py --check
```

The NFSU1 runtime and browser overlays are reversible and idempotent. Apply
them to the pinned source snapshot before building:

```sh
python3 tools/apply_runtime_profile.py --upstream work/upstream/nfsu2-web
python3 tools/apply_browser_profile.py --upstream work/upstream/nfsu2-web
```

They only change hand-written runtime and browser-host files, retaining the
originals and their hashes under the source snapshot's local overlay state.
See `--help` for the matching `--revert` commands. Re-run `--check` after
applying overlays to verify the pinned originals and saved backups.

## Private game inputs and cached analysis

Provide your own matching PC NFSU1 1.4 files. The catalog tool checks the
executable's full SHA-256 and rejects a different build. Keep the executable,
archive, extracted files and generated analysis under ignored `work/`; never
put these in a tracked folder. For example, copy your unchanged executable to
the private analysis directory and stage game data under `work/data/`:

```sh
mkdir -p work/analysis work/data
cp /path/to/your/Speed.exe work/analysis/Speed.analysis.exe
```

For the browser host, `work/data/` must contain the game files it requests and
data directories. Copy the contents of your installation there, including
`Cars`, `FrontEnd`, `Global`, `Tracks`, `Languages`, `fx`, `Sound`, `Movies`,
`SNDSTREAMS` and `SpeechStreams`. Keep the unchanged executable at the analysis
path above and point the browser's expected name at it with the allowed symlink
(skip this command if `work/data/Speed.exe` already exists):

```sh
ln -s ../analysis/Speed.analysis.exe work/data/Speed.exe
```

Sound-bank analysis expects `work/data/Sound/**/*.abk`. Do not include native
Windows plugins or mods in this experiment. The tools read source inputs
without modifying them.

Create a local virtual environment and install the pinned Python dependencies
used by the current cached analysis:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install capstone==5.0.7 pefile==2024.8.26
```

The PC analysis outputs are cached under ignored `work/analysis/`. An unchanged
rerun reuses the four original seed/catalog stages; it does not repeat the
analysis.

Generate the main executable catalog once. The wrapper fingerprints its inputs
and tools and reuses complete stages on later runs:

```sh
python3 tools/prepare_game_catalog.py --image work/analysis/Speed.analysis.exe
```

The resulting catalog and provenance stay in ignored `work/analysis/`. This
uses the original pinned analysis passes locally; no maintainer-generated
catalog is required. If a runtime callback later needs a focused addition,
follow the callback-closure command in [progress.md](progress.md) and write its
result under `work/analysis/`, keeping the baseline catalog intact.

The current working audio path also needs the cached sound-bank analysis and
emission. These commands use the private ABK data above:

```sh
python3 tools/prepare_abk_catalog.py \
  --image work/analysis/Speed.analysis.exe --data work/data
python3 tools/lift_abk_catalog.py \
  --image work/analysis/Speed.analysis.exe --data work/data \
  --output-dir gen/nfsu1-abk
```

## Emit and compile the experimental module

First follow the runtime-observed missing callback chain. This adds the two
focused callback bodies to a derived catalog while preserving the cached base
catalog. Then emit that repaired catalog with the cooperative movie-thread
yield used by the current selection:

```sh
python3 tools/repair_catalog_callbacks.py \
  --image work/analysis/Speed.analysis.exe \
  --catalog work/analysis/catalog.json \
  --entry 0x00448a40 --follow-code-immediates \
  --output-dir work/analysis/callback-closure
python3 tools/lift_catalog.py \
  --image work/analysis/Speed.analysis.exe \
  --catalog work/analysis/callback-closure/catalog.json \
  --base-catalog work/analysis/catalog.json \
  --upstream work/upstream/nfsu2-web \
  --output-dir gen/nfsu1-current \
  --cooperative-yield-entry 0x0063f0a0 \
  --hooks-file work/upstream/nfsu1-recompiled/config/hooks.txt \
  --link-stubs
```

`--hooks-file` emits `guest_hook` before each NFSU1 widescreen site so
`runtime/nfsu1_widescreen.c` can apply FOV/HUD corrections. The current lifter
also scopes five HUD constant operands so menu layout keeps its original
constants; older widescreen emissions must be regenerated. Choose a fresh
`--output-dir` when re-emitting; the lift refuses a nonempty destination.


The emitter consumes the saved catalog; it does not scan for new functions.
`--link-stubs` remains necessary because some entries are unresolved; a stub
aborts if reached and does not count as emitted game code. The current main
emission contains 22,944 bodies and 675 abort stubs. The companion ABK
emission has 28 routines and no ABK stubs. Set `WASI` if your SDK is not at
the workspace default, then compile and link:

```sh
WASI=/path/to/wasi-sdk-34 J=4 bash tools/build_nfsu1_wasm.sh
```

The script defaults to `gen/nfsu1-current`, `gen/nfsu1-abk`,
`work/upstream/nfsu2-web`, and the workspace WASI SDK path. The module and
metadata are written to the source snapshot's ignored `out/web/`. This step
can take time and consume substantial disk space; cached objects are reused
when their source hashes match. It is a bring-up build with visible abort
stubs, not a clean full lift.

## Bundle and serve the browser host

Install the isolated, pinned esbuild before bundling if it is absent, then
bundle the browser host against the linked module and local data:

```sh
npm install --prefix work/toolchain/web-bundler --no-audit --no-fund \
  --ignore-scripts esbuild@0.27.4
python3 tools/build_nfsu1_browser.py
```

The npm step can be skipped if `work/toolchain/web-bundler/node_modules/` is
already present. Start the loopback server with `python3 tools/serve_nfsu1.py`
and open `http://127.0.0.1:8765/` in your browser. Keep the server terminal open;
stop it with Ctrl+C. After changing the module or game data, restart the server
and reload the same address. Browser storage is origin-specific, so keep the
same host and port to retain the created profile. The server exposes local game
files as read-only. See [browser-testing.md](browser-testing.md) for the user
test steps and evidence to record.

## Keep outputs private

The `.gitignore` covers `work/`, `gen/`, `out/`, game executable/archive
extensions, and Python bytecode. Review `git status --ignored --short` before
sharing changes; do not force-add game binaries, extracted assets, catalogs,
analysis logs, generated game C, object files or Wasm modules. Keep upstream
license and notice files alongside their local source trees. The repository's
source and permission record explains the attribution and reuse basis.

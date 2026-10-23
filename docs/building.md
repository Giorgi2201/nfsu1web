# Build and run locally

Run commands from the repository root. This experimental build targets one PC
NFSU1 1.4 executable; see [status](status.md) for compatibility limits. Keep game
files, catalogs, emitted game C, objects and Wasm under ignored `work/`, `gen/`
and `out/`. Do not modify original inputs or distribute these private outputs.

For an existing build, start with `python3 tools/serve_nfsu1.py --check` and
`python3 tools/serve_nfsu1.py`. Rebuilding and analysis are unnecessary unless
inputs or source changed. Optional HD fonts and launch options are in
[settings](settings.md); validation commands and browser checks are in
[testing](testing.md).

## Tools and pinned sources

Use Python 3.10+, Node.js 20+, npm, Bash, a C compiler, `make`, `tar`, `shasum`
and `xargs`. Full-module Node execution was checked with Node 25.9; the Node 20
requirement covers source tests. Apple Silicon macOS is the tested build host;
other hosts remain unverified. Allow space for the installation, SDK, generated
code and object cache.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install capstone==5.0.7 pefile==2024.8.26
python3 tools/fetch_upstreams.py
python3 tools/apply_runtime_profile.py --upstream work/upstream/nfsu2-web
python3 tools/apply_browser_profile.py --upstream work/upstream/nfsu2-web
python3 tools/fetch_upstreams.py --check
```

The bootstrap materializes sparse, pinned `nfsu2-web`, `nfsu1-recompiled` and
`pcrecomp` snapshots in `work/upstream/`; revisions and blob hashes are in
`profiles/upstreams.json`. Overlays retain verified originals and support
`--revert`; consult each tool's `--help`. The final `--check` also verifies
saved overlay backups without network access.

If using this workspace's source-built Python dependencies instead of a venv,
set these variables before running analysis, emission or lifter checks:

```sh
export PYTHONPATH="$PWD/work/toolchain/capstone/bindings/python:$PWD/work/toolchain/pefile"
export LIBCAPSTONE_PATH="$PWD/work/toolchain/capstone"
```

That Capstone snapshot is 5.0.7 (`52c66920fc7bfa15fd9626dfd9f646c698aaa99b`);
pefile is 2024.8.26 (`4b3b1e2e568a88d4f1897d694d684f23d9e270c4`). Their local
provenance files and licenses stay beside the sources. To rebuild the existing
Capstone source on macOS, run this from `work/toolchain/capstone/`:

```sh
make -j4 CAPSTONE_ARCHS=x86 CAPSTONE_X86_ATT_DISABLE=yes \
  CAPSTONE_BUILD_CORE_ONLY=yes CAPSTONE_STATIC=no CAPSTONE_SHARED=yes
ln -s libcapstone.5.dylib libcapstone.dylib  # Only if the alias is absent.
```

Install [WASI SDK 34](https://github.com/WebAssembly/wasi-sdk/releases/tag/wasi-sdk-34)
for your host. The tested Apple Silicon archive is
`wasi-sdk-34.0-arm64-macos.tar.gz`, SHA-256
`9c59398106b417f8f14913380fdf0097a8cc0ff4af9eb3ce0065a859e88d49e9`.

```sh
shasum -a 256 /path/to/wasi-sdk-34.0-arm64-macos.tar.gz
mkdir -p work/toolchain
tar -xzf /path/to/wasi-sdk-34.0-arm64-macos.tar.gz -C work/toolchain
```

The SDK must contain `bin/clang`, `bin/llvm-objdump` and `share/wasi-sysroot/`.
The build defaults to `work/toolchain/wasi-sdk-34.0-arm64-macos`; set `WASI` for
another location. The script supplies the required threads, SIMD, bulk-memory,
nontrapping conversion, tail-call and exception-handling flags.

## Private game inputs

Supply your own matching installation. No game files or download source are
provided. The required `Speed.exe` is 3,178,496 bytes, SHA-256:

```text
c0fad450912952f53809a54690d235aa8b4e25b9f46650693c7cbee1b4c074b7
```

This full digest was measured locally; the pinned PC upstream publishes an
abbreviated matching digest. The selected PE has image base `0x00400000`,
SizeOfImage `0x00394368` and entry RVA `0x00270cb5`. Analysis checks the full
hash. A different executable needs separate compatibility work; bypassing the
check does not make its addresses compatible. Details live in
`profiles/nfsu1-pc.json`.

```sh
shasum -a 256 /path/to/your/Speed.exe
mkdir -p work/analysis work/data
cp /path/to/your/Speed.exe work/analysis/Speed.analysis.exe
ln -s ../analysis/Speed.analysis.exe work/data/Speed.exe
```

Skip the symlink command if that path already exists. Copy the installation's
`Cars`, `FrontEnd`, `Global`, `Tracks`, `Languages`, `fx`, `Sound`, `Movies`,
`SNDSTREAMS` and `SpeechStreams` into `work/data/`, preserving filenames and
structure. ABK analysis reads `Sound/**/*.abk`. Native Windows DLL/ASI plugins
cannot be installed directly into the browser runtime.

## Cache analysis and emit

The analysis wrappers fingerprint inputs and tools, reuse completed stages and
keep catalogs/provenance local. Do not rerun discovery for every build. The
callback repair creates a derived catalog while preserving the cached base.
Emission consumes these saved ranges and requires empty output directories.

```sh
python3 tools/prepare_game_catalog.py --image work/analysis/Speed.analysis.exe
python3 tools/prepare_abk_catalog.py \
  --image work/analysis/Speed.analysis.exe --data work/data
python3 tools/lift_abk_catalog.py \
  --image work/analysis/Speed.analysis.exe --data work/data \
  --output-dir gen/nfsu1-abk
python3 tools/repair_catalog_callbacks.py \
  --image work/analysis/Speed.analysis.exe \
  --catalog work/analysis/catalog.json \
  --entry 0x00448a40 --follow-code-immediates \
  --output-dir work/analysis/callback-closure
python3 tools/lift_catalog.py \
  --image work/analysis/Speed.analysis.exe \
  --catalog work/analysis/callback-closure/catalog.json \
  --base-catalog work/analysis/catalog.json \
  --upstream work/upstream/nfsu2-web --output-dir gen/nfsu1-current \
  --cooperative-yield-entry 0x0063f0a0 \
  --hooks-file work/upstream/nfsu1-recompiled/config/hooks.txt --link-stubs
```

Hooks and operand transformations provide scoped widescreen/HUD/font behavior;
older emissions can require regeneration when these change. `--link-stubs` is
still required: unresolved routines abort when reached. Successful compilation
alone does not establish game compatibility.

## Compile, bundle and serve

```sh
J=4 bash tools/build_nfsu1_wasm.sh
npm install --prefix work/toolchain/web-bundler --no-audit --no-fund \
  --ignore-scripts esbuild@0.27.4
python3 tools/build_nfsu1_browser.py
python3 tools/serve_nfsu1.py --check
python3 tools/serve_nfsu1.py
```

Set `WASI=/path/to/sdk`, `GEN=/absolute/path/to/emission` or `ABK_GEN=...` before
the build command to override defaults. Cached guest objects are reused when
source hashes match; `J` controls guest compilation jobs. Skip npm installation
when the pinned bundler is already available. Outputs are under the upstream
snapshot's ignored `out/web/` and `web/dist/`.

Open `http://127.0.0.1:8765/` yourself. The server provides cross-origin isolation
and read-only game data; opening HTML directly is insufficient. The browser
needs WebGPU, shared memory/storage and the Wasm features checked at startup.
The default module starts with 1 GiB shared memory and permits growth to 4 GiB;
browser/GPU memory is additional. Follow [testing](testing.md) for game checks.

After runtime changes, rebuild Wasm and the browser bundle; after browser-only
changes, rebuild the bundle. Re-emission needs a fresh ignored directory and
an explicit `GEN`/`ABK_GEN`. Restart the server and reload after changing Wasm or
data. Keep the same host and port to retain origin-specific browser saves.
Review `git status --ignored --short` before sharing; never force-add private
inputs, catalogs, emitted game code, binaries or logs. Preserve source licenses.

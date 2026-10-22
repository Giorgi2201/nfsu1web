# Local lifter toolchain and compiled smoke

For a fresh setup and the complete game-module/browser pipeline, use the
[build guide](building.md). This page records the original source-built local
toolchain and focused synthetic checks; it is historical provenance rather
than a list of prerequisites still missing from the working build.

## Current result

On 2026-10-21, `tools/run_lifter_smoke.py` passed **real upstream C emission,
native compilation and execution**. It uses the catalog adapter instead of the
web lifter's discovery method. Original synthetic fixtures cover arithmetic,
uint32 wraparound, a three-block conditional with both paths, guest return-slot
handling, EAX/ESP/EIP results and preserved ECX.

This closed the initial dependency/emission gap. Subsequent work generated the
real catalog locally, applied the NFSU1 runtime overlay and compiled the synthetic
lift to Wasm using the installed NDK compiler. See [current progress](progress.md)
for the distinction between those results and a full runtime/browser build.
No new automated suite was added.

## Available local source snapshots

All downloaded sources and build outputs are under ignored `work/` and `out/`.
These are selected source snapshots, **not Git checkouts**:

| Component | Pinned version/revision | Local location |
| --- | --- | --- |
| Web emitter and CPU/runtime files | `th0mk/nfsu2-web` `31da468582c3de14fd6f4233831f62816e2df83d` | `work/upstream/nfsu2-web/` |
| Capstone | 5.0.7, `52c66920fc7bfa15fd9626dfd9f646c698aaa99b` | `work/toolchain/capstone/` |
| pefile | 2024.8.26, `4b3b1e2e568a88d4f1897d694d684f23d9e270c4` | `work/toolchain/pefile/` |

The selected web files' Git blob hashes matched the pinned repository tree before
the reversible runtime overlay was applied; `SNAPSHOT.json` lists that baseline.
Overlay backups and applied hashes are in `.nfsu1-profile/`. Capstone provenance and build
flags are in its `SOURCE-PROVENANCE.json` and `SOURCE_BUILD.json`. Its materialized
text files have an additional trailing newline, with no semantic source edits.
Capstone uses full x86 tables; other architectures and AT&T syntax are disabled.
Upstream licenses remain beside the downloaded sources.

Shell access to package hosts cannot resolve DNS in this environment. Source
files were fetched through the connected GitHub tools, then built with the
installed Apple Clang. No package or game binaries were downloaded.

## Run the focused check here

From the repository root:

```sh
PYTHONPATH="$PWD/work/toolchain/capstone/bindings/python:$PWD/work/toolchain/pefile" \
LIBCAPSTONE_PATH="$PWD/work/toolchain/capstone" \
python3 tools/run_lifter_smoke.py --upstream work/upstream/nfsu2-web
```

Expected output:

```text
PASS: real upstream lift, arithmetic/wraparound, both branch paths, CPU ABI
```

The script emits only synthetic C and its native executable into
`out/lifter-smoke/`, using `clang -std=c11 -O2`. It does not read a game binary.
It clears optional optimization environment overrides and forces `RETEIP=1`
inside its own process so return-slot checks have a reproducible baseline.
On another machine, install the pinned upstream Python dependencies normally and
pass a matching upstream checkout. The local snapshots are not bundled in the
repository deliverables.

The Capstone native build used:

```sh
make -j4 CAPSTONE_ARCHS=x86 CAPSTONE_X86_ATT_DISABLE=yes \
  CAPSTONE_BUILD_CORE_ONLY=yes CAPSTONE_STATIC=no CAPSTONE_SHARED=yes
ln -s libcapstone.5.dylib libcapstone.dylib
```

## Compiler discovery and later WASI setup

The matching executable is selected and its catalog has been generated and
cached. The Android NDK at
`~/Library/Android/sdk/ndk/28.0.12674087/toolchains/llvm/prebuilt/darwin-x86_64/`
provides LLVM19 with Wasm support, missed by the initial standard-location scan.
`tools/wasm_smoke.py` successfully compiled actual lifted synthetic C against
the upstream CPU header and ran the Wasm in Node.

WASI SDK 34 is available under `work/toolchain/wasi-sdk-34.0-arm64-macos`.
Handwritten runtime objects and the SSE-helper object smoke both compile with
it; see [current progress](progress.md). A local browser build now exists;
browser testing remains reserved for the user.

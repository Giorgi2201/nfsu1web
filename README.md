# NFS Underground 1 browser integration

This repository is an experimental integration of the **PC** Need for Speed
Underground 1 executable with the `nfsu2-web` browser runtime. It is not a
finished port. The current user-reported milestone is intro video and audio,
profile creation that persists through reload, profile loading, and starting a
race. A completed race, broad compatibility, and reliable rendering and input
are still unverified. See [current progress](docs/progress.md) and the
[compatibility assessment](docs/compatibility.md).

## Build overview

The build uses three pinned upstream sources, materialized outside the tracked
source tree under ignored `work/upstream/`:

| Repository | Pinned revision | Purpose |
| --- | --- | --- |
| [`th0mk/nfsu2-web`](https://github.com/th0mk/nfsu2-web/tree/31da468582c3de14fd6f4233831f62816e2df83d) | `31da468582c3de14fd6f4233831f62816e2df83d` | Browser runtime, CPU ABI, and C emitter |
| [`codepdbh/nfsu1-recompiled`](https://github.com/codepdbh/nfsu1-recompiled/tree/58d9d4f63d59c941031f91973ae48c2cdb1a42b1) | `58d9d4f63d59c941031f91973ae48c2cdb1a42b1` | Original PC NFSU1 analysis and ABK routines |
| [`sp00nznet/pcrecomp`](https://github.com/sp00nznet/pcrecomp/tree/8c92919a99aaf9e129af5787776bca84863468cc) | `8c92919a99aaf9e129af5787776bca84863468cc` | Pinned PE analysis and x86 disassembler dependency |

The bootstrap materializes only the required text sources and license files
from these exact revisions into ignored `work/upstream/`; it does not clone the
full repositories. They are neither vendored nor added as submodules. Local
runtime overlays are applied reversibly to the `nfsu2-web` source snapshot.
Licenses, attribution, reuse permission notes, and inspected source hashes are
summarized in [NOTICE.md](NOTICE.md), with details in
[source-permissions.md](docs/source-permissions.md) and
[source-manifest.json](docs/source-manifest.json).

The source-only checks do not require game files or upstream sources:

```sh
python3 -m unittest discover -s tests -v
node --test tests/guest_abi.test.mjs
```

Python 3.10+ and Node.js 20+ are sufficient for those checks. The full Wasm
Node host was tested with Node.js 25.9; do not infer that the full module runs
under Node 20 from the source-only check requirement.

Start with the [build guide](docs/building.md). It covers upstream setup,
private game inputs, catalog generation, code emission, Wasm compilation and
local browser serving. Game files, catalogs, ABK analysis, generated game code,
Wasm modules and build output must stay in ignored `work/`, `gen/` or `out/`;
they are not repository deliverables. Do not modify or redistribute original
game files or generated proprietary code.

For the latest browser checks and what remains unverified, read
[browser-testing.md](docs/browser-testing.md). Historical findings and
diagnostics are in [progress.md](docs/progress.md); the original runtime
integration checklist is in [runtime-profile.md](docs/runtime-profile.md).

The main project areas are `tools/` (catalog, emission, build and host
utilities), `runtime/` (NFSU1-specific host code), `profiles/` (machine-readable
runtime/input pins), `tests/` (small source-only checks), `docs/` (findings and
instructions), `poc/` (synthetic Wasm ABI fixture), and `patches/` (upstream
license notices). Private `work/`, `gen/`, and `out/` directories hold local
inputs, cached analysis, emitted code and build evidence.

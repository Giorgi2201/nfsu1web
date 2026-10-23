# Source, licenses and permission record

Inspected on 2026-10-21. This records repository evidence and the user's supplied
authorization; it does not treat public visibility as a license.

| Repository/component | Published evidence at inspected revision | Handling in this workspace |
| --- | --- | --- |
| `codepdbh/nfsu1-recompiled` | No root LICENSE/COPYING file found in the recursive tree. `ports/dxvk_android/DXVK-LICENSE` applies to DXVK, not automatically to the project. | User reports personal maintainer permission, conditioned on attribution. Original analysis scripts copied into ignored `work/upstream/` and executed to generate the cached local catalog. |
| `th0mk/nfsu2-web` | [MIT](https://github.com/th0mk/nfsu2-web/blob/31da468582c3de14fd6f4233831f62816e2df83d/LICENSE), copyright 2026 th0mk; portions copyright 2026 Talha Müderrisoğlu. | Selected emitter/runtime/browser source snapshot downloaded into ignored `work/` with its full license retained, used by focused checks and the experimental local game build. |
| `antoxa2584x/nfsu1-sw` game-specific root sources | No root LICENSE/COPYING file found in the recursive tree. | User reports personal maintainer permission, conditioned on attribution. No source copied. |
| Vendored `xboxrecomp/` | [MIT](https://github.com/antoxa2584x/nfsu1-sw/blob/d597e08f88e3f415eb44366b22e75054f2dfd15d/xboxrecomp/LICENSE), copyright 2026 sp00nz, with explicit [third-party exceptions](https://github.com/antoxa2584x/nfsu1-sw/blob/d597e08f88e3f415eb44366b22e75054f2dfd15d/xboxrecomp/NOTICE). | Not vendored here. Do not assume the MIT file covers the whole repository. |
| xemu-derived MCPX APU and NV2A register files inside xboxrecomp | `NOTICE` lists LGPL-2.1-or-later components and copyrights; license text shipped in `LICENSES/`. | Not reused. A future browser APU port needs its own third-party compliance review. |
| pcrecomp analysis modules | [MIT license](https://github.com/sp00nznet/pcrecomp/blob/8c92919a99aaf9e129af5787776bca84863468cc/LICENSE) verified at `8c92919a99aaf9e129af5787776bca84863468cc`. | Selected PE/disassembly modules and license copied into ignored `work/upstream/pcrecomp/` for catalog generation. Legacy native-runtime/lift32 patch chains remain outside this reuse. |
| Source-built Capstone 5.0.7 | [BSD-style LICENSE.TXT](https://github.com/capstone-engine/capstone/blob/52c66920fc7bfa15fd9626dfd9f646c698aaa99b/LICENSE.TXT) and LLVM component license, both retained locally. | Public source downloaded into ignored `work/toolchain/capstone/`; full x86 native build used for synthetic lifting. |
| pefile 2024.8.26 | [MIT](https://github.com/erocarrera/pefile/blob/4b3b1e2e568a88d4f1897d694d684f23d9e270c4/LICENSE), copyright Ero Carrera. | Public source and license downloaded into ignored `work/toolchain/pefile/`. |

The user stated during this session: “i contacted maintainers personally, they
okay if we mention them in any work we might do”. We accept that as user-reported
permission for the requested work. No maintainer correspondence was independently
examined, and no broader permission terms or rights to third-party/game content
are inferred. There is no additional approval gate for continuing this work.

Credit **codepdbh**, **th0mk**, **antoxa2584x**, **sp00nz/sp00nznet**, and
**Talha Müderrisoğlu** where their projects or components contribute. Preserve
file-specific notices on future copies. Personal maintainer permission does not
replace third-party license terms.

Deliverable adapters and fixtures were newly written; the runtime overlay also
contains anchored upstream excerpts under the retained
`patches/nfsu2-web.LICENSE` notice. A selected MIT-licensed web emitter/runtime source snapshot and its
license were also downloaded into ignored `work/upstream/nfsu2-web/` for the
compiled synthetic smoke; those source files are not vendored in deliverables.
See [toolchain provenance](toolchain.md). No upstream license is represented as
licensing original game content.
The 2026-10-22 bring-up additions use that same pinned runtime revision:
the original startup observer uses the CPU registry declarations from
`win32_ext.c` and the existing `guest_backtrace` helper; the anchored COM overlay
corrects the `D3DCAPS9` write boundary and disables NFSU2 menu-address writes.
The source manifest records these interfaces and the Microsoft ABI references.
The retained MIT notice covers upstream excerpts; no game instructions are
included in these additions or the synthetic capability-boundary check.
The focused callback repair tool invokes the same pinned pcrecomp disassembler
and uses the PC project's mov/push code-seed probe rule only for newly required
callbacks. These sources remain under ignored `work/` with the notices described
above; the augmented catalog and emitted callbacks remain private local output.
The browser bring-up reuses th0mk's MIT-licensed page and generic WebGPU,
audio, input and WASI worker host at the same pinned revision. Seven browser
files are transformed by a reversible overlay; their canonical Git blobs and
the additional `dinput_pad.c` runtime pin are recorded in the manifest. Original
source notices and the retained MIT license cover those excerpts. The local
loopback server and build wrapper are original integration tooling. The isolated
esbuild 0.27.4 npm packages retain their MIT license, lockfile and package
integrities under ignored `work/toolchain/web-bundler/`; no upstream package or
lockfile is changed. Built page assets and game modules remain local and ignored.
The sound-bank pipeline also invokes codepdbh's pinned `scripts/abk_module.py`
and adapts the content-matching approach in `src/runtime/abk_code.c` to the web
runtime's `CPU *` ABI. Both original files are retained under ignored `work/`
at revision `58d9d4f63d59c941031f91973ae48c2cdb1a42b1`, with blob hashes in the
manifest. This reuse is covered by the same user-reported maintainer permission
with attribution. All bank instruction bytes, derived module/catalog/matching
tables, emitted routines and compiled game modules remain private local output.
Do not commit original executables, XBE files, assets, real analysis catalogs,
sound-bank instruction bytes, game-derived C, or modules compiled from that C.
The ignore rules provide basic protection, not a substitute for reviewing files.

## Repository packaging

`tools/fetch_upstreams.py` materializes the public text sources listed in
`profiles/upstreams.json`, at the fixed revisions above, under ignored
`work/upstream/`. Every file is checked against its Git blob hash before writing;
existing files are not overwritten. Offline checks accept canonical originals
retained by the reversible overlays. Full upstream repositories are neither
vendored nor added as submodules. `NOTICE.md` summarizes attribution and
`patches/` retains the nfsu2-web and pcrecomp MIT notices. The PC project's
reported permission is recorded as reported permission, without assigning it
a license it did not publish.

The profile-creation date/time helpers are original code using the documented
Microsoft Win32 API contracts (links in the source manifest). On Wasm, they
reuse the existing pinned `runtime/web/tz.c` timezone adapter through
`wasm_plat.h`; the same retained nfsu2-web MIT notice applies. Their focused
smoke uses synthetic data, with no game bytes or generated game functions.

The startup movie adapter reuses the notification-hook design and fresh-input
baselining from th0mk's MIT-licensed `runtime/intro.c` at the same pinned
revision (blob `652cff8089910618f033fdcdfe0908e26be8a076`). The retained
MIT notice applies. NFSU1 interface addresses were verified locally; only
handwritten host logic and interface metadata are committed. Original game
inputs and generated functions are unchanged; linked outputs remain local.

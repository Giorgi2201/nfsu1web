# Source, licenses and permission record

This records inspected license evidence and maintainer permission reported by
the project author.
[Source manifest](source-manifest.json) and [upstream pins](../profiles/upstreams.json)
contain exact revisions, file hashes and interface references. Public visibility
alone is not permission to reuse source or artwork.

## Authorization and attribution

Maintainers of the referenced repositories granted permission to reuse their
work with attribution, as reported by the project author. Correspondence was
not independently examined. This permission does not replace third-party
licenses or grant rights to game content or independently authored mod artwork.

| Source | Evidence and reuse |
| --- | --- |
| `codepdbh/nfsu1-recompiled` | No root license found; maintainer permission reported with attribution. Revision `58d9d4f63d59c941031f91973ae48c2cdb1a42b1` supplies analysis, ABK analysis/matching, widescreen source, HUD data and hooks. |
| `th0mk/nfsu2-web` | MIT, copyright 2026 th0mk; portions copyright 2026 Talha Müderrisoğlu. Revision `31da468582c3de14fd6f4233831f62816e2df83d` supplies the emitter, runtime and browser host. Notice: [nfsu2-web.LICENSE](../patches/nfsu2-web.LICENSE). |
| `sp00nznet/pcrecomp` | MIT at `8c92919a99aaf9e129af5787776bca84863468cc`; selected PE/disassembly modules support local catalog generation. Notice: [pcrecomp.LICENSE](../patches/pcrecomp.LICENSE). Legacy native-runtime/lift32 patch chains are not reused. |
| `antoxa2584x/nfsu1-sw` | No game-specific root license found; maintainer permission reported with attribution. No source copied. Its separately MIT-licensed `xboxrecomp/` at `d597e08f88e3f415eb44366b22e75054f2dfd15d` does not license the whole repository. xemu-derived LGPL APU/NV2A components are not reused. |
| Capstone 5.0.7 | Source build at `52c66920fc7bfa15fd9626dfd9f646c698aaa99b`; BSD-style and LLVM component notices retained in ignored `work/toolchain/capstone/`. |
| pefile 2024.8.26 | MIT, Ero Carrera, at `4b3b1e2e568a88d4f1897d694d684f23d9e270c4`; source and license retained in ignored `work/toolchain/pefile/`. |
| esbuild 0.27.4 | MIT; isolated npm packages, license, lockfile and package integrities retained in ignored `work/toolchain/web-bundler/`. |

Credit **codepdbh**, **th0mk**, **Talha Müderrisoğlu**, **sp00nz/sp00nznet** and
**antoxa2584x** where their work contributes. Preserve file-specific notices.

## Runtime and browser adaptations

Reversible overlays adapt the pinned MIT runtime/browser sources for the
`CPU *` ABI, COM boundaries, graphics/resizing, input, saves, date/time,
startup movies, shader skinning and depth-state handling. Browser settings
and the original `browser/` menu reuse the host's existing interfaces without
copied game artwork or fonts. The source manifest identifies individual reused
files and blobs, including `intro.c`, `tz.c`, `gpu_web.c`, `vsemu_wgsl.inc`,
`encoder.ts`, `com.c` and the emitter's guarded jump-table implementation.
Retained MIT notices cover anchored excerpts and adapted source. Bounded COM
draw diagnostics are original adapter logic using existing runtime accessors.
The Online timing correction retargets `runtime/winsock.c`'s existing
MIT-licensed monotonic NetTick adapter to NFSU1's locally identified thunk;
the runtime revision and blob are recorded in the source manifest. Protocol
corrections use local PC 1.4 analysis; no emitted game code is distributed.

The NFSU1 widescreen port comes through the pinned PC project. Its patch
semantics derive from ThirteenAG's MIT WidescreenFixesPack; retain
[WidescreenFixesPack.LICENSE](../patches/WidescreenFixesPack.LICENSE).
The license/HUD/frontend reference pin is
`708f7528fb8b54c79d4ac3c6071ea7ccc01ae162`; it does not establish which
ThirteenAG revision the PC port originally used.

## HD fonts

`runtime/nfsu1_fonts.c` and `tools/font_operands.py` adapt Aero_'s
NFSHDContentSupport under **GPL-3.0-only**, separately from this project's MIT
contributions. Source commit: `877a8f0fb817d5bab05c862d261860ed422441fe`;
`SOURCE/NFSU/dllmain.cpp` blob: `6534741da7739e9f3ddbe5ea21d683bb0068cb10`.
The full license is [NFSHDContentSupport.LICENSE](../patches/NFSHDContentSupport.LICENSE),
upstream blob `e62ec04cdeece724caeeeeaeb6ae1f6af1bb6b9a`. The adapter scopes
logical dimensions and mip selection to four imported font hashes. No ASI
binaries or game functions are included.

Raze's NFSU-HD FONTS archive `13d395-MOD.7z` supplies optional DDS artwork
for private local import. Artwork and prepared containers stay ignored under
`work/mods/`; original inputs remain unchanged. No artwork redistribution
permission or combined game-derived Wasm distribution permission is inferred.
The original preparer uses the documented PC TPK layout from xan1242's MIT
`xnfstpktool` at `bfd46d4e71df7a23db4f4e43c51aa37db2839fee` and JDLZ format
references recorded in the manifest. It preserves compressed streaming tables
and untouched textures, using an original literal-only JDLZ encoder for fonts.

## Packaging and distribution

Original contributions by Yurii Smetanka are MIT under [LICENSE](../LICENSE),
subject to the distinct third-party terms above. [NOTICE.md](../NOTICE.md)
summarizes credits. The root license grants no sublicense to upstream or game
material; GPL font adaptations retain their own terms.

This is an independent, unofficial compatibility experiment, without EA
authorization, affiliation or endorsement. Need for Speed and associated marks
belong to their respective owners. Use your own legally obtained game inputs;
maintainer permission does not authorize distribution of EA or third-party content.

`tools/fetch_upstreams.py` downloads pinned public text sources into ignored
`work/upstream/`, checks Git blob hashes and preserves originals for reversible
overlays. Full repositories are neither vendored nor submodules. Synthetic
fixtures contain authored data. Checks that extract actual emitted functions
keep those bodies in temporary or ignored local files.

Do not commit game executables/assets, real catalogs, bank instruction bytes,
game-derived C or compiled game modules. Review ignored artifacts before sharing;
ignore rules alone do not establish permission or prevent accidental disclosure.

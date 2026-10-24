# Attribution and source boundaries

Original contributions by Yurii Smetanka are licensed under the root
[MIT license](LICENSE). That grant covers only rights held by the author;
third-party material below retains its own terms. See
[source and distribution terms](docs/source-permissions.md).

This integration builds on these projects at fixed revisions:

- **th0mk/nfsu2-web**, by th0mk, with portions by Talha Müderrisoğlu:
  browser runtime, CPU ABI and emitter. Upstream excerpts in the overlays
  retain the [MIT notice](patches/nfsu2-web.LICENSE).
- **codepdbh/nfsu1-recompiled**, by codepdbh: PC NFSU1 analysis, seed rules
  and sound-bank parser/matching approach. Reuse follows maintainer permission
  reported by the project author, with attribution; no root license was present
  at the pinned revision.
- **sp00nznet/pcrecomp**, by sp00nz: PE analysis and x86 disassembly.
  Its [MIT notice](patches/pcrecomp.LICENSE) is retained.
- **ThirteenAG/WidescreenFixesPack**, by ThirteenAG: NFS Underground
  widescreen patch semantics and HUD layout data, through the PC project's
  widescreen port. Its [MIT notice](patches/WidescreenFixesPack.LICENSE)
  is retained. The PC port also retains the permission basis described above.
- **AeroWidescreen/NFSHDContentSupport**, by Aero_: HD font scaling
  semantics adapted in `runtime/nfsu1_fonts.c` and `tools/font_operands.py`.
  These adaptations are GPL-3.0; the full
  [license](patches/NFSHDContentSupport.LICENSE) is retained.
  Optional local font artwork is by Raze (NFSU-HD FONTS); it is not bundled.

The Xbox investigation also referenced **antoxa2584x/nfsu1-sw**. No source from
that repository or its vendored Xbox runtime is included in this integration.

The [source manifest](docs/source-manifest.json),
[fetch inventory](profiles/upstreams.json) and
[permission record](docs/source-permissions.md) identify revisions, hashes,
file-specific terms and toolchain dependencies. Downloaded upstream files keep
their own licenses alongside their ignored local source snapshots.

These notices do not license game content. Original game binaries, assets,
catalogs, generated game functions and compiled game modules are excluded from
this repository. Upstream licenses apply to their respective components;
there is no blanket license grant for all material mentioned here.

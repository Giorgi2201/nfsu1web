# NFSU1 mod compatibility investigation

Investigated 2026-10-23 against this project's current local browser architecture.
Research only: no mods installed, mod binaries executed, or browser tests run.
These are implementation candidates, not demonstrated game compatibility.

## Architecture constraints

- The build compiles one exact PC 1.4 executable into Wasm using the saved
  catalog and `void(CPU *)` ABI. Patching x86 instructions after compilation
  does not change the compiled code. Port patch semantics through overrides,
  guest-data changes, or emission-time transformations; preserve original inputs.
- Native Windows DLL/ASI files cannot be dropped into this runtime. Arbitrary
  code caves and native function pointers need explicit guest dispatch support.
  Unknown dispatch targets abort; there is no general interpreter fallback.
- D3D9 COM emulation feeds shared queues and WGSL shaders into WebGPU.
  Windows graphics injectors cannot load directly.
- Browser texture replacement is explicitly stubbed out in the pinned
  `runtime/web/null_platform.c`; native upstream texture-pack support does not
  establish browser support. Direct game-data replacements are a separate route.
- The browser overlay disables NFSU2 Online, LAN/free-roam integration and player
  controls. Existing upstream networking does not establish NFSU1 compatibility.
- NFSU2 widescreen addresses and mode-table writes are not NFSU1 support.
  The current overlay disables the menu writes and retains native requested size.

Local evidence: [runtime overlay](../tools/apply_runtime_profile.py),
[browser overlay](../tools/apply_browser_profile.py),
[build script](../tools/build_nfsu1_wasm.sh),
[input/profile metadata](../profiles/nfsu1-pc.json), and
[build guide](building.md). Some profile status fields are historical; use the
current implementation and progress notes when assessing completed features.

## Compatibility matrix

Effort is engineering judgment after a reliable baseline, excluding permission
delays and broad game validation. It is not a commitment or measured estimate.

| Mod | Verified contents and adaptation | Rights / blockers | Rough effort |
| --- | --- | --- | --- |
| [Widescreen Fix](https://github.com/ThirteenAG/WidescreenFixesPack/tree/master/source/NFSUnderground.WidescreenFix) | Source-backed ASI. Port NFSU1 FOV, HUD, frontend and movie corrections. Keep browser input, saves and scheduling with existing host adapters. | MIT; preserve notices. Highest priority. | 3–7 days |
| [HD Reflections](https://nfsmods.xyz/mod/3363) | Inspected NFSU archive contains ASI + INI, no replacement artwork. Port reflection dimensions, brightness and selected LOD/skybox fixes. | GPL-3. Same 1.4 executable size/entry point as ours, but validate each patch site. | 2–5 days basic; 1–2 weeks broader |
| [HD Fonts](https://nfsmods.xyz/mod/6370) | Latest archive includes fonts and gauges: DDS artwork, Binary scripts, HD Content Support, TexWizard and an InGameB pack. Port font scaling; merge textures offline or port named-texture loading. | Artwork redistribution grant not found. Support code licenses are separate. | 2–4 days fonts; 4–8 with gauges |
| [Redux 2K](https://www.nexusmods.com/needforspeedunderground/mods/2) | v1.0, Redux2K.tpf, 345.7 MB; TexMod. Requires extraction/matching and replacement support, or offline repacking. First texture candidate. | Page prohibits reupload; modification/asset reuse needs permission. Instructions say SPEED2.EXE: verify actual target textures. | 1–2 weeks shared infrastructure, then evaluation |
| [Redux 4K](https://www.nexusmods.com/needforspeedunderground/mods/3) | v1.0, Redux4K.tpf, 769.8 MB; TexMod. Alternative to 2K, not an additional layer. | Same permission/infrastructure blockers; greater memory/download cost. | Shared infrastructure; lower priority |
| [NFS Underground Remastered](https://www.nexusmods.com/needforspeedunderground/mods/4) | v1.0, NFSURemasteredMod.tpf, 675.4 MB; TexMod. Alternative art direction. | Same restrictions. Exact texture inventories not inspected. | Shared infrastructure, then evaluation |
| [Free Roam Beta 2.0](https://nfsmods.xyz/mod/577) | GLOBALB.BUN/.lzc and track replacements plus Windows Wrong Way Remover. Use local assets; replace patcher behavior with a runtime override. | No redistribution grant found. Broken minimap, limited traffic/respawn, unfinished roads and missing textures are known upstream limitations. | 2–5 days prototype |
| [Extra Options 3.0.1.1337](https://github.com/ExOptsTeam/NFSUExOpts/releases/tag/v3.0.1.1337) | Open-source ASI with memory patches, code caves and vtable changes. Port selected fixes/options. Desktop windowing/multiple-instance features have little browser value. | GPL-3. Avoid duplicating existing movie/input behavior. | 1–3 days subset; 1–3 weeks broader |
| [Extended Customization 1.2](https://nfsmods.xyz/mod/3692) | x86 ASI, INI, loader and Cheat Engine table. Rim, paint, decal, engine and LOD changes require reconstructed code ports. No source found. | Author explicitly forbids redistribution/reupload. Reported paint/startup conflicts need investigation. | 1–3 weeks, uncertain |
| [Unlimiter 1.0.0.400 alpha](https://nfsmods.xyz/mod/2283) | Source-backed ASI relocating car tables and patching car counts/hooks. Use guest addresses and runtime overrides. More-than-20-car selection remains unfinished. | No standard root license found; "No rights reserved" text leaves scope unclear. Page/source executable-size descriptions disagree. | 1–3 weeks |
| [Monte-Carlo Project 2.1.2](https://nfsmods.xyz/mod/2581) | Binary installation scripts and assets, not an ASI. Changes physics, career, traffic, colors, cars and tracks. Apply data changes locally and isolate saves/configuration. | No redistribution grant found; Winter/Fog assets have separate rights. | 3–7 days prototype; extensive gameplay checks |
| [RTX Remix NFSU 0.5](https://www.moddb.com/mods/need-for-speed-underground-rtx-remix/downloads/nfs-underground-rtx-v05) | Publisher lists runtime 1.1, d3d9.dll, launcher, assets/config and bundled scripts. Runtime cannot run directly. USD meshes/PBR textures require conversion or a new replacement layer. | Mod artwork rights unverified. Optional replacement executable is unsuitable for current exact-input/catalog policy. | Assets: weeks+; renderer equivalent: months+ |
| [GAMETEST Remastered 2025 update](https://www.patreon.com/gametestro/posts/free-mod-nfs-mod-140383143) | Requires WSF, ExOpts, Unlimiter, HD Reflections and RTGI. Decompose assets/preset settings from executable dependencies. | Attachment inventory and redistribution rights unresolved. Free download does not authorize repackaging. | Decomposition first; dependency-dependent |
| [ReShade](https://reshade.me/) | Windows injector cannot load. Adapt authorized effects as WGSL passes. Grading, sharpening and bloom are practical; depth effects need scene depth and HUD exclusion. | Core BSD-3; individual shaders have separate licenses. | Days–1 week simple effects; weeks depth effects |
| [RTGI](https://www.patreon.com/mcflypg) | GAMETEST explicitly requires Pascal Gilcher RTGI 0.21, "Old version." Exact shader filename/package bytes were not inspected. WGSL translation needs permission. | Legacy shader port/redistribution rights unverified. Independent screen-space GI is an alternative, not the same shader. | Weeks+ |
| [NFS.onl / kickStart / FreeConnect](https://nfs.onl/) | Desktop launcher/recording/server ecosystem. FreeConnect is a community server listed at nfsu.online, not browser transport. NFSU1 gateway/protocol interoperability is separate work. | Reuse licenses and acceptance of browser clients unresolved. | Weeks–months |
| [Online Collision Disabler v3](https://www.moddb.com/mods/collision-disabler-online-menus-adjustments/downloads/nfsundergroundcollpatch) | ASI changes Online car collisions, menus and registration; reports collision state/version to supported servers. World/object collisions remain. | Source/license and exact patch targets unverified. Needs working online support first. | Days–weeks after networking |

## Confirmed and suspected conflicts

| Combination | Evidence and consequence |
| --- | --- |
| Free Roam + Monte Carlo | Confirmed shared GLOBALB.LZC. Free Roam replaces the file; Monte Carlo modifies its records. Merge records rather than overwrite. Added 1011 versus 1000/1300/1400 track files do not directly collide. |
| HD Fonts + Monte Carlo | Confirmed shared GLOBALA.BUN and DYNTEX.BIN. Merge texture/database entries; installation order alone is insufficient. |
| Monte Carlo + Winter/Fog | Confirmed README order: Winter → optional Fog → Monte Carlo. Winter installed later overwrites changes. Binary 2.5.5+ required; pristine inputs recommended. |
| ExOpts + Unlimiter | Both write 1 at 0x5696E4 for disappearing wheels: confirmed redundant compatible patch, not an established conflict. Consolidate implementation. |
| Extended Customization + ExOpts | Users report startup/paint-selection crashes. Reported, not independently confirmed; no common conflicting patch site established. |
| WSF + HD Reflections | Author reports Windows compatibility. Port must coordinate main/mirror/cubemap projections; blanket FOV correction risks incorrect reflections. |
| Multiple texture packs | Exact shared hashes unverified. Treat Redux 2K, Redux 4K and Remastered as alternatives until inventories are extracted. Font/gauge overlap also unverified. |
| Remix/GAMETEST + other overhauls | Shared scripts/asset areas require inventory comparison. Directory overlap alone is not proof of a specific file conflict. |
| Server Changer + old nfsuclient | Official instructions require removing old hosts-file remapping. Confirmed configuration conflict. |
| Collision Disabler v3 + old CMP | Current patch replaces scripts/NFSUndergroundCMP.asi; old credi.eng changes are integrated. Do not keep the old patch. |
| Server Changer + Collision Disabler | Both affect online/menu/login areas, but exact mutual hook conflict remains unverified. |

Higher textures, forced LOD and larger reflections compound GPU/memory costs.
The renderer expands DXT textures on devices without BC compression: about 8×
GPU memory for DXT1 and 4× for DXT3/5. This argues against 4K defaults.

Existing startup movie overrides use 0x004de9f0, 0x004deb30 and 0x004dec50;
reconcile movie-related mod ports with `runtime/nfsu1_intro.c`. Native load order
cannot resolve conflicts between compiled overrides: choose a single owner for
each behavior and compose the implementation explicitly.

## Archive and source details

- **Free Roam inspected ZIP:** Global/GLOBALB.BUN, Global/GlobalB.lzc;
  STREAML1RB_1300.BUN, STREAML1RC_1400.BUN, TEX1000TRACK.BIN,
  TEX1300TRACK.BIN, TEX1400TRACK.BIN, TRACKB1000.lzc, TRACKB1300.lzc,
  TRACKB1400.lzc; NFSU1WrongWayRemover.exe. No redistribution grant found.
- **Monte Carlo inspected RAR:** scripts target GLOBALA.BUN, GLOBALB.LZC,
  DYNTEX.BIN, FRONTEND/FRONTB.LZC, seven language BINs, stock car/wheel
  TEXTURES.BIN, Skyline VINYLS.BIN and TEX1099TRACK.BIN. Adds
  STREAML1RA_1011.BUN, TEX1011TRACK.BIN and TRACKB1011.lzc.
- **HD Fonts inspected latest archive:** 13d395-MOD.7z; 12 gauge and four font
  DDS assets, Binary scripts, NFSUHDContentSupport.asi, TexWizard.asi/json,
  TexturePacks/InGameB/meta.json and textures.bin with 24 gauge remappings.
  Installer targets GLOBAL/DYNTEX.BIN, GLOBAL/GLOBALA.BUN and
  LANGUAGES/LANGUAGETEXTURES.BIN. Installing TexWizard.json can replace other
  pack configurations. [Archive](https://nfsmods.xyz/uploads/mods/6370/13d395-MOD.7z).
- **HD Reflections inspected latest archive:** a486f3-NFS HD Reflections.zip;
  NFSU portion is NFSUHDReflections.asi and INI. Source checks entry 0x670CB5
  and describes 3,178,496-byte Drunk! 1.4 executable. Cubemap variable 0x702A84;
  mirror size variables 0x702A9C/0x702AA0.
- **Unlimiter source:** car-loader hook 0x57C8C8, workaround 0x56A367,
  relocated car-hash table, many car-count instruction changes, maximum 127.
  Rewriting those instruction bytes at runtime is insufficient in AOT Wasm.
  Source and page share entry 0x670CB5 but disagree on executable size; validate
  exact bytes against our hashed input before porting sites.
- **GAMETEST:** public post verifies RTGI 0.21 and all four mod dependencies.
  Attachment is UG1 Update 2025 (Free).rar; exact shader filename, ReShade
  version, preset inventory and included assets remain unverified.
- **RTX Remix:** published installation manifest lists .trex, d3d9.dll,
  dinput8.dll, NvRemixLauncher32.exe, rtx-remix, rtx.conf, scripts, FrontEnd,
  Global, optional audio and optional executable. Author describes USD/PBR
  workflow; assets are not proven stock BUN replacements. Manifest documents
  a first-car-selection issue requiring disabling d3d9.dll.

Source references:

- [WSF rendering/view handling](https://raw.githubusercontent.com/ThirteenAG/WidescreenFixesPack/master/source/NFSUnderground.WidescreenFix/Rendering.ixx)
  and [configuration](https://raw.githubusercontent.com/ThirteenAG/WidescreenFixesPack/master/data/NFSUnderground.WidescreenFix/scripts/NFSUnderground.WidescreenFix.ini).
- [HD Reflections source and GPL license](https://github.com/AeroWidescreen/NFSHDReflections),
  including [NFSU implementation](https://raw.githubusercontent.com/AeroWidescreen/NFSHDReflections/main/SOURCE/NFSU/dllmain.cpp).
- [HD Content Support](https://github.com/AeroWidescreen/NFSHDContentSupport)
  is GPL-3, separate from font artwork. Its NFSU font-scaling hooks are
  0x40C0E8 and 0x4F479B. [TexWizard](https://github.com/R-033/texwizard)
  is GPL-3 and loads global texture resources with named/hash substitutions.
- [ExOpts GPL license](https://github.com/ExOptsTeam/NFSUExOpts/blob/master/LICENSE)
  and [patch implementation](https://raw.githubusercontent.com/ExOptsTeam/NFSUExOpts/master/NFSUExtraOptions/ExtraOptionsStuff.h).
- [Unlimiter source](https://github.com/nlgxzef/NFSUUnlimiter) and
  [patch implementation](https://raw.githubusercontent.com/nlgxzef/NFSUUnlimiter/main/UnlimiterStuff.h).
- [ReShade source license](https://raw.githubusercontent.com/crosire/reshade/main/LICENSE.md):
  BSD-3 core, separate from shader rights. Homepage asks users to link to its
  downloads rather than redistribute binaries/shaders, and notes multiplayer
  depth access is automatically disabled.
- [RTX runtime architecture](https://github.com/NVIDIAGameWorks/rtx-remix):
  open runtime licensing does not grant rights to the NFSU mod's artwork.
- [Marty's official site](https://www.martysmods.com/) and
  [linked terms](https://www.iubenda.com/terms-and-conditions/95125802):
  no verified legacy RTGI 0.21 transformation/redistribution grant.

## Multiplayer and redistribution

[Server Changer source](https://github.com/Pelorojo/NFSUServerChanger) exposes a
C++ ASI and Rust/Slint launcher; no top-level license was found. Its
[official guide](https://wiki.nfs.onl/doku.php?id=tutorials:serverchanger)
supports PC 1.4 NA/EU/Russian SoftClub, per-server saves and hole punching.
Source documents UDP3658 races, UDP10910 rendezvous and relay fallback.
Browsers need a controlled gateway and NFSU1-specific interoperability work;
porting the desktop launcher UI is not the solution.

[NFS.onl rules](https://nfs.onl/?site=help) allow visual improvements and Extra
Options but prohibit gameplay/physics hacks and most geometry changes. They
specify 60 or 144 FPS and kickStart 2.9 or newer. Browser clients are not
automatically accepted. [FreeConnect listing](https://nfsu.online/) establishes
community naming, not a browser transport contract. Modded physics, car rosters,
track IDs and rules need peer agreement even outside leaderboard participation.

Technical feasibility is separate from permission to bundle. WSF is MIT;
GPL adaptations need corresponding-source/license handling, including their
combination with the game-derived Wasm module. Existing permissions recorded in
[source-permissions.md](source-permissions.md) do not demonstrate mod-wide
clearance for independent artwork or shaders. EC explicitly forbids reupload;
the examined Nexus packs restrict modification/reuse/reupload. Free Roam,
Monte Carlo, font artwork, Remix artwork, GAMETEST, collision patch and online
tool rights remain unresolved. User-local imports are a possible prototype
route; do not distribute modified game containers or proprietary generated code.

## Recommended order and combinations

1. **Baseline visuals:** WSF presentation → fonts-only subset → capped HD
   Reflections → lightweight native grading/bloom. Preserve stock physics,
   roster and tracks.
2. **Optional HD:** evaluate Redux 2K alone via local import after implementing
   replacement support. Resolve artwork rights before bundling.
3. **Optional Free Roam:** dedicated assets/configuration and saves, wrong-way
   override, baseline visuals. Preserve the mod's documented limitations.
4. **Separate overhaul:** Monte Carlo with documented dependencies/order.
   Merge GLOBALB records before attempting Free Roam combination.
5. **Later:** Unlimiter when addon cars are required; EC after source/rights
   clarification; networking as a separate milestone, then collision-off support.

Any data-profile switch must account for the browser cache, keyed by path,
size and mtime. Restart the server after changing its data tree; do not preserve
both size and mtime when replacing cached files. Keep saves isolated for
overhauls and changed rosters.

## Verification limits

All supplied primary pages were reachable during investigation. Free Roam,
Monte Carlo, Extended Customization, HD Fonts and HD Reflections archives were
inspected under temporary storage, without executing binaries. Nexus archives,
GAMETEST's attachment and the 6.73 GB Remix archive were not inspected; their
inventories rely on published instructions/manifests. Source-backed checks,
author compatibility claims, user reports and engineering inferences above
are not browser/game validation. Recheck links, releases and permissions before
implementation; mutable upstream URLs are research references, not build pins.

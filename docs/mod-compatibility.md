# Mod support and next steps

Current status as of 2026-10-23. The local browser build has NFSU1 widescreen
support and four HD fonts. The user confirmed the fonts and the traffic
occlusion correction in game; this does not establish full game compatibility.

## Implemented

| Feature | Scope |
| --- | --- |
| Widescreen | NFSU1 FOV, HUD and frontend hooks, with automatic canvas resolution. See [settings](settings.md). |
| HD fonts | Four locally imported font atlases with corrected drawing scale and mip selection. Original game files stay intact; gauges are unchanged. See [font setup](settings.md#hd-fonts). |
| Traffic occlusion | Depth-disabled effect passes preserve the scene depth buffer, so later traffic remains hidden behind walls. This is a renderer correction, not a separate mod. |

## Practical next candidates

| Candidate | Required work |
| --- | --- |
| HD gauges from [Raze's HD Fonts package](https://nfsmods.xyz/mod/6370) | Import the gauge textures separately and implement the InGameB remappings. Validate every gauge layout; the existing fonts importer does not provide general TexWizard support. |
| [HD Reflections](https://github.com/AeroWidescreen/NFSHDReflections) | Port selected reflection dimensions, brightness and LOD fixes from source. Verify each PC 1.4 patch site and coordinate main, mirror and cubemap projections with widescreen. Cap sizes for browser memory/performance. |
| [Extra Options](https://github.com/ExOptsTeam/NFSUExOpts) | Select individual useful fixes and port their behavior. Existing intro/input features already have browser implementations. |
| Simple postprocessing | Implement grading or sharpening as WebGPU passes. ReShade itself cannot load; shader reuse requires checking that shader's license. |

Gauges and reflections are separate changes. Implement and validate one at a
time before combining them with larger texture or gameplay packs.

## Runtime constraints

The build compiles an exact PC 1.4 executable into Wasm using cached analysis
and the `CPU *` ABI. Changing x86 instructions after compilation does not
change emitted code. A patch needs a runtime override, guest-data change or
emission-time transformation; original executable inputs remain unchanged.

Windows ASI/DLL mods and graphics injectors cannot be dropped into the browser.
The renderer uses D3D9 emulation, shared command queues and WebGPU/WGSL.
Native upstream texture-pack support is not general browser replacement
support: the font importer handles two specific game containers only.

## Larger changes deferred

- [Redux 2K](https://www.nexusmods.com/needforspeedunderground/mods/2) needs
  texture extraction/matching and a replacement pipeline. Evaluate one pack
  first; 4K adds substantial memory and download cost, especially without BC
  texture compression.
- [Free Roam](https://nfsmods.xyz/mod/577) and
  [Monte Carlo](https://nfsmods.xyz/mod/2581) change game data and need isolated
  saves. Both touch GLOBALB; Monte Carlo also touches the fonts' GLOBALA
  container, so combine records rather than overwrite files.
- Addon cars and extended customization need additional guest hooks/table
  handling. RTX Remix/RTGI need substantial renderer work. A same-origin
  virtual-LAN switch (`/lan`) is in `nfsu1-server`; game Online/LAN races and
  community-server interoperability remain separate milestones.

## Local assets and attribution

Keep mod artwork, patched game containers, real catalogs and game-derived
builds in ignored local directories. The fonts path is a local import;
permission to reuse support code does not grant rights to bundle artwork.
HD Content Support and HD Reflections use GPL-3.0; retain their notices and
applicable source/license handling. See [source permissions](source-permissions.md).

Restart the local server after switching assets. Replacement files must get
new browser cache identities; the HD fonts overlay handles this explicitly.
For larger overhauls, keep saves separate from the stock profile.

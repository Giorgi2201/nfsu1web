# Current status

The local PC NFSU1 browser build runs with WebAssembly and WebGPU. User testing
has confirmed intro video/audio, profile creation and loading, persistent saves,
race starts, restored HD text and corrected traffic occlusion. Race completion,
full career progression, multiplayer and broad device compatibility are not
established.

## Implemented

- NFSU1 startup, input, isolated saves, sound-bank callbacks and local serving.
- Graphics presets, automatic canvas resolution and widescreen FOV/HUD hooks.
- Browser settings, keyboard aliases and startup movie controls.
- Four optional HD font atlases used in menus and race text. Gauges remain stock.
- Scene depth survives smaller depth-disabled effect passes; the user confirmed
  traffic no longer appears through walls.

The font importer retains the language pack's streaming table and produces
JDLZ streams accepted by the game's decoder. The renderer preserves persistent
depth during effects that do not use it. Focused regression checks are listed
in [testing.md](testing.md).

## Limits and next work

The build still contains abort stubs for unresolved game functions. A successful
compile or synthetic test does not establish compatibility for an untested mode.
Remaining priorities are repeatable race completion/career checks, wider browser
coverage and optional HD gauges. Other mod candidates are in
[mod-compatibility.md](mod-compatibility.md).

## Code map

| Area | Location |
| --- | --- |
| Catalog caching and emission | `tools/prepare_game_catalog.py`, `catalog_bridge.py`, `lift_catalog.py` |
| Runtime and browser overlays | `tools/apply_runtime_profile.py`, `apply_browser_profile.py` |
| NFSU1 host adapters | `runtime/` |
| Launcher and controls | `browser/` |
| Build and local server | `tools/build_nfsu1_wasm.sh`, `build_nfsu1_browser.py`, `serve_nfsu1.py` |
| Pinned source evidence | [source-manifest.json](source-manifest.json) |

The integration targets the web runtime's `CPU *` ABI and reuses saved catalog
block ranges. Native DLL/ASI injection is unavailable; patches need runtime or
emission-time adaptations. Game data, catalogs, generated C and Wasm stay local.

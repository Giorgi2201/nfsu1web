# Current status

The local PC NFSU1 browser build runs with WebAssembly and WebGPU. It supports
intro video and audio, profiles and persistent saves, single-player and Online
race starts, Online challenges, HD text, and traffic occlusion. Race completion,
full career progression, broad multiplayer coverage, and device compatibility
are not yet supported or established.

## Implemented

- NFSU1 startup, input, isolated saves, sound-bank callbacks and local serving.
- Graphics presets, automatic canvas resolution and widescreen FOV/HUD hooks.
- Browser settings, keyboard aliases and startup movie controls.
- Four optional HD font atlases used in menus and race text. Gauges remain stock.
- Scene depth survives smaller depth-disabled effect passes, keeping traffic
  behind walls.
- Same-origin LAN play and an Online lobby. News, stats and rankings use
  placeholder data; free-roam is unsupported. The server also prepares a
  local car-data overlay when a modified install needs it. See the
  [Online protocol reference](online-protocol.md).

## Limits and next work

Some game functions remain unsupported. Remaining priorities are race completion
and career progression, wider browser coverage, and optional HD gauges. Other
mod candidates are in
[mod-compatibility.md](mod-compatibility.md).

Native DLL/ASI mods are unsupported. Game data, catalogs, generated C and Wasm
stay local.

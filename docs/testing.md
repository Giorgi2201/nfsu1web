# Testing

## Command-line checks

Run checks relevant to the change; there is no need to run every smoke tool.

```sh
# Dependency-free catalog and synthetic Wasm ABI checks:
python3 -m unittest discover -s tests -v
node --test tests/guest_abi.test.mjs

# Real upstream emitter with authored fixtures (analysis dependencies required):
python3 tools/run_lifter_smoke.py --upstream work/upstream/nfsu2-web

# Font scaling and the real emitted font uploader/stream loader:
python3 tools/font_runtime_smoke.py
python3 tools/font_upload_smoke.py
python3 tools/font_container_smoke.py

# Actual frame encoder with synthetic GPU command objects:
python3 tools/depth_state_smoke.py

# HTTP routes, overlays, byte ranges and path protections:
python3 tools/browser_server_smoke.py --in-process
```

The upload/container checks require local emissions and prepared font assets.
They execute game routines against synthetic I/O/COM resources, including the
actual JDLZ decoder. The depth check reproduces a wall → smaller depth-disabled
effect → farther car sequence; the pinned original fails and the fix preserves
scene depth. These checks do not rasterize a game scene.

Other focused checks live in `tools/*smoke*`; the filename identifies the area.
`build_nfsu1_browser.py` runs startup, keyboard and bundle syntax checks.

## Manual browser check

After rebuilding, stop the old server, restart it and reload
**http://127.0.0.1:8765/**. Add `--hd-fonts work/mods/hd-fonts` to enable fonts.
Use the same origin to preserve saves.

1. Launch, skip a startup movie, load/create a profile and verify sound/input.
2. Start a race. Check HUD text, gauge alignment, traffic behind walls, crowd
   animation and reflections. Complete/save/reload the event when testing
   gameplay persistence.
3. Resize and toggle fullscreen. Check FOV, HUD placement, menu spacing and
   mouse targets. Compare graphics presets only when changing graphics code.
4. For keyboard changes, check overlapping held keys, focus loss and F10 typing.
   For fonts, inspect both menu and race text for sharpness, clipping and glyphs.

Use F9 → Stop game, then **Download log**. Report the failing steps, browser/OS,
selected preset and first relevant error. Keep storage intact during diagnosis.
The log's module hash identifies the build; `[nfsu1 fonts]`, `[nfsu1 depth]` and
`[gpu] depth size mismatch` identify the font/depth paths. Draw diagnostics are
bounded and can be disabled with `NFSU1_DEPTH_DIAGNOSTICS=0`.

Share only relevant log excerpts, removing personal paths/profile names.
Keep game data, generated code, catalogs and memory dumps private. Current
user-confirmed behavior and remaining limits are in [status.md](status.md).

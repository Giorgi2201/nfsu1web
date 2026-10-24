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

# HTTP routes, overlays, byte ranges and path protections (Rust nfsu1-server):
cargo build --manifest-path server/Cargo.toml
python3 tools/browser_server_smoke.py

# Lobby messages and virtual LAN transport (no game/browser execution):
cargo test --manifest-path server/Cargo.toml
node tools/lan_switch_smoke.mjs
```

The upload/container checks require local emissions and prepared font assets.
They execute game routines against synthetic I/O/COM resources, including the
actual JDLZ decoder. The depth check reproduces a wall → smaller depth-disabled
effect → farther car sequence; the pinned original fails and the fix preserves
scene depth. These checks do not rasterize a game scene.

Other focused checks live in `tools/*smoke*`; the filename identifies the area.
`build_nfsu1_browser.py` runs startup, keyboard and bundle syntax checks.

## Manual browser check

After rebuilding, stop the old server, restart with `./start.sh` and reload
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

## Online challenge and countdown retest

1. Restart `./start.sh` after rebuilding, then reload both clients on the same
   server. Use different profile names and keep both pages visible.
2. Enter the same Online room. Send a challenge to the other player: the target
   should receive the challenge action, with no purple `GAME=`/`PARAMS=` chat.
   Test Refuse once, then send again and Accept.
3. Start a normal created race as well. Confirm both players finish loading,
   see the countdown and can drive for at least 30 seconds.
4. If either returns to the lobby, immediately download both logs through F9.
   Keep the server terminal's `[online]` messages for the same attempt. Confirm
   the client log contains `NFSU1 NetTick: real monotonic clock`, and include
   which player hosted and whether the return happened on both clients.
   The diagnostic build also records `[nfsu1 online]` timeout/quit/cleanup
   callbacks with game heartbeat and transport ages. Save these lines and their
   short backtraces before reloading. Test once without throttle during the
   countdown, then with throttle, if checking whether input triggers the exit.

Command-line message/parser/clock checks do not establish multiplayer stability.

The car-data preparer writes `out/online-data.json` and a private sparse overlay.
Its table must have CRC `238562c5`, with every byte outside that table preserved.
The corrected local install changes 26 bytes. A focused local HTTP check has
verified full/range overlay serving, source hash preservation and a changed
cache stamp; the actual emitted checksum rejects the old table and accepts
the replacement. The user confirmed Online races work after the correction.
`[nfsu1 online] race car-table checksum` records actual/expected values for
subsequent troubleshooting; this confirmation does not establish race completion.

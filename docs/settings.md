# Settings and optional fonts

## Browser controls

Use the launcher's Options and Controls screens. Most settings apply on the
next game launch; keyboard aliases apply immediately. In-game Options still
control difficulty, transmission, camera and action bindings.

| Setting | Behavior |
| --- | --- |
| Graphics quality | Game, Low, Medium, High or Maximum; Maximum is the default. Game uses the saved profile's choices. |
| Resolution | Automatic canvas device pixels, with an 8192-pixel dimension limit. Resize/fullscreen triggers a device reset. |
| Widescreen | Enabled by default; the scene fills the window and the complete menu fits over it without stretching. `NFSU1_WIDESCREEN=0` uses guest-aspect letterboxing. |
| Startup movies | Skippable by default; Original retains native behavior, Off skips on the first update. Story/tutorial movies are unchanged. |
| Audio/background | Sound, output latency and Pause / Keep running policy. |
| Controller | Device policy, dead zones, trigger threshold and vibration permission. |

Graphics presets use NFSU1's own detail levels and capability limits; they do
not enable the upstream NFSU2 enhancement system. Their exact mapping is in
[`runtime/nfsu1_graphics.c`](../runtime/nfsu1_graphics.c).

Menu artwork uses its original 640×480 canvas, fitted and centered over the
garage background in both wide and narrow windows. The background fills the
view; menu objects parked outside the logical canvas remain hidden.

**F9** opens the game overlay. **F10** temporarily disables keyboard aliases for
typing. The WASD preset sends arrow keys; actions follow the game's Controls
menu. Aliases are stored separately from save backups in browser local storage.

Saves use `save-nfsu1`, game-data caching uses `cache-nfsu1`. Keep the same
host and port to retain the same browser storage.

## HD fonts

The optional importer uses four DDS atlases from Raze's
[NFSU-HD FONTS](https://nfsmods.xyz/mod/6370), archive `13d395-MOD.7z`.
It replaces fonts used in menus and race text at 4× atlas resolution while
preserving text size. Other font atlases and gauge artwork remain stock.
No ASI, Binary or TexWizard executable is run.

Extract the archive locally, preserving its `Textures` folder:

```sh
python3 tools/prepare_hd_fonts.py --mod /path/to/extracted-hd-fonts
./start.sh --hd-fonts work/mods/hd-fonts --check
./start.sh --hd-fonts work/mods/hd-fonts
```

Preparation reads `work/data` and writes two replacement containers and a hash
manifest under `work/mods/hd-fonts`. It refuses a nonempty output directory;
use a fresh `--output` for another import. Original game files stay unchanged.
Rebuild an older Wasm module with the current tools before enabling fonts.

The server prints `HD fonts enabled (local overlay; gauges unchanged)` when
the overlay is selected. To use stock fonts, restart without `--hd-fonts`.
Restart after replacing assets, then reload the same browser address. Cache
versions derive from content hashes; deleting saves or clearing storage is
unnecessary.

If menu or race text disappears, restart without `--hd-fonts`. HD gauges are a
separate future port.

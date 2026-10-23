# Browser menus and settings

The launcher uses cool blue and silver accents with typography inspired by
Underground’s menus. The start screen goes directly to the game status and
launch control, without a decorative banner or promotional slogans. Play, Options, Controls, Storage and About are separate
screens. No game artwork, extracted assets or external fonts are required.

## Settings audit

The comparison uses the cached, pinned `th0mk/nfsu2-web` revision
`31da468582c3de14fd6f4233831f62816e2df83d`, especially
`web/src/app/settings-ui.ts`, `settings.ts` and `web/src/input/index.ts`.
The pristine source is retained by the reversible overlay, rather than inferred
from the already modified working files.

The [EA NFSU2 PC manual](https://oldgamesdownload.com/wp-content/uploads/Need_for_Speed_Underground_2_Manual_Win_EN.pdf)
also groups its Options into audio, display, gameplay, player, controls and
music playback. Those categories informed the comparison; they do not establish
that NFSU2's patches work in NFSU1.

| Area | NFSU2 browser host | NFSU1 page |
| --- | --- | --- |
| Keyboard | Native keyboard forwarding and controls reference | Added persistent aliases, key capture, conflict detection, WASD preset and reset |
| Graphics | Resolution scale, frame rate, HUD, movie framing and game patches | Existing NFSU1 graphics presets; live device-pixel resolution and widescreen remain automatic |
| Audio | Sound output and output latency | Exposed sound output; retained latency choices |
| Browser | Fullscreen, startup movies, background behavior | Retained fullscreen/movies; exposed Pause / Keep running |
| Controller | Device policy, dead zones, full trigger, rumble | Retained policy/dead zones; exposed full-trigger threshold and vibration permission |
| Gameplay/player | Autosave and other NFSU2 patches | Use the game's own Options for transmission, difficulty, camera and other game settings |
| Online | LAN, free roam, player discovery and rooms | Unsupported NFSU2 features stay disabled |
| Saves | NFSU2 profile parsing, importing and backups | NFSU1 storage remains isolated; NFSU2 profile tools stay hidden |

Keyboard aliases map physical keys to game keys, not directly to game actions.
For example, the WASD preset sends the four arrow keys. Action bindings still
follow NFSU1's in-game Controls menu, including any changes in a saved profile.
Original keys remain usable unless reassigned. The page reserves menu/browser
shortcuts and preserves held-key releases when focus or mappings change.
Aliases also apply in game menus and text entry. Press **F10** while playing
to temporarily turn mappings off for typing, then press it again to restore
them. The toggle releases held keys and does not erase your saved mappings.
Aliases are stored under `nfsu1-keyboard-v1` in local browser storage, separately
from `settings.ini`; these aliases are not included in save backups.

Audio, fullscreen, startup, graphics, background and controller settings apply
at the next launch. Keyboard changes apply immediately. Vibration depends on
game force feedback and browser/controller support; exposing the switch does
not establish that NFSU1 produces every NFSU2 effect.

## User browser check

After `python3 tools/build_nfsu1_browser.py`, run
`python3 tools/serve_nfsu1.py` and open **http://127.0.0.1:8765/**.

1. Check each left menu item, keyboard focus and narrow-window layout.
2. In **Controls**, select **Use WASD**, reload and check the key labels persist.
   Change a binding, try an already assigned key, then press Esc to cancel.
3. Launch the game and compare WASD with the arrow keys in menus and a race.
   Use the game's Controls menu to check the action assigned to each game key.
   Hold W and Up together; releasing one should leave Up pressed until both
   are released. Switch away while holding a key, return and check it releases.
4. Open F9 → Controls and check the help; return to the game. F9 must remain
   usable after every remap. Stop through F9, then reset the keyboard on the page.
5. Change sound output and relaunch to check mute/unmute. Check background pause,
   fullscreen and the connected controller settings on subsequent launches.

Command-line smoke checks cover the browser source, input mailbox and bundle.
They do not verify visual appearance or game compatibility. No browser is
operated by the build tools.

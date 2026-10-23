# Startup movie controls

The browser's **Startup movies** setting takes effect on the next start:

- **Skippable** (default): Enter, Escape, Space or controller A/B/Start ends
  the current startup movie. Native front-end accept/click messages also skip.
- **Original**: retain the game's original skip behavior.
- **Off**: finish each startup screen on its first update. A brief initial
  frame may appear because playback can initialize before that update.

Story and tutorial movie handlers are not hooked. The intro's attract replay
uses the same intro handler and gets the selected behavior. Controller input
respects the controller Off setting.

## Implementation

`runtime/nfsu1_intro.c` adapts the notification-hook and input-baselining design
from th0mk/nfsu2-web's MIT-licensed `runtime/intro.c` at revision
`31da468582c3de14fd6f4233831f62816e2df83d`. The retained notice is in
`patches/nfsu2-web.LICENSE`. The matching local PC 1.4 executable and cached
catalog establish these interfaces:

| Screen | Vtable | Notification handler |
| --- | --- | --- |
| IntroFMVScreen | `0x006c3768` | `0x004de9f0` |
| EAlogoBumper | `0x006c3758` | `0x004deb30` |
| PSAMovie | `0x006c37a8` | `0x004dec50` |
| THXMovieScreen | `0x006c380c` | `0x004deb30` |

The callbacks use ECX=self, message at ESP+4 and four stack arguments. The
catalog and current emissions contain no direct callers. Only their indirect
dispatch entries are replaced; the adapter invokes the original lifted
handler. Original executables and generated functions remain unchanged.

Front-end ticks (`0xc98356ba`) reach all four screen types. Fresh extra input
becomes native accept for Intro/PSA or movie completion (`0xc3960eb9`) for
EA/THX. Off uses completion. The original handlers retain their distinct
native-skip and completion behavior, including player replay suppression.
Screen advance uses `0x004de4a0`; movie element teardown at `0x004f5900`
stops playback through `0x005a4c80` without posting another completion.

Input baselines reset between screens and track the object, package and vtable.
Held input alone does not generate another added skip; native accept/start
messages retain the game's original behavior. Stack cleanup stays with the
original handlers, and no object is accessed after invoking them.

## User browser check

After rebuilding, restart the local server and reload the same origin:

```sh
python3 tools/serve_nfsu1.py
```

Open http://127.0.0.1:8765/ and select **Startup movies: Skippable**.
Start the experiment, press Escape during the EA logo and hold it through the
transition. Release and press again on the next movie. Check that one fresh
press skips one movie, its audio stops, and the title/profile flow still works.
Repeat with Enter/Space and a controller if available. Restart with Original
and Off to compare. Keep existing browser storage. Download the log if anything
stalls; mode and skip events begin with `[nfsu1 intro]`.

`python3 tools/intro_runtime_smoke.py` checks the actual adapter with synthetic
guest memory and fake original handlers. This verifies modes, stack/argument
preservation, fresh input and disabled controller input. It cannot establish
rendered-game or audio behavior. No agent operates a browser for validation.

For an existing applied overlay, revert/reapply before rebuilding so the
updated runtime installation and browser settings are used:

```sh
python3 tools/apply_runtime_profile.py --upstream work/upstream/nfsu2-web --revert
python3 tools/apply_runtime_profile.py --upstream work/upstream/nfsu2-web
python3 tools/apply_browser_profile.py --upstream work/upstream/nfsu2-web --revert
J=4 bash tools/build_nfsu1_wasm.sh
python3 tools/build_nfsu1_browser.py
```

The overlay tools verify hashes and refuse to overwrite later edits.

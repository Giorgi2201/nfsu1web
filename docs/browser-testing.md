# Local browser test

The experimental browser host is built locally. Its module and game data remain
private; nothing is uploaded. The user has reported clips with sound, a profile
persisting across reload, successful profile loading and a race start. Broader
compatibility and race completion are unverified. The current runtime adds the
missing date/time imports which aborted first-time profile creation, and the
user confirmed that creation now works. The page also fixes the reported
`autosaved` startup exception. See [progress](progress.md).

## Start the local server

Run in your terminal from the repository root after following the
[build guide](building.md):

```sh
python3 tools/serve_nfsu1.py
```

Leave that terminal running and open **http://127.0.0.1:8765/**. Use the same
address on subsequent runs so browser storage stays on the same origin. The
server accepts loopback connections only and serves the local build and game
install read-only. Stop it with Ctrl+C. If the port is occupied, pass
`--port 8766` and use that port in the browser address.

## What to try

For the date/time fix, stop and restart the local server, then reload the same
address. Create a profile with a new unused name (for example `datefix1`) and
press Enter. Confirm that the game continues without an unresolved import or
exit code 134. Stop/reload afterward and check that the new profile loads.
Keep browser storage intact; loading an existing profile alone does not test
the initial creation path.

1. Wait for the module and browser checks to finish. The module is about
   101 MiB; the page checks the required WebGPU, Wasm, shared-memory and storage
   features. A failed check is useful evidence; record its exact message.
2. Click **Start experiment**. Use the keyboard first. Observe whether a picture
   appears, movies advance and sound starts. Allow about three minutes so the
   music-bank callback path is exercised.
3. Load or create a profile, try Enter and Escape, and start a race. Record
   input, rendering and save behavior, especially any failure around first-time
   profile creation. Profile loading and race start have been reported by the
   user; repeatability and race completion remain open.
4. Press F9 and choose **Stop experiment**, then use **Download log** on the
   page. Share the log with what appeared, whether sound/input worked, and when
   any failure occurred. This stop terminates the runtime; it makes no claim
   that an in-game save completed.

If the canvas stays black or the runtime stops, retain the log rather than
clearing browser storage. The useful distinction is a failed browser check,
worker trap, failed data request, shader/WebGPU error, or continued guest
activity without a visible picture.

## Rebuild after source changes

The current artifacts are already built. For another iteration:

```sh
# Only if the handwritten runtime changed; reuses the saved emissions/cache:
J=4 bash tools/build_nfsu1_wasm.sh
# Apply the reversible browser overlay, bundle, and validate local inputs:
python3 tools/build_nfsu1_browser.py
python3 tools/browser_server_smoke.py --in-process
python3 tools/serve_nfsu1.py --check
python3 tools/serve_nfsu1.py
```

Stop and restart the server after rebuilding the module or changing game files.
Its metadata and manifest describe one server run; a changed module gets a new
SHA-256 URL, and stale requests receive HTTP 409.
For the current shell/server fixes, restart the server and reload the page at
the same address. Keep the existing browser storage so the created profile is
available. Downloaded logs now begin with `nfsu1-`.

The bundler uses isolated esbuild 0.27.4 under `work/toolchain/web-bundler/`,
installed from the existing npm cache with package integrity checks. Its MIT
license and lockfile are retained there. This differs from the upstream
package's esbuild 0.28.2 development dependency; the actual bundle build passes
with 0.27.4. If that isolated toolchain is absent, install just the bundler:

```sh
npm install --prefix work/toolchain/web-bundler --no-audit --no-fund --ignore-scripts esbuild@0.27.4
```

## Validation and isolation

The page, worker and audio-worklet bundles build and pass JavaScript syntax
checks. A focused Node smoke executes the overlaid startup function with host
stubs, checking completion and exit-handler attachment. It is a shell check,
not a browser/game simulation. In-process requests through the HTTP handler pass metadata,
Wasm/PE byte ranges, 206/416 responses, HEAD, isolation headers and path checks.
The real-data manifest has 507 entries, including the explicitly allowed
`Speed.exe` symlink. Local socket binding is denied in the agent sandbox, so
these checks do not establish a listening-server or browser result; the launch
above is for your terminal. No browser was operated.
Expected disconnected clients are handled quietly. Source maps remain under
`dist-dev` for local analysis; public bundles do not advertise their URLs.

The overlay uses `save-nfsu1` for saves, `cache-nfsu1` for game data and
`nfsu1-offline-1` for the service-worker cache. Unsupported NFSU2 options,
profile rewriting and online features are disabled. The runtime overlay also
disables NFSU2 controller rescan writes, menu-key synthesis and physics-based
rumble additions. Generic keyboard/mouse, controller, graphics and audio host
interfaces remain; their game behavior still needs this browser check.

Private evidence is in `out/browser-build.json`, `out/browser-serving-check.json`,
`out/browser-runtime-build.log` and `out/browser-runtime-node.log`.

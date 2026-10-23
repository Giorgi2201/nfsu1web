# NFS Underground in your browser

An experimental browser port of **Need for Speed: Underground (2003)**, built
with WebAssembly and WebGPU.

The project recompiles the original PC game's x86 code to WebAssembly and runs
it locally in your browser. It builds on
[codepdbh's NFSU1 recompilation work](https://github.com/codepdbh/nfsu1-recompiled)
and [th0mk's NFSU2 browser runtime](https://github.com/th0mk/nfsu2-web).

**Still a work in progress.** Local browser testing has reached intro movies
with sound, profile creation and loading, saves that survive a reload, and
starting a race. HD font loading and traffic occlusion fixes are user-confirmed.
Completing races and broader game compatibility remain
unverified. Expect bugs, rendering issues and unfinished paths.

## Running it

You'll need your own legally obtained PC game files and the exact
[supported executable](docs/building.md#private-game-inputs). Game files and prebuilt game
modules are not included.

Follow the **[build and run guide](docs/building.md)** for the full setup.
The current build has been tested on Apple Silicon macOS and requires:

- Python 3.10+, Node.js/npm and WASI SDK 34.
- A browser with WebGPU and the WebAssembly features checked at startup.
- Enough memory for the game's 1 GiB initial shared memory, plus the browser,
  GPU and game data.

Once you've built it:

```sh
python3 tools/serve_nfsu1.py
```

Open **http://127.0.0.1:8765/** and click **Launch game**. Keep the server
running while you play. Use the same address each time to keep your saved
profile available.

The browser host includes graphics presets, automatic resolution, widescreen
hooks, startup movie controls and optional local HD fonts. See
[settings and fonts](docs/settings.md) for options and import instructions.

## Development

The repo contains the build tools, handwritten runtime adapters and browser
integration. Game analysis and generated code are created locally and kept out
of Git.

You can run the basic tooling and ABI checks without game files:

```sh
python3 -m unittest discover -s tests -v
node --test tests/guest_abi.test.mjs
```

These checks don't test gameplay. For browser testing and useful bug reports,
see the [test guide](docs/testing.md). Fixes and contributions are
welcome; start with [CONTRIBUTING.md](CONTRIBUTING.md).

More detail: [current status](docs/status.md) ·
[mod research](docs/mod-compatibility.md)

## Credits

This project depends on the work of:

- **[codepdbh / nfsu1-recompiled](https://github.com/codepdbh/nfsu1-recompiled)** —
  PC game analysis, sound-bank support and the widescreen port.
- **[th0mk / nfsu2-web](https://github.com/th0mk/nfsu2-web)** —
  the browser runtime and recompiler, with original recompiler and macOS
  runtime portions by **Talha Müderrisoğlu**.
- **[sp00nz / pcrecomp](https://github.com/sp00nznet/pcrecomp)** —
  PE analysis and x86 disassembly.
- **[ThirteenAG / WidescreenFixesPack](https://github.com/ThirteenAG/WidescreenFixesPack)** —
  the original widescreen fixes and HUD layout data.

Exact source revisions, notices and permission records are in
[NOTICE.md](NOTICE.md) and the [source manifest](docs/source-manifest.json).

## License

Original contributions are [MIT-licensed](LICENSE); upstream material retains
its own terms. This is an unofficial project, unaffiliated with Electronic
Arts. No license to game content is granted. See the
[source and distribution terms](docs/source-permissions.md) for details.

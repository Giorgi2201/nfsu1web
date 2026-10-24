# NFS Underground in your browser

An experimental browser port of **Need for Speed: Underground (2003)**, built
with WebAssembly and WebGPU.

The project recompiles the original PC game's x86 code to WebAssembly and runs
it locally in your browser. It builds on
[codepdbh's NFSU1 recompilation work](https://github.com/codepdbh/nfsu1-recompiled)
and [th0mk's NFSU2 browser runtime](https://github.com/th0mk/nfsu2-web).

**Work in progress.** The game starts in a local browser build, with intro
movies and sound, profiles and persistent saves, and single-player and Online
race starts. The browser build also includes HD fonts and traffic occlusion
support.
Race completion and broader compatibility remain unverified.

## Running it

You'll need your own legally obtained PC game files and the exact
[supported executable](docs/building.md#private-game-inputs). Game files and prebuilt game
modules are not included.

**Build:** copy your PC install (including `Speed.exe`) into `work/data/`, then:

```sh
./build.sh
./start.sh
```

Open **http://127.0.0.1:8765/** and click **Launch game**. Details:
[docs/building.md](docs/building.md).

Needs Python, Node, and Rust installed on the machine once; `./build.sh`
fetches the WASI SDK and other bits under `work/` when missing. Use a browser
with WebGPU. Keep the same address so your saved profile stays available.

The browser host includes graphics presets, automatic resolution, widescreen
hooks, startup movie controls and optional local HD fonts. See
[settings and fonts](docs/settings.md) for options and import instructions.

## Development

The repository contains the build tools and browser integration. Game analysis
and generated code stay local and out of Git.

Fixes and contributions are welcome; start with
[CONTRIBUTING.md](CONTRIBUTING.md).

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

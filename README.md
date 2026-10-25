# NFS Underground in your browser

An experimental browser port of **Need for Speed: Underground (2003)**, built
with WebAssembly and WebGPU.

The project recompiles the original PC game's x86 code to WebAssembly and runs
it locally in your browser. It builds on
[codepdbh's NFSU1 recompilation work](https://github.com/codepdbh/nfsu1-recompiled)
and [th0mk's NFSU2 browser runtime](https://github.com/th0mk/nfsu2-web).

**Work in progress.** The project author reports seeing intro video and audio,
a persisted profile, and a race start in the local build. Broader compatibility,
race completion, and multiplayer gameplay remain unverified.

## Running it

You'll need your own legally obtained PC game files and the exact
[supported executable](docs/building.md#supported-executable). Game files and
prebuilt game modules are not included.

**Build:** copy your PC install (including `Speed.exe`) into `work/data/`, then:

```sh
./build.sh
./start.sh
```

Open **http://127.0.0.1:8765/** and click **Launch game**. Details:
[docs/building.md](docs/building.md).

See the [build guide](docs/building.md) for prerequisites and supported build
hosts. Use a browser with WebGPU. Keep the same address so your saved profile
stays available.

See [settings and fonts](docs/settings.md) for browser options and the optional
font import instructions.

## Development

The repository contains the build tools and browser integration. See
[CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidance.

## Credits and license

This project builds on
[NFSU1 recompilation work](https://github.com/codepdbh/nfsu1-recompiled),
[the NFSU2 browser runtime](https://github.com/th0mk/nfsu2-web), and
[pcrecomp](https://github.com/sp00nznet/pcrecomp). Full credits, source
revisions, notices, and permission records are in [NOTICE.md](NOTICE.md) and
the [source manifest](docs/source-manifest.json).

Original contributions are [MIT-licensed](LICENSE); upstream material retains
its own terms. This is an unofficial project, unaffiliated with Electronic
Arts. No license to game content is granted. See the
[source and distribution terms](docs/source-permissions.md) for details.

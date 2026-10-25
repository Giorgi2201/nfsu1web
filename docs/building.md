# Build and run

## Supported executable

Copy your whole PC install into `work/data/`. Include `Speed.exe` and the game
folders such as `Cars`, `FrontEnd`, `Global`, `Tracks`, `Languages`, `fx`,
`Sound`, and `Movies`.

`Speed.exe` must be the PC Underground **1.4** build with SHA-256
`c0fad450912952f53809a54690d235aa8b4e25b9f46650693c7cbee1b4c074b7`.
Game files are not downloaded by the build.

## Prerequisites

Install Python 3.10+, Node.js 20+ with npm, Rust with Cargo, Bash, curl, tar,
and `shasum`. The build script has automated WASI SDK downloads for macOS
(arm64 and x86-64) and Linux (arm64 and x86-64); it currently stops on other
host configurations.

The first build needs network access to install Python packages and esbuild and
download WASI SDK 34 and the pinned source files. Python packages go in `.venv`,
toolchains and upstream sources go under `work/`, and generated catalog/lift
outputs go under `gen/`. The first build also generates the local game catalog
and can take longer than later builds.

## Build and launch

```sh
./build.sh
./start.sh
```

Open <http://127.0.0.1:8765/> and click **Launch game**. Run
`./start.sh --check` to validate the local server inputs without launching the
game.

The build prepares a private Online car-data overlay if the install has
modified car records. It restores the verified stock table in the overlay,
leaves original files intact, and selects the overlay when serving the game.

See [settings and optional fonts](settings.md) for browser controls and the HD
font importer. Run `J=8 ./build.sh` to use more compile jobs. Keep
`work/`, `gen/`, and game files out of Git.

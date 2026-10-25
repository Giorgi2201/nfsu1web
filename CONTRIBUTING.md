# Contributing

This is an experimental local integration. Small, focused fixes, build-guide
corrections and reproducible compatibility reports are useful. Read the
[README](README.md) and [build guide](docs/building.md) before changing the
runtime.

## Source boundaries

Contribute handwritten tooling, runtime adapters, documentation, and synthetic
fixtures. Keep game-derived inputs and outputs local; see the [source
permission record](docs/source-permissions.md) for the exclusions. Review staged
files before publishing; `.gitignore` is not an audit.

License original contributions under the project's [MIT license](LICENSE).
Preserve third-party terms and attribution; see [NOTICE.md](NOTICE.md), the
[permission record](docs/source-permissions.md), and the [source
manifest](docs/source-manifest.json). These do not grant rights to game content.

## Changes and checks

Use four-space Python and two-space JavaScript indentation. Follow nearby code
and keep changes scoped to one problem. For source-only changes, run the
relevant dependency-free checks:

```sh
python3 -m unittest discover -s tests -v
node --test tests/guest_abi.test.mjs
```

These checks need Python 3.10+ and Node.js 20+; they do not execute the game.
For runtime or build changes, use the focused validation relevant to the
change. Add tests for consequential behavior that is difficult to verify
directly; broad test suites are unnecessary.

Use imperative commit subjects. Pull requests should explain the problem,
resulting behavior and remaining limitations. Do not infer compatibility from a
successful build.

## Reporting a problem

Include your host OS and architecture, Python/Node/WASI SDK versions, repository
revision, command or in-game steps, expected behavior and first relevant error.
For browser reports, include the browser version, whether startup completed and
the failing stage.

Inspect logs before sharing. Post only the minimal relevant excerpt, removing
personal paths, profile names or other private information. Do not attach
catalogs, generated game code, game files or memory dumps. Reports involving a
different executable should give its hash and layout details rather than the
binary itself.

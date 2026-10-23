# Contributing

This is an experimental local integration. Small, focused fixes, build-guide
corrections and reproducible compatibility reports are useful. Read the
[README](README.md), [build guide](docs/building.md) and
[compatibility assessment](docs/compatibility.md) before changing the runtime.

## Source boundaries

Contribute handwritten tooling, runtime adapters, documentation and synthetic
fixtures. Do not submit game executables, assets, archives, saves, real catalogs,
game-derived generated code, object files or playable builds. Keep private
inputs and outputs in ignored `work/`, `gen/` and `out/`. Review staged files
before publishing; `.gitignore` is a convenience, not an audit.

Preserve upstream notices and attribution. For reused source, identify its
repository, revision and applicable permission or license in
[source-permissions.md](docs/source-permissions.md) and the
[source manifest](docs/source-manifest.json). See [NOTICE.md](NOTICE.md) for the
current source boundaries. Do not assume that an upstream source license
licenses game content.

Submit original contributions under the project's [MIT license](LICENSE).
Third-party code must retain its applicable terms; see the
[rights notes](docs/rights.md).

## Changes and checks

Use four-space Python and two-space JavaScript indentation. Follow nearby code
and keep changes scoped to one problem. For source-only changes, run the
relevant dependency-free checks:

```sh
python3 -m unittest discover -s tests -v
node --test tests/guest_abi.test.mjs
```

These checks need Python 3.10+ and Node.js 20+; they do not execute the game.
For runtime or build changes, use the focused compile/smoke check relevant to
the change and describe its limits. Add tests for consequential behavior that
is difficult to verify directly; broad test suites are unnecessary.

Use imperative commit subjects. Pull requests should explain the problem,
resulting behavior, validation performed and remaining limitations. Distinguish
synthetic checks, upstream emission, compilation and actual browser/game
results. Do not infer compatibility from a successful build.

## Reporting a problem

Include your host OS and architecture, Python/Node/WASI SDK versions, repository
revision, command or in-game steps, expected behavior and first relevant error.
For browser reports, include the browser version, whether startup feature checks
passed, and the failing stage. Follow [browser-testing.md](docs/browser-testing.md)
to collect a local log.

Inspect logs before sharing. Post only the minimal relevant excerpt, removing
personal paths, profile names or other private information. Do not attach
catalogs, generated game code, game files or memory dumps. Reports involving a
different executable should give its hash and layout details rather than the
binary itself.

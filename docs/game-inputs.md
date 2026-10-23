# Supported local game inputs

Supply your own legally obtained PC Need for Speed Underground installation.
This repository contains no game files and provides no game download source.
The current integration targets one exact executable associated with PC patch
1.4. Other editions or executables are unverified, even if their displayed
version is the same. Follow the [build guide](building.md) to stage inputs
under ignored `work/` without modifying originals.

## Executable fingerprint

Read-only local inspection on 2026-10-21 measured the following input:

| Property | Selected executable |
| --- | --- |
| Filename | `Speed.exe` |
| Executable bytes | 3,178,496 |
| Image base | `0x00400000` |
| SizeOfImage | `0x00394368` |
| Entry RVA | `0x00270cb5` |
| Entry VA | `0x00670cb5` |

SHA-256:

```text
c0fad450912952f53809a54690d235aa8b4e25b9f46650693c7cbee1b4c074b7
```

Check your file before building; on macOS:

```sh
shasum -a 256 /path/to/your/Speed.exe
```

The pinned upstream README publishes only `c0fad450…c074b7`. The full digest
above is a local measurement, not an independently verified full upstream
fingerprint. Its prefix/suffix and PE loader fields match the upstream
references. The analysis pipeline checks this full digest before generating or
reusing catalogs. Do not bypass the check: a different binary can have
incompatible function addresses and runtime layouts.

A second locally inspected executable had 3,121,152 bytes, image base
`0x00400000`, SizeOfImage `0x00385d98`, entry RVA `0x00264245`, and SHA-256
`6e472463ae43279ea09bfa4aac8d6d2a544104fde83e2e4bb52808f6aae761a2`.
Its exact patch version was not established; its layout does not match the
current catalog or override addresses.

The selected executable imports 254 functions across 15 DLLs. Its `.text`
virtual extent is `0x00401000..0x00696ea7` (end exclusive), size `0x00295ea7`.
Raw section alignment extends to `0x00697000`; padding is outside that virtual
extent. These measured values are recorded in the
[integration profile](../profiles/nfsu1-pc.json), which is separate from a
player save profile.

## Game data

Stage the contents of your matching installation under `work/data/`, including
`Cars`, `FrontEnd`, `Global`, `Tracks`, `Languages`, `fx`, `Sound`, `Movies`,
`SNDSTREAMS` and `SpeechStreams`. The build guide describes the expected
`Speed.exe` path and allowed symlink. Preserve the installation's filenames and
directory structure. Sound-bank analysis reads `Sound/**/*.abk`.

The locally inspected inputs contained 106 `.abk` sound banks and 25 movie
entries. These counts are observations, not a substitute for matching data or
a complete asset compatibility check. Native Windows plugins, ASI mods and
their patches are outside this build's supported input path.

During bring-up, missing media directories were staged locally and their
150 files fingerprinted in ignored `work/data-extraction.metadata.json`.
Original archives and executables were left unchanged. All staged assets,
catalogs and generated game code must remain local. User reports cover intro
movies with sound, profile creation and loading, and starting a race; they do
not establish compatibility with every asset or a completed race. See
[current progress](progress.md).

Upstream references: [loader checks](https://github.com/codepdbh/nfsu1-recompiled/blob/58d9d4f63d59c941031f91973ae48c2cdb1a42b1/android/app/src/main/cpp/guest_runtime.cpp),
[abbreviated fingerprint](https://github.com/codepdbh/nfsu1-recompiled/blob/58d9d4f63d59c941031f91973ae48c2cdb1a42b1/README.md).

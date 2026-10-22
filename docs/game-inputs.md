# Local archive selection

Read-only inspection on 2026-10-21 selected **`Need For Speed - Underground.7z`**
as the PC NFSU1 1.4 candidate for integration. Executable members were decompressed
into memory for hashing and PE metadata inspection. Neither archive nor original
game binary was modified; no executable bytes were saved or distributed.

| Property | Selected larger archive | Smaller installed-English archive |
| --- | --- | --- |
| Archive | `Need For Speed - Underground.7z` | `Need_for_Speed_Underground_Win_Installed_EN.7z` |
| Executable member | `Need For Speed Underground/speed.exe` | `Need_for_Speed_Underground_Win_Installed_EN/Game Files/Speed.exe` |
| Executable bytes | 3,178,496 | 3,121,152 |
| Image base | `0x00400000` | `0x00400000` |
| SizeOfImage | `0x00394368` | `0x00385d98` |
| Entry RVA | `0x00270cb5` | `0x00264245` |
| Entry VA | `0x00670cb5` | `0x00664245` |
| Matches upstream structural checks | Yes | No |
| Matches published hash prefix/suffix | Yes | No |

Selected executable SHA-256:

```text
c0fad450912952f53809a54690d235aa8b4e25b9f46650693c7cbee1b4c074b7
```

The upstream README publishes only `c0fad450…c074b7`. The full digest above is
our local measurement, not an independently verified full upstream fingerprint.
Combined with exact loader-field matches, this is the selected input. The local
analysis pipeline checks this full digest before generating or reusing catalogs.

The smaller executable's SHA-256 is
`6e472463ae43279ea09bfa4aac8d6d2a544104fde83e2e4bb52808f6aae761a2`.
Its exact patch version was not established; its differing layout makes it
unsuitable for directly reusing the current 1.4 catalog and override addresses.

The selected executable imports 254 functions across 15 DLLs. Its `.text`
virtual extent is `0x00401000..0x00696ea7` (end exclusive), size `0x00295ea7`.
Raw section alignment extends to `0x00697000`; do not confuse padding with the
virtual extent. Catalog coverage must be validated before choosing final
dispatch bounds.

Both archives list 106 `.abk` sound banks and 25 movie entries. Counts alone do
not establish identical assets. The larger archive additionally contains
`dinput8.dll` and five ASI mods. Initial browser integration should use the game
executable/data path without loading these native Windows plugins or applying
their patches. No archive programs were executed.

The [profile](../profiles/nfsu1-pc.json) now records the measured fingerprint
and section bounds. It remains an integration specification, not a player save
profile. A reversible overlay now consumes it in the runtime source, and the
catalog has been generated locally and cached. The linked browser build has
reached user-reported intro playback, profile loading and race start; see
[current progress](progress.md). Remaining emission stubs still limit compatibility.

During later bring-up, the selected archive's `Sound`, `Movies`, `SNDSTREAMS`
and `SpeechStreams` data directories were extracted locally into ignored
`work/data/` to satisfy observed missing-file requests. Their 150 files and
source archive are fingerprinted in `work/data-extraction.metadata.json`.
Original archives and executables remain unchanged; these staged assets must
remain local. The user subsequently reported working intro movies with sound;
this does not establish compatibility with all media.

Upstream references: [loader checks](https://github.com/codepdbh/nfsu1-recompiled/blob/58d9d4f63d59c941031f91973ae48c2cdb1a42b1/android/app/src/main/cpp/guest_runtime.cpp),
[abbreviated fingerprint](https://github.com/codepdbh/nfsu1-recompiled/blob/58d9d4f63d59c941031f91973ae48c2cdb1a42b1/README.md).

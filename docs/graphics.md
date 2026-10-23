# Graphics settings

`NFSU1_GRAPHICS=low|medium|high|max|game` selects detail for the next game
launch. The default is `max`. `game` leaves the profile's graphics choices
under the game's control. Render resolution is automatic.

On the website, open **Settings → Graphics**. **Graphics quality** offers
Game, Low, Medium, High and Maximum. The `settings.ini` key is
`graphics_quality`; changes apply on the next start/profile load.

Render resolution always follows the live window or full-screen canvas at
its device pixel density. There is no resolution selector or fixed preset
ceiling. Widescreen uses the whole canvas, subject to the 8192-pixel
dimension limit. With `NFSU1_WIDESCREEN=0`, the host fits the saved guest
aspect (4:3 or 5:4) inside the canvas instead.

After a resize settles for 250 ms, the existing upstream device-loss path
asks the game to release and recreate its render targets at the new size.
The image grows or shrinks without restarting. Resize requests are limited
to one every two seconds while the game recovers. Old `render_resolution`
settings and fixed `NFSRES` overrides are ignored by the website, so restored
settings cannot pin the resolution. Graphics quality remains selectable.

The adapter runs after initial device/capability setup and after the game
loads its profile settings. New profiles inherit the initial choice. It applies the
requested detail with the game's own capability limits, so an effect the
runtime does not advertise remains disabled. In-game changes can still take
effect during that session; choosing a website preset applies it again when
the profile is next loaded. The game's normal save operation may persist the
active choices into its profile configuration.

## Verified NFSU1 mapping

These are NFSU1 profile `.cfg` names, **not NFSU2 registry names**. NFSU1's
graphics loader reads a text configuration and its writer saves it. Seeding
the upstream NFSU2 `g_*` registry values does not configure these settings.

The four website presets follow the game's four original detail levels
(`PERFORMANCE=0..3`). The low preset intentionally retains the original game's
light glow, animated textures and basic car lighting. Medium's car-lighting
value also follows the original game.

| Setting | Meaning | Low | Medium | High | Max | Guest value | Guest capability |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| `ENVMAP` | Car environment reflections | 0 | 1 | 2 | 3 | `0x700e74` | `0x701040` |
| `WORLDENVMAP` | World environment mapping | 0 | 0 | 1 | 1 | `0x700e78` | `0x701044` |
| `SHADOW` | Car shadows | 1 | 1 | 2 | 2 | `0x700e7c` | `0x701048` |
| `HEADLIGHTS` | Headlights | 0 | 0 | 1 | 1 | `0x700e80` | `0x70104c` |
| `CARLIGHTING` | Car lighting | 1 | 0 | 1 | 1 | `0x700e84` | `0x701050` |
| `DAMAGE` | Damage effects | 0 | 0 | 1 | 1 | `0x700e88` | `0x701054` |
| `CROWD` | Crowds | 0 | 0 | 1 | 1 | `0x700e8c` | `0x701058` |
| `ROADREFLECTION` | Road reflections | 0 | 1 | 2 | 2 | `0x700e90` | `0x70105c` |
| `FOG` | Fog | 0 | 0 | 1 | 1 | `0x700e94` | `0x701060` |
| `MOTIONBLUR` | Motion blur | 0 | 0 | 0 | 1 | `0x700e98` | `0x701064` |
| `LIGHTSTREAKS` | Light streaks | 0 | 0 | 0 | 1 | `0x700e9c` | `0x701068` |
| `LIGHTGLOW` | Light glow | 1 | 1 | 1 | 1 | `0x700ea0` | `0x70106c` |
| `ANIMATEDTEXTURE` | Animated textures | 1 | 1 | 1 | 1 | `0x700ea4` | `0x701070` |
| `PARTICLESYSTEMS` | Particle effects | 0 | 1 | 1 | 1 | `0x700ea8` | `0x701074` |
| `DEPTHOFFIELD` | Depth of field | 0 | 0 | 1 | 1 | `0x700eac` | `0x701078` |
| `WorldLOD` | World geometry detail | 1 | 1 | 3 | 3 | `0x700eb0` | `0x70107c` |
| `CarLOD` | Car geometry detail | 0 | 1 | 1 | 1 | `0x700eb4` | `0x701080` |

`BPP`, `SOUNDPERF` and `SOUNDENABLE` share the configuration table but
are not changed by the detail adapter. `PERFORMANCE` lives at `0x736334`.
`RES` is an index into the game's legacy resolution list; it is not a pixel
width. Dynamic rendering supplies the actual pixel dimensions through the host;
the guest mode's aspect is preserved only with widescreen disabled. It does not rewrite `RES`.
Texture filtering and multisampling are not separate entries in this
NFSU1 table, and native NFSU2 renderer enhancements are not implied by Max.

## Local evidence and implementation

The mapping is specific to the selected PC patch 1.4 image with SHA-256
`c0fad450912952f53809a54690d235aa8b4e25b9f46650693c7cbee1b4c074b7`.
Read-only inspection of the existing private analysis image verified:

- The configuration descriptor table at `0x700ec0..0x700fc4` contains the
  names, value pointers and integer types.
- The preset routine at `0x410ed0..0x411026` defines levels 0 through 3.
- The clamp routine at `0x410ce0` maps each value to the corresponding
  capability limit. Capability setup starts at `0x410b70`.
- Initial graphics setup at `0x410e50` calls capability setup and automatic
  detail selection before the caller allocates effect resources. Applying the
  website choice after that first setup covers first launch and new profiles.
- The configuration loader at `0x41c680` reads the table and finishes through
  the capability clamp. Its direct caller loads the profile at `0x41d080`.
  The writer starts at `0x41c7a0`.

The original adapter is [runtime/nfsu1_graphics.c](../runtime/nfsu1_graphics.c).
The build wraps `sub_00410e50` and `sub_0041c680` at link time. This must cover the direct caller
as well as dispatch-table references; a dispatch-only replacement is
insufficient. Private image data and emitted game code remain local.

Preset mapping and compilation checks establish the requested values and
hook wiring. They do not establish visual correctness, performance or full
compatibility of individual effects. Browser/game validation remains manual.

Local validation compared all 17 values at all four levels against execution
of the existing emitted original preset routine. Capability clamping, Game
passthrough, CPU state preservation, initial setup applying once, and 4:3
normalization passed focused native checks. A focused resize smoke also
executes the actual resolution selector and GPU resize watcher to verify
growth, shrinkage, 4:3/5:4 proportions and stable reset tracking. The private Wasm relink passed;
disassembly of real game callers confirmed both wrapper targets. The website
bundle, settings/startup checks and in-process HTTP checks also passed.
No browser was operated.

A bounded real-game Node run also forced device loss at frame 20 and reached
the original game's Reset/recovery path: the 800×600 guest mode recreated a
1440×1080 backbuffer for a 1920×1080 view, with aspect factor 1.0. It continued
until the planned 15-second deadline. This confirms command-line recovery,
not visible rendering or browser resize behavior.

## Widescreen

True widescreen uses the pinned PC project's NFSU1 hook sites (ThirteenAG
WidescreenFixesPack semantics via `codepdbh/nfsu1-recompiled`). Sites are
listed in `config/hooks.txt`, emitted with `tools/lift_catalog.py --hooks-file`,
and handled by `runtime/nfsu1_widescreen.c` through `guest_hook` →
`nfsu1_ws_hook`. The NFSU2 runtime's `widescreen.c` addresses are not used.

With `NFSU1_DYNAMIC_RESOLUTION=1` (browser default), the device follows the
canvas. Widescreen is on unless `NFSU1_WIDESCREEN=0`, which restores
guest-aspect letterboxing. When widescreen is active, clip-space
`aspfix` stays 1.0 so hooks correct FOV, HUD, minimap, mirror
and mouse hit tests. Re-emit after changing the hook list; the Wasm build
refuses a selection that lacks the key `guest_hook` sites.

Follow the focused [manual browser checks](browser-testing.md#what-to-try)
after rebuilding, restarting the local server and reloading the existing
origin. Check 16:9 FOV, HUD edges, FMV framing, menus/mouse and live resize.

The backbuffer and matching full-size render targets follow the canvas.
Original smaller post-processing buffers, including motion blur, retain the
game's own sizing rules.

The HUD scale and center are scoped to five verified instruction operands
by `tools/widescreen_operands.py`; the original shared float constants remain
intact for menu layout, clipping and animation. The three inherited FMV quad
hooks are accepted but inert: those helpers also draw menu rectangles and
loading artwork, so enlarging their extents crops images and overlaps menus.
Re-emission with the current lifter is required; the build rejects older
emissions without the scoped operand marker.

The focused native widescreen smoke checks unchanged shared constants,
unchanged quad extents and minimap center, in addition to resolution and FOV
hook behavior. Real emission verifies all five scoped operands. These are
command-line checks. The private Wasm relink and browser bundle/startup
checks also passed; visual layout and movie framing still require the user
browser checks.

## Character skinning

The browser WGSL translator must preserve relative constant addressing in
matrix instructions. The original translator resolved `m4x4` matrix rows as
fixed constants, ignoring the address register selected by the character
shader. This made all three weighted position transforms read bone zero,
while normal calculations still used the selected bones. The result was
incorrect limb poses.

The runtime overlay now resolves each consecutive matrix row through the
existing source-operand helper. That preserves dynamic bone selection and
shader-defined constants for the matrix instruction family. This change is
in `runtime/web/vsemu_wgsl.inc` in the pinned upstream, applied reversibly by
`tools/apply_runtime_profile.py`; no game re-emission is needed.

A bounded Node run captured the real startup-created character shader and
confirmed three affected matrix operations. That run dropped graphics output;
it establishes shader reachability, not visible rendering. The focused
`tools/skinning_shader_smoke.py` uses authored synthetic shader data to check
CPU bone transforms and generated WGSL matrix addressing; it passes the
overlay and fails the pinned original. Wasm linking, browser bundling and
startup checks also passed. Browser validation
must still check crowd and starter poses and animation during a race start.

# Tools

Python here is for building Wasm/catalogs on a workstation, the same way upstream nfsu2-web keeps `tools/lift.py`.

## Host / serve (no Python)

| Command | Role |
| --- | --- |
| `../start.sh` | Build `nfsu1-server` if needed and serve the game |
| `../server/` | Rust HTTP server |
| `apply_runtime_profile.sh` | Apply `patches/nfsu2-web/runtime/**/*.patch` + copy `runtime/nfsu1_*` |
| `apply_browser_profile.sh` | Apply `patches/nfsu2-web/web/**/*.patch` + copy `browser/*` |

`gen_nfsu1_profile_h.py` only writes `nfsu1_profile.h` from `profiles/nfsu1-pc.json`.

## Lift / catalog (upstream Python, thin wrappers)

These call Capstone/pefile analysis the same way upstream does — we do not
reimplement the emitter here.

| Command | Invokes |
| --- | --- |
| `catalog.sh` | `prepare_game_catalog.py` → nfsu1-recompiled + pcrecomp scripts |
| `lift.sh` | `lift_catalog.py` → nfsu2-web `tools/lift.py` via `catalog_bridge.py` |

Related Python (`prepare_abk_catalog.py`, `lift_abk_catalog.py`, smokes) stays
for the same reason upstream keeps `tools/*.py`: analysis, not serving.

#!/usr/bin/env bash
# Apply NFSU1 runtime overlays as unified diffs + copied host sources.
# Usage: tools/apply_runtime_profile.sh --upstream work/upstream/nfsu2-web
#        tools/apply_runtime_profile.sh --upstream ... --revert
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UPSTREAM=""
REVERT=0
PROFILE="$ROOT/profiles/nfsu1-pc.json"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --upstream) UPSTREAM="$(cd "$2" && pwd)"; shift 2 ;;
    --profile) PROFILE="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"; shift 2 ;;
    --revert) REVERT=1; shift ;;
    -h|--help) sed -n '2,4p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$UPSTREAM" ]] || { echo "error: --upstream is required" >&2; exit 2; }
STATE="$UPSTREAM/.nfsu1-profile"
PATCH_ROOT="$ROOT/patches/nfsu2-web"

apply_patches() {
  local direction="$1"
  local patch
  while IFS= read -r -d '' patch; do
    local rel="${patch#"$PATCH_ROOT"/}"
    rel="${rel%.patch}"
    if [[ "$direction" == apply ]]; then
      # Skip if already applied (file matches patched content via --dry-run reverse).
      if patch -p1 -d "$UPSTREAM" --dry-run -R -i "$patch" >/dev/null 2>&1; then
        continue
      fi
      patch -p1 -d "$UPSTREAM" -N -i "$patch"
    else
      if patch -p1 -d "$UPSTREAM" --dry-run -R -i "$patch" >/dev/null 2>&1; then
        patch -p1 -d "$UPSTREAM" -R -i "$patch"
      fi
    fi
  done < <(find "$PATCH_ROOT/runtime" -name '*.patch' -print0 | sort -z)
}

copy_host() {
  install -d "$UPSTREAM/runtime"
  install -m 0644 "$ROOT/runtime/nfsu1_overrides.c" "$UPSTREAM/runtime/overrides.c"
  for f in "$ROOT"/runtime/nfsu1_*.c "$ROOT"/runtime/nfsu1_*.h "$ROOT"/runtime/*.inc \
           "$ROOT"/runtime/nfs_abk.h; do
    [[ -e "$f" ]] || continue
    install -m 0644 "$f" "$UPSTREAM/runtime/$(basename "$f")"
  done
  python3 "$ROOT/tools/gen_nfsu1_profile_h.py" --profile "$PROFILE" \
    --output "$UPSTREAM/runtime/nfsu1_profile.h"
}

if [[ "$REVERT" -eq 1 ]]; then
  apply_patches revert
  rm -f "$UPSTREAM/runtime/nfsu1_profile.h" "$UPSTREAM/runtime/overrides.c"
  for f in "$ROOT"/runtime/nfsu1_*.c "$ROOT"/runtime/nfsu1_*.h "$ROOT"/runtime/*.inc \
           "$ROOT"/runtime/nfs_abk.h; do
    [[ -e "$f" ]] || continue
    rm -f "$UPSTREAM/runtime/$(basename "$f")"
  done
  rm -f "$STATE/state.json"
  echo "Reverted NFSU1 runtime patches under $UPSTREAM"
  exit 0
fi

mkdir -p "$STATE"
# Backup pristine copies once, from current tree before first apply.
while IFS= read -r -d '' patch; do
  rel="${patch#"$PATCH_ROOT"/}"
  rel="${rel%.patch}"
  backup="$STATE/$rel"
  if [[ ! -f "$backup" ]]; then
    mkdir -p "$(dirname "$backup")"
    cp "$UPSTREAM/$rel" "$backup"
  fi
done < <(find "$PATCH_ROOT/runtime" -name '*.patch' -print0 | sort -z)

apply_patches apply
copy_host
python3 - <<PY
import hashlib, json
from pathlib import Path
state = {
  "kind": "nfsu1-runtime-patches",
  "profile_sha256": hashlib.sha256(Path("$PROFILE").read_bytes()).hexdigest(),
  "patches": sorted(p.relative_to(Path("$PATCH_ROOT")).as_posix()
                    for p in Path("$PATCH_ROOT/runtime").rglob("*.patch")),
}
Path("$STATE/state.json").write_text(json.dumps(state, indent=2) + "\n")
print(f"Applied NFSU1 runtime patches to $UPSTREAM")
PY

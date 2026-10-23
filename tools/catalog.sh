#!/usr/bin/env bash
# Cache the NFSU1 catalog via upstream nfsu1-recompiled + pcrecomp scripts.
# Thin wrapper around tools/prepare_game_catalog.py (which only orchestrates
# pinned upstream Python — Capstone/pefile analysis stays where upstream put it).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$ROOT/tools/prepare_game_catalog.py" "$@"

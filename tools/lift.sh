#!/usr/bin/env bash
# Emit web-ABI C by driving upstream nfsu2-web tools/lift.py through the
# NFSU1 catalog bridge (no local reimplementation of the emitter).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$ROOT/tools/lift_catalog.py" "$@"

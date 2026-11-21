#!/usr/bin/env bash
# Main runtime: the pinned, qualified full Meshroom 2026 distribution.
# The corrected 2023.3 recipe remains at Git commit f3173b3.
set -Eeuo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
exec bash "$repo/scripts/bootstrap_meshroom_2026.sh" "$@"

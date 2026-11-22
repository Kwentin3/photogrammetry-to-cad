#!/usr/bin/env bash
# Historical Goal #4 fixed examples. General captures: reconstruction.py/runbook.
# Usage: bash prepare_graphs.sh RUN_ROOT MESHROOM_ROOT
set -Eeuo pipefail
[[ $# == 2 ]] || { echo 'Usage: prepare_graphs.sh RUN_ROOT MESHROOM_ROOT' >&2; exit 2; }
run_root=$(realpath -e -- "$1")
meshroom=$(realpath -e -- "$2")
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$meshroom/env.sh"
exec "$MESHROOM_PYTHON" "$repo/scripts/prepare_graphs_2026.py" "$run_root" "$meshroom"

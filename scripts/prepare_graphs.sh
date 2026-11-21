#!/usr/bin/env bash
# Prepare the three bounded technical inputs using Meshroom's native graph builder.
# No reconstruction is performed here. Job time/resource ownership stays with caller.
# Usage: bash prepare_graphs.sh RUN_ROOT MESHROOM_ROOT
set -Eeuo pipefail
[[ $# == 2 ]] || { echo 'Usage: prepare_graphs.sh RUN_ROOT MESHROOM_ROOT' >&2; exit 2; }
run_root=$(realpath -e -- "$1")
meshroom=$(realpath -e -- "$2")
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$meshroom/env.sh"
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8
mkdir -p -- "$run_root/projects" "$run_root/cache"
for dataset in dice cctag synthetic-markers; do
    input=$run_root/input/$dataset
    case "$dataset" in
        dice) config=$repo/configs/photos.json ;;
        cctag) config=$repo/configs/cctag.json ;;
        synthetic-markers) input=$input/images; config=$repo/configs/synthetic-markers.json ;;
    esac
    [[ -d $input ]] || { echo "Missing input: $input" >&2; exit 1; }
    pipeline=photogrammetry
    if [[ $dataset == synthetic-markers ]]; then
        # In 2023.3.0 CameraInit.initialize runs BEFORE --overrides are applied.
        # Set the known fixture FOV in the native template first, so its emitted
        # intrinsics start at fx=1000 px rather than the default 45-degree guess.
        pipeline=$run_root/projects/synthetic-template.mg
        python3 - "$meshroom/lib/meshroom/pipelines/photogrammetry.mg" "$config" "$pipeline" <<'PY'
import json
import sys
from pathlib import Path
template, config, output = map(Path, sys.argv[1:])
graph = json.loads(template.read_text())
if graph["header"]["releaseVersion"] != "2023.3.0":
    raise SystemExit("Recheck template initialization against the installed Meshroom version")
overrides = json.loads(config.read_text())
graph["graph"]["CameraInit_1"]["inputs"]["defaultFieldOfView"] = overrides["CameraInit_1"]["defaultFieldOfView"]
output.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
PY
    fi
    "$meshroom/meshroom_batch" --input "$input" --pipeline "$pipeline" \
        --overrides "$config" --cache "$run_root/cache/$dataset" \
        --save "$run_root/projects/$dataset.mg" --compute no
done

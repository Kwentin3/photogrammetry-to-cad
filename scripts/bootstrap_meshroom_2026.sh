#!/usr/bin/env bash
# Install the pinned, retained full bundle. No download, compilation or cloud API.
# Run under remote_job.sh after arming the per-instance deadline.
# Usage: bash bootstrap_meshroom_2026.sh INSTALL_DIR --archive RETAINED_ARCHIVE
set -Eeuo pipefail
umask 077
die() { printf '%s\n' "$*" >&2; exit 1; }
[[ $# == 3 && $2 == --archive ]] || die 'Usage: bootstrap_meshroom_2026.sh INSTALL_DIR --archive FILE'
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || die 'Requires Linux x86_64'
for tool in python3 tar sha256sum flock timeout realpath grep ldd; do
    command -v "$tool" >/dev/null || die "Missing system tool: $tool"
done
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
lock=$repo/configs/runtime-2026.json
mapfile -t pinned < <(python3 - "$lock" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as stream:
    lock = json.load(stream)
for key in ("archive_sha256", "archive_bytes", "bundle_directory"):
    print(lock[key])
PY
)
[[ ${#pinned[@]} == 3 ]] || die 'Cannot read pinned runtime metadata'
expected=${pinned[0]}; expected_bytes=${pinned[1]}; bundle_name=${pinned[2]}
[[ $expected =~ ^[0-9a-f]{64}$ && $expected_bytes =~ ^[1-9][0-9]*$ ]] || die 'Invalid runtime lock'
[[ $bundle_name =~ ^Meshroom-[A-Za-z0-9.-]+$ ]] || die 'Invalid bundle directory'
archive=$(realpath -e -- "$3")
[[ $(stat -c %s -- "$archive") == "$expected_bytes" ]] || die 'Archive size differs from pin'
actual=$(sha256sum -- "$archive"); actual=${actual%% *}
[[ $actual == "$expected" ]] || die 'Archive SHA256 differs from pin'
mkdir -p -- "$1"
install_dir=$(realpath -- "$1")
[[ $install_dir != / ]] || die 'Refusing root install directory'
exec 9>"$install_dir/.meshroom-bootstrap.lock"
flock -n 9 || die 'Another bootstrap owns this install directory'
target=$install_dir/$bundle_name
if [[ -e $target ]]; then
    [[ -f $target/.archive.sha256 && $(cat "$target/.archive.sha256") == "$actual" ]] \
        || die 'Existing install is not bound to this archive; choose a new install directory'
else
    stage=$(mktemp -d "$install_dir/.meshroom-extract.XXXXXXXX")
    printf 'Extracting verified bundle into %s\n' "$stage"
    # Preserve interrupted extraction for diagnosis; remove only empty owned dirs.
    timeout --signal=TERM --kill-after=15s 300s tar -xzf "$archive" \
        --no-same-owner --no-same-permissions -C "$stage"
    bundle=$stage/$bundle_name
    [[ -x $bundle/meshroom_batch && -x $bundle/python/bin/python3 ]] || die 'Incomplete full bundle'
    [[ -x $bundle/aliceVision/bin/aliceVision_featureExtraction ]] || die 'Missing native AliceVision'
    printf '%s\n' "$actual" >"$bundle/.archive.sha256"
    mv -- "$bundle" "$target"
    rmdir -- "$stage"
fi
mkdir -p -- "$target/probes"
{
    printf '# Pinned distribution environment for native CLI and Graph API.\n'
    printf 'export MESHROOM_INSTALL_DIR=%q\n' "$target"
    printf 'export ALICEVISION_ROOT=%q\n' "$target/aliceVision"
    printf 'export MESHROOM_PYTHON=%q\n' "$target/python/bin/python3"
    printf '%s\n' \
      'export PATH="$ALICEVISION_ROOT/bin:$MESHROOM_INSTALL_DIR:$MESHROOM_INSTALL_DIR/python/bin:$PATH"' \
      'export LD_LIBRARY_PATH="$ALICEVISION_ROOT/lib64:$ALICEVISION_ROOT/lib:$MESHROOM_INSTALL_DIR/python/lib:$MESHROOM_INSTALL_DIR/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"' \
      'export PYTHONPATH="$MESHROOM_INSTALL_DIR/lib${PYTHONPATH:+:$PYTHONPATH}"' \
      'export QT_QPA_PLATFORM=offscreen'
} >"$target/env.sh.tmp"
mv -- "$target/env.sh.tmp" "$target/env.sh"
source "$target/env.sh"
timeout --signal=TERM --kill-after=5s 60s "$target/meshroom_batch" --help >"$target/probes/meshroom_batch-help.txt" 2>&1
for option in --overrideCacheDir --graphInput --save --toNode; do
    grep -Fq -- "$option" "$target/probes/meshroom_batch-help.txt" || die "Missing native batch option $option"
done
timeout --signal=TERM --kill-after=5s 60s "$target/meshroom_compute" --help >"$target/probes/meshroom_compute-help.txt" 2>&1
grep -Fq -- --cache "$target/probes/meshroom_compute-help.txt" || die 'Missing compute cache option'
timeout --signal=TERM --kill-after=5s 60s "$MESHROOM_PYTHON" - >"$target/probes/graph-api.txt" 2>&1 <<'PY'
import os, pathlib, sys
import meshroom
meshroom.setupEnvironment()
import meshroom.core
from meshroom.core.graph import Graph
meshroom.core.initPipelines()
root = pathlib.Path(os.environ["MESHROOM_INSTALL_DIR"]).resolve()
module = pathlib.Path(meshroom.__file__).resolve()
assert root in module.parents, "Meshroom module must come from pinned distribution"
assert "photogrammetryLegacy" in meshroom.core.pipelineTemplates
print("python=" + sys.executable)
print("meshroom=" + str(module))
print("legacy_template=" + meshroom.core.pipelineTemplates["photogrammetryLegacy"])
print("graph_api=" + Graph.__module__)
PY
probe() {
    local name=$1 rc=0
    ldd "$ALICEVISION_ROOT/bin/$name" >"$target/probes/$name-ldd.txt" 2>&1
    if grep -Fq 'not found' "$target/probes/$name-ldd.txt"; then die "Missing shared library for $name; inspect probe"; fi
    timeout --signal=TERM --kill-after=5s 30s "$ALICEVISION_ROOT/bin/$name" --help >"$target/probes/$name-help.txt" 2>&1 || rc=$?
    [[ $rc == 0 || $rc == 1 ]] || die "$name native help failed ($rc)"
    grep -Fq -- --input "$target/probes/$name-help.txt" || die "$name did not print native help"
}
probe aliceVision_featureExtraction
grep -wq cctag3 "$target/probes/aliceVision_featureExtraction-help.txt" || die 'Missing native CCTag3'
probe aliceVision_sfmTransform
grep -wq from_markers "$target/probes/aliceVision_sfmTransform-help.txt" || die 'Missing native marker scale'
probe aliceVision_depthMapEstimation
printf 'archive_sha256=%s\nchecked_utc=%s\n' "$actual" "$(date -u +%FT%TZ)" >"$target/probes/runtime.txt"
printf 'Pinned native imports/help probes passed: %s\nGraph generation and GPU computation require separate checks.\n' "$target"

#!/usr/bin/env bash
# Linux x86_64. No cloud/account operations, package installs or GPU calculations.
# Source: https://github.com/alicevision/Meshroom/releases/tag/v2023.3.0
# Usage: bash bootstrap_meshroom.sh INSTALL_DIR [--archive FILE] [--sha256 HASH]
# Supply the SHA256 recorded from the independently downloaded official archive.
# Without --sha256 this records the actual hash; it does not claim external verification.
set -Eeuo pipefail
umask 077

die() { printf '%s\n' "$*" >&2; exit 1; }
[[ $# -ge 1 ]] || die 'Usage: bootstrap_meshroom.sh INSTALL_DIR [--archive FILE] [--sha256 HASH]'
install_dir=$1; shift
archive=''; expected=''
while (($#)); do
    case "$1" in
        --archive) [[ $# -ge 2 ]] || die 'Missing archive'; archive=$2; shift 2 ;;
        --sha256) [[ $# -ge 2 ]] || die 'Missing SHA256'; expected=${2,,}; shift 2 ;;
        *) die "Unknown option: $1" ;;
    esac
done
[[ -z $expected || $expected =~ ^[0-9a-f]{64}$ ]] || die 'Invalid SHA256'
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || die 'Requires Linux x86_64'
for tool in curl tar sha256sum flock timeout find realpath; do
    command -v "$tool" >/dev/null || die "Missing tool: $tool"
done
mkdir -p -- "$install_dir"
install_dir=$(realpath -- "$install_dir")
[[ $install_dir != / ]] || die 'Refusing filesystem root as install directory'
exec 9>"$install_dir/.meshroom-bootstrap.lock"
flock -n 9 || die 'Another bootstrap owns this install directory'
version=2023.3.0
url=https://github.com/alicevision/Meshroom/releases/download/v2023.3.0/Meshroom-2023.3.0-linux.tar.gz
target=$install_dir/Meshroom-$version
if [[ -z $archive ]]; then
    archive=$install_dir/Meshroom-$version-linux.tar.gz
    if [[ ! -f $archive ]]; then
        # A failed transfer leaves only .part; a later invocation resumes that file.
        timeout --signal=TERM --kill-after=15s 1200s curl --fail --location \
            --proto '=https' --proto-redir '=https' --connect-timeout 20 \
            --max-time 1000 --retry 3 --retry-delay 2 --retry-max-time 1100 \
            --speed-limit 1024 --speed-time 60 --continue-at - \
            --output "$archive.part" "$url"
        mv -- "$archive.part" "$archive"
    fi
fi
archive=$(realpath -e -- "$archive")
actual=$(sha256sum -- "$archive"); actual=${actual%% *}
[[ -z $expected || $actual == "$expected" ]] || die "Archive SHA256 mismatch: $actual"
printf '%s  %s\n' "$actual" "$(basename -- "$archive")" >"$install_dir/archive.sha256.tmp"
mv -- "$install_dir/archive.sha256.tmp" "$install_dir/archive.sha256"
if [[ -d $target ]]; then
    [[ -f $target/.archive.sha256 && $(cat "$target/.archive.sha256") == "$actual" ]] \
        || die 'Existing install is not bound to this archive; use a new install directory'
else
    [[ ! -e $target ]] || die 'Install target already exists'
    stage=$(mktemp -d "$install_dir/.meshroom-extract.XXXXXXXX")
    # Preserve a failed extraction for diagnosis; never delete unknown directories.
    printf 'Extracting into %s\n' "$stage"
    timeout --signal=TERM --kill-after=15s 300s tar -xzf "$archive" \
        --no-same-owner --no-same-permissions -C "$stage"
    mapfile -d '' launchers < <(find "$stage" -maxdepth 3 -type f -name meshroom_batch -print0)
    [[ ${#launchers[@]} == 1 ]] || die 'Expected exactly one meshroom_batch in archive'
    bundle=$(dirname -- "${launchers[0]}")
    [[ -x $bundle/aliceVision/bin/aliceVision_featureExtraction ]] || die 'Missing AliceVision binary'
    printf '%s\n' "$actual" >"$bundle/.archive.sha256"
    mv -- "$bundle" "$target"
    # Only empty task-owned extraction directories are removed.
    find "$stage" -depth -type d -empty -delete
fi
mkdir -p -- "$target/probes"
{
    printf '# Source this file before direct AliceVision commands.\n'
    printf 'export ALICEVISION_ROOT=%q\n' "$target/aliceVision"
    printf '%s\n' 'export PATH="$ALICEVISION_ROOT/bin:$PATH"' \
        'export LD_LIBRARY_PATH="$ALICEVISION_ROOT/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"'
} >"$target/env.sh.tmp"
mv -- "$target/env.sh.tmp" "$target/env.sh"
# Direct AliceVision executables need their own bundled shared libraries.
# Keep any existing search path after the version-bound package directory.
source "$target/env.sh"
timeout --signal=TERM --kill-after=5s 60s "$target/meshroom_batch" --help \
    >"$target/probes/meshroom_batch-help.txt" 2>&1
for option in --cache --save --toNode --forceStatus; do
    grep -Fq -- "$option" "$target/probes/meshroom_batch-help.txt" || die "Missing native option $option"
done
probe() {
    local name=$1 rc=0
    timeout --signal=TERM --kill-after=5s 30s "$ALICEVISION_ROOT/bin/$name" --help \
        >"$target/probes/$name-help.txt" 2>&1 || rc=$?
    # AliceVision versions can report help using exit 1; a loader error is not help.
    [[ $rc == 0 || $rc == 1 ]] || die "$name help failed ($rc); inspect probes"
    grep -q -- '--input' "$target/probes/$name-help.txt" || die "$name did not print native help"
}
probe aliceVision_featureExtraction
grep -wq cctag3 "$target/probes/aliceVision_featureExtraction-help.txt" \
    || die 'This binary was not built with native CCTag3 support'
probe aliceVision_sfmTransform
grep -wq from_markers "$target/probes/aliceVision_sfmTransform-help.txt" || die 'Missing marker transform'
probe aliceVision_depthMapEstimation
printf 'version=%s\narchive_sha256=%s\nexternal_sha256_verified=%s\nchecked_utc=%s\n' \
    "$version" "$actual" "$([[ -n $expected ]] && echo yes || echo no)" "$(date -u +%FT%TZ)" \
    >"$target/probes/runtime.txt.tmp"
mv -- "$target/probes/runtime.txt.tmp" "$target/probes/runtime.txt"
printf 'Runtime: %s\nSHA256: %s\nNative help probes passed; GPU computation is still untested.\n' "$target" "$actual"

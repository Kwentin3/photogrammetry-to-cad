#!/usr/bin/env bash
# Optional Linux ML venv. Requires retained packages and pinned SAM2 source;
# performs no download, cloud API call or CUDA compilation. Base AV is untouched.
# Run under the existing remote_job.sh owner/deadline, not an unowned SSH shell.
# Usage: bash bootstrap_auto_masks.sh ENV_DIR --wheelhouse DIR --sam-source TAR_GZ
set -Eeuo pipefail
umask 077
die() { printf '%s\n' "$*" >&2; exit 1; }
[[ $# == 5 && $2 == --wheelhouse && $4 == --sam-source ]] || die \
    'Usage: bootstrap_auto_masks.sh ENV_DIR --wheelhouse DIR --sam-source TAR_GZ'
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || die 'Requires Linux x86_64'
for tool in /usr/bin/python3.12 flock realpath sha256sum; do
    command -v "$tool" >/dev/null || die "Missing system tool: $tool (Ubuntu 24.04: python3.12-venv)"
done
# Deliberately do not inherit the Meshroom bundle's Python, Qt or shared libraries.
unset PYTHONPATH PYTHONHOME LD_PRELOAD
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export LD_LIBRARY_PATH=/usr/local/nvidia/lib:/usr/local/nvidia/lib64
export PYTHONNOUSERSITE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INDEX=1
export SAM2_BUILD_CUDA=0 SAM2_BUILD_ALLOW_ERRORS=0
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
lock=$repo/requirements-auto-masks-linux-py312.txt
models=$repo/configs/auto-mask-models.json
wheelhouse=$(realpath -e -- "$3")
source_archive=$(realpath -e -- "$5")
[[ -d $wheelhouse && -f $source_archive ]] || die 'Missing retained artifacts'
target=$(realpath -m -- "$1")
case "$target" in
    /|"$repo"|"$repo"/*) die 'Keep the optional environment outside the source checkout' ;;
esac
[[ ! -e $target ]] || die 'Choose a new dedicated environment directory'
mkdir -- "$target" || die 'Choose a new directory with an existing parent'
exec 9>"$target/.bootstrap.lock"
flock -n 9 || die 'Another bootstrap owns this environment'
seed=$target/.bootstrap-seed.txt
/usr/bin/python3.12 - "$lock" "$models" "$source_archive" "$seed" <<'PY'
import hashlib, json, pathlib, re, sys
lock, models, archive, seed = map(pathlib.Path, sys.argv[1:])
pin = json.loads(models.read_text())["sam2"]["source_archive"]
assert archive.stat().st_size == pin["bytes"], "SAM2 source size differs from pin"
with archive.open('rb') as stream:
    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
assert digest == pin["sha256"], "SAM2 source SHA256 differs from pin"
# Keep native requirements syntax and hashes for the three build tools. This is
# selection from an already resolved lock, not dependency resolution.
blocks = re.split(r'(?m)(?=^[a-zA-Z0-9][a-zA-Z0-9_.-]*==)', lock.read_text())
selected = [b for b in blocks if re.match(r'(pip|setuptools|wheel)==', b)]
assert len(selected) == 3, "Build tools absent from lock"
seed.write_text(''.join(selected))
PY
/usr/bin/python3.12 -m venv "$target"
python=$target/bin/python
"$python" -m pip install --no-index --find-links "$wheelhouse" --require-hashes --no-deps -r "$seed"
# antlr4 and iopath have small pure Python sdists. Build offline using the pinned
# installed setuptools/wheel, rather than allowing isolated-build downloads.
"$python" -m pip install --no-index --find-links "$wheelhouse" --require-hashes \
    --no-build-isolation -r "$lock"
"$python" -m pip install --no-index --no-deps --no-build-isolation "$source_archive"
"$python" -m pip check
"$python" - "$models" "$target" >"$target/environment.json" <<'PY'
import importlib.metadata as md
import importlib.resources
import importlib.util
import json, pathlib, sys
import torch, torchvision, sam2
from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
root = pathlib.Path(sys.argv[2]).resolve()
for module in (torch, torchvision, sam2):
    assert root in pathlib.Path(module.__file__).resolve().parents, module.__file__
assert torch.__version__ == '2.5.1+cu124' and torchvision.__version__ == '0.20.1+cu124'
assert md.version('transformers') == '4.51.3'
direct = json.loads(md.distribution('SAM-2').read_text('direct_url.json'))
pin = json.loads(pathlib.Path(sys.argv[1]).read_text())['sam2']['source_archive']
assert direct['archive_info']['hashes']['sha256'] == pin['sha256']
config = json.loads(pathlib.Path(sys.argv[1]).read_text())['sam2']['config']
assert importlib.resources.files('sam2').joinpath(config).is_file(), 'SAM2 config missing from installed package'
assert importlib.util.find_spec('sam2._C') is None, 'Unexpected SAM2 CUDA extension'
print(json.dumps(dict(python=sys.version, executable=sys.executable,
    torch=torch.__version__, torchvision=torchvision.__version__,
    transformers=md.version('transformers'), cuda_build=torch.version.cuda,
    sam2_module=sam2.__file__, sam2_direct_url=direct,
    sam2_build_cuda=False), indent=2))
PY
{
    printf '# Source only for the optional ML subprocess; never for Meshroom.\n'
    printf 'export AUTO_MASK_PYTHON=%q\n' "$python"
    printf '%s\n' 'unset PYTHONPATH PYTHONHOME LD_PRELOAD' \
      'export LD_LIBRARY_PATH=/usr/local/nvidia/lib:/usr/local/nvidia/lib64' \
      'export PYTHONNOUSERSITE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1' \
      'export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2'
} >"$target/env.sh"
rm -- "$seed"
printf 'Optional ML environment verified: %s\nOne-frame GPU inference and mask acceptance remain separate.\n' "$target"

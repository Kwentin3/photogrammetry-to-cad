"""Fetch a small pinned real photo set outside the source checkout (stdlib only)."""

import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request


DATASETS = {
    "dice": {
        "revision": "78e0a887ba5263da66910fb4f4da0d9763e9177a",
        "project": "https://gitlab.com/photogrammetry-test-sets/dice-turntable-strong-lights-heavily-textured-w-watercolors",
        "license": "CC BY 4.0",
        "attribution": "Photogrammetry Test Set: Dice - Turntable - Strong Lights - Heavily Textured w Watercolors, alansartlog",
        "count": 33,
        "bytes": 78215551,
    },
    "cctag": {
        "revision": "a04bedff34800e876c08bf1e4a46699d4a6439db",
        "project": "https://github.com/natowi/cctag-dataset",
        "license": "CC BY-SA 4.0",
        "attribution": "Pinecones CCTAG dataset, Natowi",
        "count": 50,
        "bytes": 74304634,
    },
}
DICE_FIRST20_BYTES = 47086536


def request(url, timeout):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "photogrammetry-to-cad/goal-2"}),
        timeout=timeout,
    )


def source_files(name, timeout):
    revision = DATASETS[name]["revision"]
    if name == "dice":
        url = ("https://gitlab.com/api/v4/projects/8723847/repository/tree"
               f"?ref={revision}&per_page=100")
    else:
        url = ("https://api.github.com/repos/natowi/cctag-dataset/git/trees/"
               f"{revision}?recursive=1")
    with request(url, timeout) as response:
        data = response.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError("Source metadata exceeds 1 MiB")
    tree = json.loads(data)
    if name == "cctag":
        if tree.get("truncated"):
            raise ValueError("GitHub returned a truncated source tree")
        tree = tree["tree"]
    files = []
    for item in tree:
        path = item["path"]
        if name == "dice" and path in {f"{n:02}.JPG" for n in range(1, 34)}:
            raw = ("https://gitlab.com/api/v4/projects/8723847/repository/files/"
                   f"{path}/raw?ref={revision}")
        elif name == "cctag" and path.startswith("full/") and path.endswith(".jpg"):
            raw = f"https://raw.githubusercontent.com/natowi/cctag-dataset/{revision}/{path}"
        else:
            continue
        files.append({"name": Path(path).name, "url": raw,
                      "git_blob_sha1": item.get("sha", item.get("id"))})
    files.sort(key=lambda item: item["name"])
    if len(files) != DATASETS[name]["count"]:
        raise ValueError(f"Pinned source has unexpected image count: {len(files)}")
    return files


def hashes(path):
    size = path.stat().st_size
    git_hash = hashlib.sha1(f"blob {size}\0".encode("ascii"))
    sha256 = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            git_hash.update(chunk)
            sha256.update(chunk)
    return size, git_hash.hexdigest(), sha256.hexdigest()


def save_manifest(output, name, files, records, total, complete=False):
    manifest = {**DATASETS[name], "dataset": name, "complete": complete,
                "selected_count": len(files),
                "subset": "01.JPG..20.JPG" if name == "dice" and len(files) == 20 else "full",
                "downloaded_bytes": total,
                "verification": "Git blob IDs from pinned upstream API tree; SHA-256 computed locally. No signed release authenticity claim.",
                "scale": "No physical reference distance supplied by upstream dataset.",
                "source_files": files, "files": records}
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
        raise ValueError("Manifest readback differs")
    return manifest_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", choices=DATASETS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, choices=[20], help="Dice: use the pinned first 20 images")
    parser.add_argument("--timeout", type=float, default=30, help="Per network operation, seconds")
    parser.add_argument("--deadline", type=float, default=480, help="Overall elapsed limit, seconds")
    parser.add_argument("--max-bytes", type=int, default=80000000, help="Total dataset byte ceiling")
    args = parser.parse_args()
    output = args.output.resolve()
    checkout = Path(__file__).resolve().parents[1]
    if output == checkout or checkout in output.parents:
        parser.error("Photo output must be outside the source checkout")
    if args.timeout <= 0 or args.deadline <= 0 or args.max_bytes <= 0:
        parser.error("Limits must be positive")
    info = DATASETS[args.dataset]
    if args.limit and args.dataset != "dice":
        parser.error("--limit is supported for the dice subset only")
    expected_bytes = DICE_FIRST20_BYTES if args.limit else info["bytes"]
    if expected_bytes > args.max_bytes:
        parser.error("Pinned dataset exceeds --max-bytes")
    deadline = time.monotonic() + args.deadline
    files = source_files(args.dataset, min(args.timeout, args.deadline))
    if args.limit:
        files = files[:args.limit]
    output.mkdir(parents=True, exist_ok=True)
    total = 0
    records = []
    save_manifest(output, args.dataset, files, records, total)
    for item in files:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Dataset download deadline exceeded")
        target = output / item["name"]
        if target.exists():
            size, blob, sha256 = hashes(target)
            if blob != item["git_blob_sha1"]:
                raise ValueError(f"Existing file differs from pinned Git blob: {target}")
        else:
            partial = target.with_suffix(target.suffix + ".part")
            if partial.exists():
                raise FileExistsError(f"Unowned partial file: {partial}")
            try:
                size = 0
                with request(item["url"], min(args.timeout, remaining)) as response, partial.open("xb") as stream:
                    while True:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Dataset download deadline exceeded")
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        size += len(chunk)
                        if total + size > args.max_bytes:
                            raise ValueError("Dataset exceeds --max-bytes")
                        stream.write(chunk)
                size, blob, sha256 = hashes(partial)
                if blob != item["git_blob_sha1"]:
                    raise ValueError(f"Download differs from pinned Git blob: {target.name}")
                partial.replace(target)
            finally:
                partial.unlink(missing_ok=True)
        total += size
        if total > args.max_bytes:
            raise ValueError("Dataset exceeds --max-bytes")
        records.append({**item, "bytes": size, "sha256": sha256})
        save_manifest(output, args.dataset, files, records, total)
        print(f"{len(records)}/{len(files)} {target.name} {size} bytes verified", flush=True)
    if total != expected_bytes:
        raise ValueError(f"Unexpected dataset byte total: {total}")
    manifest_path = save_manifest(output, args.dataset, files, records, total, complete=True)
    print(f"Saved {manifest_path}", flush=True)


if __name__ == "__main__":
    main()

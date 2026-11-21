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
# Inputs are flat image folders. Permit human-readable notes alongside them,
# without guessing which additional image formats a Meshroom version can read.
METADATA_SUFFIXES = {".json", ".txt", ".md", ".csv", ".log"}


def check_input_entries(directory, names):
    """Reject unlisted potential images; never remove somebody else's files."""
    names = list(names)
    if any(not isinstance(name, str) or not name or name in {".", ".."}
           or "/" in name or "\\" in name or ":" in name for name in names):
        raise ValueError("Input file names must be plain basenames")
    if not names or len(names) != len(set(names)):
        raise ValueError("Input file list must be nonempty and unique")
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError(f"Input must be a regular directory: {directory}")
    for path in directory.iterdir():
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Unexpected input entry: {path.name}")
        if path.name not in names and path.suffix.lower() not in METADATA_SUFFIXES:
            raise ValueError(f"Unlisted input file: {path.name}")


def verify_input(output, name):
    """Verify the existing download manifest or generator truth before scanning."""
    output = Path(output)
    if name == "synthetic-markers":
        truth = json.loads((output / "truth.json").read_text(encoding="utf-8"))
        if truth.get("synthetic") is not True:
            raise ValueError("Fixture must identify itself as synthetic")
        views = truth["views"]
        records = []
        for view in views:
            path = view["file"]
            if not isinstance(path, str) or not path.startswith("images/"):
                raise ValueError("Fixture views must be inside images/")
            records.append({"name": path[len("images/"):], "sha256": view["sha256"]})
        directory = output / "images"
    else:
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        if (manifest.get("dataset") != name or manifest.get("complete") is not True
                or manifest.get("revision") != DATASETS[name]["revision"]):
            raise ValueError("Input requires a complete manifest for the pinned dataset")
        records = manifest["files"]
        # The first full CCTag download recorded the pinned source fields in
        # files[] only. Later manifests also retain source_files[]. Both use the
        # same file hashes; the historical accepted input need not be rewritten.
        selected = manifest.get("source_files", records)
        count = len(selected)
        expected_count = 20 if name == "dice" and manifest.get("subset") == "01.JPG..20.JPG" else DATASETS[name]["count"]
        if count != expected_count or manifest.get("selected_count") != count:
            raise ValueError("Manifest selection has an unexpected image count")
        if len(records) != count:
            raise ValueError("Manifest does not record every selected image")
        for record, source in zip(records, selected):
            if any(record.get(key) != source.get(key) for key in ("name", "url", "git_blob_sha1")):
                raise ValueError("Manifest files differ from the pinned source selection")
        directory = output
    check_input_entries(directory, [record["name"] for record in records])
    total = 0
    for record in records:
        path = directory / record["name"]
        if not path.is_file():
            raise ValueError(f"Missing input file: {record['name']}")
        size, blob, sha256 = hashes(path)
        if sha256 != record["sha256"]:
            raise ValueError(f"Input SHA-256 differs: {record['name']}")
        if name != "synthetic-markers" and (size != record["bytes"] or blob != record["git_blob_sha1"]):
            raise ValueError(f"Input differs from pinned Git blob: {record['name']}")
        total += size
    if name != "synthetic-markers":
        expected_bytes = DICE_FIRST20_BYTES if count == 20 else DATASETS[name]["bytes"]
        if total != manifest["downloaded_bytes"] or total != expected_bytes:
            raise ValueError("Input byte total differs from the selected dataset")
    return directory, len(records)


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
    parser.add_argument("dataset", choices=[*DATASETS, "synthetic-markers"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true", help="Verify existing input and exit without network access")
    parser.add_argument("--limit", type=int, choices=[20], help="Dice: use the pinned first 20 images")
    parser.add_argument("--timeout", type=float, default=30, help="Per network operation, seconds")
    parser.add_argument("--deadline", type=float, default=480, help="Overall elapsed limit, seconds")
    parser.add_argument("--max-bytes", type=int, default=80000000, help="Total dataset byte ceiling")
    args = parser.parse_args()
    output = args.output.resolve()
    checkout = Path(__file__).resolve().parents[1]
    if output == checkout or checkout in output.parents:
        parser.error("Photo output must be outside the source checkout")
    if args.verify_only:
        directory, count = verify_input(output, args.dataset)
        print(f"Verified {args.dataset}: {count} input images in {directory}", flush=True)
        return
    if args.dataset == "synthetic-markers":
        parser.error("Synthetic input is generated by make_marker_fixture.py; use --verify-only")
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
    check_input_entries(output, [item["name"] for item in files])
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
    verify_input(output, args.dataset)
    print(f"Saved {manifest_path}", flush=True)


if __name__ == "__main__":
    main()

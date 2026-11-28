"""Check or repair reciprocal tracks in a native COLMAP text export.

No third-party dependency. Geometry and observations remain unchanged.
"""

import argparse
import hashlib
import json
from pathlib import Path


FILES = ("cameras.txt", "images.txt", "points3D.txt")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protect_receipt(receipt, protected):
    if receipt is None:
        return
    receipt = receipt.resolve()
    for path in protected:
        path = path.resolve()
        if receipt == path or (receipt.exists() and path.exists()
                               and receipt.samefile(path)):
            raise ValueError("Receipt must not overwrite a model file")


def read_model(folder):
    lines = (folder / "images.txt").read_text(encoding="utf-8").splitlines()
    lines = [line for line in lines if not line.startswith("#")]
    if len(lines) % 2:
        raise ValueError("images.txt must contain two lines per image")
    observations = {}
    for header, row in zip(lines[::2], lines[1::2]):
        fields = header.split()
        if len(fields) < 10:
            raise ValueError("Invalid image header")
        image_id = int(fields[0])
        if image_id in observations:
            raise ValueError("Duplicate image ID")
        fields = row.split()
        if len(fields) % 3:
            raise ValueError("Invalid observation row")
        observations[image_id] = {}
        for index in range(len(fields) // 3):
            point_id = int(fields[3 * index + 2])
            if point_id == -1:
                continue
            if point_id in observations[image_id]:
                raise ValueError("Repeated point ID in one image")
            observations[image_id][point_id] = index

    output, seen, changed, track_count = [], set(), 0, 0
    remaining = {(image_id, point_id) for image_id, rows in observations.items()
                 for point_id in rows}
    for line in (folder / "points3D.txt").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            output.append(line)
            continue
        fields = line.split()
        if len(fields) < 8 or (len(fields) - 8) % 2:
            raise ValueError("Invalid point row")
        point_id = int(fields[0])
        if point_id in seen:
            raise ValueError("Duplicate point ID")
        seen.add(point_id)
        track = []
        for offset in range(8, len(fields), 2):
            image_id, old = map(int, fields[offset:offset + 2])
            key = (image_id, point_id)
            if key not in remaining:
                raise ValueError("Track is repeated or has no reciprocal observation")
            remaining.remove(key)
            new = observations[image_id][point_id]
            changed += old != new
            track_count += 1
            track.extend((str(image_id), str(new)))
        # Preserve the original line verbatim when no repair is needed.
        output.append(" ".join(fields[:8] + track))
    if remaining:
        raise ValueError("Observations are missing reciprocal point tracks")
    stats = dict(images=len(observations), points=len(seen), track_pairs=track_count,
                 changed_point2D_indices=changed)
    return stats, "\n".join(output) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path,
                        help="Directory containing the three native text files")
    parser.add_argument("--output", type=Path,
                        help="New empty directory for repaired files; omitted means check only")
    parser.add_argument("--receipt", type=Path, help="Write a path-free JSON receipt")
    args = parser.parse_args()
    source = args.input.resolve()
    protected = [source / name for name in FILES]
    if args.output is not None:
        protected.extend(args.output.resolve() / name for name in FILES)
    protect_receipt(args.receipt, protected)
    before = {name: sha(source / name) for name in FILES}
    stats, repaired = read_model(source)
    if args.output is None and stats["changed_point2D_indices"]:
        raise ValueError("Inconsistent POINT2D_IDX; use --output to repair a separate copy")
    receipt = dict(schema_version=1, source_sha256=before, **stats)
    if args.output is not None:
        target = args.output.resolve()
        if target == source:
            raise ValueError("Output must differ from input")
        if target.exists() and any(target.iterdir()):
            raise ValueError("Output must be a new or empty directory")
        target.mkdir(parents=True, exist_ok=True)
        for name in FILES[:2]:
            (target / name).write_bytes((source / name).read_bytes())
        (target / "points3D.txt").write_bytes(repaired.encode("utf-8"))
        checked, _ = read_model(target)
        if checked["changed_point2D_indices"]:
            raise ValueError("Repair did not produce reciprocal tracks")
        receipt["output_sha256"] = {name: sha(target / name) for name in FILES}
        receipt["verified_reciprocal_tracks"] = True
        receipt["unchanged_cameras_and_images"] = all(
            before[name] == receipt["output_sha256"][name] for name in FILES[:2])
    if args.receipt:
        args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()

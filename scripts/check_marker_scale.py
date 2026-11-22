"""Check native AliceVision 3.2 CCTag landmarks and numerical baseline transfer."""

import argparse
import json
import math
from pathlib import Path
import sys


def read_json(path):
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError(f"Export marker-only JSON first; input exceeds 64 MiB: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def number(value, context):
    if isinstance(value, bool):
        raise ValueError(f"Boolean where a number was expected: {context}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"Non-finite number: {context}")
    return result


def identifier(value, context):
    result = number(value, context)
    if result != int(result) or result < 0:
        raise ValueError(f"Invalid nonnegative integer ID: {context}")
    return int(result)


def vector(value, length, context):
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"Expected {length} coordinates: {context}")
    return [number(item, context) for item in value]


def scene_reconstructed_views(scene, label):
    """Validate independent native cameras and return their reconstructed view IDs."""
    pose_ids = set()
    for pose in scene.get("poses", []):
        pose_id = identifier(pose["poseId"], f"{label}.poseId")
        if pose_id in pose_ids:
            raise ValueError(f"Duplicate pose ID {pose_id} in {label}")
        transform = pose["pose"]["transform"]
        vector(transform["rotation"], 9, f"{label}.pose {pose_id}.rotation")
        vector(transform["center"], 3, f"{label}.pose {pose_id}.center")
        pose_ids.add(pose_id)
    intrinsic_ids = {identifier(item["intrinsicId"], f"{label}.intrinsicId")
                     for item in scene.get("intrinsics", [])}
    reconstructed_views = set()
    view_ids = set()
    for view in scene.get("views", []):
        view_id = identifier(view["viewId"], f"{label}.viewId")
        if view_id in view_ids:
            raise ValueError(f"Duplicate view ID {view_id} in {label}")
        view_ids.add(view_id)
        # This pilot uses independent pinhole views, without rig composition.
        if "rigId" in view:
            raise ValueError(f"Rig view requires native pose composition; unsupported by this pilot checker: {label}")
        if ("poseId" in view and "intrinsicId" in view
                and identifier(view["poseId"], f"{label}.view.poseId") in pose_ids
                and identifier(view["intrinsicId"], f"{label}.view.intrinsicId") in intrinsic_ids):
            reconstructed_views.add(view_id)
    return reconstructed_views


def cctag_landmarks(scene, reconstructed_views, label, requested=None):
    """Read native CCTag3 IDs/observations without assuming marker uniqueness."""
    found = []
    for landmark in scene.get("structure", []):
        if landmark.get("descType") != "cctag3":
            continue
        color = vector(landmark["color"], 3, f"{label}.landmark.color")
        marker_id = identifier(color[0], f"{label}.markerId")
        if requested is not None and marker_id not in requested:
            continue
        center = vector(landmark["X"], 3, f"{label}.marker {marker_id}.X")
        observation_ids = [identifier(item["observationId"], f"{label}.marker {marker_id}.observationId")
                           for item in landmark.get("observations", [])]
        if len(set(observation_ids)) != len(observation_ids):
            raise ValueError(f"Duplicate observation ID on marker {marker_id} in {label}")
        posed = sorted(set(observation_ids) & reconstructed_views)
        found.append({"id": marker_id,
                            "landmark_id": identifier(landmark["landmarkId"], f"{label}.landmarkId"),
                            "center": center, "observation_count": len(observation_ids),
                            "reconstructed_view_count": len(posed), "reconstructed_view_ids": posed})
    return found


def markers_from_scene(scene, requested, label):
    reconstructed_views = scene_reconstructed_views(scene, label)
    if len(reconstructed_views) < 2:
        raise ValueError(f"{label} needs at least two reconstructed views; export views, poses and intrinsics")
    found = {}
    for marker in cctag_landmarks(scene, reconstructed_views, label, requested):
        marker_id = marker["id"]
        if marker_id in found:
            raise ValueError(f"Duplicate cctag3 marker ID {marker_id} in {label}")
        if marker["reconstructed_view_count"] < 2:
            raise ValueError(f"Marker {marker_id} in {label} has only {marker['reconstructed_view_count']} distinct reconstructed observations")
        found[marker_id] = marker
    missing = sorted(set(requested) - found.keys())
    if missing:
        raise ValueError(f"Missing cctag3 marker IDs in {label}: {missing}")
    distance = math.dist(found[requested[0]]["center"], found[requested[1]]["center"])
    if not math.isfinite(distance) or distance <= 0:
        raise ValueError(f"Invalid zero or non-finite marker baseline in {label}")
    return {"markers": [found[key] for key in requested], "distance": distance,
            "scene_reconstructed_view_count": len(reconstructed_views)}


def reference_from_truth(path, requested, units):
    truth = read_json(path)
    if truth.get("units") != units:
        raise ValueError("Reference units must match --units; no implicit conversion")
    if units != "mm":
        raise ValueError("Fixture center_mm schema requires --units mm")
    found = {}
    for marker in truth["markers"]:
        marker_id = identifier(marker["id"], "reference.marker.id")
        if marker_id not in requested:
            continue
        if marker_id in found:
            raise ValueError(f"Duplicate reference marker ID {marker_id}")
        found[marker_id] = vector(marker["center_mm"], 3, "reference.marker.center_mm")
    if set(found) != set(requested):
        raise ValueError("Requested IDs missing from reference markers")
    distance = math.dist(found[requested[0]], found[requested[1]])
    if not math.isfinite(distance) or distance <= 0:
        raise ValueError("Invalid reference baseline")
    return {"file": str(path.resolve()), "synthetic": truth.get("synthetic"),
            "units": units, "markers": [{"id": key, "center_mm": found[key]} for key in requested],
            "distance": distance, "comparison": "Baseline only; no shared origin or orientation imposed"}


def check(args):
    if args.ids[0] == args.ids[1] or any(value < 0 or value > 31 for value in args.ids):
        raise ValueError("Provide two distinct cctag3 IDs between 0 and 31")
    for value, name in [(args.distance, "distance"), (args.atol, "atol"), (args.rtol, "rtol")]:
        if not math.isfinite(value) or value < 0 or (name == "distance" and value == 0):
            raise ValueError(f"Invalid {name}")
    before = markers_from_scene(read_json(args.before), args.ids, "before")
    after = markers_from_scene(read_json(args.after), args.ids, "after")
    tolerance = args.atol + args.rtol * abs(args.distance)
    if not math.isfinite(tolerance):
        raise ValueError("Numeric tolerance is not finite")
    error = abs(after["distance"] - args.distance)
    reference = reference_from_truth(args.reference, args.ids, args.units) if args.reference else None
    reference_error = abs(reference["distance"] - args.distance) if reference else 0.0
    observations_preserved = all(a["reconstructed_view_ids"] == b["reconstructed_view_ids"]
                                 for a, b in zip(before["markers"], after["markers"]))
    scale = after["distance"] / before["distance"]
    expected_scale = args.distance / before["distance"]
    if not math.isfinite(scale) or not math.isfinite(expected_scale):
        raise ValueError("Non-finite scale factor")
    passed = error <= tolerance and reference_error <= tolerance and observations_preserved
    return {"status": "passed" if passed else "failed", "units": args.units,
            "before_units": "arbitrary native scene units", "after_units": args.units,
            "unit_convention": "Explicit caller convention; no claim of physical capture accuracy",
            "before_file": str(args.before.resolve()), "after_file": str(args.after.resolve()),
            "ids": args.ids, "before": before, "after": after,
            "scale_factor_after_over_before": scale,
            "expected_scale_factor": expected_scale,
            "target_distance": args.distance, "absolute_target_error": error,
            "max_error": max(error, reference_error), "numeric_tolerance": tolerance,
            "tolerance_formula": "atol + rtol * abs(target_distance); numeric transfer only",
            "observation_ids_preserved": observations_preserved,
            "reference": reference, "reference_baseline_target_error": reference_error if reference else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--ids", type=int, nargs=2, required=True)
    parser.add_argument("--distance", type=float, required=True)
    parser.add_argument("--units", choices=["mm", "cm", "m"], required=True)
    parser.add_argument("--reference", type=Path, help="Optional make_marker_fixture.py truth.json")
    parser.add_argument("--atol", type=float, default=1e-6)
    parser.add_argument("--rtol", type=float, default=1e-8)
    parser.add_argument("--output", type=Path, help="Default: marker-scale-check.json beside after")
    args = parser.parse_args()
    output = (args.output or args.after.parent / "marker-scale-check.json").resolve()
    inputs = [args.before.resolve(), args.after.resolve()]
    if args.reference:
        inputs.append(args.reference.resolve())
    if output in inputs:
        parser.error("Output must differ from input files")
    checkout = Path(__file__).resolve().parents[1]
    if output == checkout or checkout in output.parents:
        parser.error("Write evidence outside the source checkout")
    try:
        result = check(args)
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError, OSError) as error:
        result = {"status": "error", "error": str(error)}
    result["output_file"] = str(output)
    serialized = json.dumps(result, indent=2, allow_nan=False) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialized, encoding="utf-8")
    if json.loads(output.read_text(encoding="utf-8")) != result:
        raise ValueError("Evidence JSON readback differs")
    print(serialized, end="")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())

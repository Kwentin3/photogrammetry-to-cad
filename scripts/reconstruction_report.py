"""Report native reconstruction facts after backup; this does not build CAD.

Run in the existing local geometry environment (Open3D + NumPy).
The scale receipt binds physical units to the native scene SHA; cloud lineage
still belongs to the native graph and its saved output route.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

from check_marker_scale import (
    cctag_landmarks, identifier, number, read_json, scene_reconstructed_views, vector,
)


IDENTITY = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
UNITS = {"mm", "cm", "m"}


def artifact(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"Expected an artifact file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(path), "sha256": digest.hexdigest(), "bytes": path.stat().st_size}


def absolute_file(value, context):
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError(f"{context} must be an absolute file path in this reporting environment")
    return Path(value).resolve(strict=True)


def scene_summary(scene):
    reconstructed = scene_reconstructed_views(scene, "scene")
    groups = {}
    for landmark in cctag_landmarks(scene, reconstructed, "scene"):
        marker_id = landmark["id"]
        groups.setdefault(marker_id, []).append({
            "landmark_id": landmark["landmark_id"],
            "center": landmark["center"],
            "observation_count": landmark["observation_count"],
            "posed_observation_count": landmark["reconstructed_view_count"],
            "posed_view_ids": landmark["reconstructed_view_ids"],
        })
    markers = [{"id": marker_id, "ambiguous": len(landmarks) > 1,
                "landmarks": landmarks}
               for marker_id, landmarks in sorted(groups.items())]
    return {
        "view_count": len(scene.get("views", [])),
        "registered_view_count": len(reconstructed),
        "registered_fraction": len(reconstructed) / len(scene["views"]) if scene.get("views") else 0.0,
        "pose_count": len(scene.get("poses", [])),
        "intrinsic_count": len(scene.get("intrinsics", [])),
        "markers": markers,
    }


def verified_scale(settings, scene_artifact, evidence_path=None):
    request = settings.get("scale", {"mode": "unknown"})
    if not isinstance(request, dict):
        raise ValueError("settings.scale must be an object")
    mode = request.get("mode")
    if mode == "unknown":
        if request.get("applied_evidence") or evidence_path is not None:
            raise ValueError("Unknown scale contradicts supplied applied scale evidence")
        return {
            "mode": "unknown", "applied": False, "units": "unknown",
            "transform": {"scale": 1.0, "rotation": IDENTITY.copy(), "translation": [0.0] * 3},
            "reason": "no measured physical scale",
        }
    if mode not in {"measured_baseline", "marker_coords"}:
        raise ValueError(f"Unsupported scale mode: {mode}")
    units = request.get("units")
    if units not in UNITS:
        raise ValueError("Known scale requires explicit mm, cm or m units")
    path = (Path(evidence_path).resolve(strict=True) if evidence_path is not None
            else absolute_file(request.get("applied_evidence"), "scale.applied_evidence"))
    evidence_artifact = artifact(path)
    evidence = read_json(path)
    if (evidence.get("status") != "passed" or evidence.get("applied") is not True
            or evidence.get("mode") != mode or evidence.get("units") != units):
        raise ValueError("Scale evidence status, applied flag, mode or units do not match settings")
    if evidence.get("scene_sha256") != scene_artifact["sha256"]:
        raise ValueError("Scale evidence does not match the actual native scene SHA-256")
    transform = evidence["transform"]
    scale = number(transform["scale"], "scale.transform.scale")
    if scale <= 0:
        raise ValueError("Applied native scale must be positive")
    transform = {"scale": scale,
                 "rotation": vector(transform["rotation"], 9, "scale.transform.rotation"),
                 "translation": vector(transform["translation"], 3, "scale.transform.translation")}
    source = evidence["source"]
    if not isinstance(source, dict):
        raise ValueError("Scale evidence source must be an object")
    if mode == "measured_baseline":
        ids = source["ids"]
        if not isinstance(ids, list) or len(ids) != 2:
            raise ValueError("Measured baseline evidence needs two distinct marker IDs")
        ids = [identifier(value, "scale.source.ids") for value in ids]
        if ids[0] == ids[1] or any(value > 31 for value in ids):
            raise ValueError("Measured baseline evidence needs two distinct CCTag3 IDs in 0..31")
        distance = number(source["distance"], "scale.source.distance")
        if distance <= 0:
            raise ValueError("Measured baseline evidence distance must be positive")
        if not source.get("measurement_source"):
            raise ValueError("Measured baseline evidence needs its measurement source")
        for key, expected in (("ids", ids), ("distance", distance),
                              ("measurement_source", source["measurement_source"])):
            if key in request and request[key] != expected:
                raise ValueError(f"Scale evidence {key} differs from requested measurement")
    else:
        if not source.get("coordinate_source"):
            raise ValueError("Marker coordinate evidence needs its coordinate source")
        if ("coordinate_source" in request
                and request["coordinate_source"] != source["coordinate_source"]):
            raise ValueError("Scale evidence coordinate_source differs from requested coordinates")
    verification = evidence["verification"]
    if not isinstance(verification, dict):
        raise ValueError("Scale evidence verification must be an object")
    return {"mode": mode, "applied": True, "units": units, "scope": "native_scene",
            "evidence": evidence_artifact, "transform": transform,
            "source": source, "verification": verification}


def cloud_summary(path):
    # Keep geometry dependencies out of source/receipt validation and --help.
    import numpy as np
    import open3d as o3d

    if Path(path).suffix.lower() != ".ply":
        raise ValueError("The dense cloud report requires the native exported PLY")
    cloud = o3d.io.read_point_cloud(str(path), remove_nan_points=False,
                                    remove_infinite_points=False, print_progress=False)
    points = np.asarray(cloud.points)
    finite = np.isfinite(points).all(axis=1)
    count = int(finite.sum())
    if count == 0:
        raise ValueError("Dense PLY contains no finite points")
    # The actual loaded point cloud is the geometry owner; no JSON bbox is trusted.
    valid_cloud = cloud.select_by_index(np.flatnonzero(finite).tolist())
    bounds = valid_cloud.get_axis_aligned_bounding_box()
    return {"point_count": len(points), "finite_point_count": count,
            "nonfinite_point_count": int(len(points) - count),
            "bbox_min": bounds.min_bound.tolist(), "bbox_max": bounds.max_bound.tolist(),
            "extent": bounds.get_extent().tolist(),
            "coordinate_frame": "native PLY; cloud lineage is recorded by the native graph"}


def report(scene_path, cloud_path, settings_path, manifest_path=None, scale_evidence_path=None):
    inputs = {"scene": artifact(scene_path), "cloud": artifact(cloud_path),
              "settings": artifact(settings_path)}
    settings = read_json(settings_path)
    manifest = (Path(manifest_path).resolve(strict=True) if manifest_path is not None
                else absolute_file(settings["input_manifest"], "settings.input_manifest"))
    inputs["input_manifest"] = artifact(manifest)
    if ("input_manifest_sha256" in settings
            and settings["input_manifest_sha256"] != inputs["input_manifest"]["sha256"]):
        raise ValueError("Input manifest does not match settings.input_manifest_sha256")
    # Validate scale before importing Open3D or reading the potentially large cloud.
    scale = verified_scale(settings, inputs["scene"], scale_evidence_path)
    scene = scene_summary(read_json(scene_path))
    return {"schema_version": 1, "status": "reported",
            "runtime": settings.get("runtime", {}), "inputs": inputs,
            "scene": scene, "scale": scale, "cloud": cloud_summary(cloud_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path, required=True,
                        help="Native canonical JSON with views/poses/intrinsics/CCTag3 observations")
    parser.add_argument("--cloud", type=Path, required=True, help="Native dense PLY exported after backup")
    parser.add_argument("--settings", type=Path, required=True, help="Effective settings and scale evidence paths")
    parser.add_argument("--manifest", type=Path,
                        help="Explicit local copy of input manifest; preserve its settings SHA-256 binding")
    parser.add_argument("--scale-evidence", type=Path,
                        help="Explicit local copy of applied scale evidence; preserve scene and scale binding")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    checkout = Path(__file__).resolve().parents[1]
    if output == checkout or checkout in output.parents:
        parser.error("Write reconstruction evidence outside the source checkout")
    protected = {args.scene.resolve(), args.cloud.resolve(), args.settings.resolve()}
    protected.update(path.resolve() for path in (args.manifest, args.scale_evidence) if path is not None)
    if output in protected:
        parser.error("Output must differ from every input and scale evidence artifact")
    try:
        settings = read_json(args.settings)
        for value in (settings.get("input_manifest"), settings.get("scale", {}).get("applied_evidence")):
            if isinstance(value, str) and value:
                protected.add(Path(value).resolve())
        if output in protected:
            parser.error("Output must differ from every input and scale evidence artifact")
        result = report(args.scene, args.cloud, args.settings, args.manifest, args.scale_evidence)
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError, OSError, RuntimeError) as error:
        result = {"schema_version": 1, "status": "error", "error": str(error)}
    result["output_file"] = str(output)
    text = json.dumps(result, indent=2, allow_nan=False) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    if json.loads(output.read_text(encoding="utf-8")) != result:
        raise ValueError("Report JSON readback differs")
    print(text, end="")
    return 0 if result["status"] == "reported" else 1


if __name__ == "__main__":
    sys.exit(main())

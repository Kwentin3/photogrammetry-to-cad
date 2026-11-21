"""Prepare one native video selector; seal its actual frames after meshroom_compute.

prepare VIDEO MESHROOM_ROOT PROJECT --output FRAMES --settings keyframe.json
seal FRAMES --source VIDEO --output manifest.json [--probe ffprobe.json]

Run prepare with the pinned Meshroom Python/environment. The caller owns thread
limits, deadline and the later native meshroom_compute invocation. Seal is stdlib
only. Timestamps are never inferred from a nominal video frame rate.
"""

import argparse
import csv
import json
import os
from pathlib import Path
import re

from fetch_dataset import check_input_entries, hashes


REPO = Path(__file__).resolve().parents[1]
RECEIPT = "video-source.json"
EXTENSIONS = {"jpg", "png", "exr"}


def outside_checkout(path):
    path = Path(path).resolve()
    if path == REPO or REPO in path.parents:
        raise ValueError(f"Video data and generated projects must stay outside checkout: {path}")
    return path


def record(path):
    size, _, digest = hashes(path)
    return {"path": str(path), "bytes": size, "sha256": digest}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_new(path, value):
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")
    if read_json(path) != value:
        raise ValueError(f"JSON readback differs: {path}")


def verify_record(value):
    path = Path(value["path"])
    actual = record(path)
    if any(actual[key] != value[key] for key in ("bytes", "sha256")):
        raise ValueError(f"Artifact changed since preparation: {path}")
    return path


def prepare(args):
    source = outside_checkout(args.video).resolve(strict=True)
    runtime = args.meshroom_root.resolve(strict=True)
    project = outside_checkout(args.project)
    frames = outside_checkout(args.output)
    settings = read_json(args.settings)
    if not isinstance(settings, dict):
        raise ValueError("Settings must be an object of native KeyframeSelection attribute names")
    reserved = {"inputPaths", "outputFolder", "outputSfMDataKeyframes", "outputSfMDataFrames"}
    if reserved.intersection(settings):
        raise ValueError("Input/output paths belong to prepare arguments, not settings")
    if settings.get("outputExtension") not in EXTENSIONS:
        raise ValueError("Video settings must explicitly choose outputExtension jpg, png or exr")
    if settings.get("renameKeyframes", False) is not False:
        raise ValueError("Source frame provenance requires renameKeyframes=false")
    keyframes = project.with_suffix(".keyframes.sfm")
    rejected = project.with_suffix(".rejected.sfm")
    cache = project.with_suffix(".cache")
    if any(path.exists() for path in (project, keyframes, rejected, cache)):
        raise FileExistsError("Preserve the existing project/results; choose a fresh PROJECT")
    if frames.exists() and (not frames.is_dir() or any(frames.iterdir())):
        raise FileExistsError(f"Choose an empty/new frames directory: {frames}")

    os.environ["MESHROOM_INSTALL_DIR"] = str(runtime)
    import meshroom
    meshroom.setupEnvironment()
    import meshroom.core
    import meshroom.core.graph as graph_module
    meshroom.core.initPipelines()
    meshroom.core.initPlugins()
    meshroom.core.initNodes()
    graph = graph_module.Graph("Video keyframes")
    with graph_module.GraphModification(graph):
        # Supply native output expressions at construction: assigning .value
        # later would not replace the descriptor's serialized expression.
        node = graph.addNewNode(
            "KeyframeSelection", name="KeyframeSelection_1",
            outputFolder=str(frames), outputSfMDataKeyframes=str(keyframes),
            outputSfMDataFrames=str(rejected),
        )
        for name, value in settings.items():
            node.attribute(name).value = value
        node.inputPaths.value = [str(source)]
    if node.isCompatibilityNode:
        raise ValueError("The installed native KeyframeSelection descriptor is incompatible")
    source_record = record(source)
    project.parent.mkdir(parents=True, exist_ok=True)
    frames.mkdir(parents=True, exist_ok=True)
    cache.mkdir()
    graph.save(str(project))
    graph.setExplicitCacheDir(str(cache))
    graph.save(str(project))
    for name, path in (("outputFolder", frames), ("outputSfMDataKeyframes", keyframes),
                       ("outputSfMDataFrames", rejected)):
        if node.attribute(name).getSerializedValue() != str(path):
            raise ValueError(f"Native output expression was not preserved: {name}")
    save_new(frames / RECEIPT, {
        "schema_version": 1, "source": source_record, "project": record(project),
        "frames": str(frames), "keyframes_sfm": str(keyframes),
        "node": node.name, "settings": settings,
        "index_basis": "zero_based_source_frame_index_in_native_filename",
    })
    print(json.dumps({"project": str(project), "cache": str(cache),
                      "compute_to": node.name, "frames": str(frames),
                      "reconstruction_started": False}), flush=True)


def seal(args):
    frames = outside_checkout(args.frames).resolve(strict=True)
    source = outside_checkout(args.source).resolve(strict=True)
    output = outside_checkout(args.output)
    receipt = read_json(frames / RECEIPT)
    if (receipt.get("schema_version") != 1 or receipt.get("frames") != str(frames)
            or Path(receipt["source"]["path"]).resolve() != source):
        raise ValueError("Source receipt belongs to another source or frames directory")
    verify_record(receipt["source"])
    verify_record(receipt["project"])
    sfm_path = Path(receipt["keyframes_sfm"])
    sfm = read_json(sfm_path)
    views = sfm.get("views", [])
    if not views:
        raise ValueError("Native keyframes SfMData has no selected views")
    entries = []
    for view in views:
        path = Path(view["path"])
        if not path.is_absolute():
            path = sfm_path.parent / path
        if path.parent.resolve() != frames:
            raise ValueError(f"Native keyframe path is outside FRAMES: {path}")
        match = re.fullmatch(r"(\d+)\.(jpg|png|exr)", path.name, re.IGNORECASE)
        if not match:
            raise ValueError(f"Native keyframe does not preserve a numeric source index: {path.name}")
        item = record(path)
        item.pop("path")
        entries.append({"name": path.name, **item, "source_frame_index": int(match[1])})
    entries.sort(key=lambda item: item["source_frame_index"])
    indices = [item["source_frame_index"] for item in entries]
    if len(indices) != len(set(indices)):
        raise ValueError("Duplicate source frame index in native keyframes")
    check_input_entries(frames, [item["name"] for item in entries])
    settings = receipt["settings"]
    csv_path = frames / settings.get("debugOptions.debugScores.csvFilename", "scores.csv")
    if settings.get("debugOptions.debugScores.exportSelectedFrames"):
        with csv_path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter=";"))
        selected = [int(row["FrameNb"]) for row in rows if row["Selected"] == "1"]
        if selected != indices:
            raise ValueError("Native scores CSV selection differs from actual keyframe files")
    manifest = {
        "schema_version": 1, "complete": True,
        "source": {"kind": "video", **receipt["source"],
                   "frame_index_basis": receipt["index_basis"]},
        "selection": {"project": receipt["project"], "settings": settings,
                      "native_keyframes_sfm": record(sfm_path)},
        "files": entries,
    }
    if args.probe:
        manifest["source"]["probe"] = record(args.probe.resolve(strict=True))
    save_new(output, manifest)
    print(json.dumps({"manifest": str(output), "frames": len(entries),
                      "source_sha256": receipt["source"]["sha256"]}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("prepare")
    command.add_argument("video", type=Path)
    command.add_argument("meshroom_root", type=Path)
    command.add_argument("project", type=Path)
    command.add_argument("--output", type=Path, required=True)
    command.add_argument("--settings", type=Path, required=True)
    command.set_defaults(run=prepare)
    command = commands.add_parser("seal")
    command.add_argument("frames", type=Path)
    command.add_argument("--source", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    command.add_argument("--probe", type=Path, help="Optional ffprobe metadata file; no timestamps are inferred")
    command.set_defaults(run=seal)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()

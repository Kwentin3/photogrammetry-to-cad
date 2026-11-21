"""Bind a transformed SfM file in a native Meshroom 2023.3 graph before loading it.

CLI paramOverrides changes values but leaves existing edges attached in this
version. Editing serialized inputs and loading as a native template recomputes
UIDs instead of preserving cached outputs through UidConflict compatibility
nodes. This is a file adapter, not a scale calculation or artifact verifier.
"""

import argparse
import json
from pathlib import Path, PurePosixPath


NODES = ("PrepareDenseScene", "DepthMap", "DepthMapFilter", "Meshing")
NATIVE_SFM = "{StructureFromMotion_1.output}"


def bind(graph_path, sfm_path, output, mask_config=None, mask_features=False):
    if graph_path.resolve() == output.resolve():
        raise ValueError("Preserve the original graph; choose a separate output")
    if not PurePosixPath(sfm_path).is_absolute() and not (mask_features and sfm_path == NATIVE_SFM):
        raise ValueError("Supply the absolute SfM path on the Linux worker")
    if mask_features and (mask_config is None or sfm_path != NATIVE_SFM):
        raise ValueError("A feature mask requires its config and the native SfM output link")
    graph = json.loads(graph_path.read_text(encoding="utf-8-sig"))
    if graph["header"]["releaseVersion"] != "2023.3.0":
        raise ValueError("Recheck the graph contract for this Meshroom version")
    # Graph.load recomputes native UIDs for templates. A saved project's old UIDs
    # otherwise trigger UidConflict nodes retaining the old cached outputs.
    graph["header"]["template"] = True
    for node_type in NODES:
        node = graph["graph"][node_type + "_1"]
        if node["nodeType"] != node_type or "input" not in node["inputs"]:
            raise ValueError(f"Unexpected native node contract: {node_type}")
        node["inputs"]["input"] = sfm_path
    if mask_config is not None:
        if "ImageMasking_1" in graph["graph"]:
            raise ValueError("A mask node already exists; inspect it before replacing its configuration")
        settings = json.loads(mask_config.read_text(encoding="utf-8-sig"))
        if "input" in settings:
            raise ValueError("The mask must use the same transformed scene as the dense stages")
        graph["header"]["nodesVersions"]["ImageMasking"] = "3.0"
        graph["graph"]["ImageMasking_1"] = {
            "nodeType": "ImageMasking", "position": [1000, 200],
            "inputs": {"input": "{CameraInit_1.output}" if mask_features else sfm_path, **settings},
        }
        if mask_features:
            graph["graph"]["FeatureExtraction_1"]["inputs"]["masksFolder"] = "{ImageMasking_1.output}"
        graph["graph"]["PrepareDenseScene_1"]["inputs"].update({
            "masksFolders": ["{ImageMasking_1.output}"],
            "maskExtension": "png", "outputFileType": "exr", "saveMetadata": True,
        })
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    return {name + "_1": graph["graph"][name + "_1"]["inputs"]["input"] for name in NODES}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph", type=Path)
    parser.add_argument("sfm_path", help="Linux worker path, or the native SfM link with --mask-features")
    parser.add_argument("output", type=Path)
    parser.add_argument("--mask-config", type=Path, help="Native ImageMasking inputs; dense only unless --mask-features is set")
    parser.add_argument("--mask-features", action="store_true", help="Mask before SfM and reuse the mask for dense processing")
    args = parser.parse_args()
    print(json.dumps(bind(args.graph, args.sfm_path, args.output, args.mask_config, args.mask_features), indent=2))


if __name__ == "__main__":
    main()

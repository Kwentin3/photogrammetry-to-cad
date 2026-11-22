"""Historical Goal #4 fixed examples; never run reconstruction.

The general photo/video route is reconstruction.py (docs/runbook.md).
This example recipe retains its original three capture-specific configurations.

Run with the pinned bundle's Python and environment supplied by its bootstrap:
    python prepare_graphs_2026.py RUN_ROOT MESHROOM_ROOT [--case dice]

CameraInit.initialize does invoke the native camera initialization executable.
The caller must own the process group, resource limits and execution deadline.
"""

import argparse
import json
import math
import os
from pathlib import Path

from fetch_dataset import verify_input


REPO = Path(__file__).resolve().parents[1]
CASES = ("dice", "cctag", "synthetic-markers")
CONFIGS = {
    "dice": "photos.json",
    "cctag": "cctag.json",
    "synthetic-markers": "synthetic-markers.json",
}


def read_config(name):
    return json.loads((REPO / "configs" / name).read_text(encoding="utf-8-sig"))


def apply_settings(node, settings):
    """Set owners; linked settings may only confirm their resolved value."""
    for name, value in settings.items():
        attribute = node.attribute(name)
        if attribute.isLink:
            # Native Attribute.value follows the input link recursively. Setting
            # the consumer would conceal an owner/config contradiction and must
            # never replace the descriptor propagation edge.
            if attribute.value != value:
                raise ValueError(
                    f"Setting contradicts native link {node.name}.{name} "
                    f"from {attribute.inputLink.fullName}: {attribute.value!r} != {value!r}")
            continue
        attribute.value = value


def add_mask(graph, source, config_name, feature_mask):
    mask = graph.addNewNode("ImageMasking", name="ImageMasking_1")
    apply_settings(mask, read_config(config_name))
    graph.addEdge(source, mask.input)
    if feature_mask:
        graph.addEdge(mask.output, graph.node("FeatureExtraction_1").masksFolder)
    dense = graph.node("PrepareDenseScene_1")
    dense.masksFolders.append("")
    graph.addEdge(mask.output, dense.masksFolders.at(0))
    # Same native EXR/alpha contract as the accepted 2023 masked profiles.
    apply_settings(dense, {"maskExtension": "png", "outputFileType": "exr", "saveMetadata": True})
    return mask


def add_metric_transform(graph, input_root, settings):
    """Adapt the existing synthetic truth to native marker attributes, in mm."""
    truth = json.loads((input_root / "truth.json").read_text(encoding="utf-8"))
    if truth["units"] != "mm" or truth["marker_center_distance_mm"] != 100.0:
        raise ValueError("This pilot requires the existing synthetic 100 mm fixture")
    if not math.isclose(truth["horizontal_field_of_view_deg"],
                        settings["CameraInit_1"]["defaultFieldOfView"], abs_tol=1e-10):
        raise ValueError("Camera FOV config differs from the synthetic generator truth")
    # Coordinates are generated truth, not measured dimensions from real photos.
    markers = [{"markerId": marker["id"],
                "markerCoord": dict(zip(("x", "y", "z"), marker["center_mm"]))}
               for marker in truth["markers"]]
    transform = graph.addNewNode("SfMTransform", name="SfMTransform_1")
    apply_settings(transform, {
        "method": "from_markers", "landmarksDescriberTypes": ["cctag3"],
        "markers": markers, "scale": 1.0,
        "applyScale": True, "applyRotation": True, "applyTranslation": True,
    })
    graph.addEdge(graph.node("StructureFromMotion_1").output, transform.input)
    # addEdge replaces the existing sparse -> dense edge. All three downstream
    # input aliases remain owned by the installed Legacy template.
    graph.addEdge(transform.output, graph.node("PrepareDenseScene_1").input)
    return transform


def check_dense_links(graph, source):
    previous = source
    for name in ("PrepareDenseScene_1", "DepthMap_1", "DepthMapFilter_1", "Meshing_1"):
        current = graph.node(name).input
        if current.inputLink != previous:
            raise ValueError(f"Installed Legacy template changed its dense input alias: {name}")
        previous = current


def prepare_case(case, run_root, template, directory, count, graph_module):
    settings = read_config(CONFIGS[case])
    graph = graph_module.Graph(f"2026-{case}")
    with graph_module.GraphModification(graph):
        graph.initFromTemplate(str(template))
        # The technical pilot stops at dense geometry, before mesh polishing.
        for name in ("Texturing_1", "MeshFiltering_1"):
            graph.removeNode(name)
        for node_name, values in settings.items():
            apply_settings(graph.node(node_name), values)

        sparse = graph.node("StructureFromMotion_1")
        camera = graph.node("CameraInit_1")
        if case == "dice":
            add_mask(graph, camera.output, "mask-turntable-white.json", feature_mask=True)
            check_dense_links(graph, sparse.output)
        elif case == "synthetic-markers":
            transform = add_metric_transform(graph, run_root / "input" / case, settings)
            # The gray background mask affects dense preparation only. Features
            # retain both markers and the original unmasked synthetic texture.
            add_mask(graph, transform.output, "mask-synthetic-background.json", feature_mask=False)
            check_dense_links(graph, transform.output)
        else:
            # Real CCTag photos have no known physical baseline; SfM only.
            for name in ("Meshing_1", "DepthMapFilter_1", "DepthMap_1", "PrepareDenseScene_1"):
                graph.removeNode(name)

        # verify_input owns the complete allowed directory contents and hashes.
        # CameraInit's native directory reader supplies the actual image list.
        # Every config (especially synthetic FOV) is in place BEFORE initialize.
        camera.nodeDesc.initialize(camera, [str(directory)], [])

    if len(camera.viewpoints) != count:
        raise ValueError(f"CameraInit admitted {len(camera.viewpoints)} of {count} verified images")
    if any(node.isCompatibilityNode for node in graph.nodes):
        raise ValueError("The installed native template produced compatibility nodes")
    project = run_root / "projects2026" / f"{case}.mg"
    cache = run_root / "cache2026" / case
    cache.mkdir(parents=True, exist_ok=True)
    # Same public save/cache call order used by the pinned meshroom_batch.
    graph.save(str(project))
    graph.setExplicitCacheDir(str(cache))
    graph.save(str(project))
    terminal = "StructureFromMotion_1" if case == "cctag" else "Meshing_1"
    print(json.dumps({"case": case, "project": str(project), "cache": str(cache),
                      "verified_images": count, "compute_to": terminal,
                      "reconstruction_started": False}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root", type=Path)
    parser.add_argument("meshroom_root", type=Path)
    parser.add_argument("--case", choices=CASES, action="append", dest="cases",
                        help="Prepare selected case(s); default: all three")
    args = parser.parse_args()
    run_root = args.run_root.resolve(strict=True)
    meshroom_root = args.meshroom_root.resolve(strict=True)
    if run_root == REPO or REPO in run_root.parents:
        parser.error("Inputs, cache and projects must stay outside the source checkout")
    cases = list(dict.fromkeys(args.cases or CASES))
    # Verify every requested input before invoking any native subprocess.
    inputs = {case: verify_input(run_root / "input" / case, case) for case in cases}
    for case, (_, count) in inputs.items():
        expected = {"dice": 20, "cctag": 50, "synthetic-markers": 10}[case]
        if count != expected:
            raise ValueError(f"Bounded 2026 pilot requires {expected} {case} images; got {count}")
        project = run_root / "projects2026" / f"{case}.mg"
        if project.exists():
            raise FileExistsError(f"Preserve the existing project; use a fresh run root: {project}")

    os.environ["MESHROOM_INSTALL_DIR"] = str(meshroom_root)
    os.environ["OMP_NUM_THREADS"] = "8"
    os.environ["OPENBLAS_NUM_THREADS"] = "8"
    import meshroom
    meshroom.setupEnvironment()
    import meshroom.core
    import meshroom.core.graph as graph_module
    meshroom.core.initPipelines()
    meshroom.core.initPlugins()
    meshroom.core.initNodes()
    template = meshroom_root / "aliceVision" / "share" / "meshroom" / "photogrammetryLegacy.mgt"
    if not template.is_file():
        raise FileNotFoundError(f"Pinned full bundle Legacy template is missing: {template}")
    (run_root / "projects2026").mkdir(exist_ok=True)
    for case, (directory, count) in inputs.items():
        prepare_case(case, run_root, template, directory, count, graph_module)


if __name__ == "__main__":
    main()

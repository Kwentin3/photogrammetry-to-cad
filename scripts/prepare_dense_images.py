"""Run native PrepareDenseScene from a saved graph without chunk ranges.

Usage in the pinned bundle environment:
    python prepare_dense_images.py PROJECT.mg --cache CACHE

The caller owns the process group, resource limits and deadline (remote_job.sh).
This adapter writes no Meshroom computation status. Check the resulting EXR view
IDs, alpha and metadata before starting DepthMap.
"""

import argparse
from pathlib import Path
import shlex
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    project = args.project.resolve(strict=True)
    cache = args.cache.resolve(strict=True)
    if not project.is_file() or not cache.is_dir():
        parser.error("Supply an existing Meshroom project and its cache directory")

    import meshroom
    meshroom.setupEnvironment()
    import meshroom.core
    from meshroom.core import desc
    from meshroom.core.graph import loadGraph
    from meshroom.core.node.chunk import NodeChunk
    meshroom.core.initPipelines()
    meshroom.core.initPlugins()
    meshroom.core.initNodes()
    graph = loadGraph(str(project), strictCompatibility=True)
    # Match meshroom_compute's public cache override; do not resave the graph.
    graph.cacheDir = str(cache)
    node = graph.node("PrepareDenseScene_1")
    if node is None or node.isCompatibilityNode or node.nodeType != "PrepareDenseScene":
        raise ValueError("Project requires the native PrepareDenseScene_1 node")
    if not Path(node.input.value).is_file():
        raise FileNotFoundError(f"Native SfM input is missing: {node.input.value}")
    for mask in node.masksFolders:
        if not mask.value or not Path(mask.value).is_dir():
            raise FileNotFoundError(f"Native mask folder is missing: {mask.value}")
    output = Path(node.output.value).resolve()
    if not output.is_relative_to(cache) or output == cache:
        raise ValueError(f"Native output must belong to the selected UID cache: {output}")

    # A fresh parallel PDS may inherit size=0 from nonparallel sparse ancestors
    # and receive no chunks. Use its native command builder directly instead of
    # changing descriptors, edges, UIDs, range settings or status files.
    chunk = NodeChunk(node, desc.Range())
    argv = shlex.split(node.nodeDesc.buildCommandLine(chunk))
    if not argv or Path(argv[0]).name != "aliceVision_prepareDenseScene":
        raise ValueError("Native command builder did not produce prepareDenseScene")
    if any(arg.split("=", 1)[0] in {"--rangeStart", "--rangeSize"} for arg in argv):
        raise ValueError("Native command contains chunk ranges; this adapter requires a whole-scene command")
    output.mkdir(parents=True, exist_ok=True)
    print(f"Project: {project}\nNative output: {output}", flush=True)
    print(shlex.join(argv), flush=True)
    subprocess.run(argv, check=True, env=node.nodeDesc.provider.runtimeEnv)
    print("Native PrepareDenseScene exited successfully. Meshroom status was not changed; verify all EXR view IDs, alpha and metadata.", flush=True)


if __name__ == "__main__":
    main()

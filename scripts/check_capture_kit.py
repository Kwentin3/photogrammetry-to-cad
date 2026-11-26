"""Raster final PDF and check native CCTag3 outputs; this is not a detector.

Requires requirements-capture-kit.txt and an official AliceVision x86_64
detector build qualified by an actual CCTag3 extraction, not its generic help.
Real-photo preflight: replace --kit with --images ORIGINALS (3-5 trial photos).
Run under the host's resource/process owner. Windows CCTag allocations exceed
the current 2 GiB Job commit limit; use the bounded Linux CI for the PDF check.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys
import time


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_native_regions(features, descriptors):
    """Read AliceVision x86_64 .feat/.desc (native size_t count + 128 uchar).

    Source contract checked in AliceVision v3.3.0 and revision d012d055:
    feature/Descriptor.hpp saveDescsToBinFile and
    feature/cctag/ImageDescriber_CCTAG.cpp. A native CCTag ID is the sole byte
    index containing 255; all remaining descriptor bytes must be zero.
    This ABI label does not identify the supplied detector's build version.
    """
    content = descriptors.read_bytes()
    if len(content) < 8:
        raise ValueError(f"Truncated native descriptor header: {descriptors}")
    count = struct.unpack("<Q", content[:8])[0]
    if count > 100000 or len(content) != 8 + 128 * count:
        raise ValueError(f"Native x86_64 descriptor count/length mismatch: {descriptors}")
    positions = [line.split() for line in features.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(positions) != count or any(len(row) != 4 for row in positions):
        raise ValueError(f"Native feature/descriptor count or columns mismatch: {features}")
    regions = []
    for index, position in enumerate(positions):
        descriptor = content[8 + index * 128:8 + (index + 1) * 128]
        active = [i for i, value in enumerate(descriptor) if value]
        if len(active) != 1 or active[0] > 31 or descriptor[active[0]] != 255:
            raise ValueError(f"Invalid native CCTag3 one-hot descriptor #{index}")
        values = [float(value) for value in position]
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"Nonfinite native feature #{index}")
        regions.append({"id": active[0], "x": values[0], "y": values[1],
                        "radius": values[2], "orientation": values[3]})
    return regions


def check_expected(regions, marker_id, center, tolerance=2):
    if [region["id"] for region in regions] != [marker_id]:
        raise ValueError(f"Expected exactly native ID {marker_id}, received {regions}")
    region = regions[0]
    error = math.hypot(region["x"] - center[0], region["y"] - center[1])
    if error > tolerance:
        raise ValueError(f"Native center error {error:.3f}px exceeds {tolerance}px")
    return error


def prepare_inputs(args, output):
    import fitz  # PyMuPDF only rasterizes/reads files; CCTag is the native CLI.

    if args.kit:
        kit = args.kit.resolve()
        manifest = json.loads((kit / "manifest.json").read_text(encoding="utf-8"))
        pdf = kit / "cctag3-print.pdf"
        if sha256(pdf) != manifest["pdf_sha256"]:
            raise ValueError("PDF differs from the delivered manifest")
        if sha256(kit / "measurements.csv") != manifest["measurements_sha256"]:
            raise ValueError("Measurements template differs from the delivered manifest")
        for filename, field in (("placement.txt", "placement_sha256"),
                                ("placement-plan.csv", "placement_plan_sha256")):
            if field in manifest and sha256(kit / filename) != manifest[field]:
                raise ValueError(f"{filename} differs from the delivered manifest")
        with fitz.open(pdf) as document:
            if len(document) != len(manifest["pages"]):
                raise ValueError("PDF page count differs from manifest")
            inputs = []
            for page, expected in zip(document, manifest["pages"]):
                expected_title = f"CCTag3 - ID {expected['native_id']}"
                if expected_title not in [line.strip() for line in page.get_text().splitlines()]:
                    raise ValueError("PDF printed ID differs from manifest")
                raster = output / f"page-{expected['page']}.png"
                pixmap = page.get_pixmap(dpi=args.dpi, alpha=False)
                pixmap.save(raster)
                inputs.append({"path": str(raster), "width": pixmap.width, "height": pixmap.height,
                               "page": expected["page"], "expected_id": expected["native_id"],
                               "expected_center_px": [v / 25.4 * args.dpi for v in expected["center_mm_from_top_left"]]})
        source = {"mode": "final_pdf", "pdf_sha256": sha256(pdf),
                  "manifest_sha256": sha256(kit / "manifest.json"), "dpi": args.dpi,
                  "rasterizer": f"PyMuPDF {fitz.VersionBind}"}
    else:
        root = args.images.resolve()
        paths = sorted(path for path in root.iterdir() if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff"})
        if not 1 <= len(paths) <= 20:
            raise ValueError("Preflight expects 1..20 original trial images (normally 3-5)")
        inputs = []
        for path in paths:
            pixmap = fitz.Pixmap(str(path))
            inputs.append({"path": str(path), "width": pixmap.width, "height": pixmap.height})
        source = {"mode": "original_images", "metric_accuracy_validated": False}
    views = []
    for view_id, item in enumerate(inputs, start=1):
        item["view_id"] = view_id
        item["sha256"] = sha256(Path(item["path"]))
        views.append({"viewId": str(view_id), "poseId": str(view_id), "intrinsicId": "4294967295",
                      "path": item["path"], "width": str(item["width"]), "height": str(item["height"]), "metadata": {}})
    scene = {"version": ["1", "2", "12"], "views": views, "intrinsics": [], "poses": []}
    scene_path = output / "input.sfm"
    scene_path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    return source, inputs, scene_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--kit", type=Path)
    source.add_argument("--images", type=Path)
    parser.add_argument("--detector", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="New directory outside Git; never reuse cached features")
    parser.add_argument("--dpi", type=int, default=72)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    if args.dpi < 36 or args.timeout <= 0 or struct.calcsize("P") != 8 or sys.byteorder != "little":
        parser.error("Requires dpi>=36, positive timeout, and little-endian x86_64 native ABI")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {"status": "NEEDS_EVIDENCE", "physical_print_validated": False,
              "metric_capture_validated": False, "platform": platform.platform()}
    started = time.monotonic()
    try:
        evidence, inputs, scene = prepare_inputs(args, output)
        result.update(evidence)
        detector = args.detector.resolve(strict=True)
        features = output / "features"
        features.mkdir()
        command = [str(detector), "--input", str(scene), "--output", str(features),
                   "--describerTypes", "cctag3", "--forceCpuExtraction", "true",
                   "--maxThreads", "1", "--maxCoresAvailable", "1", "--maxMemoryAvailable", "1073741824",
                   "--rangeStart", "0", "--rangeSize", str(len(inputs)), "--verboseLevel", "debug"]
        result.update({"detector_sha256": sha256(detector), "command": command,
                       "native_abi": "AliceVision CCTag x86_64 little endian; size_t count + 128 unsigned bytes"})
        environment = os.environ.copy()
        environment["OMP_NUM_THREADS"] = "1"
        with (output / "native.log").open("w", encoding="utf-8") as log:
            completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                       env=environment, timeout=args.timeout, check=False)
        result["native_exit_code"] = completed.returncode
        result["native_log_sha256"] = sha256(output / "native.log")
        if completed.returncode:
            raise RuntimeError(f"Native detector exited {completed.returncode}; see native.log")
        pages = []
        for item in inputs:
            base = features / f"{item['view_id']}.cctag3"
            feat, desc = Path(str(base) + ".feat"), Path(str(base) + ".desc")
            regions = read_native_regions(feat, desc)
            summary = {"view_id": item["view_id"], "image_sha256": item["sha256"],
                       "dimensions": [item["width"], item["height"]], "regions": regions,
                       "features_sha256": sha256(feat), "descriptors_sha256": sha256(desc)}
            if "expected_id" in item:
                summary.update({"page": item["page"], "expected_id": item["expected_id"],
                                "center_error_px": check_expected(regions, item["expected_id"], item["expected_center_px"])})
            pages.append(summary)
        result["images"] = pages
        result["status"] = "PASS" if args.kit else "PREFLIGHT_REVIEW_REQUIRED"
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        result["error"] = str(error)
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    (output / "validation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in {"PASS", "PREFLIGHT_REVIEW_REQUIRED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

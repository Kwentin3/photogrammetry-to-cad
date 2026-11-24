"""Lay out official CCTag3 SVGs on printable sheets; never encode marker rings.

pip install svgwrite==1.4.3 reportlab==4.5.1 svglib==1.6.0
python scripts/make_capture_kit.py --source-dir /outside/git/cctag-source --download-source
"""

import argparse
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.request import urlopen

from reportlab.graphics import renderPDF
from reportlab.lib.pagesizes import A3, A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from svglib.svglib import svg2rlg


PIN = "71021443af3f7946e8e9025a37634b57e7aad77d"
SOURCE_BASE = f"https://raw.githubusercontent.com/alicevision/CCTag/{PIN}/markersToPrint/generators/"
SOURCE_HASHES = {
    "generate.py": "93bbc70c469885fda1be54d55f84d944a4885c21cddf96bccd524c207b93365f",
    "cctag3.txt": "f68d0d7b68b080dd3e7a507a47e59fe4807649af6818226a6d9ee32912d3181a",
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_files(directory, download):
    directory.mkdir(parents=True, exist_ok=True)
    for name, expected in SOURCE_HASHES.items():
        path = directory / name
        if not path.exists() and download:
            with urlopen(SOURCE_BASE + name, timeout=30) as response:
                content = response.read(64 * 1024 + 1)
            if len(content) > 64 * 1024 or hashlib.sha256(content).hexdigest() != expected:
                raise ValueError(f"Unexpected official source: {name}")
            path.write_bytes(content)
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"Missing or changed pinned source: {path}")


def make_kit(source_dir, output, ids, diameter_mm, paper):
    if len(ids) < 2 or len(ids) != len(set(ids)) or any(i not in range(32) for i in ids):
        raise ValueError("Use at least two distinct native CCTag3 IDs in 0..31")
    page_size = {"A4": A4, "A3": A3}[paper]
    width, height = (value / mm for value in page_size)
    # Preserve the official default margin/radius ratio (400/500).
    tile_mm = diameter_mm * 1.4
    if not 20 <= diameter_mm or tile_mm > min(width - 40, height - 135):
        raise ValueError("Diameter does not fit preserved margins; select larger paper")
    output.mkdir(parents=True, exist_ok=True)
    pdf = output / "cctag3-print.pdf"
    center_x, center_y = width / 2, height / 2 + 10
    pages = []
    generator_args = ["--rings", "3", "--radius", "500", "--margin", "400",
                      "--addCross", "--whiteBackground"]
    with tempfile.TemporaryDirectory(prefix="cctag-official-") as temporary:
        generated = Path(temporary)
        subprocess.run([sys.executable, str(source_dir / "generate.py"),
                        "--outdir", str(generated), *generator_args],
                       cwd=source_dir, check=True, timeout=60)
        canvas = Canvas(str(pdf), pagesize=page_size, invariant=1)
        canvas.setTitle("CCTag3 capture kit - native IDs, print at 100 percent")
        for index, marker_id in enumerate(ids, start=1):
            canvas.setFont("Helvetica-Bold", 20)
            canvas.drawString(20 * mm, (height - 25) * mm, f"CCTag3 - ID {marker_id}")
            canvas.setFont("Helvetica", 10)
            canvas.drawString(20 * mm, (height - 34) * mm,
                              f"{paper} | actual size / 100% | no fit to page | one copy per ID")
            drawing = svg2rlg(str(generated / f"{marker_id:04d}.svg"))
            drawing.scale(tile_mm * mm / drawing.width, tile_mm * mm / drawing.height)
            renderPDF.draw(drawing, canvas, (center_x - tile_mm / 2) * mm,
                           (center_y - tile_mm / 2) * mm)
            canvas.setFont("Helvetica", 10)
            canvas.drawString(20 * mm, 77 * mm,
                              f"Outer black diameter: {diameter_mm:g} mm. Measure between gray centres.")
            canvas.drawString(20 * mm, 70 * mm,
                              "Keep white margins. Fix flat on rigid matte support. Do not fold.")
            # Two independent printer checks reveal nonuniform scaling as well.
            x0, x1, y = center_x - 50, center_x + 50, 50
            canvas.setLineWidth(0.5)
            canvas.line(x0 * mm, y * mm, x1 * mm, y * mm)
            for x in (x0, x1):
                canvas.line(x * mm, (y - 3) * mm, x * mm, (y + 3) * mm)
            canvas.drawCentredString(center_x * mm, 41 * mm, "PRINT CHECK X: 100 mm between ticks")
            x, y0, y1 = width - 12, 40, 140
            canvas.line(x * mm, y0 * mm, x * mm, y1 * mm)
            for y in (y0, y1):
                canvas.line((x - 3) * mm, y * mm, (x + 3) * mm, y * mm)
            canvas.saveState()
            canvas.translate((x - 2) * mm, ((y0 + y1) / 2) * mm)
            canvas.rotate(90)
            canvas.drawCentredString(0, 0, "PRINT CHECK Y: 100 mm")
            canvas.restoreState()
            canvas.drawString(20 * mm, 26 * mm,
                              "Print checks are not the scene baseline. Measure after mounting.")
            canvas.drawString(20 * mm, 19 * mm,
                              f"Page {index}/{len(ids)} | bank {PIN[:12]} | native ID {marker_id}")
            canvas.showPage()
            pages.append({"page": index, "native_id": marker_id,
                          "center_mm_from_bottom_left": [center_x, center_y],
                          "center_mm_from_top_left": [center_x, height - center_y]})
        canvas.save()
    measurements = output / "measurements.csv"
    with measurements.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["measurement_id", "purpose", "from_point", "to_point",
                         "measured_mm", "uncertainty_mm", "method", "notes"])
        for page in pages:
            for axis in ("x", "y"):
                writer.writerow([f"print_page_{page['page']}_{axis}", "print_check",
                                 f"page_{page['page']}_{axis}_tick_start", f"page_{page['page']}_{axis}_tick_end",
                                 "", "", "", "Nominal 100 mm; check printed sheet before mounting"])
        writer.writerow(["scale_baseline", "scale", f"cctag3:{ids[0]}:center", f"cctag3:{ids[1]}:center",
                         "", "", "", "Measure gray centres in place; this pair defines scale only"])
        for a, b in zip(ids[:2], ids[2:4]):
            writer.writerow([f"marker_check_{a}_{b}", "check", f"cctag3:{a}:center", f"cctag3:{b}:center",
                             "", "", "", "Independent marker check; do not use to fit scale"])
        for number in (1, 2):
            writer.writerow([f"object_check_{number}", "check", f"REPLACE_object_{number}_start", f"REPLACE_object_{number}_end",
                             "", "", "", "Describe and photograph both endpoints; do not fit scale"])
    manifest = {
        "family": "cctag3", "native_ids": ids, "paper": paper,
        "page_size_mm": [width, height], "outer_diameter_mm": diameter_mm,
        "source_revision": PIN, "source_base": SOURCE_BASE, "source_sha256": SOURCE_HASHES,
        "generator_arguments": generator_args, "pages": pages,
        "versions": {name: importlib.metadata.version(name) for name in ("reportlab", "svglib", "svgwrite")},
        "pdf_sha256": sha256(pdf), "measurements_sha256": sha256(measurements),
        "physical_print_validated": False, "metric_capture_validated": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True, help="Pinned official files outside Git")
    parser.add_argument("--download-source", action="store_true", help="Fetch missing pinned source files")
    parser.add_argument("--output", type=Path, default=Path("templates/capture-kit"))
    parser.add_argument("--ids", nargs="+", type=int, default=[0, 1, 2, 3])
    parser.add_argument("--diameter-mm", type=float, default=100)
    parser.add_argument("--paper", choices=["A4", "A3"], default="A4")
    args = parser.parse_args()
    source_dir = args.source_dir.resolve()
    source_files(source_dir, args.download_source)
    result = make_kit(source_dir, args.output, args.ids, args.diameter_mm, args.paper)
    print(json.dumps({"pdf": str(args.output / "cctag3-print.pdf"), "sha256": result["pdf_sha256"]}))


if __name__ == "__main__":
    main()

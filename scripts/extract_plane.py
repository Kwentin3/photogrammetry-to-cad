"""Fit one explicitly selected convex planar patch; do not infer a whole object."""

import argparse
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
import open3d as o3d
from scipy.spatial import ConvexHull, QhullError


def convex_outline(points):
    """Native 2-D hull, ordered counterclockwise without perturbing the points."""
    points = np.asarray(points, dtype=float)
    if len(points) < 3:
        raise ValueError("At least three projected points are required")
    try:
        hull = ConvexHull(points)
    except QhullError as error:
        raise ValueError("Projected patch needs three non-collinear distinct points") from error
    return points[hull.vertices]


def extract_plane(source, *, roi, meters_per_unit, distance_mm,
                  scale_status="unverified", scale_note="", iterations=2000, seed=42,
                  support_path=None):
    """ROI is in source coordinates; every output length is in millimetres."""
    source = Path(source)
    roi = np.asarray(roi, dtype=float)
    if roi.shape != (6,) or not np.isfinite(roi).all() or np.any(roi[:3] >= roi[3:]):
        raise ValueError("ROI must be finite xmin ymin zmin xmax ymax zmax with positive extents")
    if not np.isfinite(meters_per_unit) or meters_per_unit <= 0:
        raise ValueError("meters_per_unit must be finite and positive")
    if not np.isfinite(distance_mm) or distance_mm <= 0 or iterations < 1:
        raise ValueError("Positive distance_mm and iterations are required")
    if scale_status not in {"unverified", "test_assumption", "synthetic_reference", "measured"} or not scale_note.strip():
        raise ValueError("Supply a scale status and a note stating its basis")
    cloud = o3d.io.read_point_cloud(str(source))
    original_count = len(cloud.points)
    points = np.asarray(cloud.points)
    selected = np.flatnonzero(np.isfinite(points).all(axis=1)
                              & (points >= roi[:3]).all(axis=1)
                              & (points <= roi[3:]).all(axis=1))
    if len(selected) < 3:
        raise ValueError("ROI contains fewer than three finite points")
    patch = cloud.select_by_index(selected.tolist())
    mm_per_unit = meters_per_unit * 1000.0
    patch.scale(mm_per_unit, center=(0, 0, 0))
    o3d.utility.random.seed(seed)
    coefficients, indices = patch.segment_plane(distance_threshold=distance_mm,
                                                ransac_n=3, num_iterations=iterations)
    support = np.asarray(patch.points)[indices]
    if len(support) < 3:
        raise ValueError("Plane has fewer than three supporting points")
    # Keep the fitted equation intact when choosing the frame normal's sign.
    normal = np.array(coefficients[:3], dtype=float, copy=True)
    normal /= np.linalg.norm(normal)
    # Choose a repeatable sign and scene axis; neither is a measured vertical.
    if normal[np.argmax(np.abs(normal))] < 0:
        normal *= -1
    seed_axis = np.eye(3)[np.argmin(np.abs(normal))]
    x_axis = seed_axis - np.dot(seed_axis, normal) * normal
    x_axis /= np.linalg.norm(x_axis)
    y_axis = np.cross(normal, x_axis)
    centroid = support.mean(axis=0)
    # The centroid is projected onto the fitted plane, preserving its placement.
    original_normal = np.asarray(coefficients[:3])
    origin = centroid - ((original_normal @ centroid + coefficients[3])
                         / np.dot(original_normal, original_normal)) * original_normal
    local = np.column_stack(((support - origin) @ x_axis, (support - origin) @ y_axis))
    outline = convex_outline(local)
    residual = (support - origin) @ normal
    if support_path is not None:
        support_path = Path(support_path)
        support_path.parent.mkdir(parents=True, exist_ok=True)
        if not o3d.io.write_point_cloud(str(support_path), patch.select_by_index(indices)):
            raise ValueError("Could not save the actual RANSAC support cloud")
    with source.open("rb") as stream:
        source_sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
    return {
        "format": "planar-extrusion-v1",
        "part_id": "patch-01",
        "units": "mm",
        "source": {"filename": source.name, "sha256": source_sha256,
                   "binding": "Checksum of the observed input file; not proof of origin or authenticity"},
        "scale": {"meters_per_source_unit": meters_per_unit, "status": scale_status, "note": scale_note},
        "selection": {"roi_source_units": roi.tolist(), "distance_threshold_mm": distance_mm,
                      "iterations": iterations, "seed": seed, "source_points": original_count,
                      "roi_points": len(selected), "plane_points": len(indices),
                      "support_cloud_mm": support_path.name if support_path is not None else None},
        "plane": {"origin_mm": origin.tolist(), "x_axis": x_axis.tolist(),
                  "y_axis": y_axis.tolist(), "normal": normal.tolist(),
                  "equation_mm": [*normal.tolist(), float(-normal @ origin)],
                  "frame_basis": "Deterministic scene-axis projection; no independent vertical measurement"},
        "outline_mm": outline.tolist(),
        "outline_basis": "Convex envelope of projected RANSAC inliers inside the explicit ROI",
        "fit": {"rms_mm": float(np.sqrt(np.mean(residual ** 2))),
                "maximum_absolute_residual_mm": float(np.max(np.abs(residual)))},
        "thickness": {"value_mm": None, "status": "unresolved", "note": "Скрытая толщина не измерена по одной поверхности"},
        "limitations": ["One convex planar patch, not automatic part recognition",
                        "The convex envelope can bridge holes or disconnected regions; inspect the selected patch",
                        "Reconstruction scale and accuracy require independent measurements",
                        "Extrusion along the signed normal is a modelling decision, not an observed hidden surface"],
    }


def write_question(parameters, path):
    """Small vector plot of the actual computed contour, with a focused question."""
    outline = np.asarray(parameters["outline_mm"])
    low, high = outline.min(axis=0), outline.max(axis=0)
    span = np.maximum(high - low, 1e-9)
    scale = min(620 / span[0], 350 / span[1])
    pixels = (outline - low) * scale
    pixels[:, 0] += 60
    pixels[:, 1] = 430 - pixels[:, 1]
    points = " ".join(f"{x:.3f},{y:.3f}" for x, y in pixels)
    labels = "".join(f'<text x="{x + 5:.2f}" y="{y - 5:.2f}">P{i + 1}</text>'
                     for i, (x, y) in enumerate(pixels))
    title = escape(parameters["part_id"])
    source_name = escape(parameters["source"]["filename"])
    normal_text = ", ".join(f"{v:.4f}" for v in parameters["plane"]["normal"])
    units_label = "условные CAD мм" if parameters["scale"]["status"] == "unverified" else "мм"
    Path(path).write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="570" viewBox="0 0 800 570">'
        '<rect width="800" height="570" fill="white"/><g font-family="sans-serif" font-size="15">'
        f'<text x="25" y="28">{title} / {source_name}: контур в рассчитанной плоскости</text>'
        f'<text x="25" y="53">Размеры контура: {span[0]:.4g} × {span[1]:.4g} {units_label}; масштаб: '
        f'{escape(parameters["scale"]["status"])}</text>'
        f'<polygon points="{points}" fill="#daeafa" stroke="#24547c" stroke-width="2"/>{labels}'
        f'<text x="25" y="475">Направление +normal = ({normal_text}); оси x/y — правые.</text>'
        f'<text x="25" y="502">Вопрос: какова толщина участка {title} по направлению +normal?</text>'
        '<text x="25" y="528">Ответ: thickness.value_mm, статус (human / measured / test_assumption) и note.</text>'
        '<text x="25" y="552">Контур ограничивает опорные точки; проверьте ROI и принадлежность поверхности.</text>'
        '</g></svg>', encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path, help="Editable parameters JSON")
    parser.add_argument("--roi", nargs=6, type=float, required=True,
                        metavar=("XMIN", "YMIN", "ZMIN", "XMAX", "YMAX", "ZMAX"))
    parser.add_argument("--meters-per-unit", type=float, required=True)
    parser.add_argument("--distance-mm", type=float, required=True, help="RANSAC threshold, not measured accuracy")
    parser.add_argument("--scale-status", choices=("unverified", "test_assumption", "synthetic_reference", "measured"), default="unverified")
    parser.add_argument("--scale-note", required=True)
    parser.add_argument("--iterations", type=int, default=2000)
    args = parser.parse_args()
    support_path = args.output.with_suffix(".inliers.ply")
    parameters = extract_plane(args.source, roi=args.roi, meters_per_unit=args.meters_per_unit,
                               distance_mm=args.distance_mm, scale_status=args.scale_status,
                               scale_note=args.scale_note, iterations=args.iterations,
                               support_path=support_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(parameters, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_question(parameters, args.output.with_suffix(".svg"))
    print(json.dumps({"parameters": str(args.output), "question": str(args.output.with_suffix('.svg')),
                      "support_cloud_mm": str(support_path), "fit": parameters["fit"], "thickness": "unresolved"}))


if __name__ == "__main__":
    main()

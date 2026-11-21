"""Editable planar-extrusion model; lengths in mm.
The scale and hidden thickness retain their explicit evidence status.
Run: python model.py --output model.step
"""
import argparse
import json
import math
from pathlib import Path
from build123d import BuildPart, BuildSketch, Plane, Polygon, export_step, extrude, import_step

PARAMETERS = {'format': 'planar-extrusion-v1',
 'part_id': 'synthetic-board-observed-patch',
 'units': 'mm',
 'source': {'filename': 'synthetic-final-dense.ply',
            'sha256': '6b68c0ffb756fe66648cad5dea6618dee9f83d90d0f1b8a3e81eb5938949c269',
            'binding': 'Checksum of the observed input file; not proof of origin or authenticity'},
 'scale': {'meters_per_source_unit': 0.001,
           'status': 'synthetic_reference',
           'note': 'Known virtual CCTag0/1 baseline 100 mm, native SfMTransform before MVS. One '
                   'source unit is one mm; not a physical capture or manufacturing accuracy test.'},
 'selection': {'roi_source_units': [-110.0, -120.0, -3.0, 211.0, 121.0, 3.0],
               'distance_threshold_mm': 1,
               'iterations': 2000,
               'seed': 42,
               'source_points': 15884,
               'roi_points': 15884,
               'plane_points': 15861,
               'support_cloud_mm': 'parameters.inliers.ply'},
 'plane': {'origin_mm': [17.73111346005924, -14.518672069356242, 0.013733351217312943],
           'x_axis': [1.6386762728745832e-08, 0.9999999990203515, -4.426394573133863e-05],
           'y_axis': [-0.9999999314738962, -3.308722450212111e-24, -0.0003702056229981118],
           'normal': [-0.00037020562263544035, 4.426394876457458e-05, 0.9999999304942475],
           'equation_mm': [-0.00037020562263544035,
                           4.426394876457458e-05,
                           0.9999999304942475,
                           -0.00652653860765752],
           'frame_basis': 'Deterministic scene-axis projection; no independent vertical '
                          'measurement'},
 'outline_mm': [[29.12035662751094, 126.7109932323651],
                [-56.38012084186369, 126.26018093790036],
                [-78.99322752070827, 125.91912487011808],
                [-92.26733370499744, 125.66407302100704],
                [-94.20734090052622, 125.5860128192933],
                [-97.31433659911866, 125.39004875562705],
                [-100.37032002632031, 125.13118732097871],
                [-103.08332440736716, 124.88415064053186],
                [-103.28934043887526, 123.00501642907594],
                [-103.48433239186906, 117.47238335022769],
                [-103.81234565220578, 107.59147176638942],
                [-103.85334193635487, 100.1776023358721],
                [-104.12932120956583, 5.494369195751646],
                [-104.19335556316182, -175.80713054813057],
                [-103.24934251585285, -186.87502217646212],
                [-101.61433240135071, -189.74493776615748],
                [-96.16833269651306, -191.0909402823902],
                [-94.97933606378636, -191.22796844453939],
                [-16.55832496091329, -191.44787495717142],
                [10.888561497418374, -191.48590435596483],
                [92.92777897533357, -191.44284113860104],
                [130.8426772578394, -191.0188551633167],
                [133.25066820770525, -176.93492987010362],
                [133.71067649704412, -161.3428594692195],
                [133.44766804483828, 92.1130872061702],
                [133.4326694288769, 97.28799913619869],
                [132.88266468119457, 113.07466050581108],
                [132.10065699363216, 125.55899705926892],
                [105.04818424078971, 126.39322477890202]],
 'outline_basis': 'Convex envelope of projected RANSAC inliers inside the explicit ROI',
 'fit': {'rms_mm': 0.13093553338604336, 'maximum_absolute_residual_mm': 0.9526610894919765},
 'thickness': {'value_mm': 2,
               'status': 'test_assumption',
               'note': 'Agent technical test only: hidden thickness is unmeasured; extrusion goes '
                       'along the signed normal.'},
 'limitations': ['One convex planar patch, not automatic part recognition',
                 'The convex envelope can bridge holes or disconnected regions; inspect the '
                 'selected patch',
                 'Reconstruction scale and accuracy require independent measurements',
                 'Extrusion along the signed normal is a modelling decision, not an observed '
                 'hidden surface']}

def validate(parameters):
    if parameters.get("format") != "planar-extrusion-v1" or parameters.get("units") != "mm":
        raise ValueError("Expected planar-extrusion-v1 parameters in mm")
    thickness = parameters["thickness"]
    if thickness["status"] not in {"test_assumption", "human", "measured"}:
        raise ValueError("Thickness is unresolved: record a value, decision status, and note")
    value = thickness["value_mm"]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError("Thickness must be finite and positive")
    if not thickness.get("note", "").strip():
        raise ValueError("Thickness decision needs a note stating its basis")
    outline = parameters["outline_mm"]
    if len(outline) < 3 or any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in outline):
        raise ValueError("Outline needs at least three finite 2-D vertices")
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(outline, outline[1:] + outline[:1])) / 2
    if area <= 1e-12:
        raise ValueError("Outline must have positive area and counterclockwise vertex order")
    frame = parameters["plane"]
    origin = frame["origin_mm"]
    axes = [frame[key] for key in ("x_axis", "y_axis", "normal")]
    if len(origin) != 3 or not all(math.isfinite(v) for v in origin):
        raise ValueError("Plane origin must have three finite coordinates")
    if any(len(axis) != 3 or not all(math.isfinite(v) for v in axis) for axis in axes):
        raise ValueError("Plane axes must have three finite coordinates")
    dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    if any(abs(dot(a, b) - float(i == j)) > 1e-8
           for i, a in enumerate(axes) for j, b in enumerate(axes)):
        raise ValueError("Plane frame must be orthonormal; it will not be silently repaired")
    x, y, normal = axes
    cross = (x[1] * y[2] - x[2] * y[1], x[2] * y[0] - x[0] * y[2], x[0] * y[1] - x[1] * y[0])
    if dot(cross, normal) < 1 - 1e-8:
        raise ValueError("Plane frame must be right-handed")
    return area * value


def make_shape(parameters):
    validate(parameters)
    frame = parameters["plane"]
    plane = Plane(origin=frame["origin_mm"], x_dir=frame["x_axis"], z_dir=frame["normal"])
    with BuildPart() as model:
        with BuildSketch(plane):
            # build123d flattens JSON lists; tuples are its native point contract.
            Polygon(*(tuple(point) for point in parameters["outline_mm"]), align=None)
        extrude(amount=parameters["thickness"]["value_mm"])
    return model.part


def export_and_inspect(parameters, step_path):
    """Check native solids, placement, volume and STEP round-trip dimensions."""
    expected_volume = validate(parameters)
    shape = make_shape(parameters)
    if not shape.is_valid or len(shape.solids()) != 1:
        raise ValueError("Constructed CAD must be a valid single solid")
    step_path = Path(step_path)
    step_path.parent.mkdir(parents=True, exist_ok=True)
    export_step(shape, step_path)
    reopened = import_step(step_path)
    if not reopened.is_valid or len(reopened.solids()) != 1:
        raise ValueError("STEP read-back must be a valid single solid")
    original_bounds = shape.bounding_box()
    reopened_bounds = reopened.bounding_box()
    # Compare min/max, not just size: a recentered export must fail this check.
    before = [*original_bounds.min, *original_bounds.max]
    after = [*reopened_bounds.min, *reopened_bounds.max]
    extent = max(1.0, *map(abs, before))
    if max(abs(a - b) for a, b in zip(before, after)) > max(1e-5, extent * 1e-8):
        raise ValueError("STEP read-back changed scene placement or dimensions")
    if not math.isclose(reopened.volume, expected_volume, rel_tol=1e-7, abs_tol=1e-7):
        raise ValueError("STEP volume differs from contour area times explicit thickness")
    return {"valid": True, "solids": len(reopened.solids()), "volume_mm3": reopened.volume,
            "expected_volume_mm3": expected_volume,
            "bounds_min_mm": list(reopened_bounds.min), "bounds_max_mm": list(reopened_bounds.max),
            "world_extents_mm": list(reopened_bounds.size),
            "thickness": parameters["thickness"], "scale": parameters["scale"],
            "claim": "Technical CAD validity only; physical accuracy and hidden surfaces are not verified"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_suffix(".step"))
    args = parser.parse_args()
    report = export_and_inspect(PARAMETERS, args.output)
    args.output.with_suffix(".inspection.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))

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
 'source': {'filename': 'Meshing_1.ply',
            'sha256': 'c250cd5fa55b19ee3a6665549865dc05ada4472a7a590f3f5e70c01260fb03f1',
            'binding': 'Checksum of the observed input file; not proof of origin or authenticity'},
 'scale': {'meters_per_source_unit': 0.001,
           'status': 'synthetic_reference',
           'note': 'Known VIRTUAL CCTag0/1 baseline 100 mm, native SfMTransform before MVS. One '
                   'source unit is one mm by explicit application convention; not calibrated '
                   'physical capture accuracy.'},
 'selection': {'roi_source_units': [-158.63400099999998,
                                    -118.697001,
                                    -1.3407209999999998,
                                    159.350001,
                                    119.148001,
                                    1.5286609999999998],
               'distance_threshold_mm': 1.0,
               'iterations': 2000,
               'seed': 42,
               'source_points': 15659,
               'roi_points': 15659,
               'plane_points': 15622,
               'support_cloud_mm': 'parameters-unresolved.inliers.ply',
               'note': 'Full observed source bounds expanded by epsilon; no crop to the ideal '
                       'virtual board, rectangle fitting or angle constraints.'},
 'plane': {'origin_mm': [-31.459206290724612, -13.856690878949502, 0.027415799839796435],
           'x_axis': [4.1054819575758494e-09, 0.9999999999735145, -7.278120919008779e-06],
           'y_axis': [-0.9999998409038527, 0.0, -0.0005640853387976714],
           'normal': [-0.0005640853387827313, 7.278122076929961e-06, 0.9999998408773672],
           'equation_mm': [-0.0005640853387827313,
                           7.278122076929961e-06,
                           0.9999998408773672,
                           -0.045060621827862135],
           'frame_basis': 'Deterministic scene-axis projection; no independent vertical '
                          'measurement'},
 'outline_mm': [[133.00469128473938, -159.9922000214055],
                [132.84869227193357, 97.16091740208226],
                [131.47068794215414, 126.76158653232937],
                [115.50669066227258, 126.88479733988154],
                [107.3939902382635, 126.92476446708542],
                [79.80848656280229, 127.00847955993902],
                [-23.262407850663422, 127.16291235304193],
                [-52.93260933515843, 127.17479723936583],
                [-76.09650929986753, 127.09979991507825],
                [-103.22930877664899, 126.90484038002113],
                [-104.38030883051276, 126.06483606934633],
                [-104.60430906621323, 117.26581640121],
                [-104.84031019657698, -12.543191859372946],
                [-104.57130991269541, -143.1612906376315],
                [-104.38731042027737, -186.56233688194843],
                [-103.67830991341677, -187.63529776735052],
                [-101.30730846391607, -189.40118570097465],
                [-99.61730914318885, -189.53323836503694],
                [-90.20230881107321, -190.08121269252075],
                [-42.97860975307169, -190.63128569197576],
                [93.83099175174203, -190.80916880999416],
                [125.18969130151214, -190.60920360853638],
                [128.54769279306484, -190.24908794268836],
                [132.5736896659859, -188.9923300963607]],
 'outline_basis': 'Convex envelope of projected RANSAC inliers inside the explicit ROI',
 'fit': {'rms_mm': 0.13198435823305749, 'maximum_absolute_residual_mm': 1.0834921104189863},
 'thickness': {'value_mm': 2.0,
               'status': 'test_assumption',
               'note': 'AGENT TECHNICAL TEST ONLY, not a human answer. Hidden thickness is '
                       'unmeasured; extrusion goes along the signed source-derived normal.'},
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

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
 'part_id': 'camera-corresponding-observed-patch',
 'units': 'mm',
 'source': {'filename': 'Meshing_1.ply',
            'sha256': '7ee3128c7c9bd943c4b412b092c6a11950f53d31593d5d1fa1784c487bab0139',
            'binding': 'Checksum of the observed input file; not proof of origin or authenticity'},
 'scale': {'meters_per_source_unit': 0.001,
           'status': 'unverified',
           'note': 'PHYSICAL SCALE UNKNOWN. One arbitrary source unit is represented by one '
                   'NOMINAL CAD mm; no physical millimetre or hidden thickness was measured.'},
 'selection': {'roi_source_units': [0.056219878213235215,
                                    -0.1253382546174391,
                                    -0.06533842027310362,
                                    0.15438469716119552,
                                    0.009672654678883015,
                                    0.03428913117854869],
               'distance_threshold_mm': 0.00075,
               'iterations': 2000,
               'seed': 42,
               'source_points': 47037,
               'roi_points': 10291,
               'plane_points': 4870,
               'support_cloud_mm': 'parameters-unresolved.inliers.ply',
               'note': 'Matched posed camera centers bind the old accepted patch to this new '
                       'source region. A 5%-span-padded bounding box of mapped old support serves '
                       'only as an ROI hint. Plane and convex contour are fitted freely from new '
                       'source points; no old outline, ideal cube, normal or right-angle '
                       'constraint is applied.'},
 'plane': {'origin_mm': [0.1084211459753595, -0.05723477162020958, -0.019151952613326435],
           'x_axis': [-0.004335429746170785, 0.9999813839405988, -0.004293695513276646],
           'y_axis': [-0.7036786729125527, 0.0, 0.7105183497194346],
           'normal': [0.7105051226676307, 0.006101784349246905, 0.7036655731885785],
           'equation_mm': [0.7105051226676307,
                           0.006101784349246905,
                           0.7036655731885785,
                           -0.06320797567394613],
           'frame_basis': 'Deterministic scene-axis projection; no independent vertical '
                          'measurement'},
 'outline_mm': [[-0.03609387584397531, 0.05934224176015812],
                [-0.04711551537729721, 0.049825312090262266],
                [-0.05118307735769734, 0.04461556692502203],
                [-0.055643145455651855, 0.03788337158989528],
                [-0.056788013071709526, 0.03597861966563496],
                [-0.06081614995564952, 0.024092389295798884],
                [-0.06223178565487745, 0.0150359922644497],
                [-0.06259356631639092, 0.012187939740605348],
                [-0.0630291068768996, 0.00762319742493504],
                [-0.06311408146680343, 0.006252153165752244],
                [-0.06304710486367067, 0.004078060000248107],
                [-0.062390263242484895, -0.006015381747962108],
                [-0.06170064578893891, -0.012217633880998079],
                [-0.059335088092563944, -0.018928971430503042],
                [-0.05388178896067198, -0.031070383709522694],
                [-0.04960598216051139, -0.036191715850025154],
                [-0.04334019017256465, -0.04226096812525165],
                [-0.03631903577236603, -0.0473864455718037],
                [-0.03281828945101121, -0.04963988037634078],
                [-0.028919293701000243, -0.05189207656440441],
                [-0.015686646598895092, -0.05661382357433996],
                [-0.007717298937497847, -0.057347274351229834],
                [-0.003735473398815114, -0.05742429993700661],
                [0.003714905534824791, -0.0574432327114359],
                [0.009976840839002738, -0.05685495410872822],
                [0.018225123253934338, -0.05523904447624937],
                [0.021688105329902396, -0.05429906203203085],
                [0.03279103015376268, -0.050386105043676674],
                [0.0400957011614515, -0.04522966911208818],
                [0.043116139957983156, -0.04260488829878517],
                [0.04903938042642605, -0.03593447089207115],
                [0.052842105057796775, -0.02965816038093529],
                [0.05430529640848181, -0.026656365746489122],
                [0.05883871218036823, -0.017226600343683333],
                [0.060859315370284855, 0.000538209126532545],
                [0.06072026805992343, 0.004253499996528176],
                [0.06046926435731304, 0.010532699333276666],
                [0.05893667767656865, 0.02300221185245035],
                [0.053826021969799714, 0.03554124712030967],
                [0.05313355272108032, 0.03723386047838962],
                [0.04664028738852955, 0.047051803025005084],
                [0.04370429509289049, 0.049961866617801366],
                [0.029969311889778902, 0.05967034700459634],
                [0.02365595442782231, 0.062297143825677165],
                [0.016457690009403163, 0.06497029235312773],
                [0.013978427129382772, 0.06526279649836096],
                [0.006353770839699556, 0.06595825985034504],
                [-0.001601783285948346, 0.06620012061407524],
                [-0.005694566386846031, 0.06621361366058022],
                [-0.011229981341689356, 0.06600362954646252],
                [-0.01704223760263772, 0.06527360145072862],
                [-0.02343391422930785, 0.06362804489181716],
                [-0.02789127596231667, 0.06237531879464321]],
 'outline_basis': 'Convex envelope of projected RANSAC inliers inside the explicit ROI',
 'fit': {'rms_mm': 0.000443196378368507, 'maximum_absolute_residual_mm': 0.000840114180767543},
 'thickness': {'value_mm': 0.005,
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

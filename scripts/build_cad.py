"""Build a tilted planar extrusion from explicit editable parameters, then reread STEP."""

import argparse
import hashlib
import inspect
import json
import math
from pathlib import Path
from pprint import pformat

from build123d import BuildPart, BuildSketch, Plane, Polygon, export_step, extrude, import_step


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


def write_model(parameters, path):
    """Emit the same native builder as a self-contained, editable Python file."""
    header = ('"""Editable planar-extrusion model; lengths in mm.\n'
              'The scale and hidden thickness retain their explicit evidence status.\n'
              'Run: python model.py --output model.step\n"""\n'
              'import argparse\nimport json\nimport math\nfrom pathlib import Path\n'
              'from build123d import BuildPart, BuildSketch, Plane, Polygon, export_step, extrude, import_step\n\n')
    code = header + "PARAMETERS = " + pformat(parameters, sort_dicts=False, width=100) + "\n\n"
    code += "\n\n".join(inspect.getsource(function) for function in (validate, make_shape, export_and_inspect))
    code += ('\n\nif __name__ == "__main__":\n'
             '    parser = argparse.ArgumentParser(description=__doc__)\n'
             '    parser.add_argument("--output", type=Path, default=Path(__file__).with_suffix(".step"))\n'
             '    args = parser.parse_args()\n'
             '    report = export_and_inspect(PARAMETERS, args.output)\n'
             '    args.output.with_suffix(".inspection.json").write_text(json.dumps(report, indent=2) + "\\n", encoding="utf-8")\n'
             '    print(json.dumps(report))\n')
    Path(path).write_text(code, encoding="utf-8")


def build(parameters_path, output_dir):
    parameters_bytes = Path(parameters_path).read_bytes()
    parameters = json.loads(parameters_bytes)
    validate(parameters)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = export_and_inspect(parameters, output_dir / "model.step")
    write_model(parameters, output_dir / "model.py")
    report["parameters_sha256"] = hashlib.sha256(parameters_bytes).hexdigest()
    (output_dir / "inspection.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parameters", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.parameters, args.output_dir)))


if __name__ == "__main__":
    main()

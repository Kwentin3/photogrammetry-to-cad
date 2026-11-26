"""Report native reconstruction facts after backup; this does not build CAD.

Run in the existing local geometry environment (Open3D + NumPy).
The scale receipt binds physical units to the native scene SHA; cloud lineage
still belongs to the native graph and its saved output route.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from check_marker_scale import (
    MarkerError, cctag_landmarks, identifier, markers_from_scene, number, read_json,
    scene_reconstructed_views, vector, verify_applied_baseline,
)


IDENTITY = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
UNITS = {"mm", "cm", "m"}


def artifact(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"Expected an artifact file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(path), "sha256": digest.hexdigest(), "bytes": path.stat().st_size}


def absolute_file(value, context):
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError(f"{context} must be an absolute file path in this reporting environment")
    return Path(value).resolve(strict=True)


def scene_summary(scene):
    reconstructed = scene_reconstructed_views(scene, "scene")
    groups = {}
    for landmark in cctag_landmarks(scene, reconstructed, "scene"):
        marker_id = landmark["id"]
        groups.setdefault(marker_id, []).append({
            "landmark_id": landmark["landmark_id"],
            "center": landmark["center"],
            "observation_count": landmark["observation_count"],
            "posed_observation_count": landmark["reconstructed_view_count"],
            "posed_view_ids": landmark["reconstructed_view_ids"],
        })
    markers = [{"id": marker_id, "ambiguous": len(landmarks) > 1,
                "landmarks": landmarks}
               for marker_id, landmarks in sorted(groups.items())]
    return {
        "view_count": len(scene.get("views", [])),
        "registered_view_count": len(reconstructed),
        "registered_fraction": len(reconstructed) / len(scene["views"]) if scene.get("views") else 0.0,
        "pose_count": len(scene.get("poses", [])),
        "intrinsic_count": len(scene.get("intrinsics", [])),
        "markers": markers,
    }


def verified_scale(settings, scene_artifact, evidence_path=None):
    request = settings.get("scale", {"mode": "unknown"})
    if not isinstance(request, dict):
        raise ValueError("settings.scale must be an object")
    mode = request.get("mode")
    if mode == "unknown":
        if request.get("applied_evidence") or evidence_path is not None:
            raise ValueError("Unknown scale contradicts supplied applied scale evidence")
        return {
            "mode": "unknown", "applied": False, "units": "unknown",
            "transform": {"scale": 1.0, "rotation": IDENTITY.copy(), "translation": [0.0] * 3},
            "reason": "no measured physical scale",
        }
    if mode not in {"measured_baseline", "marker_coords"}:
        raise ValueError(f"Unsupported scale mode: {mode}")
    units = request.get("units")
    if units not in UNITS:
        raise ValueError("Known scale requires explicit mm, cm or m units")
    path = (Path(evidence_path).resolve(strict=True) if evidence_path is not None
            else absolute_file(request.get("applied_evidence"), "scale.applied_evidence"))
    evidence_artifact = artifact(path)
    evidence = read_json(path)
    if (evidence.get("status") != "passed" or evidence.get("applied") is not True
            or evidence.get("mode") != mode or evidence.get("units") != units):
        raise ValueError("Scale evidence status, applied flag, mode or units do not match settings")
    if evidence.get("scene_sha256") != scene_artifact["sha256"]:
        raise ValueError("Scale evidence does not match the actual native scene SHA-256")
    transform = evidence["transform"]
    scale = number(transform["scale"], "scale.transform.scale")
    if scale <= 0:
        raise ValueError("Applied native scale must be positive")
    transform = {"scale": scale,
                 "rotation": vector(transform["rotation"], 9, "scale.transform.rotation"),
                 "translation": vector(transform["translation"], 3, "scale.transform.translation")}
    source = evidence["source"]
    if not isinstance(source, dict):
        raise ValueError("Scale evidence source must be an object")
    if mode == "measured_baseline":
        ids = source["ids"]
        if not isinstance(ids, list) or len(ids) != 2:
            raise ValueError("Measured baseline evidence needs two distinct marker IDs")
        ids = [identifier(value, "scale.source.ids") for value in ids]
        if ids[0] == ids[1] or any(value > 31 for value in ids):
            raise ValueError("Measured baseline evidence needs two distinct CCTag3 IDs in 0..31")
        distance = number(source["distance"], "scale.source.distance")
        if distance <= 0:
            raise ValueError("Measured baseline evidence distance must be positive")
        if not source.get("measurement_source"):
            raise ValueError("Measured baseline evidence needs its measurement source")
        for key, expected in (("ids", ids), ("distance", distance),
                              ("measurement_source", source["measurement_source"])):
            if key in request and request[key] != expected:
                raise ValueError(f"Scale evidence {key} differs from requested measurement")
    else:
        if not source.get("coordinate_source"):
            raise ValueError("Marker coordinate evidence needs its coordinate source")
        if ("coordinate_source" in request
                and request["coordinate_source"] != source["coordinate_source"]):
            raise ValueError("Scale evidence coordinate_source differs from requested coordinates")
    verification = evidence["verification"]
    if not isinstance(verification, dict):
        raise ValueError("Scale evidence verification must be an object")
    if mode == 'measured_baseline':
        actual = verify_applied_baseline(read_json(Path(scene_artifact['path'])), ids, distance,
                                         'actual applied scene')
        if not actual['passed']:
            raise ValueError('Applied baseline differs in actual scene; scene SHA alone does not verify scale')
        verification = {**verification, **actual}
    return {"mode": mode, "applied": True, "units": units, "scope": "native_scene",
            "evidence": evidence_artifact, "transform": transform,
            "source": source, "verification": verification,
            "artifact_sha256": evidence.get('artifact_sha256', {})}


def measurements_for_report(settings, scale, path=None):
    """Read the same confirmed-distance owner as prepare, allowing relocation."""
    request = settings.get('scale', {})
    saved_path = request.get('measurements_file')
    if path is None and not saved_path:
        return None
    from capture_measurements import confirmed_scale, load_measurements
    if path is None:
        path = absolute_file(saved_path, 'scale.measurements_file')
    sheet = load_measurements(Path(path).resolve(strict=True))
    expected = request.get('measurements_sha256')
    if saved_path and not expected:
        raise ValueError('Saved measurements need their measurements_sha256 binding')
    if expected and sheet['sha256'] != expected:
        raise ValueError('Measurements differ from saved measurements_sha256')
    if scale['applied']:
        if not expected:
            raise ValueError('Known-scale measurements report requires saved measurements_sha256')
        actual = confirmed_scale(sheet)
        for key, value in actual.items():
            if key == 'measurements_file':
                continue  # Native saved path remains unchanged after local relocation.
            if request.get(key) != value or scale['source'].get(key) != value:
                raise ValueError(f'Measurements {key} differs from applied scale entry')
    return sheet


def verified_export_bindings(settings, scale, inputs):
    """Use the existing export owner, rather than treating report hashes as proof."""
    if scale['applied'] and 'mesh' not in inputs:
        raise ValueError('Known-scale measurements report requires actual --mesh')
    owners = [settings.get('artifact_sha256')]
    if scale['applied']:
        owners.append(scale.get('artifact_sha256'))
    for binding in owners:
        if not binding and not scale['applied']:
            continue  # Unknown-scale legacy inputs remain reportable without mm.
        if not isinstance(binding, dict):
            raise ValueError('Measurements report needs saved export artifact_sha256 binding')
        for key in ('scene', 'cloud', 'mesh'):
            if key in inputs and binding.get(key) != inputs[key]['sha256']:
                raise ValueError(f'Export artifact_sha256 does not match actual {key}')


def pair_report(sheet, scene, scale, tolerance_mm=None):
    """Join confirmed references to native centers; never refit a control pair."""
    if tolerance_mm is not None:
        tolerance_mm = number(tolerance_mm, 'result tolerance_mm')
        if tolerance_mm < 0:
            raise ValueError('Result tolerance_mm must be nonnegative')
    units_to_mm = {'mm': 1., 'cm': 10., 'm': 1000.}
    rows = []
    for source in sheet['rows']:
        row = {**source, 'model_mm': None, 'model_scene_units': None, 'difference_mm': None,
               'absolute_difference_mm': None, 'result_tolerance_mm': tolerance_mm,
               'check_status': 'unverified', 'reason': None}
        ids = source.get('marker_ids')
        if not ids:
            row['reason'] = 'non_marker_reference'
        else:
            try:
                observed = markers_from_scene(scene, ids, 'reported actual scene')
            except MarkerError as error:
                row.update(reason=error.code, detail=str(error))
            except ValueError as error:
                row.update(reason='invalid_marker_data', detail=str(error))
            else:
                row['observed_markers'] = observed['markers']
                row['model_scene_units'] = observed['distance']
                if not scale['applied']:
                    row['reason'] = 'unknown_scale'
                else:
                    row['model_mm'] = observed['distance'] * units_to_mm[scale['units']]
                    if source.get('confirmed_mm') is None:
                        row['reason'] = 'unconfirmed_distance'
                    else:
                        delta = row['model_mm'] - source['confirmed_mm']
                        row.update(difference_mm=delta, absolute_difference_mm=abs(delta))
                        if source['purpose'] == 'scale':
                            row['check_status'] = 'scale_transfer_verified'
                        elif source['purpose'] == 'check':
                            row['check_status'] = ('control_compared' if tolerance_mm is None
                                                   else 'control_within_tolerance' if abs(delta) <= tolerance_mm
                                                   else 'control_outside_tolerance')
                        else:
                            row['reason'] = 'non_control_reference'
        rows.append(row)
    attention = sum(row['check_status'] in {'unverified', 'control_outside_tolerance'} for row in rows)
    return {'input': {'path': str(sheet['path']), 'sha256': sheet['sha256']},
            'status': 'attention_required' if attention else 'compared', 'rows': rows,
            'unverified_rows': sum(r['check_status'] == 'unverified' for r in rows),
            'result_tolerance_mm': tolerance_mm,
            'scope': 'One scale pair checks numeric transfer; control pairs were not fitted. Input uncertainty is separate from result tolerance; no whole-scene physical accuracy claim.'}


def markdown_table(result):
    """Human view of exactly the reported rows, including unverified references."""
    if result.get('status') != 'reported':
        return '# Отчёт расстояний\n\nОшибка: ' + str(result.get('error', 'unknown')) + '\n'
    measurement = result.get('measurements')
    if measurement is None:
        return '# Отчёт расстояний\n\nРабочая форма расстояний не передана.\n'
    def cell(value):
        if value is None:
            return 'неизвестно'
        if isinstance(value, float):
            return f'{value:.6g}'
        return str(value).replace('|', '\\|').replace('\r', ' ').replace('\n', ' ')
    lines = ['# Отчёт расстояний', '',
             'Модель в мм — только после проверенного применения масштаба. Δ = модель − подтверждённая длина.',
             'Численный перенос масштабной пары не подтверждает физическую точность. Контрольные пары не использованы для подгонки.', '',
             '| Пара / роль | План, мм | Подтверждено, мм | Модель, мм | Δ, мм | Неопределённость входа, мм | Допуск результата, мм | Состояние |',
             '|---|---:|---:|---:|---:|---:|---:|---|']
    for row in measurement['rows']:
        role = {'scale': 'масштаб', 'check': 'контроль', 'print_check': 'печать',
                'manual_parameter': 'ручной параметр'}.get(row['purpose'], row['purpose'])
        endpoints = (f"ID{row['marker_ids'][0]} — ID{row['marker_ids'][1]}" if row.get('marker_ids')
                     else f"{row['from_point']} — {row['to_point']}")
        label = f"{row['measurement_id']} ({role}): {endpoints}"
        states = {'unverified': 'Не проверено', 'scale_transfer_verified': 'Масштаб численно применён',
                  'control_compared': 'Контроль: разница показана, допуск не задан',
                  'control_within_tolerance': 'Контроль: в заданном допуске',
                  'control_outside_tolerance': 'Контроль: вне заданного допуска'}
        reasons = {'non_marker_reference': 'нет автоматической 3D-точки для ручной/печатной опоры',
                   'missing_marker': 'метка отсутствует', 'ambiguous_marker': 'повторяющийся ID метки',
                   'insufficient_observations': 'недостаточно наблюдений от восстановленных камер',
                   'invalid_baseline': 'некорректная 3D-база', 'invalid_marker_data': 'некорректные данные метки',
                   'unknown_scale': 'масштаб неизвестен', 'unconfirmed_distance': 'расстояние не подтверждено',
                   'non_control_reference': 'эта строка не является контрольной парой'}
        state = states.get(row['check_status'], row['check_status'])
        if row.get('reason'):
            state += ': ' + reasons.get(row['reason'], row['reason'])
        lines.append('| ' + ' | '.join(cell(v) for v in (label, row.get('planned_mm'),
                     row.get('confirmed_mm'), row['model_mm'], row['difference_mm'],
                     row.get('uncertainty_mm'), row['result_tolerance_mm'], state)) + ' |')
    lines.extend(['', 'Подтверждения из той же рабочей формы:', ''])
    for row in measurement['rows']:
        lines.append(f"- {cell(row['measurement_id'])}: статус {cell(row['status'])}; "
                     f"способ: {cell(row.get('method') or None)}; "
                     f"источник подтверждения: {cell(row.get('confirmation_source') or None)}.")
    lines.extend(['', f"Форма: {cell(measurement['input']['path'])}",
                  f"SHA-256: {measurement['input']['sha256']}"])
    return '\n'.join(lines) + '\n'


def cloud_summary(path):
    # Keep geometry dependencies out of source/receipt validation and --help.
    import numpy as np
    import open3d as o3d

    if Path(path).suffix.lower() != ".ply":
        raise ValueError("The dense cloud report requires the native exported PLY")
    cloud = o3d.io.read_point_cloud(str(path), remove_nan_points=False,
                                    remove_infinite_points=False, print_progress=False)
    points = np.asarray(cloud.points)
    finite = np.isfinite(points).all(axis=1)
    count = int(finite.sum())
    if count == 0:
        raise ValueError("Dense PLY contains no finite points")
    # The actual loaded point cloud is the geometry owner; no JSON bbox is trusted.
    valid_cloud = cloud.select_by_index(np.flatnonzero(finite).tolist())
    bounds = valid_cloud.get_axis_aligned_bounding_box()
    return {"point_count": len(points), "finite_point_count": count,
            "nonfinite_point_count": int(len(points) - count),
            "bbox_min": bounds.min_bound.tolist(), "bbox_max": bounds.max_bound.tolist(),
            "extent": bounds.get_extent().tolist(),
            "coordinate_frame": "native PLY; cloud lineage is recorded by the native graph"}


def mesh_summary(path, cloud, scale):
    """Read the separate raw Meshing surface; preserve the source mesh bytes."""
    import numpy as np
    import open3d as o3d

    path = Path(path).resolve(strict=True)
    # Open3D's OBJ reader on Windows can fail on an absolute Unicode path.
    # Reading its native ASCII basename from the owning directory also preserves
    # relative material references. This CLI is synchronous; always restore cwd.
    previous = Path.cwd()
    try:
        os.chdir(path.parent)
        mesh = o3d.io.read_triangle_mesh(path.name, enable_post_processing=False)
    finally:
        os.chdir(previous)
    vertices, faces = np.asarray(mesh.vertices), np.asarray(mesh.triangles)
    if not len(vertices) or not len(faces):
        raise ValueError('Mesh has no readable vertices/triangles; a point cloud is not a mesh')
    if not np.isfinite(vertices).all():
        raise ValueError('Mesh contains nonfinite vertex coordinates')
    if faces.min() < 0 or faces.max() >= len(vertices):
        raise ValueError('Mesh contains invalid triangle vertex indices')
    result = {'vertex_count': len(vertices), 'triangle_count': len(faces),
              'finite_vertex_count': len(vertices), 'invalid_index_count': 0,
              'bbox_min': vertices.min(axis=0).tolist(), 'bbox_max': vertices.max(axis=0).tolist(),
              'units': scale['units'], 'processing': 'raw native Meshing output; no filtering/smoothing',
              'count_scope': 'Open3D loaded mesh; importer can merge coincident OBJ vertices',
              'coordinate_frame': 'as stored by native mesh writer; distinct from dense PLY axes'}
    if path.suffix.lower() == '.obj':
        # Pinned Mesh::save writes (x,-y,-z), whereas sfmDataIO PLY writes X.
        # This is a fixed rotation from the native contract, not a fitted alignment.
        aligned = vertices * np.array([1., -1., -1.])
        lower, upper = aligned.min(axis=0), aligned.max(axis=0)
        result['mesh_to_cloud'] = {
            'rotation': [[1., 0., 0.], [0., -1., 0.], [0., 0., -1.]],
            'translation': [0., 0., 0.], 'scale': 1.,
            'basis': 'AliceVision d012d055 Mesh::save OBJ / sfmDataIO PLY',
            'applied_to_file': False, 'bbox_min_in_cloud_frame': lower.tolist(),
            'bbox_max_in_cloud_frame': upper.tolist(),
            'bbox_delta_max': float(max(np.max(np.abs(lower - cloud['bbox_min'])),
                                        np.max(np.abs(upper - cloud['bbox_max'])))),
            'scope': 'coordinate convention and observed bounds; not object coverage or physical accuracy'}
    else:
        result['mesh_to_cloud'] = {'status': 'unverified_for_this_format', 'applied_to_file': False}
    return result


def report(scene_path, cloud_path, settings_path, manifest_path=None, scale_evidence_path=None, mesh_path=None,
           measurements_path=None, tolerance_mm=None):
    if tolerance_mm is not None and number(tolerance_mm, 'result tolerance_mm') < 0:
        raise ValueError('Result tolerance_mm must be nonnegative')
    inputs = {"scene": artifact(scene_path), "cloud": artifact(cloud_path),
              "settings": artifact(settings_path)}
    settings = read_json(settings_path)
    manifest = (Path(manifest_path).resolve(strict=True) if manifest_path is not None
                else absolute_file(settings["input_manifest"], "settings.input_manifest"))
    inputs["input_manifest"] = artifact(manifest)
    if ("input_manifest_sha256" in settings
            and settings["input_manifest_sha256"] != inputs["input_manifest"]["sha256"]):
        raise ValueError("Input manifest does not match settings.input_manifest_sha256")
    # Validate scale before importing Open3D or reading the potentially large cloud.
    scale = verified_scale(settings, inputs["scene"], scale_evidence_path)
    actual_scene = read_json(scene_path)
    sheet = measurements_for_report(settings, scale, measurements_path)
    if mesh_path is not None:
        inputs['mesh'] = artifact(mesh_path)
    if sheet is not None:
        inputs['measurements'] = artifact(Path(sheet['path']))
        verified_export_bindings(settings, scale, inputs)
    scene = scene_summary(actual_scene)
    result = {"schema_version": 1, "status": "reported",
              "runtime": settings.get("runtime", {}), "inputs": inputs,
              "scene": scene, "scale": scale, "cloud": cloud_summary(cloud_path)}
    if mesh_path is not None:
        binding = settings.get('mesh_export')
        if binding and binding['sha256'] != inputs['mesh']['sha256']:
            raise ValueError('Mesh differs from saved native export SHA-256')
        result['mesh'] = mesh_summary(mesh_path, result['cloud'], scale)
    if sheet is not None:
        result['measurements'] = pair_report(sheet, actual_scene, scale, tolerance_mm)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path, required=True,
                        help="Native canonical JSON with views/poses/intrinsics/CCTag3 observations")
    parser.add_argument("--cloud", type=Path, required=True, help="Native dense PLY exported after backup")
    parser.add_argument("--mesh", type=Path, help="Separate raw native Meshing outputMesh (OBJ qualified)")
    parser.add_argument("--settings", type=Path, required=True, help="Effective settings and scale evidence paths")
    parser.add_argument("--manifest", type=Path,
                        help="Explicit local copy of input manifest; preserve its settings SHA-256 binding")
    parser.add_argument("--scale-evidence", type=Path,
                        help="Explicit local copy of applied scale evidence; preserve scene and scale binding")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument('--measurements', type=Path, help='Same measurements CSV, optionally relocated with its saved SHA binding')
    parser.add_argument('--table', type=Path, help='Optional readable Markdown table of every measurement row')
    parser.add_argument('--tolerance-mm', type=float, help='Optional result tolerance, separate from input uncertainty/numerical transfer')
    args = parser.parse_args()
    output = args.output.resolve()
    checkout = Path(__file__).resolve().parents[1]
    table = args.table.resolve() if args.table else None
    outputs = {output} | ({table} if table else set())
    if any(p == checkout or checkout in p.parents for p in outputs):
        parser.error("Write reconstruction evidence outside the source checkout")
    protected = {args.scene.resolve(), args.cloud.resolve(), args.settings.resolve()}
    protected.update(path.resolve() for path in (args.manifest, args.scale_evidence, args.mesh, args.measurements) if path is not None)
    if outputs & protected or table == output:
        parser.error("Output must differ from every input and scale evidence artifact")
    try:
        settings = read_json(args.settings)
        for value in (settings.get("input_manifest"), settings.get("scale", {}).get("applied_evidence"),
                      settings.get('scale', {}).get('measurements_file')):
            if isinstance(value, str) and value:
                protected.add(Path(value).resolve())
        if outputs & protected:
            parser.error("Output must differ from every input and scale evidence artifact")
        result = report(args.scene, args.cloud, args.settings, args.manifest, args.scale_evidence, args.mesh,
                        args.measurements, args.tolerance_mm)
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError, OSError, RuntimeError) as error:
        result = {"schema_version": 1, "status": "error", "error": str(error)}
    result["output_file"] = str(output)
    text = json.dumps(result, indent=2, allow_nan=False) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    if json.loads(output.read_text(encoding="utf-8")) != result:
        raise ValueError("Report JSON readback differs")
    if table is not None:
        table.parent.mkdir(parents=True, exist_ok=True)
        table.write_text(markdown_table(result), encoding='utf-8')
    print(text, end="")
    return 0 if result["status"] == "reported" else 1


if __name__ == "__main__":
    sys.exit(main())

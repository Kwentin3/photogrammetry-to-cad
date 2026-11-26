"""Native-scene and actual PLY contracts for reconstruction diagnostics."""

from copy import deepcopy
import csv
import json
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
try:
    import check_marker_scale as checker
    import reconstruction_report as reporting
    import capture_measurements as measurements
finally:
    sys.path.pop(0)


def scene_fixture():
    return {
        "intrinsics": [{"intrinsicId": "10"}],
        "poses": [{"poseId": str(value), "pose": {"transform": {
            "rotation": [1, 0, 0, 0, 1, 0, 0, 0, 1], "center": [value, 0, 0]}}}
                  for value in (20, 21)],
        "views": [{"viewId": str(value), "poseId": str(pose), "intrinsicId": "10"}
                  for value, pose in ((30, 20), (31, 21), (32, 999))],
        "structure": [
            {"landmarkId": "40", "descType": "cctag3", "color": [2, 0, 0], "X": [0, 0, 0],
             "observations": [{"observationId": str(view)} for view in (30, 31, 32)]},
            {"landmarkId": "41", "descType": "cctag3", "color": [5, 0, 0], "X": [2, 0, 0],
             "observations": [{"observationId": str(view)} for view in (30, 31)]},
        ],
    }


class ReconstructionReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="reconstruction-report-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scene = self.root / "markers.json"
        self.cloud = self.root / "dense.ply"
        self.settings = self.root / "effective-settings.json"
        self.manifest = self.root / "input-manifest.json"
        self.evidence = self.root / "applied-scale.json"
        self.data = scene_fixture()
        self.write(self.scene, self.data)
        self.write(self.manifest, {"images": []})
        self.config = {"runtime": {"meshroom_commit": "test-pin"},
                       "input_manifest": str(self.manifest),
                       "scale": {"mode": "unknown"}}
        self.write(self.settings, self.config)
        # Actual binary PLY: finite bounds come from native loaded geometry.
        # RPly rejects ASCII inf and can return a partially filled cloud.
        header = ("ply\nformat binary_little_endian 1.0\nelement vertex 4\nproperty float x\n"
                  "property float y\nproperty float z\nend_header\n").encode("ascii")
        points = [(1, 2, 3), (4, 6, 8), (float("nan"), 0, 0), (0, float("inf"), 0)]
        self.cloud.write_bytes(header + b"".join(struct.pack("<fff", *point) for point in points))

    def write(self, path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def apply_scale_evidence(self):
        self.config["scale"] = {"mode": "measured_baseline", "units": "mm",
                                "ids": [2, 5], "distance": 2.0,
                                "applied_evidence": str(self.evidence)}
        evidence = {"status": "passed", "applied": True, "mode": "measured_baseline",
                    "units": "mm", "scene_sha256": reporting.artifact(self.scene)["sha256"],
                    "transform": {"scale": 2.0, "rotation": reporting.IDENTITY.copy(),
                                  "translation": [0, 0, 0]},
                    "source": {"ids": [2, 5], "distance": 2.0,
                               "measurement_source": "test fixture receipt"},
                    "verification": {"numeric_transfer": "test fixture"}}
        self.write(self.evidence, evidence)
        self.write(self.settings, self.config)
        return evidence

    def test_registered_views_duplicate_ids_and_unposed_observations(self):
        duplicate = deepcopy(self.data["structure"][0])
        duplicate["landmarkId"] = "42"
        duplicate["observations"] = [{"observationId": "32"}]
        self.data["structure"].append(duplicate)
        summary = reporting.scene_summary(self.data)
        self.assertEqual(summary["registered_view_count"], 2)
        self.assertEqual(summary["registered_fraction"], 2 / 3)
        marker = summary["markers"][0]
        self.assertEqual(marker["id"], 2)
        self.assertTrue(marker["ambiguous"])
        self.assertEqual([item["observation_count"] for item in marker["landmarks"]], [3, 1])
        self.assertEqual([item["posed_observation_count"] for item in marker["landmarks"]], [2, 0])
        with self.assertRaisesRegex(ValueError, "Duplicate cctag3 marker ID"):
            checker.markers_from_scene(self.data, [2, 5], "strict")

    def test_strict_scale_checker_keeps_unique_posed_baseline_behavior(self):
        checked = checker.markers_from_scene(self.data, [2, 5], "strict")
        self.assertEqual(checked["distance"], 2.0)
        self.assertEqual(checked["markers"][0]["observation_count"], 3)
        self.assertEqual(checked["markers"][0]["reconstructed_view_count"], 2)
        self.data["poses"].pop()
        with self.assertRaisesRegex(ValueError, "at least two reconstructed views"):
            checker.markers_from_scene(self.data, [2, 5], "strict")

    def test_unknown_scale_real_ply_bounds_and_file_hashes(self):
        result = reporting.report(self.scene, self.cloud, self.settings)
        self.assertEqual(result["scale"]["mode"], "unknown")
        self.assertEqual(result["scale"]["units"], "unknown")
        self.assertFalse(result["scale"]["applied"])
        self.assertEqual(result["cloud"]["point_count"], 4)
        self.assertEqual(result["cloud"]["finite_point_count"], 2)
        self.assertEqual(result["cloud"]["nonfinite_point_count"], 2)
        self.assertEqual(result["cloud"]["bbox_min"], [1, 2, 3])
        self.assertEqual(result["cloud"]["bbox_max"], [4, 6, 8])
        self.assertEqual(result["inputs"]["scene"]["sha256"], reporting.artifact(self.scene)["sha256"])
        self.assertEqual(result["inputs"]["input_manifest"]["path"], str(self.manifest.resolve()))

    def test_valid_bound_scale_receipt_and_stale_actual_scene_rejected(self):
        self.apply_scale_evidence()
        actual = reporting.verified_scale(self.config, reporting.artifact(self.scene))
        self.assertEqual((actual["applied"], actual["units"], actual["scope"]), (True, "mm", "native_scene"))
        # Mutate the real owner artifact, not a checksum string in the evidence.
        self.data["structure"][0]["X"][0] = 0.25
        self.write(self.scene, self.data)
        with self.assertRaisesRegex(ValueError, "native scene SHA-256"):
            reporting.verified_scale(self.config, reporting.artifact(self.scene))

    def test_missing_mismatched_and_nonfinite_evidence_fail(self):
        with self.assertRaises(ValueError):
            reporting.verified_scale({"scale": {"mode": "measured_baseline", "units": "mm"}},
                                     reporting.artifact(self.scene))
        evidence = self.apply_scale_evidence()
        for key, value in (("units", "cm"), ("applied", False)):
            wrong = deepcopy(evidence)
            wrong[key] = value
            self.write(self.evidence, wrong)
            with self.assertRaisesRegex(ValueError, "do not match"):
                reporting.verified_scale(self.config, reporting.artifact(self.scene))
        evidence["transform"]["scale"] = float("nan")
        self.write(self.evidence, evidence)
        with self.assertRaisesRegex(ValueError, "Non-finite"):
            reporting.verified_scale(self.config, reporting.artifact(self.scene))

    def cli(self, output, *extra):
        command = [sys.executable, str(SCRIPTS / "reconstruction_report.py"),
                   "--scene", str(self.scene), "--cloud", str(self.cloud),
                   "--settings", str(self.settings), "--output", str(output), *extra]
        return subprocess.run(command, capture_output=True, text=True, timeout=60)

    def test_cli_local_overrides_preserve_linux_settings_and_real_inputs(self):
        self.apply_scale_evidence()
        self.config["input_manifest"] = "/root/original-run/input-manifest.json"
        self.config["input_manifest_sha256"] = reporting.artifact(self.manifest)["sha256"]
        self.config["scale"]["applied_evidence"] = "/root/original-run/scale-evidence.json"
        self.config["scale"]["measurement_source"] = "test fixture receipt"
        self.write(self.settings, self.config)
        originals = {path: path.read_bytes() for path in (
            self.scene, self.cloud, self.settings, self.manifest, self.evidence)}
        output = self.root / "relocated-report.json"
        completed = self.cli(output, "--manifest", str(self.manifest),
                             "--scale-evidence", str(self.evidence))
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        result = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "reported")
        self.assertEqual(result["inputs"]["settings"], reporting.artifact(self.settings))
        self.assertEqual(result["inputs"]["input_manifest"], reporting.artifact(self.manifest))
        self.assertEqual(result["scale"]["evidence"], reporting.artifact(self.evidence))
        self.assertEqual(result["scale"]["source"]["measurement_source"], "test fixture receipt")
        self.assertEqual(result["cloud"]["finite_point_count"], 2)
        self.assertEqual(result["cloud"]["bbox_min"], [1, 2, 3])
        self.assertEqual(result["cloud"]["bbox_max"], [4, 6, 8])
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original, str(path))

    def test_cli_never_overwrites_explicit_local_override_inputs(self):
        self.apply_scale_evidence()
        local_manifest = self.root / "relocated-manifest.json"
        local_manifest.write_bytes(self.manifest.read_bytes())
        local_evidence = self.root / "relocated-scale.json"
        local_evidence.write_bytes(self.evidence.read_bytes())
        # The explicit inputs must be protected even before settings can be read.
        self.settings.write_text("invalid JSON", encoding="utf-8")
        for path in (local_manifest, local_evidence):
            with self.subTest(path=path.name):
                original = path.read_bytes()
                completed = self.cli(path, "--manifest", str(local_manifest),
                                     "--scale-evidence", str(local_evidence))
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("Output must differ", completed.stderr)
                self.assertEqual(path.read_bytes(), original)

    def test_local_manifest_override_keeps_saved_hash_binding(self):
        self.config["input_manifest"] = "/root/original-run/input-manifest.json"
        self.config["input_manifest_sha256"] = reporting.artifact(self.manifest)["sha256"]
        self.write(self.settings, self.config)
        self.write(self.manifest, {"images": ["foreign-image.jpg"]})
        with self.assertRaisesRegex(ValueError, "settings.input_manifest_sha256"):
            reporting.report(self.scene, self.cloud, self.settings, self.manifest)

    def test_local_evidence_override_keeps_scene_scale_and_source_bindings(self):
        evidence = self.apply_scale_evidence()
        self.config["scale"]["applied_evidence"] = "/root/original-run/scale-evidence.json"
        self.config["scale"]["measurement_source"] = "test fixture receipt"
        mutations = (
            ("mode", "marker_coords", "do not match"),
            ("units", "cm", "do not match"),
            ("scene_sha256", "foreign-scene", "native scene SHA-256"),
            ("source", {**evidence["source"], "ids": [2, 6]}, "ids differs"),
            ("source", {**evidence["source"], "distance": 3}, "distance differs"),
            ("source", {**evidence["source"], "measurement_source": "foreign receipt"},
             "measurement_source differs"),
        )
        for key, value, error in mutations:
            with self.subTest(key=key, value=value):
                altered = deepcopy(evidence)
                altered[key] = value
                self.write(self.evidence, altered)
                with self.assertRaisesRegex(ValueError, error):
                    reporting.verified_scale(self.config, reporting.artifact(self.scene), self.evidence)
        with self.assertRaisesRegex(ValueError, "Unknown scale contradicts"):
            reporting.verified_scale({"scale": {"mode": "unknown"}},
                                     reporting.artifact(self.scene), self.evidence)

    def test_cli_never_overwrites_scene_even_if_settings_are_invalid(self):
        original = self.scene.read_bytes()
        self.settings.write_text("invalid JSON", encoding="utf-8")
        command = [sys.executable, str(SCRIPTS / "reconstruction_report.py"),
                   "--scene", str(self.scene), "--cloud", str(self.cloud),
                   "--settings", str(self.settings), "--output", str(self.scene)]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Output must differ", completed.stderr)
        self.assertEqual(self.scene.read_bytes(), original)

    def measurement_sheet(self):
        path = self.root / 'measurements.csv'
        base = dict.fromkeys(measurements.FIELDS, '')
        rows = []
        for row_id, purpose, a, b, planned, actual, status in [
            ('base', 'scale', 'cctag3:2:center', 'cctag3:5:center', '2', '', 'confirmed_nominal'),
            ('control', 'check', 'cctag3:2:center', 'cctag3:7:center', '3', '2.5', 'measured'),
            ('missing', 'check', 'cctag3:2:center', 'cctag3:9:center', '', '9', 'measured'),
            ('weak', 'check', 'cctag3:2:center', 'cctag3:8:center', '', '1', 'measured'),
            ('duplicate', 'check', 'cctag3:2:center', 'cctag3:6:center', '', '4', 'measured'),
            ('plan', 'check', 'cctag3:5:center', 'cctag3:7:center', '17', '', 'planned'),
            ('print', 'print_check', 'paper:left', 'paper:right', '100', '', 'planned'),
            ('manual', 'manual_parameter', 'object:left', 'object:right', '', '4', 'measured'),
        ]:
            rows.append({**base, 'measurement_id': row_id, 'purpose': purpose,
                         'from_point': a, 'to_point': b, 'planned_mm': planned,
                         'measured_mm': actual, 'status': status, 'method': 'checked during installation',
                         'confirmation_source': 'operator reply fixture'})
        with path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=measurements.FIELDS)
            writer.writeheader(); writer.writerows(rows)
        for mid, center, observations in [(7, [0, 3, 0], [30, 31]),
                                           (8, [0, 0, 1], [30, 32]),
                                           (6, [4, 0, 0], [30, 31]),
                                           (6, [0, 4, 0], [30, 31])]:
            self.data['structure'].append({'landmarkId': str(100 + len(self.data['structure'])),
                'descType': 'cctag3', 'color': [mid, 0, 0], 'X': center,
                'observations': [{'observationId': str(v)} for v in observations]})
        self.write(self.scene, self.data)
        return path

    def bind_measurement_export(self, path):
        evidence = self.apply_scale_evidence()
        request = measurements.confirmed_scale(measurements.load_measurements(path))
        self.config['scale'] = {**request, 'applied_evidence': str(self.evidence)}
        evidence['source'] = request
        self.mesh = self.root / 'mesh.obj'
        self.mesh.write_bytes(b'v 0 0 0\nv 1 0 0\nv 0 -1 0\nf 1 2 3\n')
        binding = {key: reporting.artifact(value)['sha256']
                   for key, value in [('scene', self.scene), ('cloud', self.cloud), ('mesh', self.mesh)]}
        self.config['artifact_sha256'] = binding
        self.config['mesh_export'] = {'sha256': binding['mesh']}
        evidence['artifact_sha256'] = binding.copy()
        self.write(self.settings, self.config)
        self.write(self.evidence, evidence)

    def test_applied_baseline_checks_actual_centers_even_with_fresh_receipt_hash(self):
        evidence = self.apply_scale_evidence()
        self.data['structure'][1]['X'] = [4, 0, 0]
        numeric = checker.verify_applied_baseline(self.data, [2, 5], 2., 'changed scene')
        self.assertFalse(numeric['passed'])
        self.assertEqual(numeric['baseline_error'], 2.)
        self.write(self.scene, self.data)
        evidence['scene_sha256'] = reporting.artifact(self.scene)['sha256']
        self.write(self.evidence, evidence)
        with self.assertRaisesRegex(ValueError, 'Applied baseline differs in actual scene'):
            reporting.verified_scale(self.config, reporting.artifact(self.scene))

    def test_all_measurement_rows_and_independent_control_difference(self):
        path = self.measurement_sheet()
        self.bind_measurement_export(path)
        result = reporting.report(self.scene, self.cloud, self.settings, mesh_path=self.mesh, tolerance_mm=.1)
        rows = {row['measurement_id']: row for row in result['measurements']['rows']}
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows['base']['check_status'], 'scale_transfer_verified')
        self.assertEqual(rows['base']['model_mm'], 2.)
        self.assertEqual(rows['control']['model_mm'], 3.)
        self.assertEqual(rows['control']['difference_mm'], .5)
        self.assertEqual(rows['control']['check_status'], 'control_outside_tolerance')
        self.assertIsNone(rows['control']['uncertainty_mm'])
        for key, reason in [('missing', 'missing_marker'), ('weak', 'insufficient_observations'),
                            ('duplicate', 'ambiguous_marker'), ('plan', 'unconfirmed_distance'),
                            ('print', 'non_marker_reference'), ('manual', 'non_marker_reference')]:
            self.assertEqual(rows[key]['check_status'], 'unverified')
            self.assertEqual(rows[key]['reason'], reason)
        self.assertEqual(result['measurements']['status'], 'attention_required')
        self.assertEqual(result['scale']['transform']['scale'], 2.)
        table = reporting.markdown_table(result)
        for key in rows:
            self.assertIn(key + ' (', table)
        self.assertIn('неизвестно', table)

    def test_unknown_scale_keeps_csv_visible_without_model_mm(self):
        path = self.measurement_sheet()
        result = reporting.report(self.scene, self.cloud, self.settings, measurements_path=path)
        self.assertEqual(result['scale']['units'], 'unknown')
        self.assertEqual(len(result['measurements']['rows']), 8)
        for row in result['measurements']['rows']:
            self.assertIsNone(row['model_mm'])
            self.assertIsNone(row['difference_mm'])
            self.assertEqual(row['check_status'], 'unverified')
        base = result['measurements']['rows'][0]
        self.assertEqual(base['confirmed_mm'], 2.)
        self.assertEqual(base['reason'], 'unknown_scale')

    def test_relocated_csv_hash_and_scale_semantics_remain_bound(self):
        path = self.measurement_sheet()
        self.bind_measurement_export(path)
        relocated = self.root / 'relocated.csv'
        relocated.write_bytes(path.read_bytes())
        self.config['scale']['measurements_file'] = '/root/original-run/measurements.csv'
        self.write(self.settings, self.config)
        result = reporting.report(self.scene, self.cloud, self.settings, measurements_path=relocated, mesh_path=self.mesh)
        self.assertEqual(result['inputs']['measurements']['path'], str(relocated.resolve()))
        relocated.write_bytes(relocated.read_bytes().replace(b'2.5', b'2.6'))
        with self.assertRaisesRegex(ValueError, 'measurements_sha256'):
            reporting.report(self.scene, self.cloud, self.settings, measurements_path=relocated)
        relocated.write_bytes(path.read_bytes())
        self.config['scale']['measurement_status'] = 'measured'
        evidence = json.loads(self.evidence.read_text(encoding='utf-8'))
        evidence['source']['measurement_status'] = 'measured'
        self.write(self.settings, self.config); self.write(self.evidence, evidence)
        with self.assertRaisesRegex(ValueError, 'measurement_status differs'):
            reporting.report(self.scene, self.cloud, self.settings, measurements_path=relocated)

    def test_known_csv_rejects_foreign_cloud_mesh_and_missing_export_owner(self):
        path = self.measurement_sheet()
        self.bind_measurement_export(path)
        original = self.cloud.read_bytes()
        self.cloud.write_bytes(original + b'\n')
        with self.assertRaisesRegex(ValueError, 'artifact_sha256.*cloud'):
            reporting.report(self.scene, self.cloud, self.settings, mesh_path=self.mesh)
        self.cloud.write_bytes(original)
        self.mesh.write_bytes(self.mesh.read_bytes() + b'# changed\n')
        with self.assertRaisesRegex(ValueError, 'artifact_sha256.*mesh'):
            reporting.report(self.scene, self.cloud, self.settings, mesh_path=self.mesh)
        del self.config['artifact_sha256']
        self.write(self.settings, self.config)
        with self.assertRaisesRegex(ValueError, 'saved export artifact_sha256'):
            reporting.report(self.scene, self.cloud, self.settings, mesh_path=self.mesh)

    def test_cli_table_uses_actual_rows_and_protects_csv_input(self):
        path = self.measurement_sheet()
        self.bind_measurement_export(path)
        table = self.root / 'report.md'
        completed = self.cli(self.root / 'report.json', '--table', str(table), '--tolerance-mm', '.1', '--mesh', str(self.mesh))
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        self.assertIn('Контроль: вне заданного допуска', table.read_text(encoding='utf-8'))
        before = path.read_bytes()
        completed = self.cli(self.root / 'protected-report.json', '--measurements', str(path), '--table', str(path))
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn('Output must differ', completed.stderr)
        self.assertEqual(path.read_bytes(), before)

    def test_actual_baseline_and_result_tolerance_are_not_nominal_or_input_uncertainty(self):
        path = self.measurement_sheet()
        with path.open(encoding='utf-8', newline='') as stream:
            rows = list(csv.DictReader(stream))
        rows[0].update(status='measured', measured_mm='2.5')  # Planned2 is not used.
        rows[1]['uncertainty_mm'] = '99'
        with path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=measurements.FIELDS)
            writer.writeheader(); writer.writerows(rows)
        self.data['structure'][1]['X'] = [2.5, 0, 0]
        self.write(self.scene, self.data)
        self.bind_measurement_export(path)
        for tolerance, status in [(None, 'control_compared'), (.1, 'control_outside_tolerance'),
                                   (.6, 'control_within_tolerance')]:
            result = reporting.report(self.scene, self.cloud, self.settings, tolerance_mm=tolerance, mesh_path=self.mesh)
            self.assertEqual(result['scale']['source']['distance'], 2.5)
            self.assertEqual(result['measurements']['rows'][0]['model_mm'], 2.5)
            control = result['measurements']['rows'][1]
            self.assertEqual(control['uncertainty_mm'], 99.)
            self.assertEqual(control['difference_mm'], .5)
            self.assertEqual(control['check_status'], status)
        for bad in (-1., float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                reporting.report(self.scene, self.cloud, self.settings, tolerance_mm=bad)

    def test_known_csv_requires_mesh_and_both_complete_export_bindings(self):
        path = self.measurement_sheet()
        self.bind_measurement_export(path)
        with self.assertRaisesRegex(ValueError, 'requires actual --mesh'):
            reporting.report(self.scene, self.cloud, self.settings)
        for owner in ('settings', 'evidence'):
            with self.subTest(owner=owner):
                settings = deepcopy(self.config)
                evidence = json.loads(self.evidence.read_text(encoding='utf-8'))
                target = settings if owner == 'settings' else evidence
                del target['artifact_sha256']['mesh']
                self.write(self.settings, settings); self.write(self.evidence, evidence)
                with self.assertRaisesRegex(ValueError, 'artifact_sha256.*mesh'):
                    reporting.report(self.scene, self.cloud, self.settings, mesh_path=self.mesh)
                self.write(self.settings, self.config)
                self.bind_measurement_export(path)
        result = reporting.report(self.scene, self.cloud, self.settings, mesh_path=self.mesh)
        table = reporting.markdown_table(result)
        self.assertIn('статус confirmed_nominal', table)
        self.assertIn('checked during installation', table)
        self.assertIn('operator reply fixture', table)


if __name__ == "__main__":
    unittest.main()

"""Native-scene and actual PLY contracts for reconstruction diagnostics."""

from copy import deepcopy
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


if __name__ == "__main__":
    unittest.main()

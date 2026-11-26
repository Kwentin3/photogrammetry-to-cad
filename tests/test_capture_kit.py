"""Native file-contract and delivered print-kit checks; no pretend detector.

Full digital ID acceptance is the native Linux CI, not these parser checks.
"""

import base64
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from capture_measurements import FIELDS, confirmed_scale, load_measurements, scale_row
spec = importlib.util.spec_from_file_location("check_capture_kit", ROOT / "scripts/check_capture_kit.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

# Actual native AliceVision output retained from Goal #4, image 1286808212,
# synthetic-markers FeatureExtraction/b86d706d1d9e4ce9e87feac94ad683eb004525e9.
# Count/one-hot storage also matches official v3.3 Descriptor.hpp/CCTAG source.
NATIVE_DESCRIPTORS = base64.b64decode(
    "AgAAAAAAAAD/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)
NATIVE_FEATURES = "511.134 441.626 41.6458 0\n682.664 457.109 39.1811 0\n"


class NativeRegionContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="cctag-contract-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.feat, self.desc = self.root / "test.feat", self.root / "test.desc"
        self.feat.write_text(NATIVE_FEATURES, encoding="utf-8")
        self.desc.write_bytes(NATIVE_DESCRIPTORS)

    def test_reads_actual_native_file_and_zero_based_ids(self):
        result = checker.read_native_regions(self.feat, self.desc)
        self.assertEqual([region["id"] for region in result], [0, 1])
        self.assertAlmostEqual(result[0]["x"], 511.134)
        self.assertAlmostEqual(result[1]["radius"], 39.1811)

    def test_truncated_native_file_is_rejected(self):
        self.desc.write_bytes(NATIVE_DESCRIPTORS[:-1])
        with self.assertRaisesRegex(ValueError, "count/length"):
            checker.read_native_regions(self.feat, self.desc)

    def test_extra_active_byte_is_rejected(self):
        modified = bytearray(NATIVE_DESCRIPTORS)
        modified[8 + 2] = 255
        self.desc.write_bytes(modified)
        with self.assertRaisesRegex(ValueError, "one-hot"):
            checker.read_native_regions(self.feat, self.desc)

    def test_wrong_native_id_and_wrong_center_fail_acceptance(self):
        region = [{"id": 0, "x": 20, "y": 30}]
        with self.assertRaisesRegex(ValueError, "native ID 1"):
            checker.check_expected(region, 1, [20, 30])
        with self.assertRaisesRegex(ValueError, "center error"):
            checker.check_expected(region, 0, [40, 30])
        self.assertEqual(checker.check_expected(region, 0, [20, 30]), 0)


class DeliveredKitTests(unittest.TestCase):
    def test_measurements_use_existing_contract_and_no_invented_lengths(self):
        kit = ROOT / "templates/capture-kit"
        with (ROOT / "templates/measurements.csv").open(encoding="utf-8", newline="") as stream:
            canonical_fields = next(csv.reader(stream))
        with (kit / "measurements.csv").open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            self.assertEqual(reader.fieldnames, canonical_fields)
            rows = list(reader)
        self.assertTrue(all(not row["measured_mm"] for row in rows))
        self.assertTrue(all(row["status"] in {"planned", "unknown"} for row in rows))
        self.assertTrue(all(not row["confirmation_source"] for row in rows))
        self.assertEqual(sum(row["purpose"] == "scale" for row in rows), 1)
        self.assertEqual(sum(row["measurement_id"].startswith("object_check_") for row in rows), 2)
        self.assertEqual(sum(row["purpose"] == "print_check" for row in rows), 8)
        manifest = json.loads((kit / "manifest.json").read_text(encoding="utf-8"))
        for name, field in [("cctag3-print.pdf", "pdf_sha256"), ("measurements.csv", "measurements_sha256"),
                            ("placement.txt", "placement_sha256"), ("placement-plan.csv", "placement_plan_sha256")]:
            self.assertEqual(hashlib.sha256((kit / name).read_bytes()).hexdigest(), manifest[field])
            if name.endswith((".csv", ".txt")):
                self.assertNotIn(b"\r", (kit / name).read_bytes(), "Published kit hashes must survive Linux checkout")
        sheet = load_measurements(kit / "measurements.csv")
        self.assertIsNone(scale_row(sheet)["confirmed_mm"])
        with self.assertRaisesRegex(ValueError, "not confirmed"):
            confirmed_scale(sheet)

    @unittest.skipUnless(importlib.util.find_spec("fitz"), "Optional PDF checks require requirements-capture-kit.txt")
    def test_final_pdf_has_actual_paper_and_marker_dimensions(self):
        import fitz

        kit = ROOT / "templates/capture-kit"
        manifest = json.loads((kit / "manifest.json").read_text(encoding="utf-8"))
        with fitz.open(kit / "cctag3-print.pdf") as document:
            self.assertEqual(len(document), 4)
            for page, expected in zip(document, manifest["pages"]):
                self.assertIn(f"CCTag3 - ID {expected['native_id']}", page.get_text().splitlines())
                self.assertAlmostEqual(page.rect.width / 72 * 25.4, 210, places=3)
                self.assertAlmostEqual(page.rect.height / 72 * 25.4, 297, places=3)
                circles = [path["rect"] for path in page.get_drawings()
                           if any(item[0] == "c" for item in path["items"])]
                outer = max(circles, key=lambda rect: rect.width)
                self.assertAlmostEqual(outer.width / 72 * 25.4, 100, places=3)
                self.assertAlmostEqual(outer.height / 72 * 25.4, 100, places=3)

    @unittest.skipUnless(importlib.util.find_spec("fitz"), "Optional PDF checks require requirements-capture-kit.txt")
    def test_rejects_id_10_header_when_manifest_and_rings_have_id_1(self):
        import fitz

        original = ROOT / "templates/capture-kit"
        with tempfile.TemporaryDirectory(prefix="cctag-printed-id-") as temporary:
            root = Path(temporary)
            kit = root / "kit"
            shutil.copytree(original, kit)
            with fitz.open(original / "cctag3-print.pdf") as document:
                page = document[1]
                title = page.search_for("CCTag3 - ID 1")[0]
                page.add_redact_annot(title, fill=(1, 1, 1))
                page.apply_redactions()
                page.insert_text((title.x0, title.y1 - 4), "CCTag3 - ID 10", fontsize=20)
                self.assertIn("CCTag3 - ID 10", page.get_text().splitlines())
                self.assertNotIn("CCTag3 - ID 1", page.get_text().splitlines())
                document.save(kit / "cctag3-print.pdf")
            manifest = json.loads((original / "manifest.json").read_text(encoding="utf-8"))
            manifest["pdf_sha256"] = checker.sha256(kit / "cctag3-print.pdf")
            (kit / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            rejected_output = root / "rejected"
            rejected_output.mkdir()
            with self.assertRaisesRegex(ValueError, "PDF printed ID"):
                checker.prepare_inputs(SimpleNamespace(kit=kit, images=None, dpi=72), rejected_output)

            accepted_output = root / "accepted"
            accepted_output.mkdir()
            source, inputs, scene = checker.prepare_inputs(
                SimpleNamespace(kit=original, images=None, dpi=72), accepted_output)
            self.assertEqual(source["pdf_sha256"], checker.sha256(original / "cctag3-print.pdf"))
            self.assertEqual([item["expected_id"] for item in inputs], [0, 1, 2, 3])
            self.assertTrue(scene.is_file())

    def test_working_confirmation_does_not_change_issued_kit(self):
        original = ROOT / "templates/capture-kit"
        before = checker.sha256(original / "measurements.csv")
        with tempfile.TemporaryDirectory(prefix="cctag-working-sheet-") as temporary:
            working = Path(temporary) / "measurements.csv"
            with (original / "measurements.csv").open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            for row in rows:
                if row["purpose"] == "scale":
                    row.update(status="confirmed_nominal", method="checked during placement",
                               confirmation_source="Operator chat: placed and checked as planned")
            with working.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            sheet = load_measurements(working)
            resolved = confirmed_scale(sheet)
            self.assertEqual(resolved["distance"], scale_row(sheet)["planned_mm"])
            self.assertIsNone(scale_row(sheet)["measured_mm"])
            self.assertIsNone(resolved["measurement_uncertainty_mm"])
            self.assertEqual(checker.sha256(original / "measurements.csv"), before)


@unittest.skipUnless(os.environ.get("CCTAG_SOURCE_DIR") and all(
    importlib.util.find_spec(name) for name in ("reportlab", "svglib", "svgwrite", "fitz")),
    "Real kit generation requires CCTAG_SOURCE_DIR and optional capture dependencies")
class GeneratedPlanKitTests(unittest.TestCase):
    def setUp(self):
        import make_capture_kit
        self.maker = make_capture_kit
        self.source = Path(os.environ["CCTAG_SOURCE_DIR"])
        self.maker.source_files(self.source, False)
        temporary = tempfile.TemporaryDirectory(prefix="cctag-plan-kit-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write_plan(self, name="plan.csv", **changes):
        row = dict.fromkeys(FIELDS, "")
        row.update(measurement_id="other_scale", purpose="scale", from_point="cctag3:7:center",
                   to_point="cctag3:31:center", planned_mm="1234.5", status="planned")
        row.update(changes)
        control = dict.fromkeys(FIELDS, "")
        control.update(measurement_id="other_control", purpose="check", from_point="cctag3:23:center",
                       to_point="cctag3:5:center", planned_mm="877.25", status="planned")
        path = self.root / name
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows([row, control])
        return path

    def test_real_generator_preserves_nondefault_pairs_and_unconfirmed_plan(self):
        import fitz
        plan = self.write_plan()
        kit = self.root / "kit"
        manifest = self.maker.make_kit(self.source, kit, [7, 23, 31, 5], 160, "A3", plan)
        sheet = load_measurements(kit / "measurements.csv")
        scale = scale_row(sheet)
        self.assertEqual(scale["marker_ids"], [7, 31])
        self.assertEqual(scale["planned_mm"], 1234.5)
        self.assertIsNone(scale["measured_mm"])
        self.assertTrue(all(row["confirmed_mm"] is None for row in sheet["rows"]))
        self.assertEqual(sum(row["purpose"] == "print_check" for row in sheet["rows"]), 8)
        control = next(row for row in sheet["rows"] if row["purpose"] == "check")
        self.assertEqual(control["marker_ids"], [23, 5])
        self.assertEqual(control["planned_mm"], 877.25)
        self.assertEqual(manifest["placement_plan_sha256"], checker.sha256(plan))
        self.assertEqual((kit / "placement-plan.csv").read_bytes(), plan.read_bytes())
        self.assertIn("центры ID 7 и ID 31", (kit / "placement.txt").read_text(encoding="utf-8"))
        self.assertIn("1234.5", (kit / "placement.txt").read_text(encoding="utf-8"))
        with fitz.open(kit / "cctag3-print.pdf") as document:
            self.assertAlmostEqual(document[0].rect.width / 72 * 25.4, 297, places=3)
        output = self.root / "pdf-inputs"
        output.mkdir()
        _, inputs, _ = checker.prepare_inputs(SimpleNamespace(kit=kit, images=None, dpi=72), output)
        self.assertEqual([row["expected_id"] for row in inputs], [7, 23, 31, 5])

    def test_confirmed_sheet_cannot_be_reissued_as_a_draft_plan(self):
        plan = self.write_plan(status="confirmed_nominal", method="checked during placement",
                               confirmation_source="Operator reply")
        with self.assertRaisesRegex(ValueError, "must be unconfirmed"):
            self.maker.make_kit(self.source, self.root / "kit", [7, 23, 31, 5], 160, "A3", plan)

    def test_plan_ids_must_be_in_issued_pages(self):
        plan = self.write_plan()
        with self.assertRaisesRegex(ValueError, "not printed"):
            self.maker.make_kit(self.source, self.root / "kit", [7, 23, 5], 160, "A3", plan)


if __name__ == "__main__":
    unittest.main()

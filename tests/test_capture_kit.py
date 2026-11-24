"""Native file-contract and delivered print-kit checks; no pretend detector.

Full digital ID acceptance is the native Linux CI, not these parser checks.
"""

import base64
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
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
        self.assertEqual(sum(row["purpose"] == "scale" for row in rows), 1)
        self.assertEqual(sum(row["measurement_id"].startswith("object_check_") for row in rows), 2)
        self.assertEqual(sum(row["purpose"] == "print_check" for row in rows), 8)
        manifest = json.loads((kit / "manifest.json").read_text(encoding="utf-8"))
        for name, field in [("cctag3-print.pdf", "pdf_sha256"), ("measurements.csv", "measurements_sha256")]:
            self.assertEqual(hashlib.sha256((kit / name).read_bytes()).hexdigest(), manifest[field])

    @unittest.skipUnless(importlib.util.find_spec("fitz"), "Optional PDF checks require requirements-capture-kit.txt")
    def test_final_pdf_has_actual_paper_and_marker_dimensions(self):
        import fitz

        kit = ROOT / "templates/capture-kit"
        manifest = json.loads((kit / "manifest.json").read_text(encoding="utf-8"))
        with fitz.open(kit / "cctag3-print.pdf") as document:
            self.assertEqual(len(document), 4)
            for page, expected in zip(document, manifest["pages"]):
                self.assertIn(f"CCTag3 - ID {expected['native_id']}", page.get_text())
                self.assertAlmostEqual(page.rect.width / 72 * 25.4, 210, places=3)
                self.assertAlmostEqual(page.rect.height / 72 * 25.4, 297, places=3)
                circles = [path["rect"] for path in page.get_drawings()
                           if any(item[0] == "c" for item in path["items"])]
                outer = max(circles, key=lambda rect: rect.width)
                self.assertAlmostEqual(outer.width / 72 * 25.4, 100, places=3)
                self.assertAlmostEqual(outer.height / 72 * 25.4, 100, places=3)


if __name__ == "__main__":
    unittest.main()

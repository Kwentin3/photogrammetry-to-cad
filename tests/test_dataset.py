"""Filesystem boundary tests for the exact photographs passed to Meshroom."""

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fetch_dataset.py"
spec = importlib.util.spec_from_file_location("fetch_dataset", SCRIPT)
dataset = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dataset)

# A real one-pixel PNG: file validation uses real files and hashes, without mocks.
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jSucAAAAASUVORK5CYII=")


class DatasetInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dataset-input-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.images = self.root / "images"
        self.images.mkdir()
        self.image = self.images / "synthetic_00.png"
        self.image.write_bytes(PNG)
        self.truth = {"synthetic": True, "views": [
            {"file": "images/synthetic_00.png", "sha256": hashlib.sha256(PNG).hexdigest()}
        ]}
        self.write_truth()

    def write_truth(self):
        (self.root / "truth.json").write_text(json.dumps(self.truth), encoding="utf-8")

    def verify(self):
        return dataset.verify_input(self.root, "synthetic-markers")

    def test_exact_images_with_safe_metadata_pass(self):
        (self.images / "capture-notes.txt").write_text("Fixture notes", encoding="utf-8")
        (self.images / "camera.json").write_text("{}", encoding="utf-8")
        # The generator's board is not in the folder Meshroom scans.
        (self.root / "source_board.png").write_bytes(PNG)
        self.assertEqual(self.verify(), (self.images, 1))

    def test_unlisted_photo_fails_and_is_preserved(self):
        extra = self.images / "foreign.JPG"
        extra.write_bytes(PNG)
        with self.assertRaisesRegex(ValueError, "Unlisted input file: foreign.JPG"):
            self.verify()
        self.assertEqual(extra.read_bytes(), PNG)

    def test_unlisted_other_image_format_fails(self):
        # An extension not enumerated by this validator must not bypass the set.
        (self.images / "foreign.exr").write_bytes(b"foreign image")
        with self.assertRaisesRegex(ValueError, "Unlisted input file"):
            self.verify()

    def test_nested_photo_directory_fails_and_is_preserved(self):
        nested = self.images / "other"
        nested.mkdir()
        (nested / "foreign.png").write_bytes(PNG)
        with self.assertRaisesRegex(ValueError, "Unexpected input entry: other"):
            self.verify()
        self.assertTrue((nested / "foreign.png").is_file())

    def test_missing_photo_fails(self):
        self.image.unlink()
        with self.assertRaisesRegex(ValueError, "Missing input file"):
            self.verify()

    def test_modified_photo_fails_even_at_same_size(self):
        self.image.write_bytes(PNG[:-1] + bytes([PNG[-1] ^ 1]))
        with self.assertRaisesRegex(ValueError, "Input SHA-256 differs"):
            self.verify()

    def test_empty_or_duplicate_selection_fails(self):
        for views in ([], self.truth["views"] * 2):
            with self.subTest(views=len(views)):
                self.truth["views"] = views
                self.write_truth()
                with self.assertRaisesRegex(ValueError, "nonempty and unique"):
                    self.verify()

    def test_truth_cannot_select_a_file_outside_images(self):
        for name in ("../foreign.png", "images/../foreign.png", "images/sub/photo.png", "images/C:photo.png"):
            with self.subTest(name=name):
                self.truth["views"][0]["file"] = name
                self.write_truth()
                with self.assertRaises(ValueError):
                    self.verify()

    def test_downloader_rejects_extras_before_replacing_manifest(self):
        output = self.root / "download"
        output.mkdir()
        manifest = output / "manifest.json"
        manifest.write_text("preserved existing manifest", encoding="utf-8")
        extra = output / "foreign.jpg"
        extra.write_bytes(PNG)
        # Replace only the external API listing. Filesystem validation and the
        # downloader's ordering run unchanged, including the first-20 selection.
        upstream = [{"name": f"{number:02}.JPG"} for number in range(1, 34)]
        args = [str(SCRIPT), "dice", "--output", str(output), "--limit", "20"]
        with patch.object(dataset, "source_files", return_value=upstream), patch.object(sys, "argv", args):
            with self.assertRaisesRegex(ValueError, "Unlisted input file: foreign.jpg"):
                dataset.main()
        self.assertEqual(manifest.read_text(encoding="utf-8"), "preserved existing manifest")
        self.assertEqual(extra.read_bytes(), PNG)

    def test_real_manifest_must_be_complete_and_pinned(self):
        for changes in ({"complete": False}, {"revision": "wrong"}, {"dataset": "cctag"}):
            manifest = {"dataset": "dice", "complete": True, "revision": dataset.DATASETS["dice"]["revision"], **changes}
            (self.root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, "complete manifest"):
                dataset.verify_input(self.root, "dice")

    def test_cli_verify_only_succeeds_and_fails_without_network(self):
        command = [sys.executable, str(SCRIPT), "synthetic-markers", "--output", str(self.root), "--verify-only"]
        valid = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(valid.returncode, 0, valid.stderr)
        self.assertIn("1 input images", valid.stdout)
        self.image.unlink()
        invalid = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("Missing input file", invalid.stderr)


if __name__ == "__main__":
    unittest.main()

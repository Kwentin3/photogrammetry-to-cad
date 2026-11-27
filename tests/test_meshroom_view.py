"""Windows drive ownership at the real DOS-device boundary; no GUI required."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import meshroom_view as view


@unittest.skipUnless(sys.platform == "win32", "Native Windows subst boundary")
class DriveOwnershipTests(unittest.TestCase):
    def setUp(self):
        mask = view.kernel32().GetLogicalDrives()
        self.drive = next((f"{letter}:" for letter in "ZYXWVUTSRQ"
                           if not mask & (1 << (ord(letter) - ord("A")))
                           and view.drive_target(f"{letter}:") is None), None)
        if self.drive is None:
            self.skipTest("No free test drive")
        self.temp = tempfile.TemporaryDirectory(prefix="meshroom-view-drive-test-")
        self.addCleanup(self.temp.cleanup)
        self.a, self.b = Path(self.temp.name) / "a", Path(self.temp.name) / "b"
        self.a.mkdir()
        self.b.mkdir()
        (self.a / "owner.txt").write_text("first package", encoding="utf8")
        (self.b / "owner.txt").write_text("foreign package", encoding="utf8")

    def test_foreign_drive_is_neither_overwritten_nor_removed(self):
        with view.mapped_drive(self.a, self.drive):
            first = view.drive_target(self.drive)
            with self.assertRaisesRegex(view.ViewError, "occupied"):
                with view.mapped_drive(self.b, self.drive):
                    self.fail("Occupied drive was accepted")
            self.assertEqual(view.drive_target(self.drive), first)
            self.assertEqual(Path(f"{self.drive}/owner.txt").read_text(), "first package")
        self.assertIsNone(view.drive_target(self.drive))

    def test_error_releases_only_the_owned_mapping(self):
        with self.assertRaisesRegex(ValueError, "view failed"):
            with view.mapped_drive(self.a, self.drive):
                raise ValueError("view failed")
        self.assertIsNone(view.drive_target(self.drive))

    def test_changed_mapping_is_preserved_during_old_owner_cleanup(self):
        old = view.mapped_drive(self.a, self.drive)
        old.__enter__()
        view.remove_exact_mapping(self.drive, view.drive_target(self.drive))
        with view.mapped_drive(self.b, self.drive):
            foreign = view.drive_target(self.drive)
            with self.assertRaisesRegex(view.ViewError, "changed owner"):
                old.__exit__(None, None, None)
            self.assertEqual(view.drive_target(self.drive), foreign)
            self.assertEqual(Path(f"{self.drive}/owner.txt").read_text(), "foreign package")
        self.assertIsNone(view.drive_target(self.drive))


if __name__ == "__main__":
    unittest.main()

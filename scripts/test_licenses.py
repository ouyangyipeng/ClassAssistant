import tempfile
import unittest
from pathlib import Path

from scripts.licenses import directory_licenses, legal_file, license_texts


class NoticeCollectionTests(unittest.TestCase):
    def test_collects_legal_text_without_source_or_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "LICENSE").write_text("Synthetic license", encoding="utf-8")
            (root / ".env").write_text("Synthetic private configuration", encoding="utf-8")
            (root / "license.js").write_text("Synthetic application code", encoding="utf-8")
            (root / "vendor").mkdir()
            (root / "vendor" / "NOTICE.txt").write_text("Synthetic notice", encoding="utf-8")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "LICENSE").write_text("Unrelated nested dependency", encoding="utf-8")
            self.assertEqual(directory_licenses(root), ["Synthetic license", "Synthetic notice"])

    def test_duplicate_notices_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ("COPYING", "LICENSE.txt")]
            for path in paths:
                path.write_text("Same license\n", encoding="utf-8")
            self.assertEqual(license_texts(paths), ["Same license"])
            self.assertFalse(legal_file(Path("license.svg")))
            self.assertTrue(legal_file(Path("LICENSE-APACHE")))

    def test_does_not_read_license_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / ".env"
            source.write_text("Synthetic private configuration", encoding="utf-8")
            link = root / "LICENSE"
            try:
                link.symlink_to(source)
            except OSError:
                self.skipTest("This platform does not permit test symlinks")
            self.assertEqual(license_texts([link]), [])


if __name__ == "__main__":
    unittest.main()

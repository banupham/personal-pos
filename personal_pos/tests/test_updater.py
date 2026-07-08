from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from personal_pos import updater


class UpdaterTests(unittest.TestCase):
    def test_check_for_update_from_local_manifest(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "update.zip"
            package.write_bytes(b"zip-data")
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "version": "0.2.0",
                        "notes": "test update",
                        "package_url": str(package),
                    }
                ),
                encoding="utf-8",
            )
            config = root / "update_config.json"
            config.write_text(json.dumps({"manifest_url": str(manifest)}), encoding="utf-8")

            check = updater.check_for_update("0.1.0", config)

            self.assertTrue(check.has_update)
            self.assertEqual(check.latest_version, "0.2.0")
            self.assertEqual(check.notes, "test update")

    def test_download_package_verifies_sha256(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "update.zip"
            package.write_bytes(b"package")
            digest = hashlib.sha256(b"package").hexdigest()

            downloaded = updater.download_package(str(package), digest, root / "updates")

            self.assertEqual(downloaded.read_bytes(), b"package")

    def test_install_update_extracts_zip_and_creates_backup(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            (project / "old.txt").write_text("old", encoding="utf-8")
            package = root / "update.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("repo-main/new.txt", "new")
                archive.writestr("repo-main/personal_pos/version.py", '__version__ = "0.2.0"\n')

            backup = updater.install_update(package, project, root / "backups")

            self.assertTrue(backup.exists())
            self.assertEqual((project / "new.txt").read_text(encoding="utf-8"), "new")
            self.assertEqual((project / "personal_pos" / "version.py").read_text(encoding="utf-8"), '__version__ = "0.2.0"\n')


if __name__ == "__main__":
    unittest.main()

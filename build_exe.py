from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from personal_pos.version import __version__


ROOT = Path(__file__).resolve().parent
BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist"
RELEASE_DIR = DIST_DIR / "release"
APP_EXE = DIST_DIR / "PersonalPOS.exe"
UPDATER_EXE = DIST_DIR / "PersonalPOSUpdater.exe"
PACKAGE_PATH = RELEASE_DIR / f"PersonalPOS_{__version__}.zip"


def main() -> None:
    clean()
    build_app()
    build_updater()
    write_runtime_config()
    package_release()
    digest = sha256(PACKAGE_PATH)
    print(f"Built: {APP_EXE}")
    print(f"Built: {UPDATER_EXE}")
    print(f"Package: {PACKAGE_PATH}")
    print(f"SHA256: {digest}")


def clean() -> None:
    for path in [BUILD_DIR, DIST_DIR]:
        if path.exists():
            shutil.rmtree(path)
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)


def build_app() -> None:
    run_pyinstaller(
        [
            "--noconfirm",
            "--clean",
            "--onefile",
            "--windowed",
            "--name",
            "PersonalPOS",
            "personal_pos/app_tkinter_backup.py",
        ]
    )


def build_updater() -> None:
    run_pyinstaller(
        [
            "--noconfirm",
            "--clean",
            "--onefile",
            "--console",
            "--name",
            "PersonalPOSUpdater",
            "personal_pos/exe_update_helper.py",
        ]
    )


def run_pyinstaller(args: list[str]) -> None:
    subprocess.run([sys.executable, "-m", "PyInstaller", *args], cwd=ROOT, check=True)


def write_runtime_config() -> None:
    config_path = DIST_DIR / "update_config.json"
    config_path.write_text(
        '{\n'
        '  "manifest_url": "https://raw.githubusercontent.com/banupham/personal-pos/main/update_manifest.json"\n'
        '}\n',
        encoding="utf-8",
    )


def package_release() -> None:
    with ZipFile(PACKAGE_PATH, "w", compression=ZIP_DEFLATED) as archive:
        archive.write(APP_EXE, APP_EXE.name)
        archive.write(UPDATER_EXE, UPDATER_EXE.name)
        archive.write(DIST_DIR / "update_config.json", "update_config.json")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()

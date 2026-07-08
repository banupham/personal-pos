from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import shutil
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen
import zipfile

from .version import __version__


APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
CONFIG_PATH = APP_DIR / "update_config.json"
UPDATE_DIR = APP_DIR / "data" / "updates"
BACKUP_DIR = APP_DIR / "data" / "backups" / "program"
UPDATE_HISTORY_PATH = UPDATE_DIR / "update_history.jsonl"
DEFAULT_DB_PATH = APP_DIR / "data" / "app_pos.db"

PROTECTED_UPDATE_DIRS = {
    ".git",
    "__pycache__",
}


class UpdateError(Exception):
    pass


@dataclass(frozen=True)
class UpdateConfig:
    manifest_url: str


@dataclass(frozen=True)
class UpdateManifest:
    version: str
    notes: str
    package_url: str
    sha256: str | None = None


@dataclass(frozen=True)
class UpdateCheck:
    current_version: str
    latest_version: str
    has_update: bool
    notes: str
    package_url: str
    sha256: str | None


def load_config(path: Path = CONFIG_PATH) -> UpdateConfig:
    if not path.exists():
        raise UpdateError(f"Missing update config: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UpdateError(f"Update config is not valid JSON: {path}") from exc
    manifest_url = str(data.get("manifest_url", "")).strip()
    if not manifest_url or "YOUR_GITHUB_USERNAME" in manifest_url or "YOUR_REPO" in manifest_url:
        raise UpdateError("Please set manifest_url in personal_pos/update_config.json")
    return UpdateConfig(manifest_url=manifest_url)


def save_config(manifest_url: str, path: Path = CONFIG_PATH) -> None:
    manifest_url = manifest_url.strip()
    if not manifest_url:
        raise UpdateError("manifest_url is required")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"manifest_url": manifest_url}, indent=2), encoding="utf-8")


def fetch_manifest(manifest_url: str) -> UpdateManifest:
    data = _read_url_or_file(manifest_url)
    try:
        raw: dict[str, Any] = json.loads(data.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise UpdateError("Update manifest is not valid JSON") from exc

    version = str(raw.get("version", "")).strip()
    package_url = str(raw.get("package_url", "")).strip()
    if not version:
        raise UpdateError("Update manifest missing version")
    if not package_url:
        raise UpdateError("Update manifest missing package_url")

    raw_sha = raw.get("sha256")
    sha256 = str(raw_sha).strip() if raw_sha is not None else ""
    if sha256.lower() in {"", "none", "null"}:
        sha256 = ""

    return UpdateManifest(
        version=version,
        notes=str(raw.get("notes", "")).strip(),
        package_url=package_url,
        sha256=sha256 or None,
    )


def check_for_update(current_version: str = __version__, config_path: Path = CONFIG_PATH) -> UpdateCheck:
    config = load_config(config_path)
    manifest = fetch_manifest(config.manifest_url)
    return UpdateCheck(
        current_version=current_version,
        latest_version=manifest.version,
        has_update=_version_tuple(manifest.version) > _version_tuple(current_version),
        notes=manifest.notes,
        package_url=manifest.package_url,
        sha256=manifest.sha256,
    )


def download_package(package_url: str, sha256: str | None = None, update_dir: Path = UPDATE_DIR) -> Path:
    update_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = update_dir / f"update_{timestamp}.zip"
    data = _read_url_or_file(package_url)
    if sha256:
        digest = hashlib.sha256(data).hexdigest()
        if digest.lower() != sha256.lower():
            raise UpdateError("Downloaded update checksum does not match sha256")
    _validate_zip_bytes(data)
    target.write_bytes(data)
    return target


def install_update(
    package_path: Path,
    project_dir: Path = PROJECT_DIR,
    backup_dir: Path = BACKUP_DIR,
    *,
    db_path: Path = DEFAULT_DB_PATH,
    backup_database: bool = True,
) -> Path:
    package_path = package_path.resolve()
    project_dir = project_dir.resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    database_backup_path = None
    if backup_database:
        database_backup_path = _backup_database_before_update(db_path)

    program_backup_path = backup_dir / f"personal_pos_program_backup_{timestamp}.zip"
    _backup_project(project_dir, program_backup_path)
    _extract_update(package_path, project_dir)
    _write_update_history(package_path, program_backup_path, database_backup_path)
    return program_backup_path


def download_and_install(check: UpdateCheck) -> Path:
    if not check.has_update:
        raise UpdateError("No newer version available")
    package = download_package(check.package_url, check.sha256)
    return install_update(package)


def _backup_database_before_update(db_path: Path) -> Path | None:
    db_path = Path(db_path)
    if not db_path.exists():
        return None
    try:
        from . import backup as database_backup
    except Exception as exc:
        raise UpdateError("Cannot import database backup module before update") from exc
    try:
        return database_backup.create_database_backup(db_path, reason="before_update")
    except Exception as exc:
        raise UpdateError(f"Database backup failed before update: {exc}") from exc


def _version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in version.strip().lstrip("v").split("."):
        number = ""
        for char in piece:
            if char.isdigit():
                number += char
            else:
                break
        parts.append(int(number or "0"))
    return tuple(parts)


def _read_url_or_file(location: str) -> bytes:
    parsed = urlparse(location)
    if parsed.scheme in {"http", "https"}:
        with urlopen(location, timeout=30) as response:
            return response.read()
    if parsed.scheme == "file":
        return Path(parsed.path).read_bytes()
    return Path(location).read_bytes()


def _validate_zip_bytes(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            invalid = archive.testzip()
    except zipfile.BadZipFile as exc:
        raise UpdateError("Downloaded update package is not a valid zip file") from exc
    if invalid:
        raise UpdateError(f"Downloaded update package has a corrupt file: {invalid}")


def _backup_project(project_dir: Path, backup_path: Path) -> None:
    ignored_parts = {"__pycache__", "data", ".git"}
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in project_dir.rglob("*"):
            if path.is_dir():
                continue
            relative = path.relative_to(project_dir)
            if any(part in ignored_parts for part in relative.parts):
                continue
            archive.write(path, relative.as_posix())


def _extract_update(package_path: Path, project_dir: Path) -> None:
    with zipfile.ZipFile(package_path) as archive:
        members = [member for member in archive.infolist() if not member.is_dir()]
        prefix = _detect_common_prefix(members)
        writable_members = []
        for member in members:
            relative_name = member.filename
            if prefix and relative_name.startswith(prefix):
                relative_name = relative_name[len(prefix) :]
            if not relative_name or relative_name.endswith("/"):
                continue
            relative_path = Path(relative_name)
            if _should_skip_update_file(relative_path):
                continue
            target = (project_dir / relative_path).resolve()
            if not _is_relative_to(target, project_dir):
                raise UpdateError(f"Unsafe path in update package: {member.filename}")
            writable_members.append((member, target))

        if not writable_members:
            raise UpdateError("Update package does not contain any writable application files")

        for member, target in writable_members:
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as dest:
                shutil.copyfileobj(source, dest)


def _should_skip_update_file(relative_path: Path) -> bool:
    parts = relative_path.parts
    if not parts:
        return True
    if any(part in PROTECTED_UPDATE_DIRS for part in parts):
        return True
    if len(parts) >= 2 and parts[0] == "personal_pos" and parts[1] == "data":
        return True
    if parts[0] == "data":
        return True
    return False


def _detect_common_prefix(members: list[zipfile.ZipInfo]) -> str:
    first_parts = [member.filename.split("/", 1)[0] for member in members if "/" in member.filename]
    if first_parts and len(set(first_parts)) == 1:
        return f"{first_parts[0]}/"
    return ""


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _write_update_history(package_path: Path, program_backup_path: Path, database_backup_path: Path | None) -> None:
    UPDATE_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "package_path": str(package_path),
        "program_backup_path": str(program_backup_path),
        "database_backup_path": str(database_backup_path) if database_backup_path else None,
    }
    with UPDATE_HISTORY_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")

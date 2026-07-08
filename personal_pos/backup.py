from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys


APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
CONFIG_PATH = DATA_DIR / "backup_config.json"
DEFAULT_BACKUP_DIR = DATA_DIR / "backups" / "database"
DEFAULT_KEEP_LAST = 30


class BackupError(Exception):
    """Raised when database backup or restore cannot be completed."""


@dataclass(frozen=True)
class BackupConfig:
    backup_dir: Path = DEFAULT_BACKUP_DIR
    keep_last: int = DEFAULT_KEEP_LAST
    auto_backup_on_exit: bool = True

    def normalized(self) -> "BackupConfig":
        keep_last = max(1, int(self.keep_last or DEFAULT_KEEP_LAST))
        return BackupConfig(
            backup_dir=Path(self.backup_dir).expanduser(),
            keep_last=keep_last,
            auto_backup_on_exit=bool(self.auto_backup_on_exit),
        )


def load_config(path: Path = CONFIG_PATH) -> BackupConfig:
    if not path.exists():
        return BackupConfig().normalized()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BackupError(f"Backup config is not valid JSON: {path}") from exc

    return BackupConfig(
        backup_dir=Path(str(raw.get("backup_dir") or DEFAULT_BACKUP_DIR)).expanduser(),
        keep_last=int(raw.get("keep_last") or DEFAULT_KEEP_LAST),
        auto_backup_on_exit=bool(raw.get("auto_backup_on_exit", True)),
    ).normalized()


def save_config(config: BackupConfig, path: Path = CONFIG_PATH) -> BackupConfig:
    config = config.normalized()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "backup_dir": str(config.backup_dir),
        "keep_last": config.keep_last,
        "auto_backup_on_exit": config.auto_backup_on_exit,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return config


def update_config(
    *,
    backup_dir: str | Path | None = None,
    keep_last: int | None = None,
    auto_backup_on_exit: bool | None = None,
) -> BackupConfig:
    current = load_config()
    return save_config(
        BackupConfig(
            backup_dir=Path(backup_dir).expanduser() if backup_dir is not None else current.backup_dir,
            keep_last=keep_last if keep_last is not None else current.keep_last,
            auto_backup_on_exit=(
                auto_backup_on_exit if auto_backup_on_exit is not None else current.auto_backup_on_exit
            ),
        )
    )


def create_database_backup(
    db_path: str | Path,
    *,
    reason: str = "manual",
    config: BackupConfig | None = None,
) -> Path:
    db = Path(db_path).expanduser().resolve()
    if not db.exists():
        raise BackupError(f"Database does not exist: {db}")

    config = (config or load_config()).normalized()
    config.backup_dir.mkdir(parents=True, exist_ok=True)
    reason = _safe_name(reason or "manual")
    target = config.backup_dir / f"{db.stem}_{reason}_{_timestamp()}.db"

    # sqlite3.Connection.backup creates a consistent DB copy even when WAL mode is enabled.
    source = sqlite3.connect(db)
    try:
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()

    cleanup_old_backups(config=config)
    return target


def list_backups(config: BackupConfig | None = None) -> list[Path]:
    config = (config or load_config()).normalized()
    if not config.backup_dir.exists():
        return []
    return sorted(
        [path for path in config.backup_dir.glob("*.db") if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def cleanup_old_backups(config: BackupConfig | None = None) -> list[Path]:
    config = (config or load_config()).normalized()
    removed: list[Path] = []
    backups = list_backups(config)
    for path in backups[config.keep_last :]:
        try:
            path.unlink()
            removed.append(path)
        except FileNotFoundError:
            continue
    return removed


def restore_database_backup(
    backup_path: str | Path,
    db_path: str | Path,
    *,
    config: BackupConfig | None = None,
) -> Path:
    backup = Path(backup_path).expanduser().resolve()
    db = Path(db_path).expanduser().resolve()
    if not backup.exists():
        raise BackupError(f"Backup file does not exist: {backup}")
    if backup.suffix.lower() != ".db":
        raise BackupError("Backup file must be a .db SQLite file")

    config = (config or load_config()).normalized()
    db.parent.mkdir(parents=True, exist_ok=True)
    pre_restore = None
    if db.exists():
        pre_restore = create_database_backup(db, reason="before_restore", config=config)

    shutil.copy2(backup, db)
    _remove_sidecar_files(db)
    return pre_restore or backup


def open_backup_folder(config: BackupConfig | None = None) -> None:
    config = (config or load_config()).normalized()
    config.backup_dir.mkdir(parents=True, exist_ok=True)
    path = str(config.backup_dir)
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def google_drive_candidates() -> list[Path]:
    home = Path.home()
    candidates = [
        home / "Google Drive" / "POS_Backup",
        home / "My Drive" / "POS_Backup",
        home / "Google Drive" / "My Drive" / "POS_Backup",
        home / "Drive của tôi" / "POS_Backup",
    ]
    return [path for path in candidates if path.parent.exists()]


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.strip())
    return cleaned.strip("_") or "manual"


def _remove_sidecar_files(db_path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        sidecar = db_path.with_name(f"{db_path.name}{suffix}")
        try:
            sidecar.unlink()
        except FileNotFoundError:
            continue


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Backup and restore Personal POS SQLite database.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create a database backup")
    create_parser.add_argument("db_path", help="Path to app_pos.db")
    create_parser.add_argument("--reason", default="manual", help="Reason tag used in the backup filename")

    list_parser = subparsers.add_parser("list", help="List backup files")
    list_parser.add_argument("--limit", type=int, default=20)

    config_parser = subparsers.add_parser("config", help="Update backup config")
    config_parser.add_argument("--backup-dir")
    config_parser.add_argument("--keep-last", type=int)
    config_parser.add_argument("--auto-on-exit", choices=["yes", "no"])

    args = parser.parse_args()
    if args.command == "create":
        print(create_database_backup(args.db_path, reason=args.reason))
    elif args.command == "list":
        for path in list_backups()[: args.limit]:
            print(path)
    elif args.command == "config":
        config = update_config(
            backup_dir=args.backup_dir,
            keep_last=args.keep_last,
            auto_backup_on_exit=(args.auto_on_exit == "yes") if args.auto_on_exit else None,
        )
        print(json.dumps({
            "backup_dir": str(config.backup_dir),
            "keep_last": config.keep_last,
            "auto_backup_on_exit": config.auto_backup_on_exit,
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

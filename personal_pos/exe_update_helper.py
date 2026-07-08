from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


class ExeUpdateHelperError(Exception):
    pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply a staged Personal POS exe update.")
    parser.add_argument("--pending", required=True, help="Path to update_pending.json")
    args = parser.parse_args()
    apply_pending_update(Path(args.pending))


def apply_pending_update(pending_path: Path) -> None:
    pending_path = pending_path.resolve()
    data = _load_pending(pending_path)

    app_dir = Path(data["app_dir"]).resolve()
    staged_dir = Path(data["staged_dir"]).resolve()
    exe_name = str(data["exe_name"])
    pid = int(data["pid"])

    _validate_paths(app_dir, staged_dir)
    _wait_for_process_to_exit(pid, timeout_seconds=120)
    _copy_update_files(staged_dir, app_dir)

    exe_path = app_dir / exe_name
    if exe_path.exists():
        subprocess.Popen([str(exe_path)], cwd=str(app_dir))

    _mark_applied(pending_path)


def _load_pending(pending_path: Path) -> dict[str, object]:
    if not pending_path.exists():
        raise ExeUpdateHelperError(f"Pending update file does not exist: {pending_path}")
    try:
        data = json.loads(pending_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ExeUpdateHelperError("Pending update file is not valid JSON") from exc
    for key in ("app_dir", "staged_dir", "exe_name", "pid"):
        if key not in data:
            raise ExeUpdateHelperError(f"Pending update missing field: {key}")
    return data


def _validate_paths(app_dir: Path, staged_dir: Path) -> None:
    if not app_dir.exists() or not app_dir.is_dir():
        raise ExeUpdateHelperError(f"Application directory does not exist: {app_dir}")
    if not staged_dir.exists() or not staged_dir.is_dir():
        raise ExeUpdateHelperError(f"Staged update directory does not exist: {staged_dir}")
    if app_dir == staged_dir or staged_dir in app_dir.parents:
        raise ExeUpdateHelperError("Staged update directory must not be the application directory or its parent")


def _wait_for_process_to_exit(pid: int, *, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not _process_exists(pid):
            return
        time.sleep(1)
    raise ExeUpdateHelperError("Timed out waiting for the app to close before applying update")


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform.startswith("win"):
        return _windows_process_exists(pid)
    try:
        os.kill(pid, 0)
    except (OSError, SystemError):
        return False
    return True


def _windows_process_exists(pid: int) -> bool:
    import ctypes

    synchronize = 0x00100000
    wait_timeout = 0x00000102
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        return False
    try:
        return kernel32.WaitForSingleObject(handle, 0) == wait_timeout
    finally:
        kernel32.CloseHandle(handle)


def _copy_update_files(staged_dir: Path, app_dir: Path) -> None:
    for source in staged_dir.rglob("*"):
        if source.is_dir():
            continue
        relative = source.relative_to(staged_dir)
        if _should_skip(relative):
            continue
        target = (app_dir / relative).resolve()
        if not _is_relative_to(target, app_dir):
            raise ExeUpdateHelperError(f"Unsafe target path: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _should_skip(relative: Path) -> bool:
    parts = relative.parts
    if not parts:
        return True
    blocked = {"data", ".git", "__pycache__"}
    if any(part in blocked for part in parts):
        return True
    if relative.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
        return True
    return False


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _mark_applied(pending_path: Path) -> None:
    marker = pending_path.with_suffix(".applied.json")
    marker.write_text(
        json.dumps({"applied_at": time.strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Personal POS update failed: {exc}", file=sys.stderr)
        raise

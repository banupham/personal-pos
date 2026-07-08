from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

from . import backup
from .app_tkinter import DB_PATH, PosApp


class BackupPosApp(PosApp):
    """Personal POS desktop app with a backup menu layered on top of the base UI."""

    def __init__(self) -> None:
        super().__init__()
        self.backup_config = backup.load_config()
        self.auto_backup_var = tk.BooleanVar(value=self.backup_config.auto_backup_on_exit)
        self._install_backup_menu()
        self.protocol("WM_DELETE_WINDOW", self.close_with_optional_backup)

    def _install_backup_menu(self) -> None:
        menu_bar = tk.Menu(self)
        backup_menu = tk.Menu(menu_bar, tearoff=False)
        backup_menu.add_command(label="Sao lưu ngay", command=self.create_backup_now)
        backup_menu.add_command(label="Chọn thư mục sao lưu...", command=self.choose_backup_folder)
        backup_menu.add_command(label="Mở thư mục sao lưu", command=self.open_backup_folder)
        backup_menu.add_separator()
        backup_menu.add_command(label="Phục hồi từ file backup...", command=self.restore_from_backup)
        backup_menu.add_command(label="Số bản backup giữ lại...", command=self.change_keep_last)
        backup_menu.add_checkbutton(
            label="Tự sao lưu khi thoát",
            variable=self.auto_backup_var,
            command=self.toggle_auto_backup,
        )
        menu_bar.add_cascade(label="Sao lưu", menu=backup_menu)
        self.config(menu=menu_bar)

    def create_backup_now(self) -> None:
        try:
            path = backup.create_database_backup(DB_PATH, reason="manual", config=self.backup_config)
        except Exception as exc:
            self.show_error(exc)
            return
        messagebox.showinfo("Đã sao lưu", f"Đã tạo backup database:\n{path}")

    def choose_backup_folder(self) -> None:
        initial_dir = self._best_initial_backup_dir()
        selected = filedialog.askdirectory(
            title="Chọn thư mục sao lưu database",
            initialdir=str(initial_dir),
        )
        if not selected:
            return
        self.backup_config = backup.update_config(backup_dir=selected)
        messagebox.showinfo(
            "Đã lưu thư mục sao lưu",
            f"Database sẽ được sao lưu vào:\n{self.backup_config.backup_dir}\n\n"
            "Bạn có thể chọn thư mục nằm trong Google Drive Desktop để tự đồng bộ lên mây.",
        )

    def open_backup_folder(self) -> None:
        try:
            backup.open_backup_folder(self.backup_config)
        except Exception as exc:
            self.show_error(exc)

    def restore_from_backup(self) -> None:
        selected = filedialog.askopenfilename(
            title="Chọn file backup .db để phục hồi",
            initialdir=str(self.backup_config.backup_dir),
            filetypes=[("SQLite database", "*.db"), ("All files", "*.*")],
        )
        if not selected:
            return
        allowed = messagebox.askyesno(
            "Xác nhận phục hồi",
            "Phục hồi sẽ ghi đè database hiện tại. Ứng dụng sẽ tạo một bản backup trước khi ghi đè. Tiếp tục?",
        )
        if not allowed:
            return
        try:
            pre_restore = backup.restore_database_backup(selected, DB_PATH, config=self.backup_config)
        except Exception as exc:
            self.show_error(exc)
            return
        messagebox.showinfo(
            "Đã phục hồi",
            f"Đã phục hồi database từ:\n{selected}\n\nBackup trước khi phục hồi:\n{pre_restore}\n\n"
            "Hãy đóng và mở lại ứng dụng để tải lại dữ liệu.",
        )

    def change_keep_last(self) -> None:
        value = simpledialog.askinteger(
            "Số bản backup giữ lại",
            "Giữ lại bao nhiêu bản backup gần nhất?",
            initialvalue=self.backup_config.keep_last,
            minvalue=1,
            maxvalue=500,
            parent=self,
        )
        if value is None:
            return
        self.backup_config = backup.update_config(keep_last=value)
        removed = backup.cleanup_old_backups(config=self.backup_config)
        messagebox.showinfo(
            "Đã cập nhật",
            f"Sẽ giữ lại {self.backup_config.keep_last} bản backup gần nhất.\n"
            f"Đã xóa {len(removed)} bản cũ.",
        )

    def toggle_auto_backup(self) -> None:
        self.backup_config = backup.update_config(auto_backup_on_exit=self.auto_backup_var.get())

    def close_with_optional_backup(self) -> None:
        if self.auto_backup_var.get() and Path(DB_PATH).exists():
            try:
                backup.create_database_backup(DB_PATH, reason="auto_exit", config=self.backup_config)
            except Exception as exc:
                should_close = messagebox.askyesno(
                    "Sao lưu thất bại",
                    f"Không thể tạo backup trước khi thoát:\n{exc}\n\nVẫn thoát ứng dụng?",
                )
                if not should_close:
                    return
        self.destroy()

    def _best_initial_backup_dir(self) -> Path:
        candidates = backup.google_drive_candidates()
        if candidates:
            return candidates[0]
        return self.backup_config.backup_dir


def main() -> None:
    app = BackupPosApp()
    app.mainloop()


if __name__ == "__main__":
    main()

# Personal POS

Logic core for a small desktop sales and inventory app.

## Run Demo

```powershell
python -m personal_pos.demo
```

The demo creates `data/demo_pos.db`, adds products/customers, receives stock,
creates a sale, and prints inventory plus daily revenue.

## Run Desktop UI

```powershell
python -m personal_pos.app_tkinter
```

The Tkinter UI uses `data/app_pos.db`, the same database used by the console
test menu.

To run the UI with database backup tools enabled:

```powershell
python -m personal_pos.app_tkinter_backup
```

Current desktop features:

- Fast product search and barcode/SKU Enter-to-add on the sales screen.
- Customer debt: create customers, sell with partial payment, collect debt.
- Reports: daily revenue, gross profit, invoices, and top-selling products.
- Database backup menu through `personal_pos.app_tkinter_backup`.
- GitHub update checker/installer through `update_config.json`.

## Database Backups

Use the backup-enabled desktop UI:

```powershell
python -m personal_pos.app_tkinter_backup
```

Open the `Sao lưu` menu to:

- create a manual database backup,
- choose the backup folder,
- open the backup folder,
- restore from a `.db` backup file,
- choose how many backup files to keep,
- enable or disable auto-backup when closing the app.

Backups are SQLite `.db` files created with SQLite's backup API, so they remain
consistent even when the app database uses WAL mode. By default, backups are
stored in:

```text
personal_pos/data/backups/database
```

For cloud backup, install Google Drive Desktop, then choose a synced folder in
the `Sao lưu > Chọn thư mục sao lưu...` menu, for example:

```text
C:\Users\YOUR_NAME\Google Drive\POS_Backup
```

or any folder inside your local Google Drive sync directory.

You can also use the command line:

```powershell
python -m personal_pos.backup create personal_pos/data/app_pos.db
python -m personal_pos.backup list
python -m personal_pos.backup config --backup-dir "C:\Users\YOUR_NAME\Google Drive\POS_Backup" --keep-last 30 --auto-on-exit yes
```

## GitHub Updates

The desktop app can check a JSON manifest on GitHub, download a zip package,
back up the database, back up the program files, and extract the new version.

Default config:

```json
{
  "manifest_url": "https://raw.githubusercontent.com/banupham/personal-pos/main/update_manifest.json"
}
```

The release manifest lives at:

```text
update_manifest.json
```

Required manifest fields:

```json
{
  "version": "0.1.1",
  "notes": "Release notes shown inside the app.",
  "package_url": "https://github.com/banupham/personal-pos/archive/refs/heads/main.zip",
  "sha256": ""
}
```

`sha256` may be an empty string for branch zip updates. For a stricter release,
publish a fixed zip package, calculate its SHA256, and put that value in the
manifest.

In the desktop UI, open `Cap nhat`, click `Kiem tra`, then `Tai va cai`.

When installing an update, the updater now:

1. downloads and validates the zip package,
2. checks SHA256 when the manifest provides it,
3. creates a database backup for `personal_pos/data/app_pos.db`,
4. creates a program backup in `personal_pos/data/backups/program`,
5. extracts only application files,
6. skips runtime data under `personal_pos/data`,
7. writes update history to `personal_pos/data/updates/update_history.jsonl`.

Restart the app after installing an update.

Important release workflow:

1. Change code.
2. Bump `personal_pos/version.py`.
3. Update `update_manifest.json` with the same version.
4. Commit and merge to `main`.
5. Existing installed apps can then detect the new version.

## Run Console Test Menu

```powershell
python -m personal_pos.cli
```

## Project Shape

- `pos_core/database.py`: SQLite connection and schema migration.
- `pos_core/models.py`: dataclasses used by services.
- `pos_core/services.py`: product, customer, stock, sale, and report logic.
- `backup.py`: database backup, restore, cleanup, and backup config logic.
- `updater.py`: GitHub manifest update, package validation, program backup, and database-safe install logic.
- `app_tkinter.py`: desktop UI for personal use.
- `app_tkinter_backup.py`: desktop UI entry point with backup menu and auto-backup on exit.
- `cli.py`: console menu for quick manual testing.
- `demo.py`: quick command-line smoke test before building the desktop UI.

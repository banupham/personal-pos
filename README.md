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
python -m personal_pos.app_tkinter
```

Current desktop features:

- Fast product search and barcode/SKU Enter-to-add on the sales screen.
- Customer debt: create customers, sell with partial payment, collect debt.
- Reports: daily revenue, gross profit, invoices, and top-selling products.
- Database backup menu in the main `personal_pos.app_tkinter` UI.
- GitHub update checker/installer through `update_config.json`.

## Database Backups

Use the backup-enabled desktop UI:

```powershell
python -m personal_pos.app_tkinter
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

Default source-code config:

```json
{
  "manifest_url": "https://raw.githubusercontent.com/banupham/personal-pos/main/update_manifest.json"
}
```

The source-code release manifest lives at:

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

When installing an update from source mode, the updater now:

1. downloads and validates the zip package,
2. checks SHA256 when the manifest provides it,
3. creates a database backup for `personal_pos/data/app_pos.db`,
4. creates a program backup in `personal_pos/data/backups/program`,
5. extracts only application files,
6. skips runtime data under `personal_pos/data`,
7. writes update history to `personal_pos/data/updates/update_history.jsonl`.

Restart the app after installing an update.

## Windows EXE Update Framework

When the app is packaged as a Windows `.exe`, it cannot safely overwrite the
currently running executable. The updater now has a separate frozen-exe flow:

1. the app checks the manifest,
2. downloads and validates the release zip,
3. backs up the SQLite database,
4. backs up the current program folder,
5. extracts the new release to `data/updates/staged/<timestamp>`,
6. writes `data/updates/update_pending_<timestamp>.json`,
7. launches a helper exe when one is present,
8. the helper waits until the app closes, copies the staged files into the app
   folder, then reopens the app.

The helper source is:

```text
personal_pos/exe_update_helper.py
```

For an exe build, package this helper as a separate executable beside the main
app, using one of these names:

```text
PersonalPOSUpdater.exe
<MainExeName>Updater.exe
updater_helper.exe
```

The exe release zip should contain the new main exe and helper exe, for example:

```text
PersonalPOS.exe
PersonalPOSUpdater.exe
update_config.json
```

Do not put `data/app_pos.db` or any user database file inside the update zip.
The helper deliberately skips `data`, `.db`, `.sqlite`, and `.sqlite3` files.

Use `update_manifest_exe.example.json` as the template for packaged Windows
releases:

```json
{
  "version": "0.1.2",
  "notes": "Release notes for the packaged Windows exe build.",
  "package_url": "https://github.com/banupham/personal-pos/releases/download/v0.1.2/PersonalPOS_0.1.2_windows.zip",
  "sha256": "required_sha256_checksum_for_the_release_zip"
}
```

Important release workflow:

1. Change code.
2. Bump `personal_pos/version.py`.
3. Update the matching manifest with the same version.
4. For source mode, update `update_manifest.json`.
5. For exe mode, build and upload the Windows release zip, then update the exe
   manifest URL used by `update_config.json`.
6. Commit and merge to `main`.
7. Existing installed apps can then detect the new version.

## Run Console Test Menu

```powershell
python -m personal_pos.cli
```

## Project Shape

- `pos_core/database.py`: SQLite connection and schema migration.
- `pos_core/models.py`: dataclasses used by services.
- `pos_core/services.py`: product, customer, stock, sale, and report logic.
- `backup.py`: database backup, restore, cleanup, and backup config logic.
- `updater.py`: GitHub manifest update, package validation, program backup, database-safe source install, and frozen-exe staging logic.
- `exe_update_helper.py`: helper process used by packaged Windows exe builds to apply staged updates after the main app closes.
- `app_tkinter.py`: desktop UI for personal use.
- `app_tkinter.py`: main desktop UI with sales, inventory, reports, update, backup menu, and auto-backup on exit.
- `cli.py`: console menu for quick manual testing.
- `demo.py`: quick command-line smoke test before building the desktop UI.


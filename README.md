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

1. Push this project to a GitHub repository.
2. Create `update_manifest.json` in that repository using
   `update_manifest.example.json` as a template.
3. Set `personal_pos/update_config.json` to the raw manifest URL, for example:

```json
{
  "manifest_url": "https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/YOUR_REPO/main/update_manifest.json"
}
```

4. In the desktop UI, open `Cap nhat`, click `Kiem tra`, then `Tai va cai`.

The updater downloads a zip package, creates a backup in `personal_pos/data/backups`,
then extracts the new files. Restart the app after installing an update.

## Run Console Test Menu

```powershell
python -m personal_pos.cli
```

## Project Shape

- `pos_core/database.py`: SQLite connection and schema migration.
- `pos_core/models.py`: dataclasses used by services.
- `pos_core/services.py`: product, customer, stock, sale, and report logic.
- `backup.py`: database backup, restore, cleanup, and backup config logic.
- `app_tkinter.py`: desktop UI for personal use.
- `app_tkinter_backup.py`: desktop UI entry point with backup menu and auto-backup on exit.
- `cli.py`: console menu for quick manual testing.
- `demo.py`: quick command-line smoke test before building the desktop UI.

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

Current desktop features:

- Fast product search and barcode/SKU Enter-to-add on the sales screen.
- Customer debt: create customers, sell with partial payment, collect debt.
- Reports: daily revenue, gross profit, invoices, and top-selling products.
- GitHub update checker/installer through `update_config.json`.

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
- `app_tkinter.py`: desktop UI for personal use.
- `cli.py`: console menu for quick manual testing.
- `demo.py`: quick command-line smoke test before building the desktop UI.

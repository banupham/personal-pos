from __future__ import annotations

from datetime import date
from pathlib import Path

from .pos_core import Database, PosService
from .pos_core.models import SaleLineInput


def money(value: int) -> str:
    return f"{value:,} VND".replace(",", ".")


def main() -> None:
    db_path = Path(__file__).parent / "data" / "demo_pos.db"
    if db_path.exists():
        db_path.unlink()
    db = Database(db_path)
    db.initialize()
    service = PosService(db)

    coffee = service.create_product(
        sku="CF001",
        barcode="893000000001",
        name="Ca phe sua",
        unit="ly",
        cost_price=12000,
        sale_price=25000,
        min_stock=5,
    )
    tea = service.create_product(
        sku="TEA001",
        barcode="893000000002",
        name="Tra dao",
        unit="ly",
        cost_price=10000,
        sale_price=22000,
        min_stock=5,
    )
    customer = service.create_customer(code="KH001", name="Khach le", phone="0900000000")

    service.receive_stock(product_id=coffee.id, quantity=30, note="Nhap dau ky")
    service.receive_stock(product_id=tea.id, quantity=20, note="Nhap dau ky")

    sale = service.create_sale(
        customer_id=customer.id,
        items=[
            SaleLineInput(product_id=coffee.id, quantity=2),
            SaleLineInput(product_id=tea.id, quantity=1, discount=2000),
        ],
        discount=3000,
        paid=100000,
        payment_method="cash",
    )

    print(f"Created sale: {sale.invoice_no}")
    print(f"Total: {money(sale.total)}")
    print(f"Paid: {money(sale.paid)}")
    print(f"Change: {money(sale.change)}")
    print()

    print("Inventory:")
    for row in service.inventory():
        print(f"- {row.sku} | {row.name}: {row.on_hand} {row.unit}")
    print()

    summary = service.revenue_summary(date.today(), date.today())
    print("Today revenue:")
    print(f"- Orders: {summary.order_count}")
    print(f"- Total: {money(summary.total)}")

    print()
    print("Sales:")
    for row in service.list_sales(date.today(), date.today()):
        print(f"- {row.invoice_no} | {row.customer_name or 'Khach le'} | {money(row.total)}")

    export_dir = Path(__file__).parent / "data" / "exports"
    inventory_csv = service.export_inventory_csv(export_dir / "inventory.csv")
    sales_csv = service.export_sales_csv(export_dir / "sales_today.csv", date.today(), date.today())
    print()
    print(f"Exported: {inventory_csv}")
    print(f"Exported: {sales_csv}")


if __name__ == "__main__":
    main()

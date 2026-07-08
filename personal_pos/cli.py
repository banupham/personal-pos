from __future__ import annotations

from datetime import date
from pathlib import Path

from .pos_core import Database, PosService
from .pos_core.models import SaleLineInput
from .pos_core.services import NotEnoughStockError, PosError


DB_PATH = Path(__file__).parent / "data" / "app_pos.db"


def money(value: int) -> str:
    return f"{value:,} VND".replace(",", ".")


def read_text(label: str, *, required: bool = True) -> str | None:
    while True:
        try:
            value = input(f"{label}: ").strip()
        except EOFError:
            return None
        if value or not required:
            return value or None
        print("Vui long nhap thong tin.")


def read_int(label: str, *, minimum: int = 0) -> int:
    while True:
        try:
            raw = input(f"{label}: ").strip().replace(".", "").replace(",", "")
        except EOFError:
            raise PosError("Khong con du lieu nhap")
        try:
            value = int(raw)
        except ValueError:
            print("Vui long nhap so.")
            continue
        if value < minimum:
            print(f"Gia tri phai >= {minimum}.")
            continue
        return value


def choose_product(service: PosService) -> int | None:
    keyword = read_text("Nhap ma hang / barcode / ten hang", required=False)
    if not keyword:
        return None
    products = service.find_product(keyword)
    if not products:
        print("Khong tim thay hang hoa.")
        return None
    for product in products:
        on_hand = service.get_on_hand(product.id)
        print(f"{product.id}. {product.sku} | {product.name} | Ton: {on_hand} | Gia: {money(product.sale_price)}")
    if len(products) == 1:
        print(f"Tu dong chon: {products[0].name}")
        return products[0].id
    valid_ids = {product.id for product in products}
    while True:
        product_id = read_int("Nhap ID hang hoa muon chon", minimum=1)
        if product_id in valid_ids:
            return product_id
        print("ID khong nam trong danh sach tim thay.")


def add_product(service: PosService) -> None:
    print("\nThem hang hoa")
    product = service.create_product(
        sku=read_text("Ma hang") or "",
        barcode=read_text("Barcode", required=False),
        name=read_text("Ten hang") or "",
        unit=read_text("Don vi", required=False) or "cai",
        cost_price=read_int("Gia nhap", minimum=0),
        sale_price=read_int("Gia ban", minimum=0),
        min_stock=read_int("Ton toi thieu", minimum=0),
    )
    print(f"Da tao hang hoa: {product.id} - {product.name}")


def receive_stock(service: PosService) -> None:
    print("\nNhap kho")
    product_id = choose_product(service)
    if product_id is None:
        return
    quantity = read_int("So luong nhap", minimum=1)
    unit_cost = read_int("Gia nhap moi don vi", minimum=0)
    on_hand = service.receive_stock(product_id=product_id, quantity=quantity, unit_cost=unit_cost)
    print(f"Da nhap kho. Ton moi: {on_hand}")


def show_inventory(service: PosService) -> None:
    print("\nTon kho")
    rows = service.inventory()
    if not rows:
        print("Chua co hang hoa.")
        return
    for row in rows:
        warning = " | SAP HET" if row.on_hand <= row.min_stock else ""
        print(f"{row.product_id}. {row.sku} | {row.name} | Ton: {row.on_hand} {row.unit} | Gia: {money(row.sale_price)}{warning}")


def create_sale(service: PosService) -> None:
    print("\nBan hang")
    items: list[SaleLineInput] = []
    while True:
        product_id = choose_product(service)
        if product_id is None:
            break
        quantity = read_int("So luong ban", minimum=1)
        product = service.get_product(product_id)
        use_default = read_text(f"Gia ban mac dinh {money(product.sale_price)}? Enter de dung, nhap N de sua", required=False)
        unit_price = None
        if use_default and use_default.lower() == "n":
            unit_price = read_int("Gia ban", minimum=0)
        discount = read_int("Giam gia dong hang", minimum=0)
        items.append(SaleLineInput(product_id=product_id, quantity=quantity, unit_price=unit_price, discount=discount))
        more = read_text("Them hang khac? y/N", required=False)
        if not more or more.lower() != "y":
            break

    if not items:
        print("Hoa don rong.")
        return

    discount = read_int("Giam gia hoa don", minimum=0)
    paid = read_int("Khach dua tien", minimum=0)
    payment_method = read_text("Hinh thuc thanh toan", required=False) or "cash"
    sale = service.create_sale(items=items, discount=discount, paid=paid, payment_method=payment_method)
    print(f"Da tao hoa don: {sale.invoice_no}")
    print(f"Tong tien: {money(sale.total)}")
    print(f"Khach dua: {money(sale.paid)}")
    print(f"Tra lai: {money(sale.change)}")


def show_sales_today(service: PosService) -> None:
    print("\nHoa don hom nay")
    rows = service.list_sales(date.today(), date.today())
    if not rows:
        print("Hom nay chua co hoa don.")
        return
    for row in rows:
        print(f"{row.id}. {row.invoice_no} | {row.customer_name or 'Khach le'} | {money(row.total)} | {row.created_at}")
    summary = service.revenue_summary(date.today(), date.today())
    print(f"Tong hoa don: {summary.order_count}")
    print(f"Doanh thu: {money(summary.total)}")


def export_reports(service: PosService) -> None:
    export_dir = Path(__file__).parent / "data" / "exports"
    inventory = service.export_inventory_csv(export_dir / "inventory.csv")
    sales = service.export_sales_csv(export_dir / "sales_today.csv", date.today(), date.today())
    print(f"Da xuat ton kho: {inventory}")
    print(f"Da xuat hoa don hom nay: {sales}")


def main() -> None:
    db = Database(DB_PATH)
    db.initialize()
    service = PosService(db)

    actions = {
        "1": add_product,
        "2": receive_stock,
        "3": create_sale,
        "4": show_inventory,
        "5": show_sales_today,
        "6": export_reports,
    }

    while True:
        print("\n=== PERSONAL POS TEST ===")
        print("1. Them hang hoa")
        print("2. Nhap kho")
        print("3. Ban hang")
        print("4. Xem ton kho")
        print("5. Xem hoa don/doanh thu hom nay")
        print("6. Xuat CSV")
        print("0. Thoat")
        try:
            choice = input("Chon: ").strip()
        except EOFError:
            break
        if choice == "0":
            break
        action = actions.get(choice)
        if action is None:
            print("Lua chon khong hop le.")
            continue
        try:
            action(service)
        except NotEnoughStockError as exc:
            print(f"Loi ton kho: {exc}")
        except PosError as exc:
            print(f"Loi du lieu: {exc}")
        except Exception as exc:
            print(f"Loi khong mong muon: {exc}")


if __name__ == "__main__":
    main()

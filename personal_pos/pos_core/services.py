from __future__ import annotations

from collections.abc import Iterable
import csv
from datetime import date, datetime
from pathlib import Path
import sqlite3

from .database import Database
from .models import (
    Customer,
    CustomerBalance,
    InventoryRow,
    Product,
    ProductSalesSummary,
    ProfitSummary,
    RevenueSummary,
    SaleDetail,
    SaleItemRow,
    SaleLineInput,
    SaleListRow,
    SaleResult,
    StockMovementHistory,
)


class PosError(Exception):
    """Base exception for business-rule errors."""


class NotEnoughStockError(PosError):
    pass


class PosService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def stock_history(self, product_id: int, *, only_purchase: bool = False) -> list[StockMovementHistory]:
        sql = """
            SELECT
                id,
                product_id,
                movement_type,
                quantity,
                unit_cost,
                reference_type,
                note,
                created_at
            FROM stock_movements
            WHERE product_id = ?
        """
        params: list[object] = [product_id]

        if only_purchase:
            sql += " AND movement_type = 'purchase'"

        sql += " ORDER BY created_at DESC, id DESC"

        with self.db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [
            StockMovementHistory(
                id=row["id"],
                product_id=row["product_id"],
                movement_type=row["movement_type"],
                quantity=row["quantity"],
                unit_cost=row["unit_cost"],
                reference_type=row["reference_type"],
                note=row["note"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def create_product(
        self,
        *,
        sku: str,
        name: str,
        barcode: str | None = None,
        unit: str = "cai",
        cost_price: int = 0,
        sale_price: int = 0,
        min_stock: int = 0,
    ) -> Product:
        self._require_text(sku, "sku")
        self._require_text(name, "name")
        self._require_money(cost_price, "cost_price")
        self._require_money(sale_price, "sale_price")
        if min_stock < 0:
            raise PosError("min_stock must be >= 0")

        with self.db.session() as conn:
            cur = conn.execute(
                """
                INSERT INTO products
                    (sku, barcode, name, unit, cost_price, sale_price, min_stock)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (sku.strip(), self._clean_optional(barcode), name.strip(), unit.strip(), cost_price, sale_price, min_stock),
            )
            return self.get_product(cur.lastrowid, conn=conn)

    def update_product_price(
        self,
        product_id: int,
        *,
        cost_price: int | None = None,
        sale_price: int | None = None,
    ) -> Product:
        if cost_price is None and sale_price is None:
            raise PosError("No price value provided")
        if cost_price is not None:
            self._require_money(cost_price, "cost_price")
        if sale_price is not None:
            self._require_money(sale_price, "sale_price")

        with self.db.session() as conn:
            current = self.get_product(product_id, conn=conn)
            conn.execute(
                """
                UPDATE products
                SET cost_price = ?, sale_price = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    current.cost_price if cost_price is None else cost_price,
                    current.sale_price if sale_price is None else sale_price,
                    product_id,
                ),
            )
            return self.get_product(product_id, conn=conn)

    def get_product(self, product_id: int, *, conn: sqlite3.Connection | None = None) -> Product:
        own_conn = conn is None
        conn = conn or self.db.connect()
        try:
            row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
            if row is None:
                raise PosError(f"Product not found: {product_id}")
            return Product(
                id=row["id"],
                sku=row["sku"],
                barcode=row["barcode"],
                name=row["name"],
                unit=row["unit"],
                cost_price=row["cost_price"],
                sale_price=row["sale_price"],
                min_stock=row["min_stock"],
                is_active=bool(row["is_active"]),
            )
        finally:
            if own_conn:
                conn.close()

    def find_product(self, text: str) -> list[Product]:
        pattern = f"%{text.strip()}%"
        with self.db.session() as conn:
            rows = conn.execute(
                """
                SELECT * FROM products
                WHERE sku LIKE ? OR barcode LIKE ? OR name LIKE ?
                ORDER BY name
                """,
                (pattern, pattern, pattern),
            ).fetchall()
            return [self._product_from_row(row) for row in rows]

    def find_product_exact(self, text: str) -> Product | None:
        value = text.strip()
        if not value:
            return None
        with self.db.session() as conn:
            row = conn.execute(
                """
                SELECT * FROM products
                WHERE sku = ? OR barcode = ?
                ORDER BY id
                LIMIT 1
                """,
                (value, value),
            ).fetchone()
            return self._product_from_row(row) if row else None

    def create_customer(
        self,
        *,
        code: str,
        name: str,
        phone: str | None = None,
        address: str | None = None,
        note: str | None = None,
    ) -> Customer:
        self._require_text(code, "code")
        self._require_text(name, "name")
        with self.db.session() as conn:
            cur = conn.execute(
                """
                INSERT INTO customers (code, name, phone, address, note)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    code.strip(),
                    name.strip(),
                    self._clean_optional(phone),
                    self._clean_optional(address),
                    self._clean_optional(note),
                ),
            )
            row = conn.execute("SELECT * FROM customers WHERE id = ?", (cur.lastrowid,)).fetchone()
            return self._customer_from_row(row)

    def list_customers(self) -> list[Customer]:
        with self.db.session() as conn:
            rows = conn.execute("SELECT * FROM customers ORDER BY name").fetchall()
            return [self._customer_from_row(row) for row in rows]

    def find_customers(self, text: str) -> list[Customer]:
        pattern = f"%{text.strip()}%"
        with self.db.session() as conn:
            rows = conn.execute(
                """
                SELECT * FROM customers
                WHERE code LIKE ? OR name LIKE ? OR phone LIKE ?
                ORDER BY name
                """,
                (pattern, pattern, pattern),
            ).fetchall()
            return [self._customer_from_row(row) for row in rows]

    def receive_customer_payment(
        self,
        *,
        customer_id: int,
        amount: int,
        payment_method: str = "cash",
        note: str | None = None,
    ) -> int:
        if amount <= 0:
            raise PosError("amount must be > 0")
        with self.db.session() as conn:
            balance = self._customer_balance(customer_id, conn)
            if balance.debt <= 0:
                raise PosError("Customer has no debt")
            if amount > balance.debt:
                raise PosError("Payment cannot exceed customer debt")
            conn.execute(
                """
                INSERT INTO customer_payments (customer_id, amount, payment_method, note)
                VALUES (?, ?, ?, ?)
                """,
                (customer_id, amount, payment_method.strip() or "cash", self._clean_optional(note)),
            )
            return self._customer_balance(customer_id, conn).debt

    def customer_balances(self) -> list[CustomerBalance]:
        with self.db.session() as conn:
            rows = conn.execute("SELECT id FROM customers ORDER BY name").fetchall()
            return [self._customer_balance(row["id"], conn) for row in rows]

    def _customer_balance(self, customer_id: int, conn: sqlite3.Connection) -> CustomerBalance:
        row = conn.execute(
            """
            SELECT
                c.id,
                c.code,
                c.name,
                c.phone,
                COALESCE(SUM(s.total), 0) AS total_sales,
                COALESCE(SUM(s.paid), 0) AS invoice_paid,
                COALESCE((
                    SELECT SUM(cp.amount)
                    FROM customer_payments cp
                    WHERE cp.customer_id = c.id
                ), 0) AS extra_paid
            FROM customers c
            LEFT JOIN sales s ON s.customer_id = c.id
            WHERE c.id = ?
            GROUP BY c.id
            """,
            (customer_id,),
        ).fetchone()
        if row is None:
            raise PosError(f"Customer not found: {customer_id}")
        total_sales = row["total_sales"]
        invoice_paid = row["invoice_paid"]
        extra_paid = row["extra_paid"]
        return CustomerBalance(
            customer_id=row["id"],
            code=row["code"],
            name=row["name"],
            phone=row["phone"],
            total_sales=total_sales,
            invoice_paid=invoice_paid,
            extra_paid=extra_paid,
            debt=max(0, total_sales - invoice_paid - extra_paid),
        )

    def receive_stock(
        self,
        *,
        product_id: int,
        quantity: int,
        unit_cost: int | None = None,
        note: str | None = None,
    ) -> int:
        if quantity <= 0:
            raise PosError("quantity must be > 0")
        with self.db.session() as conn:
            product = self.get_product(product_id, conn=conn)
            cost = product.cost_price if unit_cost is None else unit_cost
            self._require_money(cost, "unit_cost")
            conn.execute(
                """
                INSERT INTO stock_movements
                    (product_id, movement_type, quantity, unit_cost, reference_type, note)
                VALUES (?, 'purchase', ?, ?, 'manual_receive', ?)
                """,
                (product_id, quantity, cost, self._clean_optional(note)),
            )
            return self.get_on_hand(product_id, conn=conn)

    def adjust_stock(self, *, product_id: int, new_quantity: int, note: str | None = None) -> int:
        if new_quantity < 0:
            raise PosError("new_quantity must be >= 0")
        with self.db.session() as conn:
            current = self.get_on_hand(product_id, conn=conn)
            delta = new_quantity - current
            if delta == 0:
                return current
            conn.execute(
                """
                INSERT INTO stock_movements
                    (product_id, movement_type, quantity, reference_type, note)
                VALUES (?, 'adjustment', ?, 'manual_adjustment', ?)
                """,
                (product_id, delta, self._clean_optional(note)),
            )
            return self.get_on_hand(product_id, conn=conn)

    def create_sale(
        self,
        *,
        items: Iterable[SaleLineInput],
        customer_id: int | None = None,
        discount: int = 0,
        paid: int = 0,
        payment_method: str = "cash",
        note: str | None = None,
    ) -> SaleResult:
        item_list = list(items)
        if not item_list:
            raise PosError("Sale must contain at least one item")
        self._require_money(discount, "discount")
        self._require_money(paid, "paid")

        with self.db.session() as conn:
            conn.execute("BEGIN IMMEDIATE")
            invoice_no = self._next_invoice_no(conn)
            prepared = []
            subtotal = 0

            for item in item_list:
                if item.quantity <= 0:
                    raise PosError("Item quantity must be > 0")
                product = self.get_product(item.product_id, conn=conn)
                unit_price = product.sale_price if item.unit_price is None else item.unit_price
                self._require_money(unit_price, "unit_price")
                self._require_money(item.discount, "item.discount")
                line_before_discount = unit_price * item.quantity
                if item.discount > line_before_discount:
                    raise PosError("Item discount cannot exceed line total")
                line_total = line_before_discount - item.discount
                on_hand = self.get_on_hand(item.product_id, conn=conn)
                if on_hand < item.quantity:
                    raise NotEnoughStockError(
                        f"Not enough stock for {product.name}: on hand {on_hand}, requested {item.quantity}"
                    )
                prepared.append((item, product, unit_price, line_total))
                subtotal += line_total

            if discount > subtotal:
                raise PosError("Sale discount cannot exceed subtotal")
            total = subtotal - discount

            cur = conn.execute(
                """
                INSERT INTO sales
                    (invoice_no, customer_id, subtotal, discount, total, paid, payment_method, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    invoice_no,
                    customer_id,
                    subtotal,
                    discount,
                    total,
                    paid,
                    payment_method.strip() or "cash",
                    self._clean_optional(note),
                ),
            )
            sale_id = cur.lastrowid

            for item, product, unit_price, line_total in prepared:
                conn.execute(
                    """
                    INSERT INTO sale_items
                        (sale_id, product_id, quantity, unit_price, discount, line_total)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (sale_id, item.product_id, item.quantity, unit_price, item.discount, line_total),
                )
                conn.execute(
                    """
                    INSERT INTO stock_movements
                        (product_id, movement_type, quantity, unit_cost, reference_type, reference_id)
                    VALUES (?, 'sale', ?, ?, 'sale', ?)
                    """,
                    (item.product_id, -item.quantity, product.cost_price, sale_id),
                )

            return SaleResult(
                id=sale_id,
                invoice_no=invoice_no,
                subtotal=subtotal,
                discount=discount,
                total=total,
                paid=paid,
                change=max(0, paid - total),
            )

    def get_on_hand(self, product_id: int, *, conn: sqlite3.Connection | None = None) -> int:
        own_conn = conn is None
        conn = conn or self.db.connect()
        try:
            row = conn.execute(
                "SELECT COALESCE(SUM(quantity), 0) AS on_hand FROM stock_movements WHERE product_id = ?",
                (product_id,),
            ).fetchone()
            return int(row["on_hand"])
        finally:
            if own_conn:
                conn.close()

    def inventory(self, *, low_stock_only: bool = False) -> list[InventoryRow]:
        with self.db.session() as conn:
            rows = conn.execute(
                """
                SELECT
                    p.id AS product_id,
                    p.sku,
                    p.barcode,
                    p.name,
                    p.unit,
                    p.min_stock,
                    p.sale_price,
                    COALESCE(SUM(sm.quantity), 0) AS on_hand,
                    (
                        SELECT sm2.note
                        FROM stock_movements sm2
                        WHERE sm2.product_id = p.id
                          AND sm2.note IS NOT NULL
                          AND TRIM(sm2.note) <> ''
                        ORDER BY sm2.created_at DESC, sm2.id DESC
                        LIMIT 1
                    ) AS last_stock_note
                FROM products p
                LEFT JOIN stock_movements sm ON sm.product_id = p.id
                WHERE p.is_active = 1
                GROUP BY p.id
                ORDER BY p.name
                """
            ).fetchall()
            result = [
                InventoryRow(
                    product_id=row["product_id"],
                    sku=row["sku"],
                    barcode=row["barcode"],
                    name=row["name"],
                    unit=row["unit"],
                    on_hand=int(row["on_hand"]),
                    min_stock=row["min_stock"],
                    sale_price=row["sale_price"],
                    last_stock_note=row["last_stock_note"],
                )
                for row in rows
            ]
            if low_stock_only:
                return [row for row in result if row.on_hand <= row.min_stock]
            return result

    def list_sales(self, from_date: date, to_date: date) -> list[SaleListRow]:
        if to_date < from_date:
            raise PosError("to_date must be after from_date")
        with self.db.session() as conn:
            rows = conn.execute(
                """
                SELECT
                    s.id,
                    s.invoice_no,
                    c.name AS customer_name,
                    s.total,
                    s.paid,
                    s.payment_method,
                    s.created_at
                FROM sales s
                LEFT JOIN customers c ON c.id = s.customer_id
                WHERE date(s.created_at) BETWEEN ? AND ?
                ORDER BY s.created_at DESC, s.id DESC
                """,
                (from_date.isoformat(), to_date.isoformat()),
            ).fetchall()
            return [
                SaleListRow(
                    id=row["id"],
                    invoice_no=row["invoice_no"],
                    customer_name=row["customer_name"],
                    total=row["total"],
                    paid=row["paid"],
                    payment_method=row["payment_method"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    def get_sale_detail(self, sale_id: int) -> SaleDetail:
        with self.db.session() as conn:
            sale = conn.execute(
                """
                SELECT
                    s.*,
                    c.name AS customer_name
                FROM sales s
                LEFT JOIN customers c ON c.id = s.customer_id
                WHERE s.id = ?
                """,
                (sale_id,),
            ).fetchone()
            if sale is None:
                raise PosError(f"Sale not found: {sale_id}")

            item_rows = conn.execute(
                """
                SELECT
                    si.product_id,
                    p.sku,
                    p.name,
                    si.quantity,
                    si.unit_price,
                    si.discount,
                    si.line_total
                FROM sale_items si
                JOIN products p ON p.id = si.product_id
                WHERE si.sale_id = ?
                ORDER BY si.id
                """,
                (sale_id,),
            ).fetchall()
            items = [
                SaleItemRow(
                    product_id=row["product_id"],
                    sku=row["sku"],
                    name=row["name"],
                    quantity=row["quantity"],
                    unit_price=row["unit_price"],
                    discount=row["discount"],
                    line_total=row["line_total"],
                )
                for row in item_rows
            ]
            return SaleDetail(
                id=sale["id"],
                invoice_no=sale["invoice_no"],
                customer_name=sale["customer_name"],
                subtotal=sale["subtotal"],
                discount=sale["discount"],
                total=sale["total"],
                paid=sale["paid"],
                payment_method=sale["payment_method"],
                note=sale["note"],
                created_at=sale["created_at"],
                items=items,
            )

    def revenue_summary(self, from_date: date, to_date: date) -> RevenueSummary:
        if to_date < from_date:
            raise PosError("to_date must be after from_date")
        from_text = from_date.isoformat()
        to_text = to_date.isoformat()
        with self.db.session() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS order_count,
                    COALESCE(SUM(subtotal), 0) AS subtotal,
                    COALESCE(SUM(discount), 0) AS discount,
                    COALESCE(SUM(total), 0) AS total,
                    COALESCE(SUM(paid), 0) AS paid
                FROM sales
                WHERE date(created_at) BETWEEN ? AND ?
                """,
                (from_text, to_text),
            ).fetchone()
            return RevenueSummary(
                from_date=from_text,
                to_date=to_text,
                order_count=row["order_count"],
                subtotal=row["subtotal"],
                discount=row["discount"],
                total=row["total"],
                paid=row["paid"],
            )

    def profit_summary(self, from_date: date, to_date: date) -> ProfitSummary:
        if to_date < from_date:
            raise PosError("to_date must be after from_date")
        with self.db.session() as conn:
            row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(item_totals.revenue), 0) AS revenue_before_invoice_discount,
                    COALESCE(SUM(item_totals.cost), 0) AS cost,
                    COALESCE(SUM(item_totals.invoice_discount), 0) AS invoice_discount
                FROM (
                    SELECT
                        s.id,
                        SUM(si.line_total) AS revenue,
                        SUM(si.quantity * COALESCE(sm.unit_cost, p.cost_price)) AS cost,
                        s.discount AS invoice_discount
                    FROM sales s
                    JOIN sale_items si ON si.sale_id = s.id
                    JOIN products p ON p.id = si.product_id
                    LEFT JOIN stock_movements sm
                        ON sm.reference_type = 'sale'
                        AND sm.reference_id = s.id
                        AND sm.product_id = si.product_id
                    WHERE date(s.created_at) BETWEEN ? AND ?
                    GROUP BY s.id
                ) AS item_totals
                """,
                (from_date.isoformat(), to_date.isoformat()),
            ).fetchone()
            revenue = row["revenue_before_invoice_discount"] - row["invoice_discount"]
            cost = row["cost"]
            return ProfitSummary(
                from_date=from_date.isoformat(),
                to_date=to_date.isoformat(),
                revenue=revenue,
                cost=cost,
                gross_profit=revenue - cost,
            )

    def top_selling_products(self, from_date: date, to_date: date, *, limit: int = 10) -> list[ProductSalesSummary]:
        if to_date < from_date:
            raise PosError("to_date must be after from_date")
        with self.db.session() as conn:
            rows = conn.execute(
                """
                SELECT
                    p.id AS product_id,
                    p.sku,
                    p.name,
                    SUM(si.quantity) AS quantity,
                    SUM(si.line_total) AS revenue,
                    SUM(si.quantity * COALESCE(sm.unit_cost, p.cost_price)) AS cost
                FROM sale_items si
                JOIN sales s ON s.id = si.sale_id
                JOIN products p ON p.id = si.product_id
                LEFT JOIN stock_movements sm
                    ON sm.reference_type = 'sale'
                    AND sm.reference_id = s.id
                    AND sm.product_id = si.product_id
                WHERE date(s.created_at) BETWEEN ? AND ?
                GROUP BY p.id
                ORDER BY quantity DESC, revenue DESC
                LIMIT ?
                """,
                (from_date.isoformat(), to_date.isoformat(), limit),
            ).fetchall()
            return [
                ProductSalesSummary(
                    product_id=row["product_id"],
                    sku=row["sku"],
                    name=row["name"],
                    quantity=row["quantity"],
                    revenue=row["revenue"],
                    cost=row["cost"],
                    gross_profit=row["revenue"] - row["cost"],
                )
                for row in rows
            ]

    def export_inventory_csv(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(["SKU", "Barcode", "Ten hang", "Don vi", "Ton kho", "Ton toi thieu", "Gia ban"])
            for row in self.inventory():
                writer.writerow(
                    [
                        row.sku,
                        row.barcode or "",
                        row.name,
                        row.unit,
                        row.on_hand,
                        row.min_stock,
                        row.sale_price,
                    ]
                )
        return output

    def export_sales_csv(self, path: str | Path, from_date: date, to_date: date) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(["Ma hoa don", "Khach hang", "Tong tien", "Da thu", "Thanh toan", "Ngay tao"])
            for row in self.list_sales(from_date, to_date):
                writer.writerow(
                    [
                        row.invoice_no,
                        row.customer_name or "",
                        row.total,
                        row.paid,
                        row.payment_method,
                        row.created_at,
                    ]
                )
        return output

    def _next_invoice_no(self, conn: sqlite3.Connection) -> str:
        prefix = datetime.now().strftime("HD%Y%m%d")
        row = conn.execute(
            "SELECT invoice_no FROM sales WHERE invoice_no LIKE ? ORDER BY invoice_no DESC LIMIT 1",
            (f"{prefix}%",),
        ).fetchone()
        if row is None:
            number = 1
        else:
            number = int(row["invoice_no"][-4:]) + 1
        return f"{prefix}{number:04d}"

    def _product_from_row(self, row: sqlite3.Row) -> Product:
        return Product(
            id=row["id"],
            sku=row["sku"],
            barcode=row["barcode"],
            name=row["name"],
            unit=row["unit"],
            cost_price=row["cost_price"],
            sale_price=row["sale_price"],
            min_stock=row["min_stock"],
            is_active=bool(row["is_active"]),
        )

    def _customer_from_row(self, row: sqlite3.Row) -> Customer:
        return Customer(
            id=row["id"],
            code=row["code"],
            name=row["name"],
            phone=row["phone"],
            address=row["address"],
            note=row["note"],
        )

    def _require_text(self, value: str, field_name: str) -> None:
        if not value or not value.strip():
            raise PosError(f"{field_name} is required")

    def _require_money(self, value: int, field_name: str) -> None:
        if value < 0:
            raise PosError(f"{field_name} must be >= 0")

    def _clean_optional(self, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

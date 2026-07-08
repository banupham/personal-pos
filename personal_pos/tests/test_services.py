from __future__ import annotations

from datetime import date
from tempfile import TemporaryDirectory
import unittest

from personal_pos.pos_core import Database, PosService
from personal_pos.pos_core.models import SaleLineInput
from personal_pos.pos_core.services import NotEnoughStockError


class PosServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.db = Database(f"{self.tmp.name}/test.db")
        self.db.initialize()
        self.service = PosService(self.db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_receive_stock_and_sale_reduce_inventory(self) -> None:
        product = self.service.create_product(
            sku="A001",
            name="Ao thun",
            cost_price=50000,
            sale_price=90000,
        )

        self.service.receive_stock(product_id=product.id, quantity=10)
        sale = self.service.create_sale(
            items=[SaleLineInput(product_id=product.id, quantity=3)],
            paid=300000,
        )

        self.assertEqual(sale.total, 270000)
        self.assertEqual(self.service.get_on_hand(product.id), 7)

    def test_sale_cannot_exceed_stock(self) -> None:
        product = self.service.create_product(sku="B001", name="Quan jean", sale_price=150000)
        self.service.receive_stock(product_id=product.id, quantity=2)

        with self.assertRaises(NotEnoughStockError):
            self.service.create_sale(items=[SaleLineInput(product_id=product.id, quantity=3)])

    def test_revenue_summary_counts_sales(self) -> None:
        product = self.service.create_product(sku="C001", name="Non", sale_price=50000)
        self.service.receive_stock(product_id=product.id, quantity=5)
        sale = self.service.create_sale(
            items=[SaleLineInput(product_id=product.id, quantity=2)],
            discount=10000,
            paid=90000,
        )

        summary = self.service.revenue_summary(date.today(), date.today())

        self.assertEqual(summary.order_count, 1)
        self.assertEqual(summary.subtotal, 100000)
        self.assertEqual(summary.discount, 10000)
        self.assertEqual(summary.total, 90000)

        rows = self.service.list_sales(date.today(), date.today())
        detail = self.service.get_sale_detail(sale.id)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].invoice_no, sale.invoice_no)
        self.assertEqual(detail.invoice_no, sale.invoice_no)
        self.assertEqual(len(detail.items), 1)
        self.assertEqual(detail.items[0].sku, "C001")

    def test_export_csv_files(self) -> None:
        product = self.service.create_product(sku="D001", name="Banh mi", sale_price=15000)
        self.service.receive_stock(product_id=product.id, quantity=10)
        self.service.create_sale(items=[SaleLineInput(product_id=product.id, quantity=1)], paid=15000)

        inventory_path = self.service.export_inventory_csv(f"{self.tmp.name}/inventory.csv")
        sales_path = self.service.export_sales_csv(f"{self.tmp.name}/sales.csv", date.today(), date.today())

        self.assertTrue(inventory_path.exists())
        self.assertTrue(sales_path.exists())
        self.assertIn("Banh mi", inventory_path.read_text(encoding="utf-8-sig"))
        self.assertIn("HD", sales_path.read_text(encoding="utf-8-sig"))

    def test_customer_debt_and_payment(self) -> None:
        customer = self.service.create_customer(code="KH-DEBT", name="Khach no")
        product = self.service.create_product(sku="E001", name="Sua", cost_price=7000, sale_price=12000)
        self.service.receive_stock(product_id=product.id, quantity=10)

        self.service.create_sale(
            customer_id=customer.id,
            items=[SaleLineInput(product_id=product.id, quantity=5)],
            paid=20000,
        )

        balance = self.service.customer_balances()[0]
        self.assertEqual(balance.debt, 40000)

        remaining = self.service.receive_customer_payment(customer_id=customer.id, amount=15000)

        self.assertEqual(remaining, 25000)

    def test_profit_and_top_selling_products(self) -> None:
        product = self.service.create_product(sku="F001", name="Nuoc suoi", cost_price=4000, sale_price=10000)
        self.service.receive_stock(product_id=product.id, quantity=20, unit_cost=4000)

        self.service.create_sale(
            items=[SaleLineInput(product_id=product.id, quantity=3)],
            discount=2000,
            paid=28000,
        )

        profit = self.service.profit_summary(date.today(), date.today())
        top = self.service.top_selling_products(date.today(), date.today())

        self.assertEqual(profit.revenue, 28000)
        self.assertEqual(profit.cost, 12000)
        self.assertEqual(profit.gross_profit, 16000)
        self.assertEqual(top[0].sku, "F001")
        self.assertEqual(top[0].quantity, 3)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    id: int
    sku: str
    barcode: str | None
    name: str
    unit: str
    cost_price: int
    sale_price: int
    min_stock: int
    is_active: bool


@dataclass(frozen=True)
class Customer:
    id: int
    code: str
    name: str
    phone: str | None
    address: str | None
    note: str | None


@dataclass(frozen=True)
class CustomerBalance:
    customer_id: int
    code: str
    name: str
    phone: str | None
    total_sales: int
    invoice_paid: int
    extra_paid: int
    debt: int


@dataclass(frozen=True)
class SaleLineInput:
    product_id: int
    quantity: int
    unit_price: int | None = None
    discount: int = 0


@dataclass(frozen=True)
class SaleResult:
    id: int
    invoice_no: str
    subtotal: int
    discount: int
    total: int
    paid: int
    change: int


@dataclass(frozen=True)
class SaleListRow:
    id: int
    invoice_no: str
    customer_name: str | None
    total: int
    paid: int
    payment_method: str
    created_at: str


@dataclass(frozen=True)
class SaleItemRow:
    product_id: int
    sku: str
    name: str
    quantity: int
    unit_price: int
    discount: int
    line_total: int


@dataclass(frozen=True)
class SaleDetail:
    id: int
    invoice_no: str
    customer_name: str | None
    subtotal: int
    discount: int
    total: int
    paid: int
    payment_method: str
    note: str | None
    created_at: str
    items: list[SaleItemRow]


@dataclass(frozen=True)
class InventoryRow:
    product_id: int
    sku: str
    barcode: str | None
    name: str
    unit: str
    on_hand: int
    min_stock: int
    sale_price: int


@dataclass(frozen=True)
class RevenueSummary:
    from_date: str
    to_date: str
    order_count: int
    subtotal: int
    discount: int
    total: int
    paid: int


@dataclass(frozen=True)
class ProfitSummary:
    from_date: str
    to_date: str
    revenue: int
    cost: int
    gross_profit: int


@dataclass(frozen=True)
class ProductSalesSummary:
    product_id: int
    sku: str
    name: str
    quantity: int
    revenue: int
    cost: int
    gross_profit: int

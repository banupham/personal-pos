from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    from . import backup, updater
    from .pos_core import Database, PosService
    from .pos_core.models import InventoryRow, SaleLineInput
    from .pos_core.services import NotEnoughStockError, PosError
    from .version import __version__
except ImportError:
    from personal_pos import backup, updater
    from personal_pos.pos_core import Database, PosService
    from personal_pos.pos_core.models import InventoryRow, SaleLineInput
    from personal_pos.pos_core.services import NotEnoughStockError, PosError
    from personal_pos.version import __version__


APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).parent
DB_PATH = APP_DIR / "data" / "app_pos.db"


def money(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def parse_int(value: str, field_name: str, minimum: int = 0) -> int:
    cleaned = value.strip().replace(".", "").replace(",", "")
    if not cleaned:
        raise PosError(f"Vui lòng nhập {field_name}")
    try:
        number = int(cleaned)
    except ValueError as exc:
        raise PosError(f"{field_name} phải là số") from exc
    if number < minimum:
        raise PosError(f"{field_name} phải >= {minimum}")
    return number


class PosApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Personal POS - Quản lý bán hàng cá nhân")
        self.geometry("1180x720")
        self.minsize(1040, 640)

        db = Database(DB_PATH)
        db.initialize()
        self.service = PosService(db)
        self.cart: list[dict[str, int | str]] = []

        self.configure(bg="#f3f5f7")
        self._configure_style()
        self._build_layout()
        self.backup_config = backup.load_config()
        self.auto_backup_var = tk.BooleanVar(value=self.backup_config.auto_backup_on_exit)
        self._install_backup_menu()
        self.protocol("WM_DELETE_WINDOW", self.close_with_optional_backup)
        self.refresh_all()

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#f3f5f7")
        style.configure("Panel.TFrame", background="#ffffff", relief="flat")
        style.configure("Sidebar.TFrame", background="#0f6c5f")
        style.configure("Sidebar.TButton", background="#0f6c5f", foreground="#ffffff", anchor="w", padding=(16, 12))
        style.map("Sidebar.TButton", background=[("active", "#14806f")])
        style.configure("Accent.TButton", background="#0f8a73", foreground="#ffffff", padding=(12, 8))
        style.map("Accent.TButton", background=[("active", "#0b735f")])
        style.configure("Danger.TButton", background="#c0392b", foreground="#ffffff", padding=(12, 8))
        style.configure("Title.TLabel", background="#ffffff", foreground="#17202a", font=("Segoe UI", 16, "bold"))
        style.configure("Subtle.TLabel", background="#ffffff", foreground="#667085")
        style.configure("Metric.TLabel", background="#ffffff", foreground="#0f6c5f", font=("Segoe UI", 18, "bold"))
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

    def _build_layout(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(self, style="Sidebar.TFrame", width=210)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)

        brand = tk.Label(
            sidebar,
            text="PERSONAL POS",
            bg="#0f6c5f",
            fg="#ffffff",
            font=("Segoe UI", 16, "bold"),
            padx=18,
            pady=22,
            anchor="w",
        )
        brand.pack(fill="x")

        for text, page in [
            ("Bán hàng", "sales"),
            ("Hàng hóa", "products"),
            ("Nhập kho", "stock"),
            ("Báo cáo", "reports"),
        ]:
            ttk.Button(sidebar, text=text, style="Sidebar.TButton", command=lambda p=page: self.show_page(p)).pack(fill="x")
        ttk.Button(sidebar, text="Công Nợ", style="Sidebar.TButton", command=lambda: self.show_page("debts")).pack(fill="x")
        ttk.Button(sidebar, text="Update", style="Sidebar.TButton", command=lambda: self.show_page("updates")).pack(fill="x")

        self.content = ttk.Frame(self, padding=16)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)

        self.pages: dict[str, ttk.Frame] = {}
        self._build_sales_page()
        self._build_products_page()
        self._build_stock_page()
        self._build_debts_page()
        self._build_reports_page()
        self._build_updates_page()
        self.show_page("sales")

    def _new_page(self, name: str) -> ttk.Frame:
        page = ttk.Frame(self.content)
        page.grid(row=0, column=0, sticky="nsew")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)
        self.pages[name] = page
        return page

    def _panel(self, parent: ttk.Frame, **grid: object) -> ttk.Frame:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=14)
        panel.grid(sticky="nsew", **grid)
        return panel

    def _build_sales_page(self) -> None:
        page = self._new_page("sales")
        page.columnconfigure(0, weight=2)
        page.columnconfigure(1, weight=3)

        left = self._panel(page, row=0, column=0, rowspan=2, padx=(0, 12), pady=0)
        right = self._panel(page, row=0, column=1, rowspan=2, pady=0)
        left.columnconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)

        ttk.Label(left, text="Tìm hàng để bán", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        search_row = ttk.Frame(left, style="Panel.TFrame")
        search_row.grid(row=1, column=0, sticky="ew", pady=(12, 8))
        search_row.columnconfigure(0, weight=1)
        self.sale_search_var = tk.StringVar()
        sale_search_entry = ttk.Entry(search_row, textvariable=self.sale_search_var)
        sale_search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        sale_search_entry.bind("<Return>", self.quick_add_search_product)
        ttk.Button(search_row, text="Tìm", style="Accent.TButton", command=self.search_sale_products).grid(row=0, column=1)

        self.sale_product_tree = ttk.Treeview(left, columns=("id", "sku", "name", "stock", "price"), show="headings", height=13)
        for col, title, width in [
            ("id", "ID", 48),
            ("sku", "Mã", 100),
            ("name", "Tên hàng", 190),
            ("stock", "Tồn", 70),
            ("price", "Giá", 90),
        ]:
            self.sale_product_tree.heading(col, text=title)
            self.sale_product_tree.column(col, width=width, anchor="w")
        self.sale_product_tree.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        self.sale_product_tree.bind("<Double-1>", lambda event: self.add_selected_to_cart())
        left.rowconfigure(2, weight=1)

        form = ttk.Frame(left, style="Panel.TFrame")
        form.grid(row=3, column=0, sticky="ew")
        for i in range(4):
            form.columnconfigure(i, weight=1)
        self.sale_qty_var = tk.StringVar(value="1")
        self.sale_price_var = tk.StringVar()
        self.sale_line_discount_var = tk.StringVar(value="0")
        ttk.Label(form, text="SL", style="Subtle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(form, text="Giá bán", style="Subtle.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(form, text="Giảm dòng", style="Subtle.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Entry(form, textvariable=self.sale_qty_var, width=8).grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Entry(form, textvariable=self.sale_price_var, width=12).grid(row=1, column=1, sticky="ew", padx=(0, 8))
        ttk.Entry(form, textvariable=self.sale_line_discount_var, width=12).grid(row=1, column=2, sticky="ew", padx=(0, 8))
        ttk.Button(form, text="Thêm vào hóa đơn", style="Accent.TButton", command=self.add_selected_to_cart).grid(row=1, column=3, sticky="ew")

        ttk.Label(right, text="Hóa đơn bán hàng", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.cart_tree = ttk.Treeview(right, columns=("sku", "name", "qty", "price", "discount", "total"), show="headings")
        for col, title, width in [
            ("sku", "Mã", 95),
            ("name", "Tên hàng", 240),
            ("qty", "SL", 55),
            ("price", "Giá", 95),
            ("discount", "Giảm", 85),
            ("total", "Thành tiền", 110),
        ]:
            self.cart_tree.heading(col, text=title)
            self.cart_tree.column(col, width=width, anchor="w")
        self.cart_tree.grid(row=2, column=0, sticky="nsew", pady=(12, 10))

        controls = ttk.Frame(right, style="Panel.TFrame")
        controls.grid(row=3, column=0, sticky="ew")
        for i in range(5):
            controls.columnconfigure(i, weight=1)
        self.invoice_discount_var = tk.StringVar(value="0")
        self.paid_var = tk.StringVar(value="0")
        self.sale_customer_id_var = tk.StringVar()
        self.total_var = tk.StringVar(value="0 VND")
        ttk.Label(controls, text="Giảm hóa đơn", style="Subtle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(controls, text="Khách đưa", style="Subtle.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(controls, text="Tổng tiền", style="Subtle.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Entry(controls, textvariable=self.invoice_discount_var).grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Entry(controls, textvariable=self.paid_var).grid(row=1, column=1, sticky="ew", padx=(0, 8))
        ttk.Label(controls, textvariable=self.total_var, style="Metric.TLabel").grid(row=1, column=2, sticky="w", padx=(0, 8))
        ttk.Button(controls, text="Xóa Dòng", command=self.remove_cart_item).grid(row=1, column=3, sticky="ew", padx=(0, 8))
        ttk.Button(controls, text="Thanh toán", style="Accent.TButton", command=self.checkout).grid(row=1, column=4, sticky="ew")

        ttk.Label(controls, text="ID Khách Nợ (DK id khách ở công nợ)", style="Subtle.TLabel").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(controls, textvariable=self.sale_customer_id_var).grid(row=3, column=0, columnspan=2, sticky="ew", padx=(0, 8))

    def _build_products_page(self) -> None:
        page = self._new_page("products")
        page.columnconfigure(0, weight=1)
        page.columnconfigure(1, weight=2)

        form = self._panel(page, row=0, column=0, padx=(0, 12), pady=0)
        table_panel = self._panel(page, row=0, column=1, pady=0)
        table_panel.columnconfigure(0, weight=1)
        table_panel.rowconfigure(1, weight=1)

        ttk.Label(form, text="Thêm hàng hóa", style="Title.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 12))
        self.product_vars: dict[str, tk.StringVar] = {}
        fields = [
            ("sku", "Mã hàng"),
            ("barcode", "Barcode"),
            ("name", "Tên hàng"),
            ("unit", "Đơn vị"),
            ("cost_price", "Giá nhập"),
            ("sale_price", "Giá bán"),
            ("min_stock", "Tồn tối thiểu"),
        ]
        for idx, (key, label) in enumerate(fields, start=1):
            ttk.Label(form, text=label, style="Subtle.TLabel").grid(row=idx * 2 - 1, column=0, sticky="w")
            var = tk.StringVar(value="cai" if key == "unit" else "0" if key in {"cost_price", "sale_price", "min_stock"} else "")
            self.product_vars[key] = var
            ttk.Entry(form, textvariable=var).grid(row=idx * 2, column=0, sticky="ew", pady=(0, 8))
        form.columnconfigure(0, weight=1)
        ttk.Button(form, text="Lưu hàng hóa", style="Accent.TButton", command=self.add_product).grid(row=15, column=0, sticky="ew", pady=(8, 0))

        ttk.Label(table_panel, text="Danh sách hàng hóa", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.inventory_tree = self._inventory_tree(table_panel)
        self.inventory_tree.grid(row=1, column=0, sticky="nsew", pady=(12, 0))

    def _build_stock_page(self) -> None:
        page = self._new_page("stock")
        page.columnconfigure(0, weight=1)
        page.columnconfigure(1, weight=2)

        form = self._panel(page, row=0, column=0, padx=(0, 12), pady=0)
        table_panel = self._panel(page, row=0, column=1, pady=0)
        table_panel.columnconfigure(0, weight=1)
        table_panel.rowconfigure(1, weight=1)

        ttk.Label(form, text="Nhập kho", style="Title.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 12))
        self.stock_product_id_var = tk.StringVar()
        self.stock_qty_var = tk.StringVar(value="1")
        self.stock_cost_var = tk.StringVar(value="0")
        self.stock_note_var = tk.StringVar()
        for idx, (label, var) in enumerate(
            [
                ("ID hàng hóa", self.stock_product_id_var),
                ("Số lượng nhập", self.stock_qty_var),
                ("Giá nhập", self.stock_cost_var),
                ("Ghi chú", self.stock_note_var),
            ],
            start=1,
        ):
            ttk.Label(form, text=label, style="Subtle.TLabel").grid(row=idx * 2 - 1, column=0, sticky="w")
            ttk.Entry(form, textvariable=var).grid(row=idx * 2, column=0, sticky="ew", pady=(0, 8))
        form.columnconfigure(0, weight=1)
        ttk.Button(form, text="Nhập kho", style="Accent.TButton", command=self.receive_stock).grid(row=9, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(form,text="Xem lịch sử nhập kho",command=self.show_stock_history,).grid(row=10, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Label(form, text="Mẹo: xem ID hàng hóa ở bảng bên phải.", style="Subtle.TLabel").grid(row=11, column=0, sticky="w", pady=(12, 0))

        ttk.Label(table_panel, text="Tồn kho hiện tại", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.stock_inventory_tree = self._inventory_tree(table_panel)
        self.stock_inventory_tree.bind("<Double-1>", lambda event: self.show_stock_history())
        self.stock_inventory_tree.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.stock_inventory_tree.bind("<<TreeviewSelect>>", self.fill_stock_product_id)

    def show_stock_history(self) -> None:
        product_id_text = self.stock_product_id_var.get().strip()

        if not product_id_text:
            messagebox.showwarning("Thiếu sản phẩm", "Hãy chọn một sản phẩm trong bảng tồn kho trước.")
            return

        try:
            product_id = int(product_id_text)
        except ValueError:
            messagebox.showerror("Sai dữ liệu", "ID sản phẩm không hợp lệ.")
            return

        rows = self.service.stock_history(product_id, only_purchase=True)

        win = tk.Toplevel(self)
        win.title(f"Lịch sử tồn kho - Sản phẩm ID {product_id}")
        win.geometry("850x420")

        columns = ("time", "type", "qty", "cost", "ref", "note")

        tree = ttk.Treeview(win, columns=columns, show="headings")
        tree.pack(fill="both", expand=True, padx=10, pady=10)

        headers = [
            ("time", "Thời gian", 150),
            ("type", "Loại", 110),
            ("qty", "Số lượng", 90),
            ("cost", "Giá nhập", 110),
            ("ref", "Nguồn", 140),
            ("note", "Ghi chú", 300),
        ]

        for col, title, width in headers:
            tree.heading(col, text=title)
            tree.column(col, width=width, anchor="w")

        for row in rows:
            tree.insert(
                "",
                "end",
                values=(
                    row.created_at,
                    row.movement_type,
                    row.quantity,
                    money(row.unit_cost) if row.unit_cost is not None else "",
                    row.reference_type or "",
                    row.note or "",
                ),
            )

    def _build_debts_page(self) -> None:
        page = self._new_page("debts")
        page.columnconfigure(0, weight=1)
        page.columnconfigure(1, weight=2)

        form = self._panel(page, row=0, column=0, padx=(0, 12), pady=0)
        table_panel = self._panel(page, row=0, column=1, pady=0)
        table_panel.columnconfigure(0, weight=1)
        table_panel.rowconfigure(1, weight=1)

        ttk.Label(form, text="Khách Hàng / Công Nợ", style="Title.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 12))
        self.customer_code_var = tk.StringVar()
        self.customer_name_var = tk.StringVar()
        self.customer_phone_var = tk.StringVar()
        self.customer_pay_id_var = tk.StringVar()
        self.customer_pay_amount_var = tk.StringVar(value="0")

        for idx, (label, var) in enumerate(
            [
                ("Mã khách", self.customer_code_var),
                ("Tên Khách", self.customer_name_var),
                ("Điện Thoại", self.customer_phone_var),
                ("ID khách thu nợ (dành cho thu nợ)", self.customer_pay_id_var),
                ("Số tiền nợ", self.customer_pay_amount_var),
            ],
            start=1,
        ):
            ttk.Label(form, text=label, style="Subtle.TLabel").grid(row=idx * 2 - 1, column=0, sticky="w")
            ttk.Entry(form, textvariable=var).grid(row=idx * 2, column=0, sticky="ew", pady=(0, 8))
        form.columnconfigure(0, weight=1)
        ttk.Button(form, text="Thêm Khách", style="Accent.TButton", command=self.add_customer).grid(row=11, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(form, text="Thu Nợ", style="Accent.TButton", command=self.receive_debt_payment).grid(row=12, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(form, text="Mẹo: nhập ID ở màn hình bán hàng.", style="Subtle.TLabel").grid(row=13, column=0, sticky="w", pady=(12, 0))

        ttk.Label(table_panel, text="Danh sách công nợ", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.debt_tree = ttk.Treeview(
            table_panel,
            columns=("id", "code", "name", "phone", "sales", "paid", "debt"),
            show="headings",
        )
        for col, title, width in [
            ("id", "ID", 55),
            ("code", "Ma", 90),
            ("name", "Ten khach", 180),
            ("phone", "Dien thoai", 110),
            ("sales", "Tong mua", 110),
            ("paid", "Da tra", 110),
            ("debt", "Con no", 110),
        ]:
            self.debt_tree.heading(col, text=title)
            self.debt_tree.column(col, width=width, anchor="w")
        self.debt_tree.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.debt_tree.bind("<<TreeviewSelect>>", self.fill_debt_customer_id)

    def _build_reports_page(self) -> None:
        page = self._new_page("reports")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)

        top = self._panel(page, row=0, column=0, pady=(0, 12))
        top.columnconfigure(3, weight=1)
        self.revenue_var = tk.StringVar(value="0 VND")
        self.orders_var = tk.StringVar(value="0")
        self.profit_var = tk.StringVar(value="0 VND")
        ttk.Label(top, text="Doanh thu hôm nay", style="Subtle.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 22))
        ttk.Label(top, textvariable=self.revenue_var, style="Metric.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 22))
        ttk.Label(top, text="Số hóa đơn", style="Subtle.TLabel").grid(row=0, column=1, sticky="w", padx=(0, 22))
        ttk.Label(top, textvariable=self.orders_var, style="Metric.TLabel").grid(row=1, column=1, sticky="w", padx=(0, 22))
        ttk.Label(top, text="Loi nhuan gop", style="Subtle.TLabel").grid(row=0, column=4, sticky="w", padx=(0, 22))
        ttk.Label(top, textvariable=self.profit_var, style="Metric.TLabel").grid(row=1, column=4, sticky="w", padx=(0, 22))
        ttk.Button(top, text="Làm mới", command=self.refresh_reports).grid(row=1, column=2, padx=(0, 8))
        ttk.Button(top, text="Xuất CSV", style="Accent.TButton", command=self.export_csv).grid(row=1, column=3, sticky="w")

        table_panel = self._panel(page, row=1, column=0)
        table_panel.columnconfigure(0, weight=1)
        table_panel.rowconfigure(1, weight=1)
        ttk.Label(table_panel, text="Hóa đơn hôm nay", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.sales_tree = ttk.Treeview(table_panel, columns=("id", "invoice", "customer", "total", "paid", "time"), show="headings")
        for col, title, width in [
            ("id", "ID", 60),
            ("invoice", "Hóa đơn", 150),
            ("customer", "Khách hàng", 180),
            ("total", "Tổng", 120),
            ("paid", "Đã thu", 120),
            ("time", "Thời gian", 180),
        ]:
            self.sales_tree.heading(col, text=title)
            self.sales_tree.column(col, width=width, anchor="w")
        self.sales_tree.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        ttk.Label(table_panel, text="Hang ban chay", style="Title.TLabel").grid(row=2, column=0, sticky="w", pady=(14, 0))
        self.top_products_tree = ttk.Treeview(
            table_panel,
            columns=("sku", "name", "qty", "revenue", "profit"),
            show="headings",
            height=6,
        )
        for col, title, width in [
            ("sku", "Ma", 110),
            ("name", "Ten hang", 240),
            ("qty", "SL ban", 80),
            ("revenue", "Doanh thu", 120),
            ("profit", "Loi nhuan", 120),
        ]:
            self.top_products_tree.heading(col, text=title)
            self.top_products_tree.column(col, width=width, anchor="w")
        self.top_products_tree.grid(row=3, column=0, sticky="nsew", pady=(8, 0))

    def _build_updates_page(self) -> None:
        page = self._new_page("updates")
        page.columnconfigure(0, weight=1)

        panel = self._panel(page, row=0, column=0, pady=0)
        panel.columnconfigure(0, weight=1)

        ttk.Label(panel, text="Cap nhat qua GitHub", style="Title.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 12))
        ttk.Label(panel, text=f"Phien ban hien tai: {__version__}", style="Subtle.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Label(panel, text="Manifest URL", style="Subtle.TLabel").grid(row=2, column=0, sticky="w", pady=(12, 0))

        self.update_manifest_url_var = tk.StringVar(value=self._load_manifest_url_for_ui())
        ttk.Entry(panel, textvariable=self.update_manifest_url_var).grid(row=3, column=0, sticky="ew", pady=(0, 8))

        button_row = ttk.Frame(panel, style="Panel.TFrame")
        button_row.grid(row=4, column=0, sticky="ew", pady=(4, 12))
        ttk.Button(button_row, text="Luu URL", command=self.save_update_url).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(button_row, text="Kiem tra", style="Accent.TButton", command=self.check_update).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(button_row, text="Tai va cai", style="Accent.TButton", command=self.install_checked_update).grid(row=0, column=2)

        self.update_status_var = tk.StringVar(value="Chua kiem tra cap nhat.")
        ttk.Label(panel, textvariable=self.update_status_var, style="Subtle.TLabel", wraplength=820).grid(row=5, column=0, sticky="ew")
        self.update_notes = tk.Text(panel, height=12, wrap="word")
        self.update_notes.grid(row=6, column=0, sticky="nsew", pady=(12, 0))
        panel.rowconfigure(6, weight=1)
        self.pending_update_check: updater.UpdateCheck | None = None

    def _inventory_tree(self, parent: ttk.Frame) -> ttk.Treeview:
        tree = ttk.Treeview(parent, columns=("id", "sku", "barcode", "name", "stock", "min", "price","note"), show="headings")
        for col, title, width in [
            ("id", "ID", 55),
            ("sku", "Mã", 110),
            ("barcode", "Barcode", 120),
            ("name", "Tên hàng", 230),
            ("stock", "Tồn", 80),
            ("min", "Tối thiểu", 85),
            ("price", "Giá bán", 110),
            ("note", "Ghi chú nhập kho", 220),
        ]:
            tree.heading(col, text=title)
            tree.column(col, width=width, anchor="w")
        return tree

    def show_page(self, name: str) -> None:
        for page in self.pages.values():
            page.grid_remove()
        self.pages[name].grid()
        self.refresh_all()

    def refresh_all(self) -> None:
        self.refresh_inventory()
        self.search_sale_products()
        self.refresh_cart()
        self.refresh_debts()
        self.refresh_reports()

    def refresh_inventory(self) -> None:
        rows = self.service.inventory()
        for tree in [getattr(self, "inventory_tree", None), getattr(self, "stock_inventory_tree", None)]:
            if tree is None:
                continue
            tree.delete(*tree.get_children())
            for row in rows:
                tree.insert("", "end", values=self._inventory_values(row))

    def _inventory_values(self, row: InventoryRow) -> tuple[object, ...]:
        return (row.product_id, row.sku, row.barcode or "", row.name, row.on_hand, row.min_stock, money(row.sale_price),row.last_stock_note or "",)

    def search_sale_products(self) -> None:
        if not hasattr(self, "sale_product_tree"):
            return
        keyword = self.sale_search_var.get().strip()
        rows = self.service.inventory()
        if keyword:
            keyword_lower = keyword.lower()
            rows = [
                row
                for row in rows
                if keyword_lower in row.sku.lower()
                or keyword_lower in (row.barcode or "").lower()
                or keyword_lower in row.name.lower()
            ]
        self.sale_product_tree.delete(*self.sale_product_tree.get_children())
        for row in rows:
            self.sale_product_tree.insert("", "end", values=(row.product_id, row.sku, row.name, row.on_hand, money(row.sale_price)))

    def quick_add_search_product(self, _event: object) -> None:
        keyword = self.sale_search_var.get().strip()
        product = self.service.find_product_exact(keyword)
        if product is None:
            self.search_sale_products()
            matches = self.sale_product_tree.get_children()
            if len(matches) == 1:
                self.sale_product_tree.selection_set(matches[0])
                self.add_selected_to_cart()
            return
        self.cart.append(
            {
                "product_id": product.id,
                "sku": product.sku,
                "name": product.name,
                "quantity": parse_int(self.sale_qty_var.get(), "so luong", minimum=1),
                "unit_price": product.sale_price,
                "discount": 0,
            }
        )
        self.sale_search_var.set("")
        self.refresh_cart()
        self.search_sale_products()

    def add_customer(self) -> None:
        try:
            customer = self.service.create_customer(
                code=self.customer_code_var.get(),
                name=self.customer_name_var.get(),
                phone=self.customer_phone_var.get() or None,
            )
        except Exception as exc:
            self.show_error(exc)
            return
        messagebox.showinfo("Thanh cong", f"Da them khach: {customer.name} - ID {customer.id}")
        self.customer_code_var.set("")
        self.customer_name_var.set("")
        self.customer_phone_var.set("")
        self.refresh_all()

    def fill_debt_customer_id(self, _event: object) -> None:
        selected = self.debt_tree.selection()
        if not selected:
            return
        values = self.debt_tree.item(selected[0], "values")
        self.customer_pay_id_var.set(str(values[0]))
        self.sale_customer_id_var.set(str(values[0]))

    def receive_debt_payment(self) -> None:
        try:
            customer_id = parse_int(self.customer_pay_id_var.get(), "ID khach", minimum=1)
            amount = parse_int(self.customer_pay_amount_var.get(), "so tien thu", minimum=1)
            remaining = self.service.receive_customer_payment(customer_id=customer_id, amount=amount)
        except Exception as exc:
            self.show_error(exc)
            return
        messagebox.showinfo("Thanh cong", f"Da thu no. Con no: {money(remaining)} VND")
        self.customer_pay_amount_var.set("0")
        self.refresh_all()

    def refresh_debts(self) -> None:
        if not hasattr(self, "debt_tree"):
            return
        self.debt_tree.delete(*self.debt_tree.get_children())
        for row in self.service.customer_balances():
            paid = row.invoice_paid + row.extra_paid
            self.debt_tree.insert(
                "",
                "end",
                values=(row.customer_id, row.code, row.name, row.phone or "", money(row.total_sales), money(paid), money(row.debt)),
            )

    def add_product(self) -> None:
        try:
            product = self.service.create_product(
                sku=self.product_vars["sku"].get(),
                barcode=self.product_vars["barcode"].get() or None,
                name=self.product_vars["name"].get(),
                unit=self.product_vars["unit"].get() or "cai",
                cost_price=parse_int(self.product_vars["cost_price"].get(), "giá nhập"),
                sale_price=parse_int(self.product_vars["sale_price"].get(), "giá bán"),
                min_stock=parse_int(self.product_vars["min_stock"].get(), "tồn tối thiểu"),
            )
        except Exception as exc:
            self.show_error(exc)
            return
        messagebox.showinfo("Thành công", f"Đã thêm hàng hóa: {product.name}")
        for key, var in self.product_vars.items():
            var.set("cai" if key == "unit" else "0" if key in {"cost_price", "sale_price", "min_stock"} else "")
        self.refresh_all()

    def fill_stock_product_id(self, _event: object) -> None:
        selected = self.stock_inventory_tree.selection()
        if not selected:
            return
        values = self.stock_inventory_tree.item(selected[0], "values")
        self.stock_product_id_var.set(str(values[0]))

    def receive_stock(self) -> None:
        try:
            product_id = parse_int(self.stock_product_id_var.get(), "ID hàng hóa", minimum=1)
            quantity = parse_int(self.stock_qty_var.get(), "số lượng", minimum=1)
            unit_cost = parse_int(self.stock_cost_var.get(), "giá nhập")
            on_hand = self.service.receive_stock(
                product_id=product_id,
                quantity=quantity,
                unit_cost=unit_cost,
                note=self.stock_note_var.get() or None,
            )
        except Exception as exc:
            self.show_error(exc)
            return
        messagebox.showinfo("Thành công", f"Đã nhập kho. Tồn mới: {on_hand}")
        self.stock_qty_var.set("1")
        self.stock_note_var.set("")
        self.refresh_all()

    def add_selected_to_cart(self) -> None:
        selected = self.sale_product_tree.selection()
        if not selected:
            messagebox.showwarning("Chưa chọn hàng", "Vui lòng chọn một hàng hóa trong bảng.")
            return
        values = self.sale_product_tree.item(selected[0], "values")
        try:
            product_id = int(values[0])
            product = self.service.get_product(product_id)
            qty = parse_int(self.sale_qty_var.get(), "số lượng", minimum=1)
            price = parse_int(self.sale_price_var.get(), "giá bán") if self.sale_price_var.get().strip() else product.sale_price
            discount = parse_int(self.sale_line_discount_var.get(), "giảm giá")
        except Exception as exc:
            self.show_error(exc)
            return
        self.cart.append(
            {
                "product_id": product.id,
                "sku": product.sku,
                "name": product.name,
                "quantity": qty,
                "unit_price": price,
                "discount": discount,
            }
        )
        self.sale_qty_var.set("1")
        self.sale_price_var.set("")
        self.sale_line_discount_var.set("0")
        self.refresh_cart()

    def refresh_cart(self) -> None:
        if not hasattr(self, "cart_tree"):
            return
        self.cart_tree.delete(*self.cart_tree.get_children())
        total = 0
        for idx, item in enumerate(self.cart):
            line_total = int(item["quantity"]) * int(item["unit_price"]) - int(item["discount"])
            total += line_total
            self.cart_tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    item["sku"],
                    item["name"],
                    item["quantity"],
                    money(int(item["unit_price"])),
                    money(int(item["discount"])),
                    money(line_total),
                ),
            )
        try:
            invoice_discount = parse_int(self.invoice_discount_var.get(), "giảm hóa đơn")
        except PosError:
            invoice_discount = 0
        self.total_var.set(f"{money(max(0, total - invoice_discount))} VND")

    def remove_cart_item(self) -> None:
        selected = self.cart_tree.selection()
        if not selected:
            return
        index = int(selected[0])
        if 0 <= index < len(self.cart):
            self.cart.pop(index)
        self.refresh_cart()

    def checkout(self) -> None:
        if not self.cart:
            messagebox.showwarning("Hóa đơn rỗng", "Vui lòng thêm hàng vào hóa đơn.")
            return
        try:
            items = [
                SaleLineInput(
                    product_id=int(item["product_id"]),
                    quantity=int(item["quantity"]),
                    unit_price=int(item["unit_price"]),
                    discount=int(item["discount"]),
                )
                for item in self.cart
            ]
            sale = self.service.create_sale(
                items=items,
                customer_id=(
                    parse_int(self.sale_customer_id_var.get(), "ID khach", minimum=1)
                    if self.sale_customer_id_var.get().strip()
                    else None
                ),
                discount=parse_int(self.invoice_discount_var.get(), "giảm hóa đơn"),
                paid=parse_int(self.paid_var.get(), "khách đưa"),
                payment_method="cash",
            )
        except NotEnoughStockError as exc:
            messagebox.showerror("Không đủ tồn kho", str(exc))
            return
        except Exception as exc:
            self.show_error(exc)
            return
        self.cart.clear()
        self.invoice_discount_var.set("0")
        self.paid_var.set("0")
        self.sale_customer_id_var.set("")
        self.refresh_all()
        messagebox.showinfo(
            "Thanh toán xong",
            f"Hóa đơn: {sale.invoice_no}\nTổng tiền: {money(sale.total)} VND\nTrả lại: {money(sale.change)} VND",
        )

    def refresh_reports(self) -> None:
        if not hasattr(self, "sales_tree"):
            return
        summary = self.service.revenue_summary(date.today(), date.today())
        profit = self.service.profit_summary(date.today(), date.today())
        self.revenue_var.set(f"{money(summary.total)} VND")
        self.orders_var.set(str(summary.order_count))
        self.profit_var.set(f"{money(profit.gross_profit)} VND")
        self.sales_tree.delete(*self.sales_tree.get_children())
        for row in self.service.list_sales(date.today(), date.today()):
            self.sales_tree.insert(
                "",
                "end",
                values=(row.id, row.invoice_no, row.customer_name or "Khách lẻ", money(row.total), money(row.paid), row.created_at),
            )

        self.top_products_tree.delete(*self.top_products_tree.get_children())
        for row in self.service.top_selling_products(date.today(), date.today()):
            self.top_products_tree.insert(
                "",
                "end",
                values=(row.sku, row.name, row.quantity, money(row.revenue), money(row.gross_profit)),
            )

    def export_csv(self) -> None:
        try:
            export_dir = APP_DIR / "data" / "exports"
            inventory = self.service.export_inventory_csv(export_dir / "inventory.csv")
            sales = self.service.export_sales_csv(export_dir / "sales_today.csv", date.today(), date.today())
        except Exception as exc:
            self.show_error(exc)
            return
        messagebox.showinfo("Đã xuất CSV", f"Tồn kho:\n{inventory}\n\nHóa đơn:\n{sales}")

    def _install_backup_menu(self) -> None:
        menu_bar = tk.Menu(self)
        backup_menu = tk.Menu(menu_bar, tearoff=False)
        backup_menu.add_command(label="Sao lưu ngay", command=self.create_backup_now)
        backup_menu.add_command(label="Chọn thư mục sao lưu...", command=self.choose_backup_folder)
        backup_menu.add_command(label="Mở thư mục sao lưu", command=self.open_backup_folder)
        backup_menu.add_separator()
        backup_menu.add_command(label="Phục hồi từ file Backups...", command=self.restore_from_backup)
        backup_menu.add_command(label="Số lượng bản backup sẽ lưu...", command=self.change_keep_last)
        backup_menu.add_checkbutton(
            label="Tự động sao lưu khi thoát",
            variable=self.auto_backup_var,
            command=self.toggle_auto_backup,
        )
        menu_bar.add_cascade(label="Sao Lưu", menu=backup_menu)
        self.config(menu=menu_bar)

    def create_backup_now(self) -> None:
        try:
            path = backup.create_database_backup(DB_PATH, reason="manual", config=self.backup_config)
        except Exception as exc:
            self.show_error(exc)
            return
        messagebox.showinfo("Da sao luu", f"Da tao backup database:\n{path}")

    def choose_backup_folder(self) -> None:
        initial_dir = self._best_initial_backup_dir()
        selected = filedialog.askdirectory(
            title="Chon thu muc sao luu database",
            initialdir=str(initial_dir),
        )
        if not selected:
            return
        self.backup_config = backup.update_config(backup_dir=selected)
        messagebox.showinfo(
            "Da luu thu muc sao luu",
            f"Database se duoc sao luu vao:\n{self.backup_config.backup_dir}\n\n"
            "Ban co the chon thu muc nam trong Google Drive Desktop de tu dong dong bo len may.",
        )

    def open_backup_folder(self) -> None:
        try:
            backup.open_backup_folder(self.backup_config)
        except Exception as exc:
            self.show_error(exc)

    def restore_from_backup(self) -> None:
        selected = filedialog.askopenfilename(
            title="Chon file backup .db de phuc hoi",
            initialdir=str(self.backup_config.backup_dir),
            filetypes=[("SQLite database", "*.db"), ("All files", "*.*")],
        )
        if not selected:
            return
        allowed = messagebox.askyesno(
            "Xac nhan phuc hoi",
            "Phuc hoi se ghi de database hien tai. Ung dung se tao mot ban backup truoc khi ghi de. Tiep tuc?",
        )
        if not allowed:
            return
        try:
            pre_restore = backup.restore_database_backup(selected, DB_PATH, config=self.backup_config)
        except Exception as exc:
            self.show_error(exc)
            return
        messagebox.showinfo(
            "Da phuc hoi",
            f"Da phuc hoi database tu:\n{selected}\n\nBackup truoc khi phuc hoi:\n{pre_restore}\n\n"
            "Hay dong va mo lai ung dung de tai lai du lieu.",
        )

    def change_keep_last(self) -> None:
        value = simpledialog.askinteger(
            "So ban backup giu lai",
            "Giu lai bao nhieu ban backup gan nhat?",
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
            "Da cap nhat",
            f"Se giu lai {self.backup_config.keep_last} ban backup gan nhat.\n"
            f"Da xoa {len(removed)} ban cu.",
        )

    def toggle_auto_backup(self) -> None:
        self.backup_config = backup.update_config(auto_backup_on_exit=self.auto_backup_var.get())

    def close_with_optional_backup(self) -> None:
        if self.auto_backup_var.get() and Path(DB_PATH).exists():
            try:
                backup.create_database_backup(DB_PATH, reason="auto_exit", config=self.backup_config)
            except Exception as exc:
                should_close = messagebox.askyesno(
                    "Sao luu that bai",
                    f"Khong the tao backup truoc khi thoat:\n{exc}\n\nVan thoat ung dung?",
                )
                if not should_close:
                    return
        self.destroy()

    def _best_initial_backup_dir(self) -> Path:
        candidates = backup.google_drive_candidates()
        if candidates:
            return candidates[0]
        return self.backup_config.backup_dir

    def _load_manifest_url_for_ui(self) -> str:
        try:
            import json

            data = updater.CONFIG_PATH.read_text(encoding="utf-8")
            return str(json.loads(data).get("manifest_url", ""))
        except Exception:
            return ""

    def save_update_url(self) -> None:
        try:
            updater.save_config(self.update_manifest_url_var.get())
        except Exception as exc:
            self.show_error(exc)
            return
        messagebox.showinfo("Thanh cong", "Da luu Manifest URL.")

    def check_update(self) -> None:
        try:
            updater.save_config(self.update_manifest_url_var.get())
            check = updater.check_for_update()
        except Exception as exc:
            self.pending_update_check = None
            self.show_error(exc)
            return
        self.pending_update_check = check
        status = (
            f"Co ban moi: {check.latest_version} (hien tai {check.current_version})"
            if check.has_update
            else f"Da la ban moi nhat: {check.current_version}"
        )
        self.update_status_var.set(status)
        self.update_notes.delete("1.0", "end")
        self.update_notes.insert(
            "1.0",
            f"Version: {check.latest_version}\nPackage: {check.package_url}\nSHA256: {check.sha256 or '(khong co)'}\n\n{check.notes}",
        )

    def install_checked_update(self) -> None:
        check = self.pending_update_check
        if check is None:
            messagebox.showwarning("Chua kiem tra", "Vui long bam Kiem tra truoc.")
            return
        if not check.has_update:
            messagebox.showinfo("Khong co ban moi", "Ung dung dang o phien ban moi nhat.")
            return
        allowed = messagebox.askyesno(
            "Xac nhan cap nhat",
            "Ung dung se tai goi cap nhat, tao backup va ghi de file chuong trinh. Tiep tuc?",
        )
        if not allowed:
            return
        try:
            backup = updater.download_and_install(check)
        except Exception as exc:
            self.show_error(exc)
            return
        messagebox.showinfo(
            "Cap nhat xong",
            f"Da cap nhat file chuong trinh.\nBackup: {backup}\nVui long dong va mo lai ung dung.",
        )

    def show_error(self, exc: Exception) -> None:
        message = str(exc) or exc.__class__.__name__
        messagebox.showerror("Lỗi", message)


def main() -> None:
    app = PosApp()
    app.mainloop()


if __name__ == "__main__":
    main()

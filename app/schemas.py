from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------- Auth ----------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeOut(BaseModel):
    id: int
    full_name: str
    role: str


# ---------- Products ----------
class ProductIn(BaseModel):
    name: str
    unit: str
    default_sale_price: Optional[Decimal] = None


class ProductOut(BaseModel):
    id: int
    name: str
    unit: str
    default_sale_price: Optional[Decimal]
    is_active: bool


# ---------- Suppliers ----------
class SupplierIn(BaseModel):
    name: str
    phone: Optional[str] = None
    opening_due: Decimal = Decimal("0")


class SupplierListOut(BaseModel):
    """Minimal shape — safe for workers (no financial figures)."""
    id: int
    name: str


class SupplierDetailOut(BaseModel):
    """Admin-only shape — includes derived due."""
    id: int
    name: str
    phone: Optional[str]
    opening_due: Decimal
    purchases: Decimal
    payments: Decimal
    current_due: Decimal


class SupplierProductIn(BaseModel):
    product_id: int
    default_rate: Decimal = Field(gt=0)


class SupplierProductOut(BaseModel):
    supplier_id: int
    product_id: int
    product_name: str
    default_rate: Decimal
    is_active: bool


# ---------- Customers ----------
class CustomerIn(BaseModel):
    name: str
    whatsapp_number: Optional[str] = None
    opening_due: Decimal = Decimal("0")


class CustomerListOut(BaseModel):
    id: int
    name: str


class CustomerDetailOut(BaseModel):
    id: int
    name: str
    whatsapp_number: Optional[str]
    opening_due: Decimal
    credit_sales: Decimal
    payments: Decimal
    current_due: Decimal


# ---------- Supplier purchases ----------
class SupplierPurchaseIn(BaseModel):
    supplier_id: int
    product_id: int
    txn_date: date
    quantity: Decimal = Field(gt=0)
    rate: Decimal = Field(gt=0)
    note: Optional[str] = None
    payment_amount: Optional[Decimal] = Field(default=None, gt=0)  # pay some/all now
    idempotency_key: Optional[UUID] = None


class SupplierPurchaseUpdate(BaseModel):
    quantity: Optional[Decimal] = Field(default=None, gt=0)
    rate: Optional[Decimal] = Field(default=None, gt=0)
    txn_date: Optional[date] = None
    note: Optional[str] = None


class SupplierPurchaseOut(BaseModel):
    id: int
    supplier_id: int
    product_id: int
    txn_date: date
    quantity: Decimal
    rate: Decimal
    total_amount: Decimal
    note: Optional[str]


# ---------- Supplier payments ----------
class SupplierPaymentIn(BaseModel):
    supplier_id: int
    amount: Decimal = Field(gt=0)
    txn_date: date
    note: Optional[str] = None
    idempotency_key: Optional[UUID] = None


class SupplierPaymentOut(BaseModel):
    id: int
    supplier_id: int
    amount: Decimal
    txn_date: date
    note: Optional[str]


# ---------- Sales ----------
class SaleIn(BaseModel):
    sale_type: str  # 'cash' | 'credit'
    customer_id: Optional[int] = None
    product_id: int
    quantity: Optional[Decimal] = Field(default=None, gt=0)
    rate: Optional[Decimal] = Field(default=None, gt=0)
    amount: Decimal = Field(gt=0)
    txn_date: date
    note: Optional[str] = None
    idempotency_key: Optional[UUID] = None


class SaleUpdate(BaseModel):
    quantity: Optional[Decimal] = None
    rate: Optional[Decimal] = None
    amount: Optional[Decimal] = None
    txn_date: Optional[date] = None
    note: Optional[str] = None


class SaleOut(BaseModel):
    id: int
    sale_type: str
    customer_id: Optional[int]
    product_id: int
    quantity: Optional[Decimal]
    rate: Optional[Decimal]
    amount: Decimal
    txn_date: date
    source: str


class SaleListItemOut(BaseModel):
    """Enriched shape for list views (product/customer name already
    joined in, so the app doesn't need a separate lookup per row)."""
    id: int
    sale_type: str
    customer_id: Optional[int]
    customer_name: Optional[str]
    product_id: int
    product_name: str
    unit: str
    quantity: Optional[Decimal]
    rate: Optional[Decimal]
    amount: Decimal
    txn_date: date


# ---------- Customer payments ----------
class CustomerPaymentIn(BaseModel):
    customer_id: int
    amount: Decimal = Field(gt=0)
    txn_date: date
    note: Optional[str] = None
    idempotency_key: Optional[UUID] = None


class CustomerPaymentOut(BaseModel):
    id: int
    customer_id: int
    amount: Decimal
    txn_date: date
    note: Optional[str]


# ---------- Expenses ----------
class ExpenseCategoryOut(BaseModel):
    id: int
    name: str


class ExpenseIn(BaseModel):
    category_id: int
    amount: Decimal = Field(gt=0)
    txn_date: date
    note: Optional[str] = None
    idempotency_key: Optional[UUID] = None


class ExpenseOut(BaseModel):
    id: int
    category_id: int
    amount: Decimal
    txn_date: date
    note: Optional[str]


class ExpenseListItemOut(BaseModel):
    id: int
    category_id: int
    category_name: str
    amount: Decimal
    txn_date: date
    note: Optional[str]


# ---------- Recurring sales ----------
class RecurringSaleIn(BaseModel):
    customer_id: int
    product_id: int
    daily_amount: Decimal = Field(gt=0)
    start_date: date
    end_date: Optional[date] = None


class RecurringSaleOut(BaseModel):
    id: int
    customer_id: int
    product_id: int
    daily_amount: Decimal
    start_date: date
    end_date: Optional[date]
    is_active: bool


# ---------- Ledger ----------
class LedgerOut(BaseModel):
    ledger_date: date
    opening_cash: Decimal
    cash_sales: Decimal
    customer_payments: Decimal
    supplier_payments: Decimal
    expenses: Decimal
    closing_cash: Decimal
    credit_sales: Decimal
    counted_amount: Optional[Decimal] = None  # set once someone counts the till for this date
    difference: Optional[Decimal] = None      # counted_amount - closing_cash, once counted


class CashAnchorIn(BaseModel):
    anchor_date: date
    amount: Decimal
    reason: Optional[str] = None


class CashCountIn(BaseModel):
    count_date: date
    counted_amount: Decimal = Field(ge=0)
    note: Optional[str] = None


class CashCountOut(BaseModel):
    count_date: date
    counted_amount: Decimal
    expected_amount: Decimal
    difference: Decimal
    note: Optional[str]


# ---------- History (customer/supplier combined timeline) ----------
class HistoryEntryOut(BaseModel):
    kind: str  # 'sale' | 'purchase' | 'payment'
    id: int
    txn_date: date
    amount: Decimal
    note: Optional[str] = None
    product_name: Optional[str] = None


# ---------- Bills ----------
class BillLineOut(BaseModel):
    product_name: str
    total: Decimal


class BillOut(BaseModel):
    customer_id: int
    customer_name: str
    period_start: date
    period_end: date
    lines: list[BillLineOut]
    grand_total: Decimal
    previous_due: Decimal
    payments_in_period: Decimal
    remaining_due: Decimal

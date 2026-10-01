from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import CurrentUser, commit, get_audited_db, get_current_user, require_admin
from ..schemas import CustomerDetailOut, CustomerIn, CustomerListOut, HistoryEntryOut

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=list[CustomerListOut])
def list_customers(db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user)):
    """Name/id only — dues are admin-only (spec §28)."""
    rows = db.execute(
        text("SELECT id, name FROM customers WHERE is_active ORDER BY name")
    ).mappings().all()
    return [CustomerListOut(**r) for r in rows]


@router.post("", response_model=CustomerListOut)
def create_customer(body: CustomerIn, db: Session = Depends(get_audited_db), _: CurrentUser = Depends(get_current_user)):
    """Both roles can add a new customer (e.g. a first-time khata signup
    during a busy shift) — this creates no financial exposure by itself."""
    row = db.execute(
        text("""
            INSERT INTO customers (name, whatsapp_number, opening_due)
            VALUES (:name, :wa, :due)
            RETURNING id, name
        """),
        {"name": body.name, "wa": body.whatsapp_number, "due": body.opening_due},
    ).mappings().first()
    commit(db)
    return CustomerListOut(**row)


@router.get("/{customer_id}", response_model=CustomerDetailOut)
def get_customer(customer_id: int, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)):
    row = db.execute(
        text("""
            SELECT c.id, c.name, c.whatsapp_number, b.opening_due, b.credit_sales, b.payments, b.current_due
            FROM customers c JOIN v_customer_balance b ON b.customer_id = c.id
            WHERE c.id = :id
        """),
        {"id": customer_id},
    ).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return CustomerDetailOut(**row)


@router.get("/{customer_id}/history", response_model=list[HistoryEntryOut])
def get_customer_history(customer_id: int, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)):
    """Admin-only: a running timeline necessarily reveals the balance
    (spec §28), unlike the plain today's-sales log in /sales."""
    rows = db.execute(
        text("""
            SELECT 'sale' AS kind, s.id, s.txn_date, s.amount, s.note, p.name AS product_name
            FROM sales s JOIN products p ON p.id = s.product_id
            WHERE s.customer_id = :cid AND s.sale_type = 'credit' AND s.deleted_at IS NULL
            UNION ALL
            SELECT 'payment', id, txn_date, amount, note, NULL
            FROM customer_payments WHERE customer_id = :cid AND deleted_at IS NULL
            ORDER BY txn_date DESC, id DESC
        """),
        {"cid": customer_id},
    ).mappings().all()
    return [HistoryEntryOut(**r) for r in rows]

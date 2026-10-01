from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import CurrentUser, commit, get_audited_db, get_current_user, require_admin
from ..schemas import (
    HistoryEntryOut,
    SupplierDetailOut,
    SupplierIn,
    SupplierListOut,
    SupplierProductIn,
    SupplierProductOut,
)

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get("", response_model=list[SupplierListOut])
def list_suppliers(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    """Everyone can list suppliers (needed for purchase-entry dropdowns), but
    only name/id go out here — dues are admin-only (spec §28)."""
    rows = db.execute(
        text("SELECT id, name FROM suppliers WHERE is_active ORDER BY name")
    ).mappings().all()
    return [SupplierListOut(**r) for r in rows]


@router.post("", response_model=SupplierDetailOut)
def create_supplier(body: SupplierIn, db: Session = Depends(get_audited_db), _: CurrentUser = Depends(require_admin)):
    row = db.execute(
        text("""
            INSERT INTO suppliers (name, phone, opening_due)
            VALUES (:name, :phone, :due)
            RETURNING id
        """),
        {"name": body.name, "phone": body.phone, "due": body.opening_due},
    ).mappings().first()
    commit(db)
    return _get_supplier_detail(db, row["id"])


@router.get("/{supplier_id}", response_model=SupplierDetailOut)
def get_supplier(supplier_id: int, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)):
    detail = _get_supplier_detail(db, supplier_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supplier not found")
    return detail


@router.get("/{supplier_id}/products", response_model=list[SupplierProductOut])
def list_supplier_products(
    supplier_id: int, db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user)
):
    """Default rates ARE visible to workers — they need them to prefill a
    purchase form. Only the running due stays admin-only."""
    rows = db.execute(
        text("""
            SELECT sp.supplier_id, sp.product_id, p.name AS product_name,
                   sp.default_rate, sp.is_active
            FROM supplier_products sp JOIN products p ON p.id = sp.product_id
            WHERE sp.supplier_id = :sid AND sp.is_active
            ORDER BY p.name
        """),
        {"sid": supplier_id},
    ).mappings().all()
    return [SupplierProductOut(**r) for r in rows]


@router.put("/{supplier_id}/products", response_model=SupplierProductOut)
def set_supplier_product_rate(
    supplier_id: int,
    body: SupplierProductIn,
    db: Session = Depends(get_audited_db),
    _: CurrentUser = Depends(require_admin),
):
    """Create or update the default rate. Existing purchases keep the rate
    they were made with — this only changes what NEW purchases prefill."""
    row = db.execute(
        text("""
            INSERT INTO supplier_products (supplier_id, product_id, default_rate)
            VALUES (:sid, :pid, :rate)
            ON CONFLICT (supplier_id, product_id)
            DO UPDATE SET default_rate = EXCLUDED.default_rate, is_active = true, updated_at = now()
            RETURNING supplier_id, product_id, default_rate, is_active
        """),
        {"sid": supplier_id, "pid": body.product_id, "rate": body.default_rate},
    ).mappings().first()
    product_name = db.execute(
        text("SELECT name FROM products WHERE id = :id"), {"id": body.product_id}
    ).scalar_one()
    commit(db)
    return SupplierProductOut(**row, product_name=product_name)


@router.get("/{supplier_id}/history", response_model=list[HistoryEntryOut])
def get_supplier_history(supplier_id: int, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)):
    rows = db.execute(
        text("""
            SELECT 'purchase' AS kind, sp.id, sp.txn_date, sp.total_amount AS amount, sp.note, p.name AS product_name
            FROM supplier_purchases sp JOIN products p ON p.id = sp.product_id
            WHERE sp.supplier_id = :sid AND sp.deleted_at IS NULL
            UNION ALL
            SELECT 'payment', id, txn_date, amount, note, NULL
            FROM supplier_payments WHERE supplier_id = :sid AND deleted_at IS NULL
            ORDER BY txn_date DESC, id DESC
        """),
        {"sid": supplier_id},
    ).mappings().all()
    return [HistoryEntryOut(**r) for r in rows]


def _get_supplier_detail(db: Session, supplier_id: int) -> SupplierDetailOut | None:
    row = db.execute(
        text("""
            SELECT sp.id, sp.name, sp.phone, b.opening_due, b.purchases, b.payments, b.current_due
            FROM suppliers sp JOIN v_supplier_balance b ON b.supplier_id = sp.id
            WHERE sp.id = :id
        """),
        {"id": supplier_id},
    ).mappings().first()
    return SupplierDetailOut(**row) if row else None

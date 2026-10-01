from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..deps import CurrentUser, commit, get_audited_db, get_current_user, require_admin
from ..schemas import SupplierPaymentIn, SupplierPaymentOut

router = APIRouter(prefix="/supplier-payments", tags=["supplier-payments"])


@router.post("", response_model=SupplierPaymentOut)
def create_supplier_payment(
    body: SupplierPaymentIn, db: Session = Depends(get_audited_db), user: CurrentUser = Depends(get_current_user)
):
    row = db.execute(
        text("""
            INSERT INTO supplier_payments (supplier_id, amount, txn_date, note, idempotency_key, created_by)
            VALUES (:sid, :amt, :date, :note, :ikey, :uid)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id, supplier_id, amount, txn_date, note
        """),
        {"sid": body.supplier_id, "amt": body.amount, "date": body.txn_date, "note": body.note,
         "ikey": str(body.idempotency_key) if body.idempotency_key else None, "uid": user.id},
    ).mappings().first()

    if row is None:
        row = db.execute(
            text("SELECT id, supplier_id, amount, txn_date, note FROM supplier_payments WHERE idempotency_key = :k"),
            {"k": str(body.idempotency_key)},
        ).mappings().first()
    commit(db)
    return SupplierPaymentOut(**row)


@router.delete("/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supplier_payment(
    payment_id: int, db: Session = Depends(get_audited_db), user: CurrentUser = Depends(require_admin)
):
    result = db.execute(
        text("""
            UPDATE supplier_payments SET deleted_at = now(), deleted_by = :uid
            WHERE id = :id AND deleted_at IS NULL
        """),
        {"id": payment_id, "uid": user.id},
    )
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found (or already deleted)")
    commit(db)

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..deps import CurrentUser, commit, get_audited_db, get_current_user, require_admin
from ..schemas import CustomerPaymentIn, CustomerPaymentOut

router = APIRouter(prefix="/customer-payments", tags=["customer-payments"])


@router.post("", response_model=CustomerPaymentOut)
def create_customer_payment(
    body: CustomerPaymentIn, db: Session = Depends(get_audited_db), user: CurrentUser = Depends(get_current_user)
):
    row = db.execute(
        text("""
            INSERT INTO customer_payments (customer_id, amount, txn_date, note, idempotency_key, created_by)
            VALUES (:cid, :amt, :date, :note, :ikey, :uid)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id, customer_id, amount, txn_date, note
        """),
        {"cid": body.customer_id, "amt": body.amount, "date": body.txn_date, "note": body.note,
         "ikey": str(body.idempotency_key) if body.idempotency_key else None, "uid": user.id},
    ).mappings().first()

    if row is None:
        row = db.execute(
            text("SELECT id, customer_id, amount, txn_date, note FROM customer_payments WHERE idempotency_key = :k"),
            {"k": str(body.idempotency_key)},
        ).mappings().first()
    commit(db)
    return CustomerPaymentOut(**row)


@router.delete("/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer_payment(
    payment_id: int, db: Session = Depends(get_audited_db), user: CurrentUser = Depends(require_admin)
):
    result = db.execute(
        text("""
            UPDATE customer_payments SET deleted_at = now(), deleted_by = :uid
            WHERE id = :id AND deleted_at IS NULL
        """),
        {"id": payment_id, "uid": user.id},
    )
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found (or already deleted)")
    commit(db)

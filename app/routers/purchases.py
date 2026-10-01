from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..deps import CurrentUser, commit, get_audited_db, get_current_user, require_admin
from ..schemas import SupplierPurchaseIn, SupplierPurchaseOut, SupplierPurchaseUpdate

router = APIRouter(prefix="/purchases", tags=["purchases"])


@router.post("", response_model=SupplierPurchaseOut)
def create_purchase(
    body: SupplierPurchaseIn,
    db: Session = Depends(get_audited_db),
    _: CurrentUser = Depends(get_current_user),  # both roles can enter purchases (spec §28)
):
    row = db.execute(
        text("""
            INSERT INTO supplier_purchases
                (supplier_id, product_id, txn_date, quantity, rate, note, idempotency_key, created_by)
            VALUES (:sid, :pid, :date, :qty, :rate, :note, :ikey, :uid)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id, supplier_id, product_id, txn_date, quantity, rate, total_amount, note
        """),
        {
            "sid": body.supplier_id, "pid": body.product_id, "date": body.txn_date,
            "qty": body.quantity, "rate": body.rate, "note": body.note,
            "ikey": str(body.idempotency_key) if body.idempotency_key else None,
            "uid": _.id,
        },
    ).mappings().first()

    if row is None:
        # idempotency key already used — return the existing row, not an error
        row = db.execute(
            text("""
                SELECT id, supplier_id, product_id, txn_date, quantity, rate, total_amount, note
                FROM supplier_purchases WHERE idempotency_key = :ikey
            """),
            {"ikey": str(body.idempotency_key)},
        ).mappings().first()

    # Optional payment made at purchase time (spec §7-8) — same transaction,
    # so it either both succeed or both roll back together.
    if body.payment_amount:
        db.execute(
            text("""
                INSERT INTO supplier_payments (supplier_id, purchase_id, amount, txn_date, created_by)
                VALUES (:sid, :pid, :amt, :date, :uid)
            """),
            {"sid": body.supplier_id, "pid": row["id"], "amt": body.payment_amount,
             "date": body.txn_date, "uid": _.id},
        )

    commit(db)
    return SupplierPurchaseOut(**row)


@router.patch("/{purchase_id}", response_model=SupplierPurchaseOut)
def update_purchase(
    purchase_id: int,
    body: SupplierPurchaseUpdate,
    db: Session = Depends(get_audited_db),
    _: CurrentUser = Depends(require_admin),  # edits are admin-only (see chat: proposed default)
):
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")

    set_clause = ", ".join(f"{k} = :{k}" for k in fields)
    row = db.execute(
        text(f"""
            UPDATE supplier_purchases SET {set_clause}
            WHERE id = :id AND deleted_at IS NULL
            RETURNING id, supplier_id, product_id, txn_date, quantity, rate, total_amount, note
        """),
        {**fields, "id": purchase_id},
    ).mappings().first()

    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Purchase not found (or already deleted)")
    commit(db)
    return SupplierPurchaseOut(**row)


@router.delete("/{purchase_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase(
    purchase_id: int, db: Session = Depends(get_audited_db), user: CurrentUser = Depends(require_admin)
):
    result = db.execute(
        text("""
            UPDATE supplier_purchases SET deleted_at = now(), deleted_by = :uid
            WHERE id = :id AND deleted_at IS NULL
        """),
        {"id": purchase_id, "uid": user.id},
    )
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Purchase not found (or already deleted)")
    commit(db)

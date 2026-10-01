from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import CurrentUser, commit, get_audited_db, get_current_user, require_admin
from ..schemas import SaleIn, SaleListItemOut, SaleOut, SaleUpdate

router = APIRouter(prefix="/sales", tags=["sales"])


@router.get("", response_model=list[SaleListItemOut])
def list_sales(
    txn_date: date | None = None,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    """Both roles can see this (spec §28 restricts DUES/ledger/profit, not a
    plain log of transactions someone just entered themselves). Defaults to
    today so the mobile 'Today's Sales' screen needs no date param."""
    rows = db.execute(
        text("""
            SELECT s.id, s.sale_type, s.customer_id, c.name AS customer_name,
                   s.product_id, p.name AS product_name, p.unit,
                   s.quantity, s.rate, s.amount, s.txn_date
            FROM sales s
            JOIN products p ON p.id = s.product_id
            LEFT JOIN customers c ON c.id = s.customer_id
            WHERE s.deleted_at IS NULL
              AND s.txn_date = COALESCE(:d, fn_shop_today())
            ORDER BY s.created_at DESC
        """),
        {"d": txn_date},
    ).mappings().all()
    return [SaleListItemOut(**r) for r in rows]


@router.post("", response_model=SaleOut)
def create_sale(body: SaleIn, db: Session = Depends(get_audited_db), user: CurrentUser = Depends(get_current_user)):
    if body.sale_type not in ("cash", "credit"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "sale_type must be 'cash' or 'credit'")
    if body.sale_type == "credit" and not body.customer_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "credit sales require a customer_id")

    row = db.execute(
        text("""
            INSERT INTO sales (sale_type, customer_id, product_id, quantity, rate, amount,
                                txn_date, note, idempotency_key, created_by)
            VALUES (:type, :cid, :pid, :qty, :rate, :amount, :date, :note, :ikey, :uid)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id, sale_type, customer_id, product_id, quantity, rate, amount, txn_date, source
        """),
        {
            "type": body.sale_type, "cid": body.customer_id, "pid": body.product_id,
            "qty": body.quantity, "rate": body.rate, "amount": body.amount, "date": body.txn_date,
            "note": body.note, "ikey": str(body.idempotency_key) if body.idempotency_key else None,
            "uid": user.id,
        },
    ).mappings().first()

    if row is None:
        row = db.execute(
            text("""
                SELECT id, sale_type, customer_id, product_id, quantity, rate, amount, txn_date, source
                FROM sales WHERE idempotency_key = :k
            """),
            {"k": str(body.idempotency_key)},
        ).mappings().first()
    commit(db)
    return SaleOut(**row)


@router.patch("/{sale_id}", response_model=SaleOut)
def update_sale(
    sale_id: int, body: SaleUpdate, db: Session = Depends(get_audited_db), _: CurrentUser = Depends(require_admin)
):
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")
    set_clause = ", ".join(f"{k} = :{k}" for k in fields)
    row = db.execute(
        text(f"""
            UPDATE sales SET {set_clause} WHERE id = :id AND deleted_at IS NULL
            RETURNING id, sale_type, customer_id, product_id, quantity, rate, amount, txn_date, source
        """),
        {**fields, "id": sale_id},
    ).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sale not found (or already deleted)")
    commit(db)
    return SaleOut(**row)


@router.delete("/{sale_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sale(sale_id: int, db: Session = Depends(get_audited_db), user: CurrentUser = Depends(require_admin)):
    result = db.execute(
        text("UPDATE sales SET deleted_at = now(), deleted_by = :uid WHERE id = :id AND deleted_at IS NULL"),
        {"id": sale_id, "uid": user.id},
    )
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sale not found (or already deleted)")
    commit(db)

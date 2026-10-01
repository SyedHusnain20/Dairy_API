from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..deps import CurrentUser, commit, get_audited_db, get_current_user, get_db, require_admin
from ..schemas import ExpenseCategoryOut, ExpenseIn, ExpenseListItemOut, ExpenseOut

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.get("/categories", response_model=list[ExpenseCategoryOut])
def list_categories(db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user)):
    rows = db.execute(
        text("SELECT id, name FROM expense_categories WHERE is_active ORDER BY name")
    ).mappings().all()
    return [ExpenseCategoryOut(**r) for r in rows]


@router.get("", response_model=list[ExpenseListItemOut])
def list_expenses(
    txn_date: date | None = None, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)
):
    """Admin-only: unlike /sales (a log of amounts the entrant already
    knows), a running expense total is closer to the 'financial figures'
    spec §28 keeps from workers."""
    rows = db.execute(
        text("""
            SELECT e.id, e.category_id, c.name AS category_name, e.amount, e.txn_date, e.note
            FROM expenses e JOIN expense_categories c ON c.id = e.category_id
            WHERE e.deleted_at IS NULL AND e.txn_date = COALESCE(:d, fn_shop_today())
            ORDER BY e.created_at DESC
        """),
        {"d": txn_date},
    ).mappings().all()
    return [ExpenseListItemOut(**r) for r in rows]


@router.post("", response_model=ExpenseOut)
def create_expense(body: ExpenseIn, db: Session = Depends(get_audited_db), user: CurrentUser = Depends(get_current_user)):
    row = db.execute(
        text("""
            INSERT INTO expenses (category_id, amount, txn_date, note, idempotency_key, created_by)
            VALUES (:cat, :amt, :date, :note, :ikey, :uid)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id, category_id, amount, txn_date, note
        """),
        {"cat": body.category_id, "amt": body.amount, "date": body.txn_date, "note": body.note,
         "ikey": str(body.idempotency_key) if body.idempotency_key else None, "uid": user.id},
    ).mappings().first()

    if row is None:
        row = db.execute(
            text("SELECT id, category_id, amount, txn_date, note FROM expenses WHERE idempotency_key = :k"),
            {"k": str(body.idempotency_key)},
        ).mappings().first()
    commit(db)
    return ExpenseOut(**row)


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(expense_id: int, db: Session = Depends(get_audited_db), user: CurrentUser = Depends(require_admin)):
    result = db.execute(
        text("UPDATE expenses SET deleted_at = now(), deleted_by = :uid WHERE id = :id AND deleted_at IS NULL"),
        {"id": expense_id, "uid": user.id},
    )
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Expense not found (or already deleted)")
    commit(db)

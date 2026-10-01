from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..deps import CurrentUser, commit, get_audited_db, get_current_user, get_db, require_admin
from ..schemas import RecurringSaleIn, RecurringSaleOut

router = APIRouter(prefix="/recurring-sales", tags=["recurring-sales"])


@router.post("", response_model=RecurringSaleOut)
def create_rule(body: RecurringSaleIn, db: Session = Depends(get_audited_db), user: CurrentUser = Depends(require_admin)):
    row = db.execute(
        text("""
            INSERT INTO recurring_sales (customer_id, product_id, daily_amount, start_date, end_date, created_by)
            VALUES (:cid, :pid, :amt, :start, :end, :uid)
            RETURNING id, customer_id, product_id, daily_amount, start_date, end_date, is_active
        """),
        {"cid": body.customer_id, "pid": body.product_id, "amt": body.daily_amount,
         "start": body.start_date, "end": body.end_date, "uid": user.id},
    ).mappings().first()
    commit(db)
    return RecurringSaleOut(**row)


@router.get("", response_model=list[RecurringSaleOut])
def list_rules(db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)):
    rows = db.execute(
        text("""
            SELECT id, customer_id, product_id, daily_amount, start_date, end_date, is_active
            FROM recurring_sales ORDER BY id
        """)
    ).mappings().all()
    return [RecurringSaleOut(**r) for r in rows]


@router.patch("/{rule_id}/stop", response_model=RecurringSaleOut)
def stop_rule(rule_id: int, db: Session = Depends(get_audited_db), _: CurrentUser = Depends(require_admin)):
    """Deactivates the rule going forward. Already-generated sale rows are
    untouched — stopping is not the same as deleting history (spec §15)."""
    row = db.execute(
        text("""
            UPDATE recurring_sales SET is_active = false WHERE id = :id
            RETURNING id, customer_id, product_id, daily_amount, start_date, end_date, is_active
        """),
        {"id": rule_id},
    ).mappings().first()
    commit(db)
    return RecurringSaleOut(**row)


@router.post("/generate")
def generate(through: date | None = None, db: Session = Depends(get_audited_db), _: CurrentUser = Depends(require_admin)):
    """Safe to call repeatedly (e.g. on every admin app open, or a nightly
    cron) — the UNIQUE(recurring_sale_id, txn_date) constraint means it
    only ever fills in missing days, never duplicates."""
    params = {"through": through} if through else {}
    sql = "SELECT fn_generate_recurring_sales(:through) AS rows_created" if through else "SELECT fn_generate_recurring_sales() AS rows_created"
    result = db.execute(text(sql), params).mappings().first()
    commit(db)
    return {"rows_created": result["rows_created"]}

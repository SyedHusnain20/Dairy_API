from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import CurrentUser, commit, get_audited_db, require_admin
from ..schemas import CashAnchorIn, CashCountIn, CashCountOut, LedgerOut

router = APIRouter(prefix="/ledger", tags=["ledger"])


@router.get("/{ledger_date}", response_model=LedgerOut)
def get_ledger(ledger_date: date, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)):
    """require_admin is the enforcement point: a worker's valid JWT still
    gets 403 here, at the API layer, regardless of what the mobile app's
    navigation does or doesn't show (spec §29)."""
    row = dict(db.execute(text("SELECT * FROM fn_daily_ledger(:d)"), {"d": ledger_date}).mappings().first())
    count = db.execute(
        text("SELECT counted_amount, difference FROM cash_counts WHERE count_date = :d"),
        {"d": ledger_date},
    ).mappings().first()
    if count:
        row["counted_amount"] = count["counted_amount"]
        row["difference"] = count["difference"]
    return LedgerOut(**row)


@router.post("/cash-count", response_model=CashCountOut)
def save_cash_count(body: CashCountIn, db: Session = Depends(get_audited_db), user: CurrentUser = Depends(require_admin)):
    """Records the physical count for a day against what the ledger expected
    at that moment (spec: the surplus/shortfall check from the original
    daily_closing_screen). expected_amount is deliberately a snapshot —
    edits to that day's transactions afterward won't retroactively change
    what this count was compared against."""
    expected = db.execute(
        text("SELECT closing_cash FROM fn_daily_ledger(:d)"), {"d": body.count_date}
    ).scalar_one()
    row = db.execute(
        text("""
            INSERT INTO cash_counts (count_date, counted_amount, expected_amount, note, counted_by)
            VALUES (:date, :counted, :expected, :note, :uid)
            ON CONFLICT (count_date) DO UPDATE SET
                counted_amount = EXCLUDED.counted_amount,
                expected_amount = EXCLUDED.expected_amount,
                note = EXCLUDED.note,
                counted_by = EXCLUDED.counted_by,
                counted_at = now()
            RETURNING count_date, counted_amount, expected_amount, difference, note
        """),
        {"date": body.count_date, "counted": body.counted_amount, "expected": expected,
         "note": body.note, "uid": user.id},
    ).mappings().first()
    commit(db)
    return CashCountOut(**row)


@router.post("/cash-anchor", status_code=201)
def set_cash_anchor(body: CashAnchorIn, db: Session = Depends(get_audited_db), user: CurrentUser = Depends(require_admin)):
    """Admin override of opening cash for a date (spec §23). Only needed for
    day 1 (go-live) or a manual correction — normal days roll forward
    automatically from the previous day's closing."""
    db.execute(
        text("""
            INSERT INTO cash_anchors (anchor_date, amount, reason, created_by)
            VALUES (:date, :amount, :reason, :uid)
            ON CONFLICT (anchor_date) DO UPDATE SET amount = EXCLUDED.amount, reason = EXCLUDED.reason
        """),
        {"date": body.anchor_date, "amount": body.amount, "reason": body.reason, "uid": user.id},
    )
    commit(db)
    return {"status": "ok"}

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import CurrentUser, require_admin
from ..schemas import BillLineOut, BillOut

router = APIRouter(prefix="/customers", tags=["bills"])


@router.get("/{customer_id}/bill", response_model=BillOut)
def get_bill(
    customer_id: int,
    period_start: date,
    period_end: date,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_admin),
):
    """JSON bill data for the given range (spec §16-17). Rendering this to a
    shareable PNG/JPEG (spec §18) is a presentation-layer step — the
    Flutter side turns this payload into an image, e.g. by rendering a
    widget with RepaintBoundary and sharing it via share_plus."""
    if period_end < period_start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "period_end must not be before period_start")

    customer = db.execute(
        text("SELECT id, name, opening_due FROM customers WHERE id = :id"), {"id": customer_id}
    ).mappings().first()
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")

    lines = db.execute(
        text("""
            SELECT p.name AS product_name, sum(s.amount) AS total
            FROM sales s JOIN products p ON p.id = s.product_id
            WHERE s.customer_id = :cid AND s.sale_type = 'credit' AND s.deleted_at IS NULL
              AND s.txn_date BETWEEN :start AND :end
            GROUP BY p.name ORDER BY p.name
        """),
        {"cid": customer_id, "start": period_start, "end": period_end},
    ).mappings().all()
    grand_total = sum((l["total"] for l in lines), Decimal("0"))

    prior_sales = db.execute(
        text("""
            SELECT COALESCE(sum(amount), 0) AS total FROM sales
            WHERE customer_id = :cid AND sale_type = 'credit' AND deleted_at IS NULL AND txn_date < :start
        """),
        {"cid": customer_id, "start": period_start},
    ).scalar_one()
    prior_payments = db.execute(
        text("""
            SELECT COALESCE(sum(amount), 0) AS total FROM customer_payments
            WHERE customer_id = :cid AND deleted_at IS NULL AND txn_date < :start
        """),
        {"cid": customer_id, "start": period_start},
    ).scalar_one()
    previous_due = customer["opening_due"] + prior_sales - prior_payments

    payments_in_period = db.execute(
        text("""
            SELECT COALESCE(sum(amount), 0) AS total FROM customer_payments
            WHERE customer_id = :cid AND deleted_at IS NULL AND txn_date BETWEEN :start AND :end
        """),
        {"cid": customer_id, "start": period_start, "end": period_end},
    ).scalar_one()

    return BillOut(
        customer_id=customer["id"],
        customer_name=customer["name"],
        period_start=period_start,
        period_end=period_end,
        lines=[BillLineOut(**l) for l in lines],
        grand_total=grand_total,
        previous_due=previous_due,
        payments_in_period=payments_in_period,
        remaining_due=previous_due + grand_total - payments_in_period,
    )

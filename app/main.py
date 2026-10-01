from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from .routers import (
    auth, bills, customer_payments, customers, expenses,
    ledger, products, purchases, recurring, sales, supplier_payments, suppliers,
)

app = FastAPI(title="Dairy Shop API")

for r in (auth, products, suppliers, customers, purchases, supplier_payments,
          sales, customer_payments, expenses, recurring, ledger, bills):
    app.include_router(r.router)


@app.exception_handler(DBAPIError)
async def db_error_handler(request: Request, exc: DBAPIError):
    """Business-rule violations (no-overpayment guard, supplier/product
    mismatch, etc.) are enforced as Postgres triggers/constraints so they
    hold no matter which client writes the data. Some of those triggers are
    DEFERRED — they fire at COMMIT, which happens after the endpoint
    function has already returned, inside the get_audited_db dependency's
    teardown. This handler is what turns that into a clean 400 instead of
    a generic 500, by reading the message Postgres raised.
    """
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    diag = getattr(orig, "diag", None)
    message = (getattr(diag, "message_primary", None) or str(orig or exc)).strip()

    # SQLSTATE class '23' = integrity constraint violation (check, FK, unique,
    # not-null, exclusion) -- this covers both immediate errors (raised
    # synchronously from db.execute()) and our deferred guard triggers
    # (raised from the commit() call in deps.py, still inside the endpoint's
    # own execution -- see the note there for why that ordering matters).
    is_business_rule = bool(sqlstate) and sqlstate.startswith("23")
    status_code = 400 if is_business_rule else 500
    return JSONResponse(status_code=status_code, content={"detail": message})


@app.get("/health")
def health():
    return {"status": "ok"}

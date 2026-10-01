from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import CurrentUser, commit, get_audited_db, get_current_user, require_admin
from ..schemas import ProductIn, ProductOut

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductOut])
def list_products(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    sql = "SELECT id, name, unit, default_sale_price, is_active FROM products"
    if not include_inactive:
        sql += " WHERE is_active"
    sql += " ORDER BY name"
    rows = db.execute(text(sql)).mappings().all()
    return [ProductOut(**r) for r in rows]


@router.post("", response_model=ProductOut)
def create_product(body: ProductIn, db: Session = Depends(get_audited_db), _: CurrentUser = Depends(require_admin)):
    row = db.execute(
        text("""
            INSERT INTO products (name, unit, default_sale_price)
            VALUES (:name, :unit, :price)
            RETURNING id, name, unit, default_sale_price, is_active
        """),
        {"name": body.name, "unit": body.unit, "price": body.default_sale_price},
    ).mappings().first()
    commit(db)
    return ProductOut(**row)


@router.patch("/{product_id}/deactivate", response_model=ProductOut)
def deactivate_product(
    product_id: int, db: Session = Depends(get_audited_db), _: CurrentUser = Depends(require_admin)
):
    row = db.execute(
        text("""
            UPDATE products SET is_active = false WHERE id = :id
            RETURNING id, name, unit, default_sale_price, is_active
        """),
        {"id": product_id},
    ).mappings().first()
    commit(db)
    return ProductOut(**row)

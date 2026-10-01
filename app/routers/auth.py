from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import CurrentUser, get_current_user
from ..schemas import MeOut, Token
from ..security import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    row = db.execute(
        text("SELECT id, role, password_hash, is_active FROM users WHERE lower(username) = lower(:u)"),
        {"u": form.username},
    ).mappings().first()

    if row is None or not row["is_active"] or not verify_password(form.password, row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password")

    db.execute(text("UPDATE users SET last_login_at = now() WHERE id = :id"), {"id": row["id"]})
    db.commit()

    token = create_access_token(user_id=row["id"], role=row["role"])
    return Token(access_token=token)


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser = Depends(get_current_user)):
    return MeOut(id=user.id, full_name=user.full_name, role=user.role)

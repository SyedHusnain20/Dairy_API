from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from .database import get_db, set_audit_user
from .security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


@dataclass
class CurrentUser:
    id: int
    role: str
    full_name: str


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> CurrentUser:
    try:
        payload = decode_access_token(token)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Could not validate credentials")

    user_id = int(payload["sub"])
    row = db.execute(
        text("SELECT id, role, full_name, is_active FROM users WHERE id = :id"),
        {"id": user_id},
    ).mappings().first()

    if row is None or not row["is_active"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")

    return CurrentUser(id=row["id"], role=row["role"], full_name=row["full_name"])


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Backend-level role enforcement (spec §29): a worker's token is
    rejected here regardless of what the mobile UI does or doesn't show."""
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user


def get_audited_db(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """A DB session tagged with the current user, so every insert/update/
    delete trigger records who made the change. Use this (instead of
    get_db) in any endpoint that writes data.

    IMPORTANT — endpoints using this dependency MUST call db.commit()
    themselves, as the LAST step before returning their response, via the
    commit() helper below. Do NOT rely on this dependency to commit after
    yield: FastAPI sends the response before running a generator
    dependency's post-yield code, so a commit placed there raises the
    no-overpayment guard's deferred constraint (which only fires at COMMIT)
    too late — after the client has already been told "200 OK". This was
    caught in testing: a worker's huge overpayment came back as a
    successful response with a real payment id, while the database had
    actually rejected and rolled it back. Calling commit() inside the
    endpoint, before the return statement, ensures that failure surfaces
    as a clean error instead.

    This dependency's own job is just tagging the session and rolling
    back if the endpoint raises before ever committing.
    """
    set_audit_user(db, user.id)
    try:
        yield db
    except Exception:
        db.rollback()
        raise


def commit(db: Session) -> None:
    """Call as the last step of any write endpoint, before returning the
    response. Lets constraint violations (including deferred ones) raise
    and propagate to db_error_handler in main.py while we're still inside
    the endpoint's own execution — i.e. before FastAPI has built or sent
    a response, so a rejected write can never look like a success."""
    db.commit()

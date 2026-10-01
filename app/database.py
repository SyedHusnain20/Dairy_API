from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from .config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def set_audit_user(db: Session, user_id: int) -> None:
    """Tag the current DB transaction with who's making the change, so the
    fn_audit() trigger records it in audit_log. Must be called after a
    transaction has started (SET LOCAL only applies within one).
    Session.begin() below starts the transaction; call this right after.
    """
    db.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(user_id)})

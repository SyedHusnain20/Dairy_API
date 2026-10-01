"""
Create a user (admin or worker) with a bcrypt-hashed password.

Usage (run from the project root, with the venv active):
    python -m scripts.create_user --username admin --full-name "Owner" --role admin
    python -m scripts.create_user --username worker1 --full-name "Worker One" --role worker

You'll be prompted for the password so it never appears in shell history.
"""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.security import hash_password  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--role", choices=["admin", "worker"], required=True)
    args = parser.parse_args()

    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        db.execute(
            text("""
                INSERT INTO users (username, full_name, password_hash, role)
                VALUES (:username, :full_name, :hash, :role)
            """),
            {"username": args.username, "full_name": args.full_name,
             "hash": hash_password(password), "role": args.role},
        )
        db.commit()
        print(f"Created {args.role} user '{args.username}'.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

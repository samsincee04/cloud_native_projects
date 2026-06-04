from __future__ import annotations

import os

from sqlalchemy.orm import Session

from app.db import SessionLocal, create_tables
from worker.jobs import run_expiry_alerts, run_refresh_shopping_lists


def main() -> int:
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is required")

    create_tables()

    session: Session = SessionLocal()
    try:
        expiry = run_expiry_alerts(session)
        shopping = run_refresh_shopping_lists(session)
    finally:
        session.close()

    created = expiry.created_count + shopping.created_count
    skipped = expiry.skipped_count + shopping.skipped_count

    print(
        "jobs=daily "
        f"created_count={created} skipped_count={skipped} "
        f"(expiry_created={expiry.created_count} expiry_skipped={expiry.skipped_count} "
        f"shopping_created={shopping.created_count} shopping_skipped={shopping.skipped_count})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

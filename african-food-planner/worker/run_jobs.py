"""Legacy entrypoint: runs daily + weekly jobs in one shot."""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from app.db import SessionLocal, create_tables
from worker.jobs import (
    run_expiry_alerts,
    run_refresh_shopping_lists,
    run_weekly_plan_reminder,
)


def main() -> int:
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is required")

    create_tables()

    session: Session = SessionLocal()
    try:
        expiry = run_expiry_alerts(session)
        shopping = run_refresh_shopping_lists(session)
        weekly = run_weekly_plan_reminder(session)
    finally:
        session.close()

    created = expiry.created_count + shopping.created_count + weekly.created_count
    skipped = expiry.skipped_count + shopping.skipped_count + weekly.skipped_count

    print(
        "jobs=all "
        f"created_count={created} skipped_count={skipped} "
        f"(expiry_created={expiry.created_count} expiry_skipped={expiry.skipped_count} "
        f"shopping_created={shopping.created_count} shopping_skipped={shopping.skipped_count} "
        f"weekly_created={weekly.created_count} weekly_skipped={weekly.skipped_count})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from app.db import SessionLocal, create_tables
from worker.jobs import run_weekly_plan_reminder


def main() -> int:
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is required")

    create_tables()

    session: Session = SessionLocal()
    try:
        weekly = run_weekly_plan_reminder(session)
    finally:
        session.close()

    print(
        "jobs=weekly "
        f"created_count={weekly.created_count} skipped_count={weekly.skipped_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

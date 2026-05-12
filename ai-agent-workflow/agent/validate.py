"""Validate Step 4.1 extraction JSON against rubric (item count, evidence, item_id)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


def err(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def load(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        err(f"Cannot read {path}: {e}")
    except json.JSONDecodeError as e:
        err(f"Invalid JSON in {path}: {e}")


def validate_file(path: Path, expected_items: int) -> List[str]:
    data = load(path)
    problems: List[str] = []
    task = data.get("task")
    if task not in ("summary", "risks"):
        problems.append(f"task must be 'summary' or 'risks', got {task!r}")

    items = data.get("items")
    if not isinstance(items, list):
        problems.append("'items' must be a list")
        return problems

    if len(items) != expected_items:
        problems.append(
            f"expected exactly {expected_items} items, got {len(items)}"
        )

    id_pat = (
        re.compile(r"^summary_claim_(\d{2})$")
        if task == "summary"
        else re.compile(r"^risks_item_(\d{2})$")
    )

    for i, it in enumerate(items, start=1):
        if not isinstance(it, dict):
            problems.append(f"items[{i}] is not an object")
            continue
        iid = it.get("item_id")
        if not isinstance(iid, str) or not id_pat.match(iid):
            want = "summary_claim_NN" if task == "summary" else "risks_item_NN"
            problems.append(
                f"items[{i}].item_id must match {want}, got {iid!r}"
            )
        else:
            m = id_pat.match(iid)
            if m and int(m.group(1)) != i:
                problems.append(
                    f"items[{i}].item_id sequence mismatch: expected _{i:02d}, got {iid!r}"
                )
        ev = it.get("tenk_evidence")
        if not isinstance(ev, list) or len(ev) == 0:
            problems.append(f"items[{i}].tenk_evidence must be a non-empty list")

    return problems


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate extraction JSON (items count, tenk_evidence, item_id scheme)."
    )
    parser.add_argument(
        "files",
        nargs="+",
        type=str,
        help="One or more JSON files from agent.extract",
    )
    parser.add_argument(
        "--expect-items",
        type=int,
        default=5,
        help="Required number of items (default: 5)",
    )
    args = parser.parse_args()

    all_ok = True
    for fp in args.files:
        path = Path(fp).expanduser().resolve()
        probs = validate_file(path, args.expect_items)
        if probs:
            all_ok = False
            print(f"{path}:", file=sys.stderr)
            for p in probs:
                print(f"  - {p}", file=sys.stderr)
        else:
            print(f"OK {path}")

    if not all_ok:
        err("Validation failed.", code=2)


if __name__ == "__main__":
    main()

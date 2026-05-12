#!/usr/bin/env python3
"""Deterministic pair evaluation using current run_once clustering logic."""

from __future__ import annotations

import json
import re
import sys
import types
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# Allow importing clustering helpers from run_once.py without DB deps.
try:
    import psycopg as _psycopg  # type: ignore  # noqa: F401
except ModuleNotFoundError:
    psycopg_stub = types.ModuleType("psycopg")
    psycopg_stub.Cursor = object  # used only in type hints inside run_once
    sys.modules["psycopg"] = psycopg_stub

from run_once import (
    SEMANTIC_MERGE_THRESHOLD,
    classify_noise_lane,
    cluster_id_from_hash,
    cluster_key_string,
    date_bucket,
    detect_competition,
    epl_team_pair_from_title,
    hash_cluster_key,
    is_gossip,
    topic_from_title_and_url,
    topic_merge_group,
    title_summary_tfidf_cosine,
    title_core_signature,
    title_signature_n,
    title_signature_n_slug,
)

_MONTH_TO_NUM = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


@dataclass
class PairRow:
    label: str
    url_a: str
    title_a: str
    cluster_id_a: str | None
    url_b: str
    title_b: str
    cluster_id_b: str | None
    notes: str = ""


@dataclass
class PredictedArticleCluster:
    cluster_id: uuid.UUID
    key: str
    mode: str
    noise_lane: str | None


def _infer_published_at_from_url(url: str) -> datetime:
    """Infer deterministic date bucket from URL path; fallback is fixed epoch day."""
    # Example: /2026/apr/19/... or /2026/04/19/...
    m = re.search(r"/(20\d{2})/([a-z]{3}|\d{1,2})/(\d{1,2})/", url.lower())
    if m:
        year = int(m.group(1))
        month_raw = m.group(2)
        day = int(m.group(3))
        if month_raw.isdigit():
            month = int(month_raw)
        else:
            month = _MONTH_TO_NUM.get(month_raw)
        if month is not None:
            try:
                return datetime(year, month, day, tzinfo=UTC)
            except ValueError:
                pass
    return datetime(1970, 1, 1, tzinfo=UTC)


def compute_cluster_for_eval(title: str, url: str) -> PredictedArticleCluster:
    """Mirror run_once cluster-key logic (topic-gated + noise lanes)."""
    competition = detect_competition(url, url)
    published_at = _infer_published_at_from_url(url)
    date_b = date_bucket(published_at)

    if competition in ("F1", "NBA"):
        team1, team2 = "unknown", "unknown"
    else:
        team1, team2 = epl_team_pair_from_title(title)

    noise_lane = classify_noise_lane(title, url)
    gossip_hit, gossip_source = is_gossip(title, url)
    if gossip_hit:
        noise_lane = "gossip"
    topic_tag = topic_from_title_and_url(title, url)
    if noise_lane == "gossip":
        topic_tag = "gossip"
    effective_topic = noise_lane if noise_lane is not None else topic_tag
    topic_key = topic_merge_group(effective_topic)
    sig6_slug = title_signature_n_slug(title, 6)

    if gossip_hit:
        mode = "gossip_key"
        gossip_sig = title_signature_n_slug(title, 6)
        gossip_domain_group = (
            gossip_source
            if gossip_source in ("mirror.co.uk", "dailymail.co.uk")
            else "generic"
        )
        key = f"GOSSIP|domain={gossip_domain_group}|sig6={gossip_sig}|topic=gossip"
    elif team1 == "unknown" and team2 == "unknown":
        mode = "title_fallback"
        signature = title_core_signature(title)
        key = f"title:{signature}:topic={topic_key}"
    elif team2 == "unknown" and team1 != "unknown":
        mode = "entity_key_plus_sig"
        base = cluster_key_string(competition, date_b, team1, team2)
        key = f"{base}:topic={topic_key}:{sig6_slug}"
        _ = title_signature_n(title, 6)
    else:
        mode = "entity_key"
        base = cluster_key_string(competition, date_b, team1, team2)
        key = f"{base}:topic={topic_key}"

    if noise_lane is not None:
        key = f"noise={noise_lane}|{key}"

    key_hash = hash_cluster_key(key)
    cluster_id = cluster_id_from_hash(key_hash)
    return PredictedArticleCluster(
        cluster_id=cluster_id,
        key=key,
        mode=mode,
        noise_lane=noise_lane,
    )


def load_gold(path: Path) -> list[PairRow]:
    rows: list[PairRow] = []
    text = path.read_text(encoding="utf-8")
    for line_no, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        rows.append(
            PairRow(
                label=str(obj["label"]),
                url_a=str(obj["url_a"]),
                title_a=str(obj["title_a"]),
                cluster_id_a=(str(obj["cluster_id_a"]) if obj.get("cluster_id_a") else None),
                url_b=str(obj["url_b"]),
                title_b=str(obj["title_b"]),
                cluster_id_b=(str(obj["cluster_id_b"]) if obj.get("cluster_id_b") else None),
                notes=str(obj.get("notes", "")),
            )
        )
    return rows


def _resolve_gold_path(arg: str | None) -> Path:
    root = Path(__file__).resolve().parents[1]
    use_arg = arg or "docs/gold_pairs.jsonl"
    path = Path(use_arg)
    if not path.is_absolute():
        path = root / path
    return path


def main() -> int:
    gold_path = _resolve_gold_path(sys.argv[1] if len(sys.argv) > 1 else None)
    if not gold_path.is_file():
        print(f"Missing gold file: {gold_path}", file=sys.stderr)
        return 1

    rows = load_gold(gold_path)
    tp = fp = fn = tn = 0
    fp_examples: list[tuple[PairRow, PredictedArticleCluster, PredictedArticleCluster]] = []
    fn_examples: list[tuple[PairRow, PredictedArticleCluster, PredictedArticleCluster]] = []

    for row in rows:
        pa = compute_cluster_for_eval(row.title_a, row.url_a)
        pb = compute_cluster_for_eval(row.title_b, row.url_b)

        gold_merge = row.label == "merge"
        semantic_score = title_summary_tfidf_cosine(
            row.title_a,
            None,
            row.title_b,
            None,
        )
        if semantic_score >= SEMANTIC_MERGE_THRESHOLD:
            pred_merge = True
        else:
            pred_merge = pa.cluster_id == pb.cluster_id

        if gold_merge and pred_merge:
            tp += 1
        elif (not gold_merge) and pred_merge:
            fp += 1
            if len(fp_examples) < 3:
                fp_examples.append((row, pa, pb))
        elif gold_merge and (not pred_merge):
            fn += 1
            if len(fn_examples) < 3:
                fn_examples.append((row, pa, pb))
        else:
            tn += 1

    pred_pos = tp + fp
    gold_pos = tp + fn
    precision = tp / pred_pos if pred_pos else float("nan")
    recall = tp / gold_pos if gold_pos else float("nan")

    print(f"gold_file={gold_path}")
    print("prediction_mode=current_run_once_logic")
    print("stale_cluster_id_fields=reference_only")
    print(f"pairs_total={len(rows)}")
    print("confusion_matrix:")
    print(f"  TP={tp}  FP={fp}")
    print(f"  FN={fn}  TN={tn}")
    print(f"precision={precision:.4f}" if precision == precision else "precision=nan")
    print(f"recall={recall:.4f}" if recall == recall else "recall=nan")

    print("\nFP_examples (predicted merge, gold not_merge), up to 3:")
    if not fp_examples:
        print("  (none)")
    else:
        for i, (r, pa, pb) in enumerate(fp_examples, start=1):
            print(f"  [{i}] {r.title_a}")
            print(f"      a {r.url_a}")
            print(f"      {r.title_b}")
            print(f"      b {r.url_b}")
            print(f"      predicted_cluster={pa.cluster_id}")
            print(
                "      stale_reference="
                f"a:{r.cluster_id_a or 'missing'} b:{r.cluster_id_b or 'missing'}"
            )

    print("\nFN_examples (predicted not_merge, gold merge), up to 3:")
    if not fn_examples:
        print("  (none)")
    else:
        for i, (r, pa, pb) in enumerate(fn_examples, start=1):
            print(f"  [{i}] {r.title_a}")
            print(f"      a {r.url_a}  computed_cluster={pa.cluster_id}")
            print(f"      {r.title_b}")
            print(f"      b {r.url_b}  computed_cluster={pb.cluster_id}")
            print(
                "      stale_reference="
                f"a:{r.cluster_id_a or 'missing'} b:{r.cluster_id_b or 'missing'}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

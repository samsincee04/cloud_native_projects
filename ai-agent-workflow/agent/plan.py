"""Step 4.2: web-style query planning per extracted item (OpenRouter)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List
from urllib import request
from urllib.error import HTTPError

from dotenv import load_dotenv


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def err_exit(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def load_input_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        err_exit(f"Cannot read input file: {e}")
    except json.JSONDecodeError as e:
        err_exit(f"Input is not valid JSON: {e}")


def infer_company_name(filing_id: str) -> str:
    override = os.getenv("COMPANY_NAME", "").strip()
    if override:
        return override
    head = filing_id.split("_")[0].lower()
    fid = filing_id.lower()
    aliases: Dict[str, str] = {
        "msft": "Microsoft",
        "microsoft": "Microsoft",
        "tesla": "Tesla",
        "tsla": "Tesla",
        "aapl": "Apple",
        "nvda": "NVIDIA",
        "googl": "Alphabet",
        "goog": "Alphabet",
        "amzn": "Amazon",
        "meta": "Meta",
    }
    if head in aliases:
        return aliases[head]
    for k, v in aliases.items():
        if k in fid:
            return v
    err_exit(
        "Cannot infer company name from filing_id. Set COMPANY_NAME in .env "
        "or use a known filing_id prefix (e.g. msft_, tesla_)."
    )


def validate_step41(data: Dict[str, Any]) -> None:
    for k in ("task", "filing_id", "items"):
        if k not in data:
            err_exit(f"Input JSON missing required key: {k}")
    if data["task"] not in ("summary", "risks"):
        err_exit(f"task must be 'summary' or 'risks', got: {data['task']!r}")
    items = data.get("items")
    if not isinstance(items, list) or not items:
        err_exit("Input 'items' must be a non-empty list.")
    for i, it in enumerate(items, start=1):
        if not isinstance(it, dict):
            err_exit(f"items[{i}] must be an object.")
        for f in ("item_id", "item_text", "tenk_evidence"):
            if f not in it:
                err_exit(f"items[{i}] missing field: {f}")
        if not isinstance(it["tenk_evidence"], list) or not it["tenk_evidence"]:
            err_exit(f"items[{i}].tenk_evidence must be a non-empty list.")


def item_keywords(item_text: str) -> List[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9\-]+", item_text)
    stop = {
        "that", "this", "with", "from", "have", "been", "were", "will", "their",
        "which", "about", "into", "than", "also", "such", "other", "these", "those",
        "each", "most", "some", "more", "very", "when", "what", "where", "while",
        "during", "before", "after", "above", "below", "between", "through", "under",
        "within", "without", "against", "across", "including", "company", "business",
        "operating", "financial", "results", "fiscal", "year", "than", "only", "must",
    }
    out: List[str] = []
    for w in words:
        wl = w.lower()
        if len(wl) >= 4 and wl not in stop:
            out.append(wl)
    if not out:
        for w in words:
            wl = w.lower()
            if len(wl) >= 3 and wl not in stop:
                out.append(wl)
    return out[:16]


def query_has_item_keyword(query: str, keywords: List[str]) -> bool:
    q = query.lower()
    for kw in keywords:
        if kw in q:
            return True
    return False


def build_plan_prompt(
    company_name: str,
    filing_id: str,
    item_text: str,
    queries_per_item: int,
    keywords_hint: str,
) -> str:
    return (
        "You write short web-search queries (search-engine keyword phrases, not questions to a chatbot).\n"
        f"Return ONLY a JSON array of exactly {queries_per_item} strings.\n"
        "Rules:\n"
        f'- Every query MUST contain the company name "{company_name}" exactly as written.\n'
        "- Every query MUST include at least one topic-specific keyword from the atomic item "
        "(use words from the item; see keyword hints below).\n"
        "- Each query is a short phrase (under 20 words), not a paragraph.\n"
        "- Output must be valid JSON only: a single array of strings, no markdown fences.\n\n"
        f"filing_id: {filing_id}\n"
        f"Keyword hints from item (use at least one per query): {keywords_hint}\n\n"
        "Atomic item:\n"
        f"{item_text}\n"
    )


def strip_code_fence(content: str) -> str:
    s = content.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s


def parse_string_array(content: str) -> List[str]:
    raw = strip_code_fence(content)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        err_exit(f"LLM did not return valid JSON: {e}")
    if not isinstance(data, list):
        err_exit("LLM output must be a JSON array.")
    out: List[str] = []
    for x in data:
        if not isinstance(x, str) or not x.strip():
            err_exit("LLM array must contain only non-empty strings.")
        out.append(x.strip())
    return out


def call_openrouter_plan(user_prompt: str) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip()
    model = os.getenv("OPENROUTER_MODEL", "").strip()
    if not api_key or not model:
        err_exit("OPENROUTER_API_KEY and OPENROUTER_MODEL must be set in .env")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You output only valid JSON: a single array of strings for web search queries. "
                    "No prose outside JSON."
                ),
            },
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
    }

    req = request.Request(
        url=f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
    except HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        detail = _openrouter_error_detail(err_body)
        err_exit(f"OpenRouter HTTP {e.code}: {detail}")

    data = json.loads(body)
    choices = data.get("choices")
    if choices:
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if content is not None and isinstance(content, str) and content.strip():
            return content
        err_exit(
            "OpenRouter returned empty message content. "
            f"Body (truncated): {json.dumps(data)[:1200]}"
        )
    err_detail = _extract_api_error_message(data)
    if err_detail:
        err_exit(f"OpenRouter API error: {err_detail}")
    err_exit(
        "OpenRouter response missing choices. "
        f"Body (truncated): {json.dumps(data)[:1200]}"
    )


def _openrouter_error_detail(body: str) -> str:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return body[:1200]
    return _extract_api_error_message(data) or body[:1200]


def _extract_api_error_message(data: Dict[str, Any]) -> str | None:
    err = data.get("error")
    if err is None:
        return None
    if isinstance(err, dict):
        return str(err.get("message") or err.get("type") or json.dumps(err))
    return str(err)


def validate_queries(
    queries: List[str],
    company_name: str,
    keywords: List[str],
    queries_per_item: int,
) -> None:
    if len(queries) != queries_per_item:
        err_exit(
            f"Expected exactly {queries_per_item} queries, got {len(queries)}."
        )
    cn = company_name.lower()
    for j, q in enumerate(queries, start=1):
        ql = q.lower()
        if cn not in ql:
            err_exit(
                f'Query {j} must include company name "{company_name}". Got: {q!r}'
            )
        if not query_has_item_keyword(q, keywords):
            err_exit(
                f"Query {j} must include at least one topic keyword from the item. Got: {q!r}"
            )
        if len(q) > 400:
            err_exit(f"Query {j} is too long; use short search phrases.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan web search queries per extracted item.")
    parser.add_argument("--input", type=str, required=True, help="Step 4.1 JSON from agent.extract.")
    parser.add_argument("--output", type=str, required=True, help="Path to write planned JSON.")
    parser.add_argument(
        "--queries_per_item",
        type=int,
        choices=[1, 2],
        required=True,
        help="Exactly 1 or 2 queries per item.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv(project_root() / ".env")

    in_path = Path(args.input).expanduser().resolve()
    out_path = Path(args.output).expanduser().resolve()

    data = load_input_json(in_path)
    validate_step41(data)
    company_name = infer_company_name(str(data["filing_id"]))
    filing_id = str(data["filing_id"])
    qpi = args.queries_per_item

    out_items: List[Dict[str, Any]] = []
    for it in data["items"]:
        item = deepcopy(it)
        item_text = str(item["item_text"])
        kws = item_keywords(item_text)
        if not kws:
            err_exit("Could not derive keywords from item_text for query validation.")
        kw_hint = ", ".join(kws[:8])
        prompt = build_plan_prompt(
            company_name, filing_id, item_text, qpi, kw_hint
        )
        raw = call_openrouter_plan(prompt)
        queries = parse_string_array(raw)
        if len(queries) > qpi:
            queries = queries[:qpi]
        validate_queries(queries, company_name, kws, qpi)
        item["queries"] = queries
        out_items.append(item)

    out_doc: Dict[str, Any] = {
        "task": data["task"],
        "filing_id": data["filing_id"],
        "items": out_items,
    }

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        err_exit(f"Cannot write output file: {e}")


if __name__ == "__main__":
    main()

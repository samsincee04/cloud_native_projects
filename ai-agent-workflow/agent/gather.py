"""Step 4.3: Tavily search + extract for planned queries."""

from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

try:
    from tavily import TavilyClient
except ImportError as e:
    print("Missing dependency: pip install tavily-python", file=sys.stderr)
    raise SystemExit(1) from e


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def err_exit(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


MAX_EXTRACTED_CHARS = 8000
URLS_PER_QUERY = 3


def load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        err_exit(f"Cannot read input file: {e}")
    except json.JSONDecodeError as e:
        err_exit(f"Input is not valid JSON: {e}")


def validate_input(data: Dict[str, Any]) -> None:
    for k in ("task", "filing_id", "items"):
        if k not in data:
            err_exit(f"Input JSON missing required key: {k}")
    items = data.get("items")
    if not isinstance(items, list) or not items:
        err_exit("Input 'items' must be a non-empty list.")
    for i, it in enumerate(items, start=1):
        if not isinstance(it, dict):
            err_exit(f"items[{i}] must be an object.")
        if "queries" not in it or not isinstance(it["queries"], list) or not it["queries"]:
            err_exit(f"items[{i}] must include non-empty 'queries' list.")


def truncate_text(text: str, limit: int = MAX_EXTRACTED_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


def normalize_url(u: str) -> str:
    return (u or "").strip()


def parse_search_result(res: Dict[str, Any]) -> Tuple[str, Optional[str], Optional[str]]:
    url = normalize_url(str(res.get("url", "")))
    title = res.get("title")
    if title is not None:
        title = str(title)
    snippet = res.get("content")
    if snippet is not None:
        snippet = str(snippet)
    return url, title, snippet


def parse_extract_result(res: Dict[str, Any]) -> Tuple[str, str]:
    url = normalize_url(str(res.get("url", "")))
    raw = res.get("raw_content") or res.get("content") or ""
    return url, str(raw) if raw is not None else ""


def gather_for_item(
    client: TavilyClient,
    item: Dict[str, Any],
    max_searches: int,
    max_extracts: int,
    search_calls: List[int],
    extract_calls: List[int],
    url_store: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Mutates search_calls[0], extract_calls[0], url_store.
    Returns (sources_for_item, gather_status).
    """
    queries = [str(q).strip() for q in item.get("queries", []) if str(q).strip()]
    sources: List[Dict[str, Any]] = []
    seen_in_item: set[str] = set()

    incomplete = False

    for q in queries:
        if search_calls[0] >= max_searches:
            incomplete = True
            break
        try:
            resp = client.search(
                query=q,
                max_results=URLS_PER_QUERY,
                topic="finance",
            )
        except Exception as e:
            err_exit(f"Tavily search failed for query {q!r}: {e}")
        search_calls[0] += 1

        results = resp.get("results") or []
        for res in results[:URLS_PER_QUERY]:
            url, title, snippet = parse_search_result(res)
            if not url:
                continue
            if url in seen_in_item:
                continue
            seen_in_item.add(url)

            if url not in url_store:
                if extract_calls[0] >= max_extracts:
                    url_store[url] = {
                        "url": url,
                        "title": title,
                        "snippet": snippet,
                        "extracted_text": "",
                        "retrieved_at": _now_iso(),
                    }
                    incomplete = True
                else:
                    try:
                        ex = client.extract(urls=[url], format="text")
                    except Exception as e:
                        err_exit(f"Tavily extract failed for {url!r}: {e}")
                    extract_calls[0] += 1
                    extracted = ""
                    for er in ex.get("results") or []:
                        u2, raw = parse_extract_result(er)
                        if normalize_url(u2) == url:
                            extracted = raw
                            break
                    url_store[url] = {
                        "url": url,
                        "title": title,
                        "snippet": snippet,
                        "extracted_text": truncate_text(extracted),
                        "retrieved_at": _now_iso(),
                    }
            rec = url_store[url]
            sources.append(
                {
                    "url": rec["url"],
                    "title": rec.get("title"),
                    "snippet": rec.get("snippet"),
                    "extracted_text": rec.get("extracted_text", ""),
                    "retrieved_at": rec.get("retrieved_at"),
                }
            )

    if incomplete:
        return sources, "partial_budget_exhausted"
    return sources, "gathered"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Gather web sources via Tavily search + extract.")
    p.add_argument("--input", type=str, required=True, help="Step 4.2 JSON from agent.plan.")
    p.add_argument("--output", type=str, required=True, help="Path to write gathered JSON.")
    p.add_argument("--max_searches", type=int, required=True, help="Max Tavily search calls (total).")
    p.add_argument("--max_extracts", type=int, required=True, help="Max URLs to extract (total).")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.max_searches < 0 or args.max_extracts < 0:
        err_exit("--max_searches and --max_extracts must be non-negative.")

    load_dotenv(project_root() / ".env")

    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        err_exit(
            "TAVILY_API_KEY is missing. Add it to your .env file (e.g. TAVILY_API_KEY=...)."
        )

    in_path = Path(args.input).expanduser().resolve()
    out_path = Path(args.output).expanduser().resolve()

    data = load_json(in_path)
    validate_input(data)

    client = TavilyClient(api_key=api_key)
    search_calls = [0]
    extract_calls = [0]
    url_store: Dict[str, Dict[str, Any]] = {}

    out_items: List[Dict[str, Any]] = []
    budget_search_exhausted = False

    for item in data["items"]:
        it = deepcopy(item)
        if budget_search_exhausted or search_calls[0] >= args.max_searches:
            budget_search_exhausted = True
            it["sources"] = []
            it["gather_status"] = "budget_exhausted"
            out_items.append(it)
            continue

        sources, status = gather_for_item(
            client,
            item,
            args.max_searches,
            args.max_extracts,
            search_calls,
            extract_calls,
            url_store,
        )
        if search_calls[0] >= args.max_searches:
            budget_search_exhausted = True
        it["sources"] = sources
        it["gather_status"] = status
        out_items.append(it)

    out_doc = {
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

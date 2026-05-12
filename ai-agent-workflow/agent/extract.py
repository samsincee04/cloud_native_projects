from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List
from urllib import request

from dotenv import load_dotenv


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def err_exit(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def load_input_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        err_exit(f"Cannot read input file: {e}")
    except json.JSONDecodeError as e:
        err_exit(f"Input is not valid JSON: {e}")
    return data


def validate_input(data: Dict[str, Any]) -> None:
    required = ("task", "filing_id", "answer", "evidence")
    missing = [k for k in required if k not in data]
    if missing:
        err_exit(f"Input JSON missing required keys: {', '.join(missing)}")
    task = data["task"]
    if task not in ("summary", "risks"):
        err_exit(f"task must be 'summary' or 'risks', got: {task!r}")
    if not isinstance(data.get("evidence"), list) or not data["evidence"]:
        err_exit("Input 'evidence' must be a non-empty list.")


def normalize_evidence_object(obj: Any) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        err_exit("Each evidence entry must be a JSON object.")
    out: Dict[str, Any] = {}
    cid = obj.get("id")
    if cid is not None:
        out["id"] = cid
    if "text" not in obj or not str(obj["text"]).strip():
        err_exit("Each evidence object must include non-empty 'text'.")
    out["text"] = str(obj["text"]).strip()
    if "source" in obj:
        out["source"] = obj["source"]
    if "page" in obj and obj["page"] is not None:
        out["page"] = obj["page"]
    return out


def top_k_evidence(evidence: List[Any], max_items: int) -> List[Dict[str, Any]]:
    normalized = [normalize_evidence_object(e) for e in evidence]
    k = min(len(normalized), max_items)
    if k < 1:
        err_exit("No valid evidence entries after normalization.")
    return deepcopy(normalized[:k])


def build_extraction_prompt(task: str, answer: str, max_items: int) -> str:
    kind = "independent factual claims about the company (summary task)" if task == "summary" else (
        "independent risk statements (risks task)"
    )
    return (
        f"You split a 10-K analysis into exactly {max_items} short atomic items.\n"
        f"Each item must be one idea only: {kind}.\n"
        "Rules:\n"
        f"- Return ONLY a JSON array of exactly {max_items} strings (no keys, no object wrapper).\n"
        "- Each string is one short atomic sentence or bullet-sized phrase.\n"
        "- Do not include markdown, commentary, or text outside the JSON array.\n"
        "- Base items only on the answer text below.\n\n"
        "Answer to split:\n"
        f"{answer}\n"
    )


def call_openrouter_json_array(user_prompt: str) -> str:
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
                    "You output only valid JSON. For extraction tasks you return "
                    "only a JSON array of strings, nothing else."
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
    except Exception as e:
        err_exit(f"OpenRouter request failed: {e}")
    data = json.loads(body)
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        err_exit(f"Unexpected OpenRouter response shape: {e}")


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract atomic claims or risks from query JSON output."
    )
    parser.add_argument("--input", type=str, required=True, help="Path to query --format json file.")
    parser.add_argument("--output", type=str, required=True, help="Path to write extraction JSON.")
    parser.add_argument(
        "--max_items",
        type=int,
        required=True,
        help="Exact number of atomic items to extract.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.max_items < 1:
        err_exit("--max_items must be a positive integer.")

    load_dotenv(project_root() / ".env")
    in_path = Path(args.input).expanduser().resolve()
    out_path = Path(args.output).expanduser().resolve()

    data = load_input_json(in_path)
    validate_input(data)
    task = data["task"]
    filing_id = data["filing_id"]
    answer = str(data["answer"])
    evidence_in = data["evidence"]

    tenk_block = top_k_evidence(evidence_in, args.max_items)

    prompt = build_extraction_prompt(task, answer, args.max_items)
    raw_reply = call_openrouter_json_array(prompt)
    items_text = parse_string_array(raw_reply)

    if len(items_text) < args.max_items:
        err_exit(
            f"LLM returned {len(items_text)} items; expected exactly {args.max_items}."
        )
    if len(items_text) > args.max_items:
        items_text = items_text[: args.max_items]

    prefix = "summary_claim" if task == "summary" else "risks_item"
    items: List[Dict[str, Any]] = []
    for i, text in enumerate(items_text, start=1):
        items.append(
            {
                "item_id": f"{prefix}_{i:02d}",
                "item_text": text,
                "tenk_evidence": deepcopy(tenk_block),
            }
        )

    out_doc = {
        "task": task,
        "filing_id": filing_id,
        "items": items,
    }

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        err_exit(f"Cannot write output file: {e}")


if __name__ == "__main__":
    main()

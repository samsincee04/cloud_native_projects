"""Step 4.4: evaluate gathered sources and assign verdicts (OpenRouter)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple
from urllib import request
from urllib.error import HTTPError

from dotenv import load_dotenv


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def err_exit(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


ALLOWED_VERDICTS = frozenset({"supports", "contradicts", "insufficient_evidence"})
MAX_EXCERPT_CHARS = 2500


def load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        err_exit(f"Cannot read input file: {e}")
    except json.JSONDecodeError as e:
        err_exit(f"Input is not valid JSON: {e}")


def validate_input(data: Dict[str, Any]) -> None:
    if "items" not in data or not isinstance(data["items"], list):
        err_exit("Input must contain a non-empty 'items' list.")
    for i, it in enumerate(data["items"], start=1):
        if not isinstance(it, dict):
            err_exit(f"items[{i}] must be an object.")
        if "item_text" not in it:
            err_exit(f"items[{i}] missing 'item_text'.")
        if "sources" not in it or not isinstance(it["sources"], list):
            err_exit(f"items[{i}] missing 'sources' list.")


def normalize_url(u: str) -> str:
    return (u or "").strip()


def allowed_source_urls(sources: List[Dict[str, Any]]) -> Set[str]:
    out: Set[str] = set()
    for s in sources:
        if isinstance(s, dict) and s.get("url"):
            out.add(normalize_url(str(s["url"])))
    return out


def has_usable_extracted_text(sources: List[Dict[str, Any]]) -> bool:
    for s in sources:
        if not isinstance(s, dict):
            continue
        et = s.get("extracted_text")
        if et is not None and str(et).strip():
            return True
    return False


def guardrail_insufficient(reason: str) -> Tuple[str, str, List[str]]:
    return "insufficient_evidence", reason, []


def build_evidence_block(sources: List[Dict[str, Any]]) -> Tuple[str, Set[str]]:
    lines: List[str] = []
    urls: Set[str] = set()
    for s in sources:
        if not isinstance(s, dict):
            continue
        url = normalize_url(str(s.get("url", "")))
        if not url:
            continue
        urls.add(url)
        et = s.get("extracted_text")
        text = "" if et is None else str(et).strip()
        if len(text) > MAX_EXCERPT_CHARS:
            text = text[:MAX_EXCERPT_CHARS] + "\n...[truncated]"
        lines.append(f"URL: {url}\nEXCERPT:\n{text}\n")
    return "\n---\n".join(lines), urls


def build_judge_prompt(item_text: str, evidence_block: str, url_list: List[str]) -> str:
    allowed = "\n".join(f"- {u}" for u in url_list)
    return (
        "You judge whether external web sources support, contradict, or fail to substantiate "
        "the atomic claim below.\n"
        "Return ONLY a single JSON object (no markdown fences) with exactly these keys:\n"
        '- "verdict": one of: supports, contradicts, insufficient_evidence\n'
        '- "verdict_reason": short string grounded in the excerpts (paraphrase allowed)\n'
        '- "cited_urls": array of strings; each MUST be copied exactly from the allowed URL list below\n\n'
        "Rules:\n"
        "- If excerpts are weak, off-topic, or do not address the claim, verdict must be insufficient_evidence.\n"
        "- cited_urls must be a subset of the allowed URLs only; use [] if insufficient_evidence.\n"
        "- Do not invent URLs.\n\n"
        f"Allowed URLs (only these may appear in cited_urls):\n{allowed}\n\n"
        "Atomic claim:\n"
        f"{item_text}\n\n"
        "Source excerpts:\n"
        f"{evidence_block}\n"
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


def call_openrouter_judge(user_prompt: str) -> str:
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
                    "You output only valid JSON objects for verdict tasks. "
                    "No markdown outside JSON."
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


def parse_verdict_object(content: str) -> Dict[str, Any]:
    raw = strip_code_fence(content)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        err_exit(f"Model did not return valid JSON: {e}")
    if not isinstance(obj, dict):
        err_exit("Model output must be a JSON object.")
    return obj


def normalize_verdict(
    obj: Dict[str, Any],
    allowed_urls: Set[str],
) -> Tuple[str, str, List[str]]:
    verdict = obj.get("verdict")
    reason = obj.get("verdict_reason")
    cited = obj.get("cited_urls")

    if not isinstance(verdict, str) or verdict.strip() not in ALLOWED_VERDICTS:
        verdict = "insufficient_evidence"
    else:
        verdict = verdict.strip()

    if not isinstance(reason, str) or not reason.strip():
        reason = "No valid reason provided; treating as insufficient evidence."
    else:
        reason = reason.strip()

    if not isinstance(cited, list):
        cited = []
    cleaned: List[str] = []
    for u in cited:
        if not isinstance(u, str):
            continue
        nu = normalize_url(u)
        if nu in allowed_urls:
            cleaned.append(nu)

    if verdict != "insufficient_evidence" and not cleaned:
        verdict = "insufficient_evidence"
        if "cited" not in reason.lower():
            reason = (
                f"{reason} (No valid cited URLs from the allowed list; insufficient_evidence.)"
            )

    return verdict, reason, cleaned


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Assign verdicts to gathered items (Step 4.4).")
    p.add_argument("--input", type=str, required=True, help="Step 4.3 JSON from agent.gather.")
    p.add_argument("--output", type=str, required=True, help="Path to write judged JSON.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv(project_root() / ".env")

    in_path = Path(args.input).expanduser().resolve()
    out_path = Path(args.output).expanduser().resolve()

    data = load_json(in_path)
    validate_input(data)

    out_items: List[Dict[str, Any]] = []
    for it in data["items"]:
        item = deepcopy(it)
        sources = item.get("sources", [])
        if not isinstance(sources, list):
            sources = []

        if not sources or not has_usable_extracted_text(sources):
            v, r, cu = guardrail_insufficient(
                "No sources were available, or all extracted_text fields were empty; "
                "external evidence cannot be evaluated."
            )
            item["verdict"] = v
            item["verdict_reason"] = r
            item["cited_urls"] = cu
            out_items.append(item)
            continue

        block, url_set = build_evidence_block(sources)
        if not url_set:
            v, r, cu = guardrail_insufficient(
                "No valid URLs in sources; cannot cite external evidence."
            )
            item["verdict"] = v
            item["verdict_reason"] = r
            item["cited_urls"] = cu
            out_items.append(item)
            continue

        url_list = sorted(url_set)
        prompt = build_judge_prompt(str(item.get("item_text", "")), block, url_list)
        raw = call_openrouter_judge(prompt)
        obj = parse_verdict_object(raw)
        verdict, reason, cited = normalize_verdict(obj, url_set)
        item["verdict"] = verdict
        item["verdict_reason"] = reason
        item["cited_urls"] = cited
        out_items.append(item)

    out_doc = {
        **{k: v for k, v in data.items() if k != "items"},
        "items": out_items,
    }

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        err_exit(f"Cannot write output file: {e}")


if __name__ == "__main__":
    main()

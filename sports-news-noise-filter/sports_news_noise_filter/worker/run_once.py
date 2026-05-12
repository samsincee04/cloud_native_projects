from __future__ import annotations

import hashlib
import json
import math
import os
import time
import re
import socket
import sys
import uuid
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional
AUDIO_TITLE_MARKERS = ("episode", "listen", "podcast", "audio")

REPORT_SPORTS = ("soccer", "nba", "wnba", "f1", "other")
REPORT_TOPICS = (
    "match",
    "preview",
    "lineup",
    "transfer",
    "injury",
    "discipline",
    "manager",
    "finance",
    "standings",
    "tactics",
    "opinion",
    "other",
)

TOPIC_COMPATIBILITY: dict[str, set[str]] = {
    "match": {"match", "preview", "lineup", "updates"},
    "preview": {"preview", "lineup", "match", "updates"},
    "lineup": {"lineup", "preview", "match", "updates"},
    "opinion": {"opinion", "tactics", "standings"},
    "tactics": {"tactics", "opinion", "standings"},
    "standings": {"standings", "opinion", "tactics"},
    "transfer": {"transfer"},
    "injury": {"injury"},
    "discipline": {"discipline"},
    "manager": {"manager"},
    "finance": {"finance"},
    "other": {"other"},
    # Noise lanes are hard-isolated.
    "gossip": {"gossip"},
    "betting": {"betting"},
    "watch": {"watch"},
    "updates": {"updates", "match", "preview", "lineup"},
}
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import psycopg
from psycopg.types.json import Json

DEFAULT_DATABASE_URL = "postgresql://sports:sports@localhost:5432/sportsnews"
REQUEST_TIMEOUT_SECONDS = 15
SIM_THRESHOLD_DEFAULT = 0.82
EMBEDDING_DIM = 384
EMBEDDINGS_PROVIDER_DEFAULT = "stub"
EMBEDDINGS_MODEL_DEFAULT = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_LOOKBACK_DAYS = 7
HIGH_SIM_OVERRIDE_DEFAULT = 0.88

# LLM enrichment (optional; OpenRouter-compatible API).
ENABLE_LLM_SUMMARY_DEFAULT = "false"
LLM_PROVIDER_DEFAULT = "openrouter"
LLM_MODEL_DEFAULT = "nvidia/nemotron-3"
LLM_TIMEOUT_SECS_DEFAULT = 30
LLM_MAX_TOKENS_DEFAULT = 400
LLM_JUDGE_SIM_LOW = 0.78
LLM_JUDGE_SIM_HIGH = 0.82
LLM_ENRICH_MAX_CLUSTERS = 50
LLM_ENRICH_SLEEP_SECS_DEFAULT = 0.0

_LOCAL_EMBEDDER = None
_EMBEDDING_SKIP_LOGGED = False
_EMBEDDING_LOCAL_LOAD_ERROR_LOGGED = False
_LLM_SKIP_LOGGED = False


def _log_llm_skip_once(reason: str) -> None:
    global _LLM_SKIP_LOGGED
    if _LLM_SKIP_LOGGED:
        return
    print(f"llm_skip: reason={reason}")
    _LLM_SKIP_LOGGED = True


def llm_enrichment_config() -> tuple[bool, str, str, str, int, float]:
    """Returns (enabled, api_key, provider, model, max_tokens, timeout_secs)."""
    raw = os.getenv("ENABLE_LLM_SUMMARY", ENABLE_LLM_SUMMARY_DEFAULT).strip().lower()
    enabled = raw in ("1", "true", "yes", "on")
    api_key = (os.getenv("LLM_API_KEY") or "").strip()
    provider = os.getenv("LLM_PROVIDER", LLM_PROVIDER_DEFAULT).strip() or LLM_PROVIDER_DEFAULT
    model = os.getenv("LLM_MODEL", LLM_MODEL_DEFAULT).strip() or LLM_MODEL_DEFAULT
    try:
        max_tokens = int(os.getenv("LLM_MAX_TOKENS", str(LLM_MAX_TOKENS_DEFAULT)))
    except ValueError:
        max_tokens = LLM_MAX_TOKENS_DEFAULT
    try:
        timeout = float(os.getenv("LLM_TIMEOUT_SECS", str(LLM_TIMEOUT_SECS_DEFAULT)))
    except ValueError:
        timeout = float(LLM_TIMEOUT_SECS_DEFAULT)
    return enabled, api_key, provider, model, max_tokens, timeout


def llm_should_run() -> bool:
    enabled, api_key, _, _, _, _ = llm_enrichment_config()
    return bool(enabled and api_key)


def llm_enrich_inter_request_sleep_secs() -> float:
    """Pause between cluster enrichment calls (helps OpenRouter free-tier per-minute caps)."""
    try:
        return max(0.0, float(os.getenv("LLM_ENRICH_SLEEP_SECS", str(LLM_ENRICH_SLEEP_SECS_DEFAULT))))
    except ValueError:
        return 0.0


def llm_enrichment_response_format_json() -> bool:
    """Ask OpenRouter for JSON object output (supported by many models; 400 falls back)."""
    raw = (os.getenv("LLM_RESPONSE_FORMAT_JSON") or "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


def llm_enrichment_should_use_response_format_json(model: str) -> bool:
    """``json_object`` + reasoning models often yields empty ``content``; skip for o-series."""
    if not llm_enrichment_response_format_json():
        return False
    m = model.lower()
    for needle in ("/o4", "o4-mini", "/o3", "o3-mini", "/o1", "o1-mini", "o1-preview"):
        if needle in m:
            return False
    return True


def print_llm_container_env_summary() -> None:
    """What the container actually sees from Compose (no API key printed)."""
    raw = os.getenv("ENABLE_LLM_SUMMARY")
    stripped = (raw or "").strip()
    if raw is None:
        shown = "(unset)"
    elif not stripped:
        shown = "(empty)"
    else:
        shown = repr(stripped)
    flag_on = stripped.lower() in ("1", "true", "yes", "on")
    key_set = bool((os.getenv("LLM_API_KEY") or "").strip())
    print(
        "llm_container_env: "
        f"ENABLE_LLM_SUMMARY={shown} "
        f"flag_on={flag_on} "
        f"LLM_API_KEY_present={key_set} "
        f"will_enrich={flag_on and key_set}"
    )


def _normalize_openrouter_message_content(content: object) -> str:
    """OpenRouter / some models return ``content`` as a string or a list of blocks."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif isinstance(block.get("content"), str):
                    parts.append(block["content"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts).strip()
    return ""


def _openrouter_reasoning_details_to_text(details: object) -> str:
    """Flatten OpenRouter / reasoning-model ``reasoning_details`` into plain text."""
    if details is None:
        return ""
    if isinstance(details, str):
        return details.strip()
    if isinstance(details, dict):
        chunks: list[str] = []
        for key in ("text", "content", "summary", "reasoning"):
            v = details.get(key)
            if isinstance(v, str) and v.strip():
                chunks.append(v.strip())
        nested = details.get("details") or details.get("reasoning_details")
        sub = _openrouter_reasoning_details_to_text(nested)
        if sub:
            chunks.append(sub)
        return "\n".join(chunks).strip()
    if isinstance(details, list):
        parts: list[str] = []
        for item in details:
            parts.append(_openrouter_reasoning_details_to_text(item))
        return "\n".join(p for p in parts if p).strip()
    return ""


_SKIP_REASONING_VALUE_KEYS = frozenset(
    {"encrypted_content", "encrypted_text", "signature", "hash", "checksum"}
)


def _collect_reasoning_strings(
    obj: object, *, min_len: int = 8, _depth: int = 0
) -> list[str]:
    """Deep-collect user-visible strings from OpenRouter ``reasoning`` / ``reasoning_details``."""
    if _depth > 24:
        return []
    out: list[str] = []
    if isinstance(obj, str):
        t = obj.strip()
        if len(t) >= min_len:
            out.append(t)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in _SKIP_REASONING_VALUE_KEYS:
                continue
            out.extend(
                _collect_reasoning_strings(v, min_len=min_len, _depth=_depth + 1)
            )
    elif isinstance(obj, list):
        for v in obj:
            out.extend(
                _collect_reasoning_strings(v, min_len=min_len, _depth=_depth + 1)
            )
    return out


def _openrouter_message_assistant_text(msg: dict) -> str:
    """Normalize assistant text; reasoning models may split output across ``content`` and ``reasoning``."""
    refusal = msg.get("refusal")
    if refusal is True:
        raise ValueError("LLM refused the request (refusal=true)")
    if isinstance(refusal, str) and refusal.strip():
        raise ValueError(f"LLM refused: {refusal.strip()[:500]}")

    blocks: list[str] = []
    content = _normalize_openrouter_message_content(msg.get("content"))
    if content:
        blocks.append(content)

    reasoning = msg.get("reasoning")
    if isinstance(reasoning, list):
        reasoning = _openrouter_reasoning_details_to_text(reasoning)
    if isinstance(reasoning, str) and reasoning.strip():
        blocks.append(reasoning.strip())

    rd_text = _openrouter_reasoning_details_to_text(msg.get("reasoning_details"))
    if rd_text:
        blocks.append(rd_text)

    if not blocks:
        loose: list[str] = []
        loose.extend(_collect_reasoning_strings(msg.get("reasoning_details")))
        loose.extend(_collect_reasoning_strings(msg.get("reasoning")))
        if loose:
            blocks.append("\n\n".join(loose))

    out = "\n\n".join(blocks).strip()
    if not out:
        raise ValueError(f"empty LLM message content (keys={list(msg.keys())})")
    return out


def _openrouter_chat_completion_payload_to_text(
    payload: dict,
    *,
    api_key: str,
    timeout: float,
) -> str:
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw_bytes = resp.read()
    except HTTPError as e:
        frag = e.read().decode("utf-8", errors="replace")[:800]
        raise ValueError(f"openrouter HTTP {e.code}: {frag}") from e
    outer = json.loads(raw_bytes.decode("utf-8"))
    err = outer.get("error")
    if err:
        raise ValueError(f"openrouter error: {err}")
    choices = outer.get("choices") or []
    if not choices:
        raise ValueError("no choices in LLM response")
    msg = choices[0].get("message") or {}
    return _openrouter_message_assistant_text(msg)


def openrouter_chat_completion(
    user_prompt: str,
    *,
    api_key: str,
    model: str,
    max_tokens: int,
    timeout: float,
    response_format_json: bool = False,
) -> str:
    """POST to OpenRouter chat completions; returns assistant message content."""
    base: dict = {
        "model": model,
        "messages": [{"role": "user", "content": user_prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    if response_format_json:
        with_json = {**base, "response_format": {"type": "json_object"}}
        try:
            return _openrouter_chat_completion_payload_to_text(
                with_json, api_key=api_key, timeout=timeout
            )
        except ValueError as exc:
            if "HTTP 400" not in str(exc):
                raise
            return _openrouter_chat_completion_payload_to_text(
                base, api_key=api_key, timeout=timeout
            )
    return _openrouter_chat_completion_payload_to_text(
        base, api_key=api_key, timeout=timeout
    )


def _strip_json_fence(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s


def _extract_first_json_object(text: str) -> str | None:
    """If the model adds prose around JSON, take the first balanced {...} span."""
    s = text.strip()
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    for i, ch in enumerate(s[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


def _extract_all_balanced_json_spans(text: str) -> list[str]:
    """Every top-level balanced ``{...}`` span (reasoning prose may precede the real JSON)."""
    s = text.strip()
    out: list[str] = []
    n = len(s)
    i = 0
    while i < n:
        start = s.find("{", i)
        if start < 0:
            break
        depth = 0
        end = -1
        for j in range(start, n):
            ch = s[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = j
                    break
        if end < 0:
            break
        out.append(s[start : end + 1])
        i = end + 1
    return out


def parse_llm_json_object(text: str) -> dict:
    s = _strip_json_fence(text)
    if not s:
        raise ValueError("LLM returned empty text after stripping code fences")
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    candidates: list[dict] = []
    seen: set[str] = set()
    for span in _extract_all_balanced_json_spans(s):
        if span in seen:
            continue
        seen.add(span)
        try:
            o = json.loads(span)
            if isinstance(o, dict):
                candidates.append(o)
        except json.JSONDecodeError:
            continue
    if candidates:
        for o in reversed(candidates):
            summ = o.get("summary")
            if isinstance(summ, str) and summ.strip():
                return o
        for o in reversed(candidates):
            if isinstance(o.get("summary"), str):
                return o
        for o in reversed(candidates):
            if "same_story" in o:
                return o
        return candidates[-1]

    blob = _extract_first_json_object(s)
    if blob and blob not in seen:
        try:
            obj = json.loads(blob)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    preview = s[:160].replace("\n", "\\n")
    raise ValueError(f"LLM JSON parse failed; preview={preview!r}")


def build_cluster_context_payload(
    *,
    cluster_id: uuid.UUID,
    headline: str | None,
    sport: str | None,
    topic: str | None,
    source_count: int,
    prior_summary: str | None,
    articles: list[tuple[str, str]],
) -> dict:
    return {
        "cluster_id": str(cluster_id),
        "headline": headline or "",
        "sport": sport or "",
        "topic": topic or "",
        "source_count": source_count,
        "prior_summary": prior_summary or "",
        "articles": [{"title": t, "url": u} for t, u in articles],
    }


def build_cluster_enrichment_prompt(context: dict) -> str:
    ctx = json.dumps(context, ensure_ascii=False)
    return f"""You are a sports news assistant. Using ONLY this cluster context JSON, output one JSON object and nothing else.
The first character of your reply MUST be `{{` and the last MUST be `}}`. Do not write plans, analysis, or sentences like "We need to" before the JSON. No markdown fences.

Context:
{ctx}

Required JSON shape:
{{
  "summary": "string, 2-4 sentences synthesizing the story",
  "what_changed": "string, short bullet-style lines. If prior_summary in context is non-empty, briefly state what changed vs that prior text. If prior_summary is empty, use exactly: New story.",
  "facts": null OR an object (only when sport is exactly \\"soccer\\"): {{
    "competition": "string or empty",
    "score": "string or empty",
    "venue": "string or empty",
    "kickoff_time": "string or empty",
    "injuries": [],
    "suspensions": [],
    "manager_quotes": [{{"speaker": "", "quote": ""}}]
  }},
  "entities": {{
    "teams": [],
    "players": [],
    "managers": [],
    "league": ""
  }}
}}

Rules:
- If sport is not soccer, set "facts" to null.
- Cap each array in entities at 10 items; keep strings concise.
- Extract only what is supported by the titles/URLs; do not invent scores or quotes."""


def build_merge_judge_prompt(
    *,
    new_title: str,
    new_url: str,
    candidate_title: str,
    candidate_url: str,
    similarity: float,
) -> str:
    return f"""You decide if two news items describe the same underlying story for clustering.

Item A (new):
title: {new_title}
url: {new_url}

Item B (candidate):
title: {candidate_title}
url: {candidate_url}

Embedding cosine similarity (approx): {similarity:.4f}

Reply with ONLY valid JSON: {{"same_story": true or false, "reason": "short string"}}"""


def llm_merge_judge_verdict(
    item: FeedItem,
    candidate_title: str,
    candidate_url: str,
    similarity: float,
    *,
    api_key: str,
    model: str,
    max_tokens: int,
    timeout: float,
) -> tuple[bool, str]:
    prompt = build_merge_judge_prompt(
        new_title=item.title,
        new_url=item.url,
        candidate_title=candidate_title,
        candidate_url=candidate_url,
        similarity=similarity,
    )
    content = openrouter_chat_completion(
        prompt,
        api_key=api_key,
        model=model,
        max_tokens=min(max_tokens, 200),
        timeout=timeout,
    )
    obj = parse_llm_json_object(content)
    same = obj.get("same_story")
    reason = str(obj.get("reason") or "")
    if not isinstance(same, bool):
        raise ValueError("same_story must be boolean")
    return same, reason


def fetch_cluster_enrichment_candidates(
    cur: psycopg.Cursor,
    *,
    limit: int,
) -> list[tuple[uuid.UUID, str | None, str | None, str | None, str | None, int]]:
    cur.execute(
        """
        SELECT
            c.id,
            c.headline,
            c.sport,
            c.topic,
            c.summary AS prior_summary,
            COUNT(a.id)::int AS source_count
        FROM clusters c
        JOIN articles a ON a.cluster_id = c.id
        GROUP BY c.id, c.headline, c.sport, c.topic, c.summary
        HAVING COUNT(a.id) >= 2
            OR BOOL_OR(COALESCE(a.sport, '') = 'soccer')
            OR BOOL_OR(COALESCE(c.sport, '') = 'soccer')
        ORDER BY COUNT(a.id) DESC, MAX(a.created_at) DESC
        LIMIT %s
        """,
        (limit,),
    )
    rows = cur.fetchall()
    out: list[tuple[uuid.UUID, str | None, str | None, str | None, str | None, int]] = []
    for row in rows:
        out.append(
            (
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
                int(row[5]),
            )
        )
    return out


def fetch_cluster_article_titles_urls(
    cur: psycopg.Cursor,
    cluster_id: uuid.UUID,
    *,
    limit: int = 5,
) -> list[tuple[str, str]]:
    cur.execute(
        """
        SELECT title, url FROM articles
        WHERE cluster_id = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (cluster_id, limit),
    )
    return [(r[0] or "", r[1] or "") for r in cur.fetchall()]


def run_llm_cluster_enrichment_pass(database_url: str) -> None:
    enabled, api_key, provider, model, max_tokens, timeout = llm_enrichment_config()
    if not enabled or not api_key:
        _log_llm_skip_once("disabled_or_missing_key")
        return
    llm_label = f"{provider}:{model}"
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            ensure_llm_cluster_columns_psycopg(cur)
            candidates = fetch_cluster_enrichment_candidates(
                cur, limit=LLM_ENRICH_MAX_CLUSTERS
            )
        conn.commit()
    sleep_between = llm_enrich_inter_request_sleep_secs()
    rate_429 = 0
    for idx, row in enumerate(candidates):
        cid, headline, sport, topic, prior_summary, source_count = row
        try:
            with psycopg.connect(database_url) as conn:
                with conn.cursor() as cur:
                    articles = fetch_cluster_article_titles_urls(cur, cid, limit=5)
                    ctx = build_cluster_context_payload(
                        cluster_id=cid,
                        headline=headline,
                        sport=sport,
                        topic=topic,
                        source_count=source_count,
                        prior_summary=prior_summary,
                        articles=articles,
                    )
                    prompt = build_cluster_enrichment_prompt(ctx)
                    raw = openrouter_chat_completion(
                        prompt,
                        api_key=api_key,
                        model=model,
                        max_tokens=max_tokens,
                        timeout=timeout,
                        response_format_json=llm_enrichment_should_use_response_format_json(
                            model
                        ),
                    )
                    obj = parse_llm_json_object(raw)
                    summary = str(obj.get("summary") or "").strip()
                    what_changed = str(obj.get("what_changed") or "").strip()
                    facts = obj.get("facts")
                    entities = obj.get("entities")
                    if not summary:
                        raise ValueError("missing summary")
                    if not what_changed:
                        what_changed = "New story." if not (prior_summary or "").strip() else what_changed
                    if not isinstance(entities, dict):
                        entities = {}
                    for key in ("teams", "players", "managers"):
                        v = entities.get(key)
                        if isinstance(v, list):
                            entities[key] = v[:10]
                        else:
                            entities[key] = []
                    if "league" not in entities:
                        entities["league"] = str(entities.get("league") or "")
                    if (sport or "").lower() != "soccer":
                        facts = None
                    elif facts is not None and not isinstance(facts, dict):
                        facts = None
                    headline_out = headline
                    raw_h = (headline or "").strip()
                    ph = "[placeholder]"
                    if raw_h.startswith(ph):
                        cleaned = raw_h[len(ph) :].strip()
                        if cleaned:
                            headline_out = cleaned
                    cur.execute(
                        """
                        UPDATE clusters SET
                            headline = %s,
                            summary = %s,
                            what_changed = %s,
                            facts_json = %s,
                            entities_json = %s,
                            llm_model_name = %s,
                            llm_updated_at = NOW()
                        WHERE id = %s
                        """,
                        (
                            headline_out,
                            summary,
                            what_changed,
                            Json(facts) if facts is not None else None,
                            Json(entities),
                            llm_label,
                            cid,
                        ),
                    )
                conn.commit()
            print(
                "llm_enrich_saved: "
                f"cluster_id={cid} sport={sport or ''} topic={topic or ''} "
                f"sources={source_count} model={llm_label}"
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "HTTP 429" in msg or "429" in msg:
                rate_429 += 1
                if rate_429 <= 2:
                    print(f"llm_enrich_failed: cluster_id={cid} error={msg[:220]}")
            else:
                print(f"llm_enrich_failed: cluster_id={cid} error={msg[:200]}")
        if sleep_between > 0 and idx + 1 < len(candidates):
            time.sleep(sleep_between)
    if rate_429 > 2:
        print(
            f"llm_enrich_rate_limited: openrouter_429_total={rate_429} "
            "(extra per-cluster lines omitted; add credits, wait for reset, or set LLM_ENRICH_SLEEP_SECS)"
        )


def _log_embedding_skip_once(reason: str) -> None:
    global _EMBEDDING_SKIP_LOGGED
    if _EMBEDDING_SKIP_LOGGED:
        return
    print(f"embedding_merge_skipped: reason={reason}")
    _EMBEDDING_SKIP_LOGGED = True


def _get_local_embedder(model_name: str):
    global _LOCAL_EMBEDDER, _EMBEDDING_LOCAL_LOAD_ERROR_LOGGED
    if _LOCAL_EMBEDDER is not None:
        return _LOCAL_EMBEDDER
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:  # noqa: BLE001
        if not _EMBEDDING_LOCAL_LOAD_ERROR_LOGGED:
            print(f"embedding_local_unavailable: reason=import_failed detail={exc}")
            _EMBEDDING_LOCAL_LOAD_ERROR_LOGGED = True
        return None
    try:
        _LOCAL_EMBEDDER = SentenceTransformer(model_name)
    except Exception as exc:  # noqa: BLE001
        if not _EMBEDDING_LOCAL_LOAD_ERROR_LOGGED:
            print(f"embedding_local_unavailable: reason=model_load_failed detail={exc}")
            _EMBEDDING_LOCAL_LOAD_ERROR_LOGGED = True
        return None
    return _LOCAL_EMBEDDER


def _embedding_to_pgvector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"


def embed_text(text: str) -> list[float] | None:
    provider = os.getenv("EMBEDDINGS_PROVIDER", EMBEDDINGS_PROVIDER_DEFAULT).strip().lower()
    model_name = os.getenv("EMBEDDINGS_MODEL", EMBEDDINGS_MODEL_DEFAULT).strip() or EMBEDDINGS_MODEL_DEFAULT
    _ = os.getenv("EMBEDDINGS_API_KEY")
    if provider == "stub":
        _log_embedding_skip_once("provider=stub")
        return None
    if provider in {"openai", "openrouter"}:
        _log_embedding_skip_once(f"provider={provider}_not_implemented")
        return None
    if provider != "local":
        _log_embedding_skip_once(f"provider={provider}_unsupported")
        return None
    embedder = _get_local_embedder(model_name)
    if embedder is None:
        _log_embedding_skip_once("local_model_unavailable")
        return None
    try:
        vector = embedder.encode(text, normalize_embeddings=True).tolist()
    except Exception as exc:  # noqa: BLE001
        _log_embedding_skip_once(f"local_encode_failed:{exc}")
        return None
    if not isinstance(vector, list) or len(vector) != EMBEDDING_DIM:
        print(
            "embedding_local_error: "
            f"expected_dim={EMBEDDING_DIM} got_dim={len(vector) if isinstance(vector, list) else 'non_list'}"
        )
        _log_embedding_skip_once("invalid_embedding_dimension")
        return None
    return [float(x) for x in vector]


def estimate_prompt_tokens(
    prompt_text: str,
    *,
    model_name: str = "unset",
) -> tuple[int, int, str]:
    """Rough token estimate for a would-be prompt (chars / 4, rounded up)."""
    prompt_chars = len(prompt_text)
    prompt_tokens_est = math.ceil(prompt_chars / 4) if prompt_chars else 0
    return prompt_chars, prompt_tokens_est, model_name


def build_would_be_cluster_prompt(
    headline: str | None,
    sport: str | None,
    topic: str | None,
    source_count: int,
    article_title_urls: list[tuple[str, str]],
) -> str:
    """Deterministic pseudo-prompt for future summarization (worker-only)."""
    lines = [
        f"Headline: {headline or ''}",
        f"Sport: {sport or 'unknown'}",
        f"Topic: {topic or 'unknown'}",
        f"Source count: {source_count}",
        "Articles:",
    ]
    for i, (atitle, aurl) in enumerate(article_title_urls, start=1):
        lines.append(f"  {i}. {atitle} — {aurl}")
    return "\n".join(lines)


def print_llm_prompt_token_sample(
    database_url: str,
    cluster_ids_this_run: set[uuid.UUID],
    *,
    limit: int = 5,
) -> None:
    """Debug: first N clusters by UUID order; no LLM calls."""
    if not cluster_ids_this_run:
        print("llm_prompt_token_sample: (no clusters touched this run)")
        return
    ordered = sorted(cluster_ids_this_run)
    sample = ordered[:limit]
    _, _, provider, model, _, _ = llm_enrichment_config()
    configured_model = f"{provider}:{model}"
    print(f"llm_prompt_token_sample (first {len(sample)} clusters):")
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            for cid in sample:
                cur.execute(
                    "SELECT headline, sport, topic FROM clusters WHERE id = %s",
                    (cid,),
                )
                crow = cur.fetchone()
                if not crow:
                    continue
                ch, cs, ct = crow[0], crow[1], crow[2]
                cur.execute(
                    "SELECT COUNT(*) FROM articles WHERE cluster_id = %s",
                    (cid,),
                )
                source_count = int(cur.fetchone()[0])
                cur.execute(
                    """
                    SELECT title, url FROM articles
                    WHERE cluster_id = %s
                    ORDER BY created_at ASC
                    LIMIT 3
                    """,
                    (cid,),
                )
                rows = [(r[0], r[1]) for r in cur.fetchall()]
                prompt = build_would_be_cluster_prompt(
                    ch, cs, ct, source_count, rows
                )
                pc, pt, mname = estimate_prompt_tokens(
                    prompt, model_name=configured_model
                )
                print(
                    f"  cluster_id={cid} -> prompt_chars={pc} -> "
                    f"prompt_tokens_est={pt} -> model_name={mname}"
                )

# Premier League clubs (20) — canonical slugs for cluster keys + phrase hints for title matching.
# Phrases are checked against normalized titles (lowercase, punctuation → spaces).
EPL_TEAM_PHRASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("arsenal", ("arsenal",)),
    ("aston_villa", ("aston villa",)),
    ("bournemouth", ("bournemouth",)),
    ("brentford", ("brentford",)),
    (
        "brighton_hove_albion",
        ("brighton hove albion", "brighton and hove", "brighton"),
    ),
    ("burnley", ("burnley",)),
    ("chelsea", ("chelsea",)),
    ("crystal_palace", ("crystal palace",)),
    ("everton", ("everton",)),
    ("fulham", ("fulham",)),
    ("leeds_united", ("leeds united", "leeds",)),
    ("liverpool", ("liverpool",)),
    ("manchester_city", ("manchester city", "man city",)),
    ("manchester_united", ("manchester united", "man united", "man utd",)),
    ("newcastle_united", ("newcastle united", "newcastle",)),
    ("nottingham_forest", ("nottingham forest", "nottingham",)),
    ("sunderland", ("sunderland",)),
    ("tottenham_hotspur", ("tottenham hotspur", "tottenham", "spurs",)),
    ("west_ham_united", ("west ham united", "west ham",)),
    (
        "wolverhampton_wanderers",
        ("wolverhampton wanderers", "wolverhampton", "wolves",),
    ),
)

STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "to",
        "of",
        "in",
        "on",
        "for",
        "with",
        "after",
        "as",
        "at",
        "vs",
        "and",
        "or",
        "report",
        "highlights",
        "reaction",
        "analysis",
        "preview",
        "watch",
        "liveblog",
    }
)

_BOILERPLATE_TRAILING = (
    "as it happened",
    "live",
    "match report",
    "video",
    "football weekly",
    "report",
    "highlights",
    "reaction",
    "analysis",
    "preview",
    "watch",
    "liveblog",
)


@dataclass(slots=True)
class FeedItem:
    title: str
    url: str
    published_at: datetime | None
    source: str
    summary: str | None


@dataclass(slots=True)
class MergeMeta:
    sport: str | None
    effective_topic: str
    noise_lane: str | None
    title: str
    url: str


def read_feed_urls() -> tuple[list[str], int]:
    """Parse docs/rss_sources.md: URLs only inside the ## (all URLs) fenced code block.

    Returns (unique feed URLs in document order, raw URL line count before deduplication).
    """
    docs_file = Path(__file__).resolve().parents[1] / "docs" / "rss_sources.md"
    lines = docs_file.read_text(encoding="utf-8").splitlines()
    in_section = False
    in_fence = False
    raw: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not in_section:
            if stripped == "## (all URLs)":
                in_section = True
            continue
        if not in_fence:
            if stripped.startswith("```"):
                in_fence = True
            continue
        if stripped.startswith("```"):
            break
        if stripped.startswith("http://") or stripped.startswith("https://"):
            raw.append(stripped)
    unique = list(dict.fromkeys(raw))
    return unique, len(raw)


def fetch_rss(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "sports-news-noise-filter/0.1"})
    with urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:  # noqa: S310
        return resp.read()


def classify_fetch_failure(exc: BaseException) -> tuple[str, str]:
    """Classify transport/HTTP errors when fetching a feed (not parse)."""
    if isinstance(exc, HTTPError):
        code = exc.code
        if code == 403:
            return "403", f"HTTP {code}"
        if code == 404:
            return "404", f"HTTP {code}"
        return "other", f"HTTP {code}"
    if isinstance(exc, TimeoutError):
        return "timeout", "timeout"
    if isinstance(exc, socket.timeout):
        return "timeout", "socket timeout"
    if isinstance(exc, URLError):
        r = exc.reason
        if isinstance(r, (TimeoutError, socket.timeout)):
            return "timeout", str(exc)[:160]
        low = str(exc).lower()
        if "timed out" in low or "timeout" in low:
            return "timeout", str(exc)[:160]
        return "other", str(exc)[:160]
    return "other", str(exc)[:160]


def should_skip_audio_item(title: str, url: str) -> tuple[bool, bool]:
    """Return (skip_item, url_based_skip) for podcast/audio filtering."""
    url_lc = url.lower()
    title_lc = title.lower()
    url_hit = "bbc.co.uk/sounds" in url_lc or "bbc.co.uk/iplayer" in url_lc
    title_hit = any(m in title_lc for m in AUDIO_TITLE_MARKERS)
    if url_hit or title_hit:
        return True, url_hit
    return False, False


def should_skip_feature_item(title: str, url: str) -> tuple[bool, bool]:
    """Non-news feature / promo / video-style items. Returns (skip, url_looks_video_host)."""
    url_lc = url.lower()
    stripped = title.strip()
    tl = title.lower()
    title_skip = (
        stripped.upper().startswith("WATCH:")
        or "generation game" in tl
        or "have tried other races" in tl
        or "drivers play" in tl
    )
    url_video = (
        "/video" in url_lc
        or "/watch" in url_lc
        or "youtube.com" in url_lc
        or "/sport/av" in url_lc
    )
    if not title_skip:
        return False, False
    return True, url_video


def classify_noise_lane(title: str, url: str) -> Optional[str]:
    """Classify noise-prone content lanes that should not contaminate core clusters."""
    t = _normalize_title_text(title)
    padded = f" {t} "
    u = url.lower()

    def has_phrase(phrase: str) -> bool:
        return f" {phrase} " in padded

    betting_phrases = (
        "odds",
        "prediction",
        "predictions",
        "best bets",
        "betting",
        "bookmakers",
        "spread",
    )
    watch_phrases = (
        "how to watch",
        "what tv channel",
        "tv channel",
        "live stream",
        "streaming info",
        "where to watch",
        "kick off time",
        "kickoff time",
    )
    gossip_phrases = (
        "girlfriend",
        "boyfriend",
        "wife",
        "husband",
        "dating",
        "romance",
        "relationship",
        "instagram",
        "wags",
        "gorgeous",
        "stuns",
        "private life",
        "in tears",
        "gossip",
        "breaks silence",
    )
    forced_updates_phrases = (
        "team news",
        "live",
        "live!",
        "minute-by-minute",
        "as it happened",
        "live stream",
        "how to watch",
        "tv channel",
        "kick off time",
        "kick-off time",
        "kickoff",
    )
    updates_phrases = (
        "lineup",
        "injury",
        "injuries",
        "doubt",
        "set to miss",
        "returns",
        "preview",
    )
    tabloid_domain_hints = (
        "mirror.co.uk",
        "thesun.co.uk",
        "dailymail.co.uk",
    )

    if any(has_phrase(p) for p in betting_phrases) or any(
        s in u for s in ("/betting/",)
    ):
        return "betting"
    if any(has_phrase(p) for p in forced_updates_phrases):
        return "updates"
    if any(has_phrase(p) for p in watch_phrases) or any(
        s in u for s in ("/watch/", "/live-stream")
    ):
        return "watch"
    tabloid_bias = any(dom in u for dom in tabloid_domain_hints)
    if any(has_phrase(p) for p in gossip_phrases):
        return "gossip"
    if tabloid_bias:
        return "gossip"
    if any(has_phrase(p) for p in updates_phrases):
        return "updates"
    return None


def is_gossip(title: str, url: str) -> tuple[bool, str]:
    """Deterministic gossip detector with keyword + tabloid-domain hints."""
    t = _normalize_title_text(title)
    padded = f" {t} "
    u = url.lower()

    gossip_keywords = (
        "girlfriend",
        "dating",
        "wife",
        "wag",
        "instagram",
        "baby",
        "pregnant",
        "gorgeous",
        "stunning",
    )
    domain_hints = ("mirror.co.uk", "dailymail.co.uk")

    for dom in domain_hints:
        if dom in u:
            return True, dom
    for kw in gossip_keywords:
        if f" {kw} " in padded:
            return True, "keyword"
    return False, ""


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        return dt.astimezone(UTC) if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        pass
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(UTC) if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


def parse_rss_items(xml_bytes: bytes, source_url: str) -> list[FeedItem]:
    root = ET.fromstring(xml_bytes)
    items: list[FeedItem] = []
    for node in root.findall(".//item"):
        title = clean_text(node.findtext("title")) or "Untitled"
        url = clean_text(node.findtext("link"))
        if not url:
            continue
        published_at = parse_datetime(node.findtext("pubDate"))
        summary = clean_text(node.findtext("description"))
        items.append(
            FeedItem(
                title=title,
                url=url,
                published_at=published_at,
                source=source_url,
                summary=summary,
            )
        )
    return items


def _normalize_title_text(title: str) -> str:
    """Lowercase, drop punctuation, collapse spaces, trim."""
    s = title.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _strip_trailing_boilerplate(normalized: str) -> str:
    """Remove listed trailing phrases if present (end of string, word boundary)."""
    s = normalized
    for phrase in _BOILERPLATE_TRAILING:
        while True:
            if s == phrase:
                return ""
            boundary = f" {phrase}"
            if s.endswith(boundary):
                s = s[: -len(boundary)].rstrip()
                continue
            break
    return s


def title_signature_n(title: str, n: int) -> str:
    """First n content tokens after normalize + boilerplate strip + stopword removal."""
    normalized = _normalize_title_text(title)
    normalized = _strip_trailing_boilerplate(normalized)
    tokens = [t for t in normalized.split() if t and t not in STOPWORDS]
    signature = " ".join(tokens[:n]).strip()
    return signature if signature else "untitled"


def title_signature_n_slug(title: str, n: int) -> str:
    """Underscore-joined first n tokens (for embedding in colon-separated cluster keys)."""
    sig = title_signature_n(title, n)
    return "_".join(sig.split()) if sig else "untitled"


def title_core_signature(title: str) -> str:
    """Normalized title signature: boilerplate stripped, stopwords removed, first 12 tokens."""
    return title_signature_n(title, 12)


def detect_competition(feed_url: str, item_url: str) -> str:
    """Assign EPL, UCL, F1, NBA, or OTHER from feed and item URL host/path."""
    parts = [feed_url.lower(), item_url.lower()]
    joined = " ".join(parts)
    if "formula1.com" in joined or "/sport/formula1" in joined or "/formula1/" in joined:
        return "F1"
    if "espn.com" in joined and "nba" in joined:
        return "NBA"
    if "premierleague" in joined or "/football/premier-league" in joined:
        return "EPL"
    if "championsleague" in joined or "/football/champions-league" in joined:
        return "UCL"
    return "OTHER"


def epl_team_pair_from_title(title: str) -> tuple[str, str]:
    """Soccer: match PL team names in title; return two slugs (alphabetical) or unknown."""
    norm = _normalize_title_text(title)
    padded = f" {norm} "
    # Prefer longer phrases first to reduce ambiguous substrings.
    teams_sorted = sorted(
        EPL_TEAM_PHRASES,
        key=lambda row: -max(len(p) for p in row[1]),
    )
    found: set[str] = set()
    for slug, phrases in teams_sorted:
        for phrase in sorted(phrases, key=len, reverse=True):
            if f" {phrase} " in padded:
                found.add(slug)
                break
    ordered = sorted(found)
    if not ordered:
        return "unknown", "unknown"
    if len(ordered) == 1:
        return ordered[0], "unknown"
    return ordered[0], ordered[1]


def date_bucket(published_at: datetime | None) -> str:
    if published_at is None:
        dt = datetime.now(UTC)
    else:
        dt = (
            published_at.astimezone(UTC)
            if published_at.tzinfo
            else published_at.replace(tzinfo=UTC)
        )
    return dt.strftime("%Y-%m-%d")


def cluster_key_string(
    competition: str,
    date_b: str,
    team1: str,
    team2: str,
) -> str:
    return f"{competition}:{date_b}:{team1}:{team2}"


def hash_cluster_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def cluster_id_from_hash(key_hash: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"cluster:{key_hash}")


def _embedding_input_text(item: FeedItem) -> str:
    snippet = (item.summary or "").strip()
    if snippet:
        return f"{item.title}\n\n{snippet}"
    return item.title


def is_highlights_like(title: str, url: str) -> bool:
    t = title.lower()
    u = url.lower()
    needles = (
        "highlights",
        "watch",
        "video",
        "/highlights",
        "/video",
        "match highlights",
        "extended highlights",
    )
    return any(n in t or n in u for n in needles)


def is_report_like(title: str, url: str) -> bool:
    t = title.lower()
    u = url.lower()
    needles = ("match report", "report", "as it happened", "live", "/live/")
    return any(n in t or n in u for n in needles)


def allow_high_sim_soccer_override(
    new_meta: MergeMeta,
    cand_meta: MergeMeta,
    sim: float,
    high_sim_override: float,
) -> bool:
    if sim < high_sim_override:
        return False
    if new_meta.sport != "soccer" or cand_meta.sport != "soccer":
        return False
    hard_noise_lanes = {"betting", "gossip", "watch"}
    if (
        new_meta.effective_topic in hard_noise_lanes
        or cand_meta.effective_topic in hard_noise_lanes
        or new_meta.noise_lane in hard_noise_lanes
        or cand_meta.noise_lane in hard_noise_lanes
    ):
        return False
    allowed_topics = {"match", "updates", "other"}
    if (
        new_meta.effective_topic not in allowed_topics
        or cand_meta.effective_topic not in allowed_topics
    ):
        return False
    new_highlights_like = is_highlights_like(new_meta.title, new_meta.url)
    cand_highlights_like = is_highlights_like(cand_meta.title, cand_meta.url)
    new_report_like = is_report_like(new_meta.title, new_meta.url)
    cand_report_like = is_report_like(cand_meta.title, cand_meta.url)
    return (new_highlights_like and cand_report_like) or (
        new_report_like and cand_highlights_like
    )


def has_article_embedding(cur: psycopg.Cursor, article_id: uuid.UUID) -> bool:
    try:
        cur.execute(
            "SELECT 1 FROM article_embeddings WHERE article_id = %s LIMIT 1",
            (article_id,),
        )
    except Exception as exc:  # noqa: BLE001
        _log_embedding_skip_once(f"embedding_table_unavailable:{exc}")
        return True
    return cur.fetchone() is not None


def upsert_article_embedding(
    cur: psycopg.Cursor,
    article_id: uuid.UUID,
    model_name: str,
    embedding: list[float],
) -> None:
    try:
        cur.execute(
            """
            INSERT INTO article_embeddings (article_id, model_name, embedding)
            VALUES (%s, %s, %s::vector)
            ON CONFLICT (article_id)
            DO UPDATE SET
                model_name = EXCLUDED.model_name,
                embedding = EXCLUDED.embedding,
                created_at = NOW()
            """,
            (article_id, model_name, _embedding_to_pgvector_literal(embedding)),
        )
    except Exception as exc:  # noqa: BLE001
        _log_embedding_skip_once(f"embedding_upsert_failed:{exc}")


def try_embedding_merge(
    cur: psycopg.Cursor,
    *,
    item: FeedItem,
    article_id: uuid.UUID,
    sport_tag: str | None,
    embedding: list[float] | None,
    effective_topic: str,
    threshold: float,
    high_sim_override: float,
) -> tuple[uuid.UUID | None, float, str | None, str, list[tuple[float, str, str, uuid.UUID]]]:
    """Embedding-first merge using pgvector nearest-neighbor search."""
    if embedding is None:
        return None, 0.0, None, "no_candidates", []
    if sport_tag is None:
        return None, 0.0, None, "missing_sport", []
    vector_literal = _embedding_to_pgvector_literal(embedding)
    try:
        cur.execute(
            """
            SELECT
                a.id,
                a.cluster_id,
                a.title,
                a.url,
                a.sport,
                1 - (ae.embedding <=> %s::vector) AS similarity
            FROM article_embeddings ae
            JOIN articles a ON a.id = ae.article_id
            WHERE a.cluster_id IS NOT NULL
              AND a.id <> %s::uuid
              AND a.url <> %s
              AND COALESCE(a.published_at, a.created_at) >= NOW() - INTERVAL '7 days'
              AND a.sport = %s::text
            ORDER BY ae.embedding <=> %s::vector ASC
            LIMIT 5
            """,
            (vector_literal, article_id, item.url, sport_tag, vector_literal),
        )
    except Exception as exc:  # noqa: BLE001
        _log_embedding_skip_once(f"similarity_query_failed:{exc}")
        return None, 0.0, None, "no_candidates", []
    rows = cur.fetchall()
    if not rows:
        return None, 0.0, None, "no_candidates", []
    top5: list[tuple[float, str, str, uuid.UUID]] = []
    for row in rows:
        top5.append((float(row[5] or 0.0), row[2] or "", row[3] or "", row[1]))
    row = rows[0]
    candidate_cluster = row[1]
    candidate_title = row[2] or ""
    candidate_url = row[3] or ""
    candidate_sport = row[4]
    score = float(row[5] or 0.0)
    if not candidate_cluster or not candidate_title:
        return None, score, candidate_title, "no_candidates", top5

    cand_lane = classify_noise_lane(candidate_title, candidate_url)
    cand_gossip, _ = is_gossip(candidate_title, candidate_url)
    if cand_gossip:
        cand_lane = "gossip"
    cand_topic = topic_from_title_and_url(candidate_title, candidate_url)
    if cand_lane == "gossip":
        cand_topic = "gossip"
    cand_effective_topic = cand_lane if cand_lane is not None else cand_topic

    new_meta = MergeMeta(
        sport=sport_tag,
        effective_topic=effective_topic,
        noise_lane=effective_topic if effective_topic in {"betting", "gossip", "watch"} else None,
        title=item.title,
        url=item.url,
    )
    cand_meta = MergeMeta(
        sport=candidate_sport,
        effective_topic=cand_effective_topic,
        noise_lane=cand_lane,
        title=candidate_title,
        url=candidate_url,
    )
    hard_noise_lanes = {"gossip", "betting", "watch"}
    if (
        effective_topic in hard_noise_lanes
        or cand_effective_topic in hard_noise_lanes
    ):
        return None, score, candidate_title, "noise_lane", top5
    if not topics_compatible(effective_topic, cand_effective_topic):
        if allow_high_sim_soccer_override(
            new_meta=new_meta,
            cand_meta=cand_meta,
            sim=score,
            high_sim_override=high_sim_override,
        ):
            return candidate_cluster, score, candidate_title, "override", top5
        return None, score, candidate_title, "topic_gate", top5
    if score >= threshold:
        return candidate_cluster, score, candidate_title, "merged", top5
    return None, score, candidate_title, "below_threshold", top5


def sport_from_feed_url(feed_url: str) -> str:
    """Map the RSS feed URL to a sport tag (feed is source of truth)."""
    f = feed_url.lower()

    if "espn.com" in f and "/nba/" in f:
        return "nba"

    if "formula1.com" in f:
        return "f1"
    if "/formula1/" in f or "sport/formula1" in f:
        return "f1"
    if "espn.com" in f and "/f1/" in f:
        return "f1"
    if "autosport.com" in f and "/f1/" in f:
        return "f1"
    if "feeds.as.com" in f and "/motor/" in f and "formula" in f:
        return "f1"

    if "yahoo.com" in f and "/wnba/" in f:
        return "wnba"
    if "yahoo.com" in f and "/nba/" in f:
        return "nba"
    if "feeds.as.com" in f and "/baloncesto/" in f and "nba" in f:
        return "nba"

    if "espn.com" in f and "/soccer/" in f:
        return "soccer"
    if "espn.com" in f and "/football/soccer/" in f:
        return "soccer"
    if "espn.co.uk" in f and "football" in f:
        return "soccer"
    if "theguardian.com/football" in f:
        return "soccer"
    if (
        "premierleague" in f
        or "championsleague" in f
        or "womens-super-league" in f
    ):
        return "soccer"
    if "newsrss.bbc.co.uk" in f and "/football/" in f:
        return "soccer"
    if "feeds.bbci.co.uk/sport/football" in f:
        return "soccer"
    if "feeds.bbci.co.uk/sport/scotland" in f:
        return "soccer"
    if "feeds.as.com" in f and "/futbol/" in f:
        return "soccer"
    if "kicker.de" in f:
        return "soccer"
    if "bundesliga.com" in f:
        return "soccer"
    if "uefa.com" in f:
        return "soccer"
    if "cbssports.com" in f and "soccer" in f:
        return "soccer"
    if "foxsports.com" in f and "soccer" in f:
        return "soccer"
    if "standard.co.uk" in f and "football" in f:
        return "soccer"
    if "dailymail.co.uk" in f and "football" in f:
        return "soccer"
    if "fifa.com" in f:
        return "soccer"
    if "telegraph.co.uk" in f and "football" in f:
        return "soccer"
    if "irishtimes.com" in f and "soccer" in f:
        return "soccer"
    if "independent.co.uk" in f and "football" in f:
        return "soccer"
    if "bbc.co.uk/sport/football" in f:
        return "soccer"
    if "planetfootball.com" in f:
        return "soccer"
    if any(
        x in f
        for x in (
            "birminghammail.co.uk",
            "leicestermercury.co.uk",
            "chroniclelive.co.uk",
            "heraldscotland.com",
            "scotsman.com",
        )
    ):
        return "soccer"
    if "liverpoolfc.com" in f:
        return "soccer"
    if "arsenal.com" in f:
        return "soccer"
    if "marca.com" in f:
        return "soccer"

    return "other"


# Title overrides (after feed + URL): longest phrases first within each list; word boundaries via padded norm.
_TITLE_SOCCER: tuple[str, ...] = (
    "premier league",
    "champions league",
    "europa league",
    "man united",
    "man city",
    "fa cup",
    "tottenham",
    "liverpool",
    "chelsea",
    "arsenal",
    "carabao",
    "wsl",
    "uefa",
    "fifa",
    "spurs",
)
_TITLE_F1: tuple[str, ...] = (
    "formula 1",
    "grand prix",
    "qualifying",
    "paddock",
    "verstappen",
    "hamilton",
    "leclerc",
    "norris",
    "f1",
)
_TITLE_NBA: tuple[str, ...] = (
    "warriors",
    "celtics",
    "lakers",
    "knicks",
    "bucks",
    "play offs",
    "playoffs",
    "nba",
)
_TITLE_WNBA: tuple[str, ...] = (
    "wnba",
    "liberty",
    "aces",
    "fever",
    "storm",
    "lynx",
)


def _padded_normalized_title(title: str) -> str:
    return f" {_normalize_title_text(title)} "


def _title_matches_any_keyword(title: str, keywords: tuple[str, ...]) -> bool:
    padded = _padded_normalized_title(title)
    for kw in sorted(keywords, key=len, reverse=True):
        if f" {kw} " in padded:
            return True
    return False


def _sport_from_url_path_when_other(url: str) -> str | None:
    """High-confidence path/domain hints when feed alone said other."""
    u = url.lower()
    if "/football/" in u:
        return "soccer"
    if "/formula1/" in u or "formula1.com" in u:
        return "f1"
    if "/nba/" in u:
        return "nba"
    if "/wnba/" in u:
        return "wnba"
    return None


def _epl_club_phrase_in_title(title: str) -> bool:
    """Any known EPL club phrase in title (same boundaries as clustering)."""
    norm = _normalize_title_text(title)
    padded = f" {norm} "
    teams_sorted = sorted(
        EPL_TEAM_PHRASES,
        key=lambda row: -max(len(p) for p in row[1]),
    )
    for _slug, phrases in teams_sorted:
        for phrase in sorted(phrases, key=len, reverse=True):
            if f" {phrase} " in padded:
                return True
    return False


def _sport_from_title_when_other(title: str) -> str | None:
    """Title keywords; order WNBA → NBA → F1 → soccer to reduce cross-league bleed."""
    if _title_matches_any_keyword(title, _TITLE_WNBA):
        return "wnba"
    if _title_matches_any_keyword(title, _TITLE_NBA):
        return "nba"
    if _title_matches_any_keyword(title, _TITLE_F1):
        return "f1"
    if _title_matches_any_keyword(title, _TITLE_SOCCER) or _epl_club_phrase_in_title(
        title
    ):
        return "soccer"
    return None


def sport_for_article(item: FeedItem) -> str:
    """Feed URL first; if other (or empty), apply URL-path then title keyword overrides."""
    base = sport_from_feed_url(item.source)
    if base not in ("other", None, ""):
        return base
    from_url = _sport_from_url_path_when_other(item.url)
    if from_url is not None:
        return from_url
    from_title = _sport_from_title_when_other(item.title)
    if from_title is not None:
        return from_title
    return "other"


def _padded_title(title: str) -> str:
    norm = _normalize_title_text(title)
    return f" {norm} "


def _title_has_scoreline(title: str) -> bool:
    """Score-like patterns: x-y, x–y, or x:y (e.g. 2-1, 2–1, 2:1)."""
    t = title.lower()
    if re.search(r"\b\d{1,2}\s*[-–]\s*\d{1,2}\b", t):
        return True
    return bool(re.search(r"\b\d{1,2}\s*:\s*\d{1,2}\b", t))


def _topic_is_match_signals(
    title: str,
    url: str,
    padded: str,
    recap_keywords: tuple[str, ...],
) -> bool:
    """Headlines that must stay match (also used so preview does not override them)."""
    u = url.lower()

    def has_phrase(p: str) -> bool:
        return f" {p} " in padded

    if _title_has_scoreline(title):
        return True
    if any(has_phrase(p) for p in sorted(recap_keywords, key=len, reverse=True)):
        return True
    if any(
        has_phrase(p)
        for p in (
            "as it happened",
            "full time",
            "fulltime",
            "match report",
            "highlights",
            "live blog",
            "penalty shootout",
            "extra time",
        )
    ):
        return True
    if any(s in u for s in ("/live/", "minute-by-minute", "live-commentary")):
        return True
    if has_phrase("live") or padded.rstrip().endswith(" live"):
        return True
    return False


def topic_from_title_url(title: str, url: str) -> str:
    """Return one of: match, preview, lineup, transfer, injury, discipline, manager, finance, standings, tactics, opinion, other.

    Priority: match → preview → lineup → transfer → injury → discipline → manager → finance
    → standings → tactics → opinion → other. Match beats preview/recap overlap; tactics before opinion.
    """
    # --- Keyword lists (match + tactics; normalized titles use space boundaries via has_phrase) ---
    _match_recap_kw: tuple[str, ...] = (
        "squeeze past",
        "late point",
        "matchwinner",
        "on target",
        "hold off",
        "comeback",
        "knockout",
        "hat trick",
        "thriller",
        "dramatic",
        "victory",
        "defeat",
        "rescues",
        "stuns",
        "thrash",
        "winner",
        "brace",
        "rout",
        "loss",
        "draw",
        "beat",
        "edges",
        "sinks",
        "grabs",
        "earns",
        "rally",
        "late",
        "double",
        "win",
    )
    _tac_kw: tuple[str, ...] = (
        "qualifying pace",
        "improved pace",
        "state of play",
        "title odds",
        "race pace",
        "formation",
        "tactics",
        "tactical",
        "midfield",
        "approach",
        "pressing",
        "shortens",
        "shape",
        "press",
        "pace",
        "system",
        "odds",
    )
    _tac_how_why_kw: tuple[str, ...] = (
        "how they",
        "how the",
        "how it",
        "why they",
        "why the",
        "why it",
    )

    padded = _padded_title(title)
    u = url.lower()

    def has_phrase(p: str) -> bool:
        return f" {p} " in padded

    is_match_topic = _topic_is_match_signals(title, url, padded, _match_recap_kw)

    # 1) match — scorelines, live, result / recap (beats preview & opinion)
    if is_match_topic:
        return "match"

    n = _normalize_title_text(title)

    # 2) preview — not when headline is already a live blog / recap (match signals)
    if not is_match_topic:
        if n.startswith("preview") or has_phrase("preview") or "/preview/" in u:
            return "preview"
        if any(
            has_phrase(p)
            for p in sorted(
                (
                    "quarter-final",
                    "quarterfinal",
                    "semi-final",
                    "semifinal",
                    "ahead of",
                    "match preview",
                    "build up",
                    "build-up",
                    "what time",
                    "where to watch",
                    "set up",
                    "sets up",
                    "before",
                    "clash",
                    "faces",
                    "face",
                    "test",
                    "tie",
                ),
                key=len,
                reverse=True,
            )
        ):
            return "preview"

    # 3) lineup
    if any(
        has_phrase(p)
        for p in (
            "lineup",
            "line up",
            "line-up",
            "starting xi",
            "predicted xi",
            "team news",
        )
    ):
        return "lineup"

    # 4) transfer
    if any(
        has_phrase(p)
        for p in (
            "transfer",
            "signing",
            "signs for",
            "signs new",
            "joins",
            "loan deal",
            "record bid",
            "contract extension",
        )
    ) or "/transfers/" in u or "/transfer-" in u:
        return "transfer"

    # 5) injury
    if any(
        has_phrase(p)
        for p in (
            "injury",
            "injured",
            "hamstring",
            "ruled out",
            "sidelined",
            "fitness doubt",
            "setback",
            "knock",
        )
    ):
        return "injury"

    # 6) discipline
    if any(
        has_phrase(p)
        for p in (
            "suspended",
            "suspension",
            "ban",
            "banned",
            "red card",
            "sent off",
            "disciplinary",
        )
    ):
        return "discipline"

    # 7) manager
    if any(
        has_phrase(p)
        for p in ("manager", "head coach", "sacked", "appointed", "dismissed", "departs")
    ):
        return "manager"

    # 8) finance
    if any(
        has_phrase(p)
        for p in ("takeover", "financial fair play", "revenue", "profit", "debt", "ffp", "wage bill")
    ):
        return "finance"

    # 9) standings
    if any(
        has_phrase(p)
        for p in ("standings", "league table", "relegation zone", "title race", "top scorer", "golden boot")
    ):
        return "standings"

    # 10) tactics — shape/press/system, F1 cues, + common how/why tactical framings
    if any(has_phrase(p) for p in sorted(_tac_kw, key=len, reverse=True)):
        return "tactics"
    if any(has_phrase(p) for p in sorted(_tac_how_why_kw, key=len, reverse=True)):
        return "tactics"

    # 11) opinion / analysis (after tactics; Guardian pipe skips audio/podcast)
    _opinion_phrases = (
        "player ratings",
        "talking points",
        "what we learned",
        "report card",
        "takeaways",
        "op-ed",
        "analysis",
        "editorial",
        "opinion",
        "verdict",
        "column",
        "review",
        "ratings",
    )
    if any(has_phrase(p) for p in sorted(_opinion_phrases, key=len, reverse=True)):
        return "opinion"
    if n.startswith("why "):
        return "opinion"
    if " | " in title and not should_skip_audio_item(title, url)[0]:
        return "opinion"

    return "other"


def topic_from_title_and_url(title: str, url: str) -> str:
    """Deterministic keyword topic classifier used for topic-gated clustering."""
    return topic_from_title_url(title, url)


def topics_compatible(topic_a: str, topic_b: str) -> bool:
    """Symmetric compatibility check for topic-gated merges."""
    comp_a = TOPIC_COMPATIBILITY.get(topic_a, {topic_a})
    comp_b = TOPIC_COMPATIBILITY.get(topic_b, {topic_b})
    return topic_b in comp_a or topic_a in comp_b


def topic_merge_group(topic: str) -> str:
    """Normalize compatible topics into deterministic merge bundles."""
    if topic in ("match", "preview", "lineup", "updates"):
        return "match_bundle"
    if topic in ("opinion", "tactics", "standings"):
        return "analysis_bundle"
    return topic


def ensure_sport_columns_psycopg(cur: psycopg.Cursor) -> None:
    cur.execute(
        "ALTER TABLE articles ADD COLUMN IF NOT EXISTS sport VARCHAR(32)"
    )
    cur.execute(
        "ALTER TABLE clusters ADD COLUMN IF NOT EXISTS sport VARCHAR(32)"
    )


def ensure_topic_columns_psycopg(cur: psycopg.Cursor) -> None:
    cur.execute(
        "ALTER TABLE articles ADD COLUMN IF NOT EXISTS topic VARCHAR(32)"
    )
    cur.execute(
        "ALTER TABLE clusters ADD COLUMN IF NOT EXISTS topic VARCHAR(32)"
    )


def ensure_llm_cluster_columns_psycopg(cur: psycopg.Cursor) -> None:
    """LLM output columns on clusters (idempotent; mirrors backend migration)."""
    for stmt in (
        "ALTER TABLE clusters ADD COLUMN IF NOT EXISTS summary TEXT",
        "ALTER TABLE clusters ADD COLUMN IF NOT EXISTS what_changed TEXT",
        "ALTER TABLE clusters ADD COLUMN IF NOT EXISTS facts_json JSONB",
        "ALTER TABLE clusters ADD COLUMN IF NOT EXISTS entities_json JSONB",
        "ALTER TABLE clusters ADD COLUMN IF NOT EXISTS llm_model_name TEXT",
        "ALTER TABLE clusters ADD COLUMN IF NOT EXISTS llm_updated_at TIMESTAMPTZ",
    ):
        cur.execute(stmt)


def upsert_cluster(cur: psycopg.Cursor, cluster_id: uuid.UUID, title: str) -> None:
    summary = f"[placeholder] {title[:460]}"
    cur.execute(
        """
        INSERT INTO clusters (id, headline, sport, topic, created_at)
        VALUES (%s, %s, NULL, NULL, NOW())
        ON CONFLICT (id)
        DO UPDATE SET headline = EXCLUDED.headline
        """,
        (cluster_id, summary),
    )


def recompute_cluster_sport(cur: psycopg.Cursor, cluster_id: uuid.UUID) -> None:
    """Set cluster.sport to the mode of non-null article sports (tie-break: lexicographic)."""
    cur.execute(
        """
        SELECT sport FROM articles
        WHERE cluster_id = %s AND sport IS NOT NULL
        GROUP BY sport
        ORDER BY COUNT(*) DESC, sport ASC
        LIMIT 1
        """,
        (cluster_id,),
    )
    row = cur.fetchone()
    mode = row[0] if row else None
    cur.execute("UPDATE clusters SET sport = %s WHERE id = %s", (mode, cluster_id))


def recompute_cluster_topic(cur: psycopg.Cursor, cluster_id: uuid.UUID) -> None:
    """Set cluster.topic to the mode of non-null article topics (tie-break: lexicographic)."""
    cur.execute(
        """
        SELECT topic FROM articles
        WHERE cluster_id = %s AND topic IS NOT NULL
        GROUP BY topic
        ORDER BY COUNT(*) DESC, topic ASC
        LIMIT 1
        """,
        (cluster_id,),
    )
    row = cur.fetchone()
    mode = row[0] if row else None
    cur.execute("UPDATE clusters SET topic = %s WHERE id = %s", (mode, cluster_id))


def upsert_article(
    cur: psycopg.Cursor,
    item: FeedItem,
    cluster_id: uuid.UUID,
    sport: str,
    topic: str,
    article_id: uuid.UUID,
) -> tuple[bool, uuid.UUID]:
    cur.execute(
        """
        INSERT INTO articles (id, cluster_id, title, url, source, published_at, summary, sport, topic, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (url)
        DO UPDATE SET
            cluster_id = EXCLUDED.cluster_id,
            title = EXCLUDED.title,
            source = EXCLUDED.source,
            published_at = EXCLUDED.published_at,
            summary = EXCLUDED.summary,
            sport = EXCLUDED.sport,
            topic = EXCLUDED.topic
        RETURNING (xmax = 0) AS inserted, id
        """,
        (
            article_id,
            cluster_id,
            item.title,
            item.url,
            item.source,
            item.published_at,
            item.summary,
            sport,
            topic,
        ),
    )
    row = cur.fetchone()
    if not row:
        return False, article_id
    return bool(row[0]), row[1]


def existing_article_id_by_url(
    cur: psycopg.Cursor,
    url: str,
) -> uuid.UUID | None:
    cur.execute("SELECT id FROM articles WHERE url = %s LIMIT 1", (url,))
    row = cur.fetchone()
    if not row:
        return None
    return row[0]


def print_post_run_cluster_report(database_url: str) -> None:
    """Report cluster sizes from DB (same join/filters as GET /feed_clusters)."""
    os.environ.setdefault("DATABASE_URL", database_url)
    backend_root = Path(__file__).resolve().parents[1] / "backend"
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    from sqlalchemy import desc, func, select

    from app.db import SessionLocal
    from app.models import Article, Cluster

    def article_url_filters():
        return (
            ~Article.url.contains("bbc.co.uk/sounds/"),
            ~Article.url.contains("bbc.co.uk/iplayer/"),
        )

    top_stmt = (
        select(
            Cluster.id,
            Cluster.headline,
            func.count(Article.id).label("size"),
        )
        .join(Article, Article.cluster_id == Cluster.id)
        .where(*article_url_filters())
        .group_by(Cluster.id, Cluster.headline)
        .order_by(desc(func.count(Article.id)))
        .limit(5)
    )

    demo_stmt = (
        select(
            Cluster.id,
            Cluster.headline,
            func.count(Article.id).label("size"),
        )
        .join(Article, Article.cluster_id == Cluster.id)
        .where(*article_url_filters())
        .group_by(Cluster.id, Cluster.headline)
        .having(func.count(Article.id) >= 2)
        .order_by(desc(func.count(Article.id)))
        .limit(5)
    )

    session = SessionLocal()
    try:
        print("top_clusters:")
        for row in session.execute(top_stmt).all():
            hid = row.headline or ""
            print(f"  cluster_id={row.id} size={int(row.size)} headline={hid}")

        print("good_demo_candidates:")
        for row in session.execute(demo_stmt).all():
            cid = row.id
            tstmt = (
                select(Article.title)
                .where(Article.cluster_id == cid)
                .where(*article_url_filters())
                .order_by(Article.created_at.asc())
                .limit(5)
            )
            titles = list(session.scalars(tstmt).all())
            tstr = " | ".join(titles)
            hid = row.headline or ""
            print(
                f"  cluster_id={cid} size={int(row.size)} headline={hid} titles={tstr}"
            )
    finally:
        session.close()


def main() -> int:
    database_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    print_llm_container_env_summary()
    embeddings_model = (
        os.getenv("EMBEDDINGS_MODEL", EMBEDDINGS_MODEL_DEFAULT).strip()
        or EMBEDDINGS_MODEL_DEFAULT
    )
    try:
        sim_threshold = float(os.getenv("SIM_THRESHOLD", str(SIM_THRESHOLD_DEFAULT)))
    except ValueError:
        sim_threshold = SIM_THRESHOLD_DEFAULT
    try:
        high_sim_override = float(
            os.getenv("HIGH_SIM_OVERRIDE", str(HIGH_SIM_OVERRIDE_DEFAULT))
        )
    except ValueError:
        high_sim_override = HIGH_SIM_OVERRIDE_DEFAULT
    feed_urls, total_feed_urls = read_feed_urls()
    if not feed_urls:
        print("[error] no feed URLs found in docs/rss_sources.md")
        return 1

    print(f"total_feed_urls={total_feed_urls}")
    print(f"feeds_used={len(feed_urls)}")
    print(f"sample_feeds={feed_urls[:5]}")

    fetched = 0
    inserted = 0
    updated = 0
    skipped_audio_items = 0
    skipped_audio_urls = 0
    skipped_feature_items = 0
    skipped_feature_urls = 0
    processed_for_cluster = 0
    cluster_ids: set[uuid.UUID] = set()
    sport_tag_counts: Counter[str] = Counter()
    topic_tag_counts: Counter[str] = Counter()
    sport_other_sample_titles: list[str] = []
    topic_other_sample_titles: list[str] = []
    noise_lane_counts: Counter[str] = Counter()
    noise_lane_samples: dict[str, list[str]] = {
        "betting": [],
        "watch": [],
        "gossip": [],
        "updates": [],
    }
    base_key_seen_topics: dict[str, set[str]] = {}
    blocked_topic_logs = 0
    forced_gossip_logs = 0
    gossip_key_logs = 0
    embedding_merge_logs = 0
    embedding_attempt_logs = 0

    feed_failure_counts: Counter[str] = Counter()
    failed_feed_records: list[tuple[str, str, str]] = []
    feeds_ok_count = 0

    llm_judge_active = llm_should_run()
    (
        _llm_en,
        llm_api_key_judge,
        _llm_prov,
        llm_model_judge,
        llm_max_tok_judge,
        llm_timeout_judge,
    ) = llm_enrichment_config()

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            ensure_sport_columns_psycopg(cur)
            ensure_topic_columns_psycopg(cur)
            ensure_llm_cluster_columns_psycopg(cur)
            for feed_url in feed_urls:
                try:
                    payload = fetch_rss(feed_url)
                except (HTTPError, URLError, TimeoutError, OSError) as exc:
                    kind, reason = classify_fetch_failure(exc)
                    feed_failure_counts[kind] += 1
                    failed_feed_records.append((feed_url, kind, reason))
                    continue
                except Exception as exc:  # noqa: BLE001
                    feed_failure_counts["other"] += 1
                    failed_feed_records.append(
                        (feed_url, "other", str(exc)[:160]),
                    )
                    continue
                try:
                    items = parse_rss_items(payload, source_url=feed_url)
                except ET.ParseError as exc:
                    feed_failure_counts["parse_error"] += 1
                    failed_feed_records.append(
                        (feed_url, "parse_error", str(exc)[:160]),
                    )
                    continue
                feeds_ok_count += 1
                for item in items:
                    fetched += 1
                    skip_audio, url_audio = should_skip_audio_item(
                        item.title, item.url
                    )
                    if skip_audio:
                        skipped_audio_items += 1
                        if url_audio:
                            skipped_audio_urls += 1
                        continue

                    skip_feature, feature_url_video = should_skip_feature_item(
                        item.title, item.url
                    )
                    if skip_feature:
                        skipped_feature_items += 1
                        if feature_url_video:
                            skipped_feature_urls += 1
                        continue

                    processed_for_cluster += 1
                    competition = detect_competition(item.source, item.url)
                    date_b = date_bucket(item.published_at)
                    if competition in ("F1", "NBA"):
                        team1, team2 = "unknown", "unknown"
                    else:
                        team1, team2 = epl_team_pair_from_title(item.title)

                    noise_lane = classify_noise_lane(item.title, item.url)
                    gossip_hit, gossip_source = is_gossip(item.title, item.url)
                    if gossip_hit:
                        noise_lane = "gossip"
                    if noise_lane is not None:
                        noise_lane_counts[noise_lane] += 1
                        if len(noise_lane_samples[noise_lane]) < 3:
                            noise_lane_samples[noise_lane].append(item.title)
                    if noise_lane == "gossip" and forced_gossip_logs < 10:
                        domain = item.url.split("/")[2] if "://" in item.url else item.url
                        print(
                            "[noise-lane] forced gossip: "
                            f"domain={domain} title={item.title[:120]}"
                        )
                        forced_gossip_logs += 1
                    topic_tag = topic_from_title_and_url(item.title, item.url)
                    if noise_lane == "gossip":
                        topic_tag = "gossip"
                    effective_topic = noise_lane if noise_lane is not None else topic_tag
                    topic_key = topic_merge_group(effective_topic)
                    tag = sport_for_article(item)
                    current_article_id = existing_article_id_by_url(cur, item.url) or uuid.uuid4()

                    sig6_slug = title_signature_n_slug(item.title, 6)

                    item_embedding = embed_text(_embedding_input_text(item))
                    if not tag:
                        embedding_cluster_id = None
                        embedding_score = 0.0
                        embedding_title = None
                        embedding_reason = "missing_sport"
                        embedding_top5: list[tuple[float, str, str, uuid.UUID]] = []
                        if embedding_attempt_logs < 10:
                            print(
                                "embedding_skip: "
                                f'missing_sport_fallback_to_deterministic title="{item.title[:120]}"'
                            )
                    else:
                        embedding_cluster_id, embedding_score, embedding_title, embedding_reason, embedding_top5 = try_embedding_merge(
                            cur,
                            item=item,
                            article_id=current_article_id,
                            sport_tag=tag,
                            embedding=item_embedding,
                            effective_topic=effective_topic,
                            threshold=sim_threshold,
                            high_sim_override=high_sim_override,
                        )
                        if embedding_attempt_logs < 10:
                            top5_fmt = []
                            for score, cand_title, cand_url, cand_cluster in embedding_top5:
                                domain = (
                                    cand_url.split("/")[2].lower()
                                    if "://" in cand_url
                                    else cand_url.lower()
                                )
                                top5_fmt.append(
                                    (f"{score:.2f}", cand_title[:70], domain, str(cand_cluster))
                                )
                            print(
                                "embedding_candidates: "
                                f'new_title="{item.title[:80]}" '
                                f"sport={tag} "
                                f"threshold={sim_threshold:.2f} "
                                f"top5={top5_fmt}"
                            )
                            print(
                                "embedding_candidates: "
                                f'note="sport_filter_active" sport={tag}'
                            )

                    if (
                        llm_judge_active
                        and tag
                        and embedding_cluster_id is None
                        and embedding_top5
                        and LLM_JUDGE_SIM_LOW <= embedding_score <= LLM_JUDGE_SIM_HIGH
                        and embedding_reason in ("below_threshold", "topic_gate")
                        and effective_topic not in {"gossip", "betting", "watch"}
                    ):
                        try:
                            _cand_sim, cand_t, cand_u, cand_cid = embedding_top5[0]
                            same_story, judge_reason = llm_merge_judge_verdict(
                                item,
                                cand_t,
                                cand_u,
                                embedding_score,
                                api_key=llm_api_key_judge,
                                model=llm_model_judge,
                                max_tokens=llm_max_tok_judge,
                                timeout=llm_timeout_judge,
                            )
                            verdict_lbl = "YES" if same_story else "NO"
                            jr = judge_reason.replace('"', "'")[:200]
                            print(
                                f'llm_judge: sim={embedding_score:.2f} '
                                f'verdict={verdict_lbl} reason="{jr}"'
                            )
                            if same_story:
                                embedding_cluster_id = cand_cid
                                embedding_title = cand_t
                                embedding_reason = "llm_judge"
                        except Exception as exc:  # noqa: BLE001
                            print(
                                "llm_judge_failed: "
                                f"sim={embedding_score:.2f} error={str(exc)[:160]}"
                    )

                    if gossip_hit:
                        mode = "gossip_key"
                        gossip_sig = title_signature_n_slug(item.title, 6)
                        gossip_domain_group = (
                            gossip_source
                            if gossip_source in ("mirror.co.uk", "dailymail.co.uk")
                            else "generic"
                        )
                        key = (
                            f"GOSSIP|domain={gossip_domain_group}|"
                            f"sig6={gossip_sig}|topic=gossip"
                        )
                        if gossip_key_logs < 10:
                            domain = (
                                item.url.split("/")[2]
                                if "://" in item.url
                                else item.url
                            )
                            print(
                                "[gossip-key] "
                                f"title={item.title[:100]} "
                                f"domain={domain} key={key}"
                            )
                            gossip_key_logs += 1
                    elif team1 == "unknown" and team2 == "unknown":
                        mode = "title_fallback"
                        signature = title_core_signature(item.title)
                        key = f"title:{signature}:topic={topic_key}"
                    elif team2 == "unknown" and team1 != "unknown":
                        mode = "entity_key_plus_sig"
                        base = cluster_key_string(
                            competition, date_b, team1, team2
                        )
                        seen = base_key_seen_topics.setdefault(base, set())
                        noise_lanes = {"gossip", "betting", "watch", "updates"}
                        if (
                            seen
                            and all(
                                not topics_compatible(effective_topic, prev)
                                for prev in seen
                            )
                            and blocked_topic_logs < 10
                        ):
                            prev_topic = sorted(seen)[0]
                            lane_a = (
                                effective_topic
                                if effective_topic in noise_lanes
                                else "none"
                            )
                            lane_b = (
                                prev_topic if prev_topic in noise_lanes else "none"
                            )
                            if (
                                effective_topic in noise_lanes
                                and prev_topic in noise_lanes
                                and effective_topic != prev_topic
                            ):
                                reason = "lane mismatch"
                            elif "gossip" in (effective_topic, prev_topic):
                                reason = "gossip gating"
                            elif "updates" in (effective_topic, prev_topic):
                                reason = "updates gating"
                            else:
                                reason = "topic mismatch"
                            print(
                                "[topic-gate] blocked merge: "
                                f"topic_a={effective_topic} "
                                f"topic_b={prev_topic} "
                                f"lane_a={lane_a} "
                                f"lane_b={lane_b} "
                                f"reason={reason}"
                            )
                            blocked_topic_logs += 1
                        seen.add(effective_topic)
                        key = f"{base}:topic={topic_key}:{sig6_slug}"
                        signature = title_signature_n(item.title, 6)
                    else:
                        mode = "entity_key"
                        base = cluster_key_string(
                            competition, date_b, team1, team2
                        )
                        seen = base_key_seen_topics.setdefault(base, set())
                        noise_lanes = {"gossip", "betting", "watch", "updates"}
                        if (
                            seen
                            and all(
                                not topics_compatible(effective_topic, prev)
                                for prev in seen
                            )
                            and blocked_topic_logs < 10
                        ):
                            prev_topic = sorted(seen)[0]
                            lane_a = (
                                effective_topic
                                if effective_topic in noise_lanes
                                else "none"
                            )
                            lane_b = (
                                prev_topic if prev_topic in noise_lanes else "none"
                            )
                            if (
                                effective_topic in noise_lanes
                                and prev_topic in noise_lanes
                                and effective_topic != prev_topic
                            ):
                                reason = "lane mismatch"
                            elif "gossip" in (effective_topic, prev_topic):
                                reason = "gossip gating"
                            elif "updates" in (effective_topic, prev_topic):
                                reason = "updates gating"
                            else:
                                reason = "topic mismatch"
                            print(
                                "[topic-gate] blocked merge: "
                                f"topic_a={effective_topic} "
                                f"topic_b={prev_topic} "
                                f"lane_a={lane_a} "
                                f"lane_b={lane_b} "
                                f"reason={reason}"
                            )
                            blocked_topic_logs += 1
                        seen.add(effective_topic)
                        key = f"{base}:topic={topic_key}"
                    if noise_lane is not None:
                        key = f"noise={noise_lane}|{key}"

                    if embedding_cluster_id is not None:
                        cluster_id = embedding_cluster_id
                        if (
                            embedding_reason == "override"
                            and embedding_merge_logs < 10
                        ):
                            print(
                                "override_merge: "
                                f"score={embedding_score:.2f} "
                                "reason=highlights_report_override "
                                f"{item.title[:80]} -> "
                                f"{(embedding_title or '')[:80]} "
                                f"cluster_id={cluster_id}"
                            )
                        if embedding_merge_logs < 10:
                            print(
                                "embedding_merge: "
                                f"score={embedding_score:.2f} "
                                f"{item.title[:80]} -> "
                                f"{(embedding_title or '')[:80]} "
                                f"cluster_id={cluster_id}"
                            )
                            embedding_merge_logs += 1
                    else:
                        if embedding_attempt_logs < 10:
                            print(
                                "embedding_no_merge: "
                                f"best={embedding_score:.2f} reason={embedding_reason}"
                            )
                        key_hash = hash_cluster_key(key)
                        cluster_id = cluster_id_from_hash(key_hash)
                    if embedding_attempt_logs < 10:
                        embedding_attempt_logs += 1
                    if processed_for_cluster <= 10:
                        if mode == "title_fallback":
                            print(
                                f"[cluster-debug] title_fallback {item.title} -> "
                                f"{signature} -> {cluster_id}"
                            )
                        elif mode == "entity_key_plus_sig":
                            print(
                                f"[cluster-debug] entity_key_plus_sig {item.title} -> "
                                f"{competition},{date_b},{team1}+{team2},"
                                f"sig6={sig6_slug} -> {cluster_id}"
                            )
                        else:
                            print(
                                f"[cluster-debug] entity_key {item.title} -> "
                                f"{competition},{date_b},{team1}+{team2} -> "
                                f"{cluster_id}"
                            )
                    cluster_ids.add(cluster_id)
                    sport_tag_counts[tag] += 1
                    if tag == "other" and len(sport_other_sample_titles) < 10:
                        sport_other_sample_titles.append(item.title)
                    upsert_cluster(cur, cluster_id, item.title)
                    topic_tag_counts[topic_tag] += 1
                    if (
                        topic_tag == "other"
                        and len(topic_other_sample_titles) < 10
                    ):
                        topic_other_sample_titles.append(item.title)
                    was_inserted, article_id = upsert_article(
                        cur, item, cluster_id, tag, topic_tag, article_id=current_article_id
                    )
                    if item_embedding is not None and not has_article_embedding(cur, article_id):
                        upsert_article_embedding(
                            cur,
                            article_id=article_id,
                            model_name=embeddings_model,
                            embedding=item_embedding,
                    )
                    recompute_cluster_sport(cur, cluster_id)
                    recompute_cluster_topic(cur, cluster_id)
                    if was_inserted:
                        inserted += 1
                    else:
                        updated += 1
        conn.commit()

    run_llm_cluster_enrichment_pass(database_url)

    feeds_failed_count = len(feed_urls) - feeds_ok_count

    print("feed_health_report:")
    print(f"  feeds_total={total_feed_urls}")
    print(f"  feeds_used={len(feed_urls)}")
    print(f"  feeds_ok_count={feeds_ok_count}")
    print(f"  feeds_failed_count={feeds_failed_count}")
    print(
        "  failure_breakdown:",
        f"403={feed_failure_counts.get('403', 0)}",
        f"404={feed_failure_counts.get('404', 0)}",
        f"timeout={feed_failure_counts.get('timeout', 0)}",
        f"parse_error={feed_failure_counts.get('parse_error', 0)}",
        f"other={feed_failure_counts.get('other', 0)}",
    )
    print("  failed_feed_samples (up to 10):")
    for url, kind, reason in failed_feed_records[:10]:
        print(f"    [{kind}] {url}")
        print(f"      reason: {reason}")

    print("content_distribution_report:")
    print("  by_sport:")
    for k in REPORT_SPORTS:
        print(f"    {k}={sport_tag_counts.get(k, 0)}")
    _extra_sports = {
        sk: sv
        for sk, sv in sport_tag_counts.items()
        if sk not in REPORT_SPORTS
    }
    if _extra_sports:
        print(f"    extra={_extra_sports}")
    print("  by_topic:")
    for k in REPORT_TOPICS:
        print(f"    {k}={topic_tag_counts.get(k, 0)}")
    _extra_topics = {
        tk: tv
        for tk, tv in topic_tag_counts.items()
        if tk not in REPORT_TOPICS
    }
    if _extra_topics:
        print(f"    extra={_extra_topics}")

    print("debug_samples:")
    print("  sport_other_sample_titles (up to 10):")
    for t in sport_other_sample_titles:
        print(f"    {t}")
    print("  topic_other_sample_titles (up to 10):")
    for t in topic_other_sample_titles:
        print(f"    {t}")
    print("noise_lane_report:")
    print(
        "  noise_lane_counts:",
        f"betting={noise_lane_counts.get('betting', 0)}",
        f"watch={noise_lane_counts.get('watch', 0)}",
        f"gossip={noise_lane_counts.get('gossip', 0)}",
        f"updates={noise_lane_counts.get('updates', 0)}",
    )
    print("  noise_lane_sample_titles (up to 3 each):")
    for lane in ("betting", "watch", "gossip", "updates"):
        print(f"    {lane}:")
        samples = noise_lane_samples.get(lane, [])
        if not samples:
            print("      (none)")
            continue
        for title in samples:
            print(f"      {title}")

    print(
        "audio_skip_report:",
        f"skipped_audio_items={skipped_audio_items}",
        f"skipped_audio_urls={skipped_audio_urls}",
    )
    print(
        "feature_skip_report:",
        f"skipped_feature_items={skipped_feature_items}",
        f"skipped_feature_urls={skipped_feature_urls}",
    )

    print_llm_prompt_token_sample(database_url, cluster_ids)

    print_post_run_cluster_report(database_url)

    print("run_once completed")
    print(f"raw_feed_url_lines_in_doc={total_feed_urls}")
    print(f"feeds_used={len(feed_urls)}")
    print(f"items_fetched={fetched}")
    print(f"articles_inserted={inserted}")
    print(f"articles_updated={updated}")
    print(f"clusters_touched={len(cluster_ids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

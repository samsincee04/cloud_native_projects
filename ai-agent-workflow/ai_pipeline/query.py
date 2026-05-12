from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib import request
from urllib.error import HTTPError

import chromadb
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run RAG query for 10-K tasks.")
    parser.add_argument("--task", choices=["summary", "risks"], required=True)
    parser.add_argument("--filing_id", type=str, required=True)
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text, matching Lab 8).",
    )
    return parser.parse_args()


def load_prompt(task: str) -> str:
    prompt_path = project_root() / "ai_pipeline" / "prompts" / f"{task}.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def retrieve_context(
    task: str,
    filing_id: str,
    top_k: int,
    embedding_model_name: str,
) -> Tuple[str, List[Dict[str, Any]]]:
    vector_store_dir = project_root() / "ai_pipeline" / "vector_store"
    if not vector_store_dir.exists():
        raise FileNotFoundError(
            "Vector store not found. Run `python -m ai_pipeline.ingest --pdf <path> --filing_id <id>` first."
        )

    client = chromadb.PersistentClient(path=str(vector_store_dir))
    collection = client.get_collection("sec_filings")

    query_text = (
        "Summarize company overview, financial performance, and operations from the 10-K."
        if task == "summary"
        else "Identify key risks, impacts, and evidence from the 10-K."
    )

    embedder = SentenceTransformer(embedding_model_name)
    query_embedding = embedder.encode([query_text], convert_to_numpy=True).tolist()[0]

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where={"filing_id": filing_id},
        include=["documents", "metadatas", "distances"],
    )

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    ids = results.get("ids", [[]])[0]
    if not documents:
        raise ValueError("No retrieved chunks found in vector store for this filing_id.")

    lines: List[str] = []
    evidence: List[Dict[str, Any]] = []
    for i, doc in enumerate(documents, start=1):
        idx = i - 1
        meta = metadatas[idx] if idx < len(metadatas) else {}
        distance = distances[idx] if idx < len(distances) else None
        chunk_id = ids[idx] if idx < len(ids) else None
        source_pdf = meta.get("pdf_filename", "unknown")
        chunk_idx = meta.get("chunk_index", "unknown")
        lines.append(
            f"[C{i}] source={source_pdf} chunk_index={chunk_idx} distance={distance}\n{doc}"
        )
        page_val = meta.get("page")
        evidence.append(
            {
                "id": chunk_id,
                "source": source_pdf,
                "page": page_val if page_val is not None else None,
                "text": doc,
            }
        )

    return "\n\n".join(lines), evidence


def call_openrouter(prompt_text: str, context_text: str) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip()
    model = os.getenv("OPENROUTER_MODEL", "").strip()
    if not api_key or not model:
        raise ValueError("OPENROUTER_API_KEY and OPENROUTER_MODEL must be set in .env")

    full_prompt = (
        f"{prompt_text}\n\n"
        "Retrieved context (use only this context):\n"
        f"{context_text}\n"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a careful financial 10-K assistant."},
            {"role": "user", "content": full_prompt},
        ],
        "temperature": 0,
    }

    req = request.Request(
        url=f"{base_url}/chat/completions",
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
        raise ValueError(f"OpenRouter HTTP {e.code}: {detail}") from e

    data = json.loads(body)
    choices = data.get("choices")
    if choices:
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if content is not None and isinstance(content, str) and content.strip():
            return content
        raise ValueError(
            "OpenRouter returned empty message content. "
            f"Body (truncated): {json.dumps(data)[:1200]}"
        )
    err_detail = _extract_api_error_message(data)
    if err_detail:
        raise ValueError(f"OpenRouter API error: {err_detail}")
    raise ValueError(
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


def main() -> None:
    load_dotenv()
    args = parse_args()
    json_mode = args.format == "json"

    top_k = int(os.getenv("RAG_TOP_K", "6"))
    embedding_model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2").strip()

    prompt_text = load_prompt(args.task)
    context_text, evidence = retrieve_context(
        args.task,
        args.filing_id.strip(),
        top_k=top_k,
        embedding_model_name=embedding_model_name,
    )
    response = call_openrouter(prompt_text=prompt_text, context_text=context_text)

    if json_mode:
        out = {
            "task": args.task,
            "filing_id": args.filing_id.strip(),
            "answer": response,
            "evidence": evidence,
        }
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(response)


if __name__ == "__main__":
    main()

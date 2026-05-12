from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib import request

import chromadb
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run RAG query for 10-K tasks.")
    parser.add_argument("--task", choices=["summary", "risks"], required=True)
    return parser.parse_args()


def load_prompt(task: str) -> str:
    prompt_path = project_root() / "ai_pipeline" / "prompts" / f"{task}.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def retrieve_context(task: str, top_k: int, embedding_model_name: str) -> str:
    vector_store_dir = project_root() / "ai_pipeline" / "vector_store"
    if not vector_store_dir.exists():
        raise FileNotFoundError(
            "Vector store not found. Run `python -m ai_pipeline.ingest` first."
        )

    client = chromadb.PersistentClient(path=str(vector_store_dir))
    collection = client.get_collection("tenk_chunks")

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
        include=["documents", "metadatas", "distances"],
    )

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    if not documents:
        raise ValueError("No retrieved chunks found in vector store.")

    lines = []
    for i, doc in enumerate(documents, start=1):
        meta = metadatas[i - 1] if i - 1 < len(metadatas) else {}
        distance = distances[i - 1] if i - 1 < len(distances) else None
        source_pdf = meta.get("source_pdf", "unknown")
        chunk_idx = meta.get("chunk_index", "unknown")
        lines.append(
            f"[C{i}] source={source_pdf} chunk_index={chunk_idx} distance={distance}\n{doc}"
        )
    return "\n\n".join(lines)


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
    with request.urlopen(req, timeout=120) as resp:
        body = resp.read().decode("utf-8")
    data = json.loads(body)
    return data["choices"][0]["message"]["content"]


def main() -> None:
    load_dotenv()
    args = parse_args()
    top_k = int(os.getenv("RAG_TOP_K", "6"))
    embedding_model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2").strip()

    prompt_text = load_prompt(args.task)
    context_text = retrieve_context(args.task, top_k=top_k, embedding_model_name=embedding_model_name)
    response = call_openrouter(prompt_text=prompt_text, context_text=context_text)
    print(response)


if __name__ == "__main__":
    main()

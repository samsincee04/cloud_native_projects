from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import List

import chromadb
from dotenv import load_dotenv
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def extract_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    pages_text: List[str] = []
    for page in reader.pages:
        pages_text.append(page.extract_text() or "")
    text = "\n".join(pages_text).strip()
    if not text:
        raise ValueError(f"No extractable text found in PDF: {pdf_path}")
    return text


def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    if chunk_size <= 0:
        raise ValueError("CHUNK_SIZE must be > 0")
    if chunk_overlap < 0:
        raise ValueError("CHUNK_OVERLAP must be >= 0")
    if chunk_overlap >= chunk_size:
        raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")

    chunks: List[str] = []
    step = chunk_size - chunk_overlap
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest SEC filing PDF into ChromaDB.")
    parser.add_argument("--pdf", type=str, required=True, help="Path to PDF file.")
    parser.add_argument("--filing_id", type=str, required=True, help="Stable filing identifier.")
    return parser.parse_args()


def ingest() -> None:
    load_dotenv()
    args = parse_args()

    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    filing_id = args.filing_id.strip()
    if not filing_id:
        raise ValueError("filing_id must be non-empty.")

    chunk_size = int(os.getenv("CHUNK_SIZE", "800"))
    chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "150"))
    embedding_model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2").strip()

    raw_text = extract_pdf_text(pdf_path)
    chunks = chunk_text(raw_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if not chunks:
        raise ValueError("No chunks generated from PDF text.")

    embedder = SentenceTransformer(embedding_model_name)
    embeddings = embedder.encode(chunks, convert_to_numpy=True).tolist()

    vector_store_dir = project_root() / "ai_pipeline" / "vector_store"
    vector_store_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(vector_store_dir))

    collection_name = "sec_filings"
    collection = client.get_or_create_collection(name=collection_name)

    try:
        collection.delete(where={"filing_id": filing_id})
    except Exception:
        pass

    pdf_filename = pdf_path.name
    ids = [f"{filing_id}::{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "filing_id": filing_id,
            "pdf_filename": pdf_filename,
            "chunk_index": i,
        }
        for i in range(len(chunks))
    ]
    collection.add(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas)

    print(f"PDF: {pdf_path}")
    print(f"filing_id: {filing_id}")
    print(f"Total characters: {len(raw_text)}")
    print(f"Total chunks: {len(chunks)}")
    print(f"Vector store: {vector_store_dir}")


if __name__ == "__main__":
    ingest()

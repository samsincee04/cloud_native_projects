from __future__ import annotations

import os
from pathlib import Path
from typing import List

import chromadb
from dotenv import load_dotenv
from pypdf import PdfReader
from sec_api import PdfGeneratorApi
from sentence_transformers import SentenceTransformer


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def download_10k_pdf_if_missing() -> Path:
    load_dotenv()

    sec_api_key = os.getenv("SEC_API_KEY", "").strip()
    filing_10k_url = os.getenv(
        "FILING_10K_URL",
        "https://www.sec.gov/Archives/edgar/data/1318605/000162828024002390/tsla-20231231.htm",
    ).strip()
    output_name = os.getenv("RAW_10K_PDF_NAME", "tesla_10K.pdf").strip()

    raw_dir = project_root() / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_path = raw_dir / output_name

    if output_path.exists():
        print(f"PDF already exists, skipping download: {output_path}")
        return output_path

    if not sec_api_key:
        raise ValueError("SEC_API_KEY is missing. Add it to your .env file.")

    pdf_generator = PdfGeneratorApi(sec_api_key)
    pdf_bytes = pdf_generator.get_pdf(filing_10k_url)

    with output_path.open("wb") as file:
        file.write(pdf_bytes)

    print(f"Downloaded 10-K PDF to: {output_path}")
    return output_path


def resolve_pdf_path() -> Path:
    raw_dir = project_root() / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    configured_name = os.getenv("RAW_10K_PDF_NAME", "tesla_10K.pdf").strip()
    configured_path = raw_dir / configured_name
    if configured_path.exists():
        return configured_path

    pdf_files = sorted(raw_dir.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError(
            "No PDF found in data/raw/. Put a 10-K PDF there or run download_10k_pdf_if_missing()."
        )
    return pdf_files[0]


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


def ingest() -> None:
    load_dotenv()

    chunk_size = int(os.getenv("CHUNK_SIZE", "800"))
    chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "150"))
    embedding_model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2").strip()

    pdf_path = resolve_pdf_path()
    raw_text = extract_pdf_text(pdf_path)
    chunks = chunk_text(raw_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if not chunks:
        raise ValueError("No chunks generated from PDF text.")

    embedder = SentenceTransformer(embedding_model_name)
    embeddings = embedder.encode(chunks, convert_to_numpy=True).tolist()

    vector_store_dir = project_root() / "ai_pipeline" / "vector_store"
    vector_store_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(vector_store_dir))

    collection_name = "tenk_chunks"
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    collection = client.create_collection(name=collection_name)

    ids = [f"chunk-{i}" for i in range(len(chunks))]
    metadatas = [{"source_pdf": pdf_path.name, "chunk_index": i} for i in range(len(chunks))]
    collection.add(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas)

    print(f"PDF: {pdf_path}")
    print(f"Total characters: {len(raw_text)}")
    print(f"Total chunks: {len(chunks)}")
    print(f"Vector store: {vector_store_dir}")


if __name__ == "__main__":
    ingest()

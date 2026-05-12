# SEC 10-K AI Analysis

A standalone AI analysis subsystem that processes a SEC 10-K filing and produces structured, evidence-grounded outputs using prompt engineering, in-context learning, and retrieval-augmented generation.

## Overview

This project analyzes a single company 10-K filing and produces two main outputs:

1. An executive summary of the business and financial highlights.
2. A structured list of material risk factors grounded in retrieved filing text.

The system uses ChromaDB as a local vector store, sentence-transformer embeddings for retrieval, and prompt files stored as reusable artifacts.

## Features

- Loads a SEC 10-K PDF from `data/raw/`
- Extracts PDF text using `pypdf`
- Chunks filing text with configurable chunk size and overlap
- Stores embeddings in a local ChromaDB vector store
- Retrieves relevant filing chunks for summary and risk-analysis tasks
- Uses separate prompt files for summary and risk outputs
- Produces grounded LLM responses based only on retrieved evidence

## Tech Stack

- Python
- ChromaDB
- Sentence Transformers
- pypdf
- python-dotenv
- OpenRouter / OpenAI-compatible API

## Project Structure

```text
sec-10k-ai-analysis/
├── ai_pipeline/
│   ├── __init__.py
│   ├── ingest.py
│   ├── query.py
│   └── prompts/
│       ├── summary.md
│       └── risks.md
├── data/
│   ├── raw/
│   └── processed/
├── pyproject.toml
├── agents.md
├── README.md
└── .gitignore

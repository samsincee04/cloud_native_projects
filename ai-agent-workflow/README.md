# AI Agent Workflow

A cloud-native AI agent project that uses a multi-step workflow to plan, gather information, extract key details, judge outputs, and validate results.

## Overview

This project explores an agent-style workflow where separate modules handle different parts of an AI task. The system uses environment-based configuration for API keys and model settings, while keeping secrets outside version control.

## Features

- Multi-step agent workflow
- Planning module
- Information gathering module
- Extraction module
- Judging/evaluation module
- Validation module
- Environment-based API configuration
- Optional RAG/vector-store support through the included AI pipeline files

## Tech Stack

- Python
- OpenRouter / OpenAI-compatible API
- Tavily API, if web search is used
- python-dotenv
- ChromaDB / local vector store, if using the AI pipeline portion
## Architecture Overview

The system is decoupled into two primary framework directories:

1. **`ai_pipeline/` (Data Preparation Subsystem):** Standardizes local PDF text extraction, applies sliding-window vectorization, indexes tokens into a persistent database, and manages semantic cosine-similarity context retrieval.
2. **`agent/` (Agentic Verification Loop):** Coordinates a multi-step sequence that breaks down data, plans search engine parameters, executes rate-limited web scraping, and conducts whitelisted citation fact-checking.

```text
       [ Raw PDF Document ]
                │
                ▼
      ┌────────────────────┐
      │   ai_pipeline/     │  <-- Local Vector Indexing & Context Retrieval
      └─────────┬──────────┘
                │  (Emits Formatted Lab 8 JSON Output)
                ▼
      ┌────────────────────┐
      │  1. agent.extract  │  <-- Stage 4.1: Atomizes text into unique data items
      └─────────┬──────────┘
                │
                ▼
      ┌────────────────────┐
      │ 2. agent.validate  │  <-- Rubric Check: Local linting barrier (POSIX Code 2)
      └─────────┬──────────┘
                │
                ▼
      ┌────────────────────┐
      │   3. agent.plan    │  <-- Stage 4.2: Generates token-dense search keywords
      └─────────┬──────────┘
                │
                ▼
      ┌────────────────────┐
      │  4. agent.gather   │  <-- Stage 4.3: Tavily Scraper (Hard API & Token Caps)
      └─────────┬──────────┘
                │
                ▼
      ┌────────────────────┐
      │   5. agent.judge   │  <-- Stage 4.4: Local Evaluator (Whitelist URL Enforcement)

## Project Structure

```text
ai-agent-workflow/
├── agent/
│   ├── plan.py
│   ├── gather.py
│   ├── extract.py
│   ├── judge.py
│   └── validate.py
├── ai_pipeline/
├── data/
├── agents.md
├── pyproject.toml
├── README.md
├── .env.example
└── .gitignore

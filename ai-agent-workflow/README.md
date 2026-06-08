# AI Agent Workflow System

A modular, production-grade **Retrieval-Augmented Generation (RAG) and Fact-Checking Pipeline** designed to audit unstructured financial text. The system ingests raw corporate compliance documents (such as SEC 10-K filings), atomizes them into distinct claims, plans and executes budget-aware live web research, and programmatically evaluates verdicts while completely eliminating LLM hallucination vectors.

Rather than relying on a single loose, non-deterministic prompt, this architecture implements a **5-stage agentic workflow** using isolated file-to-file command-line interfaces (CLIs). Every state transition is rigorously sandboxed and validated against rigid schemas, ensuring enterprise-grade predictability and runtime stability.

---

## Overview

This project explores a production-grade, modular agentic lifecycle where specialized backend utilities decouple a heavy analytical workload into highly targeted, serializable steps. By separating data preparation from multi-step verification, the system maintains strict token tracking, deterministic data paths, and resilient fault guardrails. Configuration is entirely managed via local environment files, keeping sensitive provider orchestration keys decoupled from remote source control.

---

## Features & Defensive Design

* **Strict Namespace Isolation:** Uses metadata-filtering (`where={"filing_id": ...}`) during vector database retrieval. Multiple distinct corporate filings safely coexist in the same collection without context cross-contamination.
* **Algorithmic Token Filtering:** Employs localized regex-driven tokenization and financial stop-word stripping to convert messy prose into clean, high-signal search engine keywords.
* **Deterministic Array & Naming Bounds:** Guarantees that the generated item count exactly matches user-specified arguments, enforcing a stable, predictable alphanumeric serialization schema (`summary_claim_01`, `risks_item_01`).
* **Resource and Cost Accounting Throttling:** Implements hard API budgets for web queries. If limits are reached, the system pauses calls gracefully and tags state records with clear status metrics (`partial_budget_exhausted | budget_exhausted`) instead of throwing an unhandled exception.
* **Zero-Hallucination Citation Safeguards:** Cross-references model-generated hyperlinks against a compiled in-memory whitelist of successfully scraped source URLs. Any unverified or hallucinated link is programmatically purged, and the item's verdict is automatically flipped to `insufficient_evidence`.

---

## Tech Stack

* **Core Language:** Python 3.11+ (Leverages native standard library structures like `urllib.request` to optimize runtime velocity and maintain a zero-dependency footprint where applicable)
* **Vector Store:** ChromaDB (Persistent local client instance)
* **Embeddings & Vectorization:** Local `sentence-transformers` utilizing the `all-MiniLM-L6-v2` topology (Zero cloud dependencies for internal vectorization)
* **LLM Orchestration:** OpenRouter API (Configured to execute at `temperature: 0` to completely mitigate stochastic completion variances)
* **Web Scraping Engine:** Tavily Client SDK (Finance-focused extraction mode)

---

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
                │  (Emits Formatted Data Contract JSON)
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
      └────────────────────┘

ai-agent-workflow/
├── agent/
│   ├── extract.py      # Stage 4.1: Claims atomization and context slicing
│   ├── validate.py     # POSIX-compliant linting barrier and rubric sequence checker
│   ├── plan.py         # Stage 4.2: Corporate identity inference and search query planner
│   ├── gather.py       # Stage 4.3: Budget-aware web search and HTML scraper module
│   └── judge.py        # Stage 4.4: Automated validator node & citation verifier
├── ai_pipeline/
│   ├── prompts/
│   │   ├── risks.md    # Few-shot prompt template for financial risk registers
│   │   └── summary.md  # Few-shot prompt template for company financial highlights
│   ├── ingest.py       # Extracts PDF text and commits chunk embeddings to vector index
│   └── query.py        # Executes isolated namespace RAG queries to emit data contracts
├── data/               # Local repository for raw source artifacts and testing documents
├── .env.example        # Environment variable layout template
├── .gitignore          # Rules for preventing secrets from hitting remote source control
├── pyproject.toml      # Project dependency and structural environment settings
└── README.md           # System documentation

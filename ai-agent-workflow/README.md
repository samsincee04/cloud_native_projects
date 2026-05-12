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

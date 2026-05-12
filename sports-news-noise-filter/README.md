# Sports News Noise Filter

A cloud-native sports news filtering project that collects sports articles, groups related stories, and presents users with a cleaner feed organized around major sports topics and events.

## Overview

This project is designed to reduce duplicate, rumor-heavy, and repetitive sports news. Instead of showing every article separately, the system groups similar stories into clusters so users can quickly understand what happened and choose which topic to open.

## Features

- Collects sports news from multiple sources
- Normalizes article data for storage and processing
- Groups related stories into clusters
- Supports filtering by sport, team, or topic
- Provides a frontend interface for viewing clustered stories
- Uses a backend API to serve article and cluster data
- Includes worker-based processing for article ingestion and clustering

## Tech Stack

- Frontend: Next.js
- Backend: FastAPI
- Worker: Python
- Database: PostgreSQL
- AI/NLP: Sentence embeddings and LLM-assisted summaries

## Project Structure

```text
sports-news-noise-filter/
├── backend/
├── frontend/
├── worker/
├── infra/
├── docs/
└── README.md

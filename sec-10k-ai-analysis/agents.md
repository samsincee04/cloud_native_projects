Objective:
Build a standalone AI analysis subsystem for a single SEC 10-K PDF that produces:
1) an executive summary, and
2) a structured list of material risk factors,
using prompt engineering, in-context learning, and RAG with ChromaDB.
Hard Constraints:
- All work is contained under lab8-ai/.
- Dependency management uses pyproject.toml only
- Do not add requirements.txt or other dependency files.
- No web server and no frontend code.
- Prompts must be stored as files under ai_pipeline/prompts/ and loaded at runtime.
- Use ChromaDB as the vector store, persisted under ai_pipeline/vector_store/.
- The LLM output must be grounded only in retrieved text. Do not use external knowledge.
Required Entry Points:
- python -m ai_pipeline.ingest
- python -m ai_pipeline.query --task summary
- python -m ai_pipeline.query --task risks
Acceptance Checks:
- Ingest creates a persisted ChromaDB store under ai_pipeline/vector_store/.
- Query runs after ingestion and returns a structured response.
- Editing ai_pipeline/prompts/summary.md changes the summary output without code changes.
- Editing ai_pipeline/prompts/risks.md changes the risks output without code changes.
- If vector_store is missing, query fails with a clear error message.

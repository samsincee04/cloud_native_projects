Objective:
Modify the copied AI pipeline so that it:
1) explicitly selects which PDF filing to ingest and query, and
2) can emit structured JSON output for agent consumption.
Scope:
- This step prepares the system for agentic verification later.
- No web search, tool use, or verification logic is implemented yet.
Hard Constraints:
- All work is confined to the copied lab9-agents directory.
- Use a single ChromaDB collection for all filings.
- Every stored chunk must include metadata with key "filing_id".
- Retrieval must filter using metadata (where={"filing_id": ...}).
- No assumptions about "first PDF in directory" are allowed.
Ingestion Requirements:
- ingest.py must require:
--pdf <path to PDF>
--filing_id <string identifier>
- Each chunk must store:
- filing_id
- pdf_filename
- chunk_index
- Chunk IDs must be globally unique using:
<filing_id>::<chunk_index>
Query Requirements:
- query.py must require:
--task {summary,risks}
--filing_id <string identifier>
- Retrieval must filter on filing_id metadata.
- Add optional flag:
--format {text,json}
- When format=json is specified:
- Output must be valid JSON only.
- No extra logging or text may be printed.
JSON Output Contract:
- JSON output must include:
- task
- filing_id
- answer
- evidence (list of objects with id, source/page if available, and text)
Prohibited:
- Changing prompt semantics beyond formatting.
- Introducing agent frameworks or external tools.
- Removing Lab 8 functionality.
Acceptance Checks:
- Two PDFs ingested with different filing_id values coexist in the same ChromaDB.
- Querying with filing_id A never returns evidence from filing_id B.
- JSON output parses successfully using json.loads().
- Text output remains available when --format is not specified.

Step 4.1 Scope:
- Implement claim/risk extraction from Lab 8 JSON output.
- Do not implement Tavily calls or any tool use in this step.
New CLI Entry Point:
- python -m agent.extract --input <lab8_json> --output <claims_json> --max_items <int>
Input Contract (Lab 8 JSON):
- The input file is JSON produced by ai_pipeline.query with --format json.
- It includes fields:
- task
- filing_id
- answer
- evidence (list)
Output Contract (Step 4.1 JSON):
- Output must be valid JSON only.
- Output must include:
- task
- filing_id
- items: list of objects
- Each item object must include:
- item_id (string)
- item_text (string) # atomic claim or risk statement
- tenk_evidence (list) # subset of Lab 8 evidence objects
Determinism Requirements:
- For a given input file and max_items, the number of output items must be exactly max_items.
- item_id values must be stable and predictable:
- summary_claim_01, summary_claim_02, ...
- risks_item_01, risks_item_02, ...
Prohibited in Step 4.1:
- Tavily usage
- Web access
- Adding new dependencies or frameworks
- Modifying the Lab 8 prompt files
Acceptance Checks (Step 4.1):
- Running agent.extract produces a JSON file with exactly max_items items.
- Each item includes at least one tenk_evidence snippet.
- The output JSON parses with json.loads() and contains no extra printed text.

Step 4.2 Scope:
- Implement query planning for each extracted item.
- Do not implement Tavily calls or any tool use in this step.
New CLI Entry Point:
- python -m agent.plan --input <claims_json> --output <planned_json> --queries_per_item <int>
Input Contract (Step 4.1 JSON):
- Input includes keys: task, filing_id, items[]
- Each item includes: item_id, item_text, tenk_evidence[]
Output Contract (Step 4.2 JSON):
- Output must be valid JSON only.
- Output must include: task, filing_id, items[]
- Each item must include all previous fields plus:
- queries: list of strings
Planning Rules:
- queries_per_item must be either 1 or 2.
- Each query must include:
- the company name
- and at least one disambiguating keyword derived from the item_text
- Queries must be phrased as web-search queries, not questions to an LLM.
Prohibited in Step 4.2:
- Tavily usage
- Web access
- Adding new dependencies or frameworks
Acceptance Checks (Step 4.2):
- Running agent.plan adds a "queries" list to every item.
- Each item has exactly queries_per_item queries.
- Every query string contains the word "Microsoft".
- Output JSON parses with json.loads() and contains no extra printed text.

Step 4.3 Scope:
- Implement Tavily tool use: search and extract.
- Do not implement verdict assignment or final report synthesis yet.
New CLI Entry Point:
- python -m agent.gather --input <planned_json> --output <gathered_json>
--max_searches <int> --max_extracts <int>
Tooling Requirements:
- Use Tavily with the API key provided via environment variable:
TAVILY_API_KEY
- Do not hardcode the key.
- Fail fast with a clear error if TAVILY_API_KEY is missing.
Budget Rules (Hard):
- Total Tavily searches executed must be <= max_searches.
- Total URLs extracted must be <= max_extracts.
- Stop searching/extracting when budgets are reached.
Input Contract (Step 4.2 JSON):
- task, filing_id, items[]
- each item has: item_id, item_text, tenk_evidence[], queries[]
Output Contract (Step 4.3 JSON):
- Preserve all prior fields.
- Add to each item:
- sources: list of objects, each with:
- url
- title (if available)
- snippet (if available)
- extracted_text (short, bounded)
- retrieved_at (optional ISO timestamp)
- sources may be empty if budgets are exhausted, but this must be explicit:
include a field "gather_status" per item with values:
gathered | partial_budget_exhausted | budget_exhausted
Prohibited in Step 4.3:
- Assigning supports/contradicts/insufficient verdicts
- Adding new dependencies or frameworks
Acceptance Checks (Step 4.3):
- agent.gather runs and produces valid JSON.
- Total searches and extracts do not exceed budgets.
- At least one item has >= 1 source when budgets allow.
- Missing TAVILY_API_KEY produces a clear error message.

Step 4.4 Scope:
- Implement source evaluation and verdict assignment.
- Do not call Tavily or any external tools in this step.
New CLI Entry Point:
- python -m agent.judge --input <gathered_json> --output <judged_json>
Input Contract (Step 4.3 JSON):
- task, filing_id, items[]
- each item includes: item_id, item_text, tenk_evidence[], queries[], sources[], gather_status
Output Contract (Step 4.4 JSON):
- Preserve all prior fields.
- Add to each item:
- verdict: supports | contradicts | insufficient_evidence
- verdict_reason: short string grounded in evidence
- cited_urls: list of URLs used for the verdict (subset of sources)
Evaluation Rules:
- If sources list is empty, verdict must be insufficient_evidence.
- If sources exist but do not clearly address the item_text, verdict must be insufficient_evidence.
- Do not hallucinate citations: cited_urls must come from sources[].url only.
- The verdict_reason must refer to specific extracted_text content (paraphrase allowed).
Prohibited in Step 4.4:
- Any new web calls or Tavily calls
- Any new dependencies or frameworks
Acceptance Checks (Step 4.4):
- agent.judge runs and produces valid JSON.
- Every item has a verdict in the allowed set.
- Items with zero sources have verdict == insufficient_evidence.
- cited_urls is always a subset of sources[].url.
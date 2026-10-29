# Candidate Evidence Assistant

A local RAG application for one synthetic job description and 15 synthetic resumes.
It answers candidate questions, compares selected candidates, shows supporting
quotes, and proposes a shortlist for a hiring manager to review. It does not make
final hiring decisions.

## Requirements

- Windows, Python 3.13, Git, Docker Desktop running Linux containers.
- Node.js 22.12+ or Node.js 24 LTS and npm.
- An OpenAI API key with access to the configured generation and embedding models.
- Run every backend command from the repository root. Commands below use PowerShell.

## Setup

Clone this repository, enter its directory, and run:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
Copy-Item .env.example .env
code .env
docker compose up -d --wait
.\.venv\Scripts\python.exe -m app.ingest --dry-run
.\.venv\Scripts\python.exe -m app.ingest
npm.cmd --prefix frontend ci
```

Set OPENAI_API_KEY in .env before ingestion. Keep .env private. The dataset already
lives in Dataset/job_description.txt and Dataset/resumes/*.docx. Ingestion should
report 16 sources and 86 chunks. It replaces the index atomically; rerunning it
does not add duplicates. Re-ingest when changing data or the embedding model.
The schema uses 1536-dimensional vectors.

The default generation model is gpt-5.4-mini-2026-03-17. Change CHAT_MODEL only to
a model your account can access that supports Responses API structured outputs.
The embedding model is text-embedding-3-small.

## Run

Terminal 1:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

Terminal 2:

```powershell
npm.cmd --prefix frontend run dev
```

Open http://127.0.0.1:5173. API documentation is at http://127.0.0.1:8000/docs.
The Vite development server proxies /api to FastAPI; no browser API key or CORS
configuration is needed. npm run build verifies frontend compilation; the local
demo uses npm run dev, since the preview server has no API proxy.

Use candidate checkboxes for a comparison, or leave them empty for global Q&A.
The shortlist button always considers all 15 candidates and asks for up to three
proposals. Inspect citations, unknowns, and JD criteria before making any decision.
Candidate IDs map to local resume filenames; identities are not needed for scoring.

Example questions:

- What labelled retrieval evaluation did CAND-001 perform?
- Compare privacy logging evidence for CAND-004 and CAND-012.
- Which Kubernetes certification has CAND-001 earned?
- Who implemented combined keyword and dense retrieval?

POST /ask accepts question, candidate_ids, and mode ("qa" or "shortlist").
Unknown IDs produce 400; invalid input produces 422; unavailable dependencies
produce 503. /health checks the local index, not OpenAI account availability.

## Automated tests

Offline tests do not make OpenAI calls:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -m "not integration"
```

Create the dedicated integration database once:

```powershell
docker compose exec -T db createdb -U rag rag_test
```

If it already exists, keep it and proceed. Tests reject a URL whose database name
is not rag_test. They replace tables only inside that dedicated test database.

```powershell
$env:TEST_DATABASE_URL = "postgresql://rag:rag_local_only@localhost:5433/rag_test"
.\.venv\Scripts\python.exe -m pytest -q --junitxml=reports/test-results.xml
npm.cmd --prefix frontend run build
```

The focused suite covers real DOCX parsing, metadata, privacy, corrupt/empty input,
duplicate IDs, real pgvector ordering and candidate filters, atomic re-ingestion,
comparisons, citation validation, abstention, direct injection, unsafe outputs,
shortlist coverage, API errors, labels, and metric calculations. Model outputs are
faked in unit tests; live model behavior is evaluated separately below.

## Evaluation

The 15 labelled cases in evaluation/cases.json identify expected candidates, exact
source chunks, evidence points, answerability, and safety behavior. Inspect labels
against the original files before running. Use only the dev cases for tuning; keep
test cases frozen. Both splits use the same corpus, so this is a demonstration
benchmark rather than an independently collected generalization test.

```powershell
.\.venv\Scripts\python.exe -m evaluation.run --validate-only
.\.venv\Scripts\python.exe -m evaluation.run --split dev --output reports/dev-report.json
.\.venv\Scripts\python.exe -m evaluation.run --split all --output reports/sample-report.json
.\.venv\Scripts\python.exe -m evaluation.review --init
code reports\manual-review.json
```

Fill the review using evaluation/RUBRIC.md, then:

```powershell
.\.venv\Scripts\python.exe -m evaluation.review
.\.venv\Scripts\python.exe scripts\write_results.py
```

Live evaluation calls OpenAI and incurs API usage. Each Q&A case uses at most one
embedding call and one generation call; policy refusals skip both. Shortlisting
uses one generation call over the complete small corpus. The report records model
IDs, prompt/label/dataset hashes, code revision, cases, metrics, errors, and review.
Use new report and review filenames for reruns, passing matching --report/--review
arguments. Do not attach an old human review to a new run.

Recall@k and Hit@k measure labelled evidence-chunk retrieval. Candidate-filtered
queries use k=4 per candidate; global queries use k=8. Citation validity checks
source existence, candidate ownership, and exact quote membership. Evidence-point
recall is a lexical coverage proxy. Human review separately measures answer
correctness, semantic groundedness, and safety. No LLM-as-judge is used.
Abstention recall, false abstention, refusal accuracy, errors, and safety failures
are reported separately. A null metric means no applicable denominator.

## Results

<!-- RESULTS_START -->
Automated tests: 23 collected; 0 failures, 0 errors, 0 skipped.

Evaluation: 15/15 completed; citation validity=1.0; abstention recall=0; deterministic safety failures=0.

Human review: correctness=0.8; groundedness=0.9166666666666666; safety failures=0.

See [all metrics and error analysis](docs/RESULTS.md), including Recall@k/Hit@k by retrieval strategy, and [the JSON report](reports/sample-report.json).
<!-- RESULTS_END -->

## Design and privacy

- Python/FastAPI, React/Vite, PostgreSQL/pgvector; direct OpenAI SDK calls.
- Short section chunks preserve evidence boundaries and paragraph locators.
- Exact cosine search is adequate for 75 resume chunks; no approximate index,
  hybrid retrieval, reranking, orchestration framework, or background worker.
- Comparison retrieval gives each selected candidate the same budget. Shortlisting
  includes all candidates to avoid excluding someone through a global top-k cutoff.
- The LLM receives explicit JD criteria and untrusted evidence. Output schemas,
  citation checks, privacy checks, and conservative abstention add guardrails.
- Raw synthetic files and the local source mapping retain names. Indexed/model text
  uses candidate IDs, excludes education and identity headers, redacts contact
  patterns, and drops lines matching protected-attribute or obvious injection patterns.
- OpenAI receives redacted resume chunks for embeddings, redacted questions for
  retrieval, and question/JD/retrieved evidence for generation. Shortlist generation
  receives all sanitized resume sections. Names in filenames and raw DOCX files are
  not sent. Responses requests use store=False; this does not guarantee zero provider
  retention. See docs/ARCHITECTURE.md for the data flow and limitations.
- No request bodies, resumes, or model payloads are logged. Reports contain sanitized
  evidence and answers; only this authorized synthetic dataset is suitable for public
  submission. This app has no authentication and binds to localhost.

## Limitations and scope

Parsing targets the supplied DOCX template and TXT JD. No PDF/OCR, uploads,
multi-user access, production deployment, conversation memory, or background jobs.
Pattern-based privacy/injection defenses are incomplete. Quote validation does not
prove semantic entailment. Missing retrieved evidence is not proof of missing skill.
Resume claims are self-reports, not verified qualifications. A shortlist can vary
between model runs and must be reviewed by a person.

See docs/ARCHITECTURE.md for trade-offs and docs/RESULTS.md for measured results,
case reviews, failure examples, and known limitations.

To stop the database without deleting indexed data:

```powershell
docker compose down
```
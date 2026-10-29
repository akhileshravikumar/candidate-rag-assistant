# Architecture and design decisions

## Goal and flow

This is a local, single-user challenge implementation for the supplied synthetic
corpus. It supports human review of explicit job requirements, not automated hiring.

```text
DOCX resumes + TXT JD
  -> local parser -> remove identity/non-required sections -> redact/filter
  -> OpenAI embeddings -> PostgreSQL sources + chunks + vectors

React -> FastAPI -> input guardrails -> explicit candidate scope
  -> exact pgvector search (Q&A) OR all sanitized candidate sections (shortlist)
  -> structured OpenAI response -> citation/privacy validation -> cited UI result

Labelled cases -> same Service.ask -> deterministic metrics -> human review -> JSON
```

## Parsing and provenance

DOCX document.xml paragraphs are read in document order, including table paragraphs.
The supplied files have five useful sections: Profile, Technical Skills, Experience,
Projects, Additional Notes. Every section has one short content paragraph. A chunk
keeps its entire paragraph without overlap, candidate ID, source ID, section,
paragraph locator, and deterministic ID. The 15 resumes produce 75 chunks.

The TXT JD supplies R1-R7 and P1-P4 as 11 individual chunks with line locators.
All 86 chunks are embedded and stored. Q&A searches resume chunks only; all JD
criteria are always supplied to generation so criteria cannot disappear through
retrieval. The API exposes JD criterion text and locators beside resume citations.

Each source has its SHA-256, relative raw-file path, candidate ID, and local name
mapping. Raw files remain on disk, not in model prompts. Stable IDs support gold
labels and regression tests. Changing paragraphs changes locators; validate and
review evaluation labels after dataset changes.

The parser deliberately rejects unsupported input, duplicate candidate IDs, missing
content, and oversized paragraphs instead of silently dropping required material.
It is not a general resume parser. There is no OCR, pagination-based citation system,
or layout analysis. Education is excluded because this JD has no degree criterion.
All indexing work completes synchronously before the database replacement begins.

## Retrieval and storage

Use text-embedding-3-small with 1536 dimensions and cosine distance. Exact pgvector
ordering is inexpensive at this scale; HNSW/IVFFlat adds no useful benefit here.
There is no numeric similarity cutoff: similarity is a ranking signal, not calibrated
answerability. Generation must abstain when supplied evidence cannot answer.

Global Q&A returns top 8 resume chunks. Selected-candidate queries return top 4 for
each selected ID, which avoids one candidate dominating a comparison. IDs mentioned
in the question are combined with UI-selected IDs. Unknown IDs fail explicitly.
All 15 candidates are considered for shortlisting using their 75 sanitized sections.
This is a deliberate exhaustive-context path for a tiny corpus, not a top-k ranking
benchmark. It does not scale without a more explicit per-requirement retrieval step.

PostgreSQL stores vectors and metadata together. Parameterized SQL prevents query
injection. Ingestion replaces the demo index in a transaction after all embeddings
are obtained; failure preserves the previous index. The embedding model is recorded
and checked before querying. No ORM or migration framework is needed for one small
stable schema. A real schema change would require a migration or intentional rebuild.

## Grounding and the shortlist

The model produces structured findings, unknowns, and advisory candidate IDs.
Every finding has a candidate, JD requirement IDs, and supporting exact quotes.
The server rejects nonexistent sources, cross-candidate citations, altered quotes,
unknown requirement IDs, invalid shortlist references, and detected sensitive output.
An invalid generated answer becomes a visible abstention with validation_failed=true.

There is no free-form uncited summary outside the findings. This simplifies checking,
but a real quote can still fail to support its accompanying finding. Human evaluation
checks entailment and distinguishes partial exposure from demonstrated implementation.
Unknowns identify topics to verify; the UI explicitly says "not found in retrieved
evidence" and avoids asserting a candidate lacks a skill.

The shortlist is an LLM proposal, at most three IDs with cited rationale. Required
criteria precede preferred criteria. There are no invented suitability percentages,
arbitrary numeric weights, auto-rejection rules, or downstream hiring actions.
The human reviewer can disagree, ask a comparison question, inspect sources, and
contact candidates outside this app. Source claims remain unverified self-reports.

## Threat model and data minimization

Resume content and user questions may contain injection attempts. The demo uses
explicit trust boundaries in the system prompt, conservative input/output checks,
structured outputs, exact citation validation, and no tools available to the model.
Some obvious injected lines are removed before indexing. The live evaluation also
adds a malicious retrieved chunk after ingestion, exercising downstream defenses
rather than only testing the ingestion filter. A refused request is distinct from
an unanswerable request or a dependency outage.

Direct identifiers are retained only in local raw files/source metadata. Candidate
IDs replace known names; email, phone, and link patterns are redacted. Protected
attributes and obvious injection lines are excluded. This is data minimization,
not guaranteed anonymization. Unknown name spellings, unfamiliar contact formats,
or subtle protected-attribute proxies may evade these filters. Names can appear
in the authorized public synthetic dataset, but are not used as job criteria.

Outbound to OpenAI:

| Operation | Data sent |
| --- | --- |
| Index embeddings | Sanitized resume paragraphs and explicit JD criteria |
| Query embedding | Sanitized question |
| Answer generation | Sanitized question, candidate IDs, JD criteria, retrieved sanitized sections |
| Shortlist generation | JD criteria and all sanitized candidate sections |

No raw DOCX bytes, local filenames with names, database credentials, or API keys
are put in prompts. Logging omits request bodies, document text, and provider
exceptions. API keys stay in .env, which Git ignores. Responses uses store=False.
That flag does not remove all possible provider retention; see OpenAI's
[data controls](https://developers.openai.com/api/docs/guides/your-data).
The provider is external even when the UI and database run locally.

## Testing, evaluation, and results

Offline tests cover the required deterministic paths with faked model responses.
A separate test uses a real pgvector database for SQL ordering, filters, atomic
rollback, and re-ingestion. These tests do not claim to measure model reasoning.

The live harness runs 15 labelled cases through the application service, records
full sanitized evidence/answers, and emits JSON. Five development cases support
debugging and ten test cases are frozen before tuning. Source-grounded labels were
prepared from the supplied corpus; verify them manually. Shortlist labels allow
multiple defensible candidates rather than prescribing one universal ranking.

Deterministic checks: evidence-chunk Recall@k/Hit@k, expected candidate coverage,
lexical evidence-point recall, exact citation validity, status accuracy, abstention
recall, false abstention, refusal accuracy, safety sentinels, errors, and validation
failures. Errors are not counted as successful abstentions; null denominators stay null.
Human review separately scores correctness, semantic groundedness, and safety.
No LLM judge is included. This keeps costs and evaluation complexity small.

Measured results and case-level error analysis are generated in RESULTS.md and
reports/sample-report.json. Do not invent performance numbers before running them.
Tests, model behavior, and human judgments are separate forms of evidence.

## Deliberately omitted within 16 hours

Background processing, caching, hybrid retrieval, reranking, agents, asynchronous
workflows, automatic document enrichment, PDF/OCR, authentication, production
deployment, complex UI design, and large evaluation frameworks. These are scope
choices. Minimum privacy, citation validation, candidate coverage, error handling,
automated tests, and evaluation remain part of the core implementation.

## Known limitations

- Exact-quote validation is necessary but not sufficient for semantic grounding.
- Pattern-based defenses are bypassable and can also over-refuse benign questions.
- Global top-k can omit relevant candidates; use selected comparisons or shortlist
  for a review that needs broader candidate coverage.
- LLM outputs and shortlist order can vary even with a fixed model snapshot.
- Small synthetic examples cannot establish performance on real resumes.
- The service has no authentication; keep it bound to localhost.
- The system does not verify that resume statements are true.

Examples and observed failures, including the distinction between expected negative
tests and actual live errors, appear in RESULTS.md.
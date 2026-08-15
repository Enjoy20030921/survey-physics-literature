# Review Data Contracts

Read this file before creating, updating, or auditing a review directory. Store UTF-8 text, use English field names and enum values, and preserve stable identifiers across updates.

## Directory contract

```text
literature-reviews/<topic-slug>/
├── protocol.json
├── records.jsonl
├── screening.csv
├── evidence.csv
├── search_runs.jsonl
├── references.bib
├── update_summary.md
├── report_zh.tex          # zh or bilingual
├── report_en.tex          # en or bilingual
├── report_zh.pdf          # after successful compilation
├── report_en.pdf          # after successful compilation
├── review-macros.tex
├── fulltext/
│   ├── manifest.jsonl
│   └── <record-id>.pdf
├── generated/
├── .cache/api/            # deterministic source-response cache
├── build/                 # compilation logs and intermediates
└── runs/<UTC timestamp>/
```

Do not create language-specific report files that the normalized `report_language` does not request. When changing language on an existing review, archive obsolete report files under `runs/<timestamp>/archived_outputs/`.

## `protocol.json`

Required shape:

```json
{
  "schema_version": 1,
  "topic_slug": "island-formula",
  "research_question": "Which assumptions control Page-curve recovery from island prescriptions?",
  "categories": ["hep-th", "gr-qc"],
  "date_range": {"mode": "all-time", "from": null, "to": null},
  "inclusion_criteria": ["Directly analyzes the research question"],
  "exclusion_criteria": ["No substantive technical result"],
  "seed_papers": [],
  "report_language": "bilingual",
  "queries": [
    {"query_id": "arxiv-q01", "source": "arxiv", "query": "cat:hep-th AND all:\"island formula\"", "enabled": true},
    {"query_id": "inspire-q01", "source": "inspire", "query": "find keyword island formula", "enabled": true}
  ],
  "sources": {"arxiv": true, "inspire": true, "crossref": true},
  "limits": {"max_results_per_query": 1000},
  "contact_email": null,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "protocol_history": []
}
```

Use only `zh`, `en`, or `bilingual` for `report_language`. Use ISO 8601 dates. For a bounded review, set `date_range.mode` to `bounded` and provide inclusive `from` and `to` values in `YYYY-MM-DD` format.

Each query must contain the exact source-specific string actually sent to the API. Never replace a query after retrieval; append a protocol-history entry and add a new query ID.

## `records.jsonl`

Write one JSON object per canonical record. Required fields:

```json
{
  "record_id": "arxiv:1911.12333",
  "title": "Record title",
  "authors": ["Family, Given"],
  "year": 2019,
  "published_date": "2019-11-27",
  "updated_date": "2020-01-02",
  "abstract": "Abstract text",
  "doi": "10.xxxx/example",
  "arxiv_id": "1911.12333",
  "arxiv_version": "v2",
  "inspire_recid": "1234567",
  "categories": ["hep-th", "gr-qc"],
  "publication_type": "article",
  "publication_status": "published",
  "journal_title": "Journal name",
  "volume": "1",
  "pages": "1--20",
  "citation_count": 0,
  "citation_count_without_self_citations": 0,
  "bibtex_key": "Author:2019abc",
  "urls": {"abstract": null, "pdf": null, "doi": null, "inspire": null},
  "source_records": [],
  "retrieved_at": "2026-01-01T00:00:00Z"
}
```

Use `null` for unavailable scalar values and empty arrays for unavailable lists. Preserve an existing `record_id` and `bibtex_key` when later sources provide higher-priority identifiers.

Identifier normalization:

- DOI: lowercase, remove `https://doi.org/`, `http://dx.doi.org/`, and `doi:`.
- arXiv: remove URL prefixes and a terminal version such as `v3`; store the version separately.
- INSPIRE: store the decimal recid as a string.
- Fallback ID: `title:<first 16 hex characters of SHA-256(normalized title|year|first author)>`.

## `screening.csv`

Use this exact header:

```csv
record_id,stage,decision,reason_code,reason_detail,reviewer,decided_at
```

Allowed values:

- `stage`: `title_abstract`, `full_text`
- `decision`: `include`, `exclude`, `uncertain`

Append a new row when a decision changes. Treat the last row for each `(record_id, stage)` as current; do not rewrite history.

## `evidence.csv`

Use this exact header:

```csv
claim_id,record_id,claim_summary,evidence_type,direction,locator,assumptions,limitations,confidence,verified_at
```

Allowed values:

- `evidence_type`: `analytic`, `numerical`, `experimental`, `review`, `conceptual`
- `direction`: `supports`, `contradicts`, `qualifies`, `context`
- `confidence`: `high`, `medium`, `low`

Make `claim_id` stable and unique, for example `C001`. Require a non-empty `locator` for every evidence row. Use section, page, equation, figure, or table references; never use an abstract as the locator for a substantive claim.

## `search_runs.jsonl`

Append one object per source query attempt:

```json
{
  "run_id": "20260101T000000Z",
  "query_id": "arxiv-q01",
  "source": "arxiv",
  "query": "cat:hep-th AND all:\"island formula\"",
  "request_url": "https://export.arxiv.org/api/query?...",
  "started_at": "2026-01-01T00:00:00Z",
  "completed_at": "2026-01-01T00:00:04Z",
  "result_count": 20,
  "retrieved_count": 20,
  "truncated": false,
  "cache_used": false,
  "status": "ok",
  "error": null
}
```

Allowed `status` values are `ok`, `partial`, and `failed`. A failed required source prevents an exhaustive-coverage claim.

## Full-text manifest

Append one object per download attempt to `fulltext/manifest.jsonl` with `record_id`, `url`, `status`, `path`, `sha256`, `content_type`, `retrieved_at`, and `error`. Use `downloaded`, `cached`, `unavailable`, `restricted`, or `failed` as status values.

## BibTeX stability

Prefer an INSPIRE `texkey`. Otherwise generate `Family:YYYYTitleToken`; resolve collisions with a stable hash suffix. Once assigned, never change a key during an incremental update. Keep all reports on the same `references.bib`.

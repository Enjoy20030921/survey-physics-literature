# Source Guides

Read this file before live retrieval. Use APIs rather than scraping human-facing search pages.

## arXiv

- Endpoint: `https://export.arxiv.org/api/query`
- Response: Atom XML
- Primary fields: `search_query`, `id_list`, `start`, `max_results`, `sortBy`, `sortOrder`
- Wait at least three seconds between consecutive requests.
- Cache identical queries; arXiv search results do not need repeated retrieval within the same day.
- Request manageable pages. Refine queries that return more than 1,000 records; never hide result truncation.
- Strip terminal versions from canonical arXiv identifiers while preserving the retrieved version separately.
- Treat the arXiv PDF link as a lawful full-text candidate.

Reference: <https://info.arxiv.org/help/api/user-manual.html>

## INSPIRE

- Endpoint: `https://inspirehep.net/api/literature`
- Response: JSON
- Query parameters: `q`, `sort`, `size`, `page`, and `fields`
- Follow `links.next` for pagination and keep page size at or below 1,000.
- Stay below 15 requests per five-second window. The bundled script spaces calls and applies a minimum five-second retry delay after HTTP 429.
- Use `citation_count` and `citation_count_without_self_citations` only as descriptive metadata or work-order hints.
- Prefer `metadata.texkeys[0]` for a stable BibTeX key.
- Retrieve a record by `/api/literature/<recid>`, `/api/arxiv/<id>`, or `/api/doi/<doi>` when exact enrichment is needed.
- INSPIRE can return literature records as BibTeX, but preserve the canonical review record rather than replacing it with an opaque BibTeX blob.

Reference: <https://github.com/inspirehep/rest-api-doc>

## Crossref

- Endpoint: `https://api.crossref.org/v1/works/<encoded-doi>`
- Use Crossref only after DOI normalization and only to fill missing publication metadata.
- Send a descriptive user agent. If the user has supplied a contact email, add `mailto` and use the polite pool.
- Do not treat a missing Crossref record as evidence that the paper is invalid.
- Do not use Crossref abstracts as full-text evidence.

Reference: <https://www.crossref.org/documentation/retrieve-metadata/rest-api/>

## Query design

Build at least one query per independent concept path. For each path:

1. Define the scientific concept.
2. Add standard English terms, historical terminology, acronyms, spelling variants, and named formalisms.
3. Apply category and date constraints explicitly.
4. Translate the concepts into source-specific syntax.
5. Review the exact query string before retrieval.
6. Freeze it in `protocol.json`.

Do not translate Chinese terminology literally when the field uses a different English term. Search the scholarly vocabulary used in titles and abstracts.

## Failure handling

- Retry HTTP 429 and transient 5xx responses with bounded exponential backoff.
- Use a valid cache entry during offline or transient failure and mark `cache_used`.
- Log partial pagination and the last successful page.
- Continue with another source when safe, but mark the run partial and prohibit exhaustive-coverage language.
- Never fabricate a DOI, arXiv ID, recid, citation count, abstract, or full-text locator.

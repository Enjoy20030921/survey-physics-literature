---
name: survey-physics-literature
description: "Conduct auditable HEP and gr-qc literature reviews, systematic reviews, research-landscape syntheses, citation-network expansions from seed papers, and incremental review updates. Trigger for English requests such as literature review, systematic review, research landscape, citation expansion, find related papers, or update an existing review, and for Chinese requests including 物理文献调研, 文献综述, 系统性综述, 梳理研究进展, 查找相关论文, 从种子论文扩展, 更新已有综述, 高能物理, 引力, hep, or gr-qc. Produce Chinese, English, or separate bilingual XeLaTeX reports with a shared BibTeX library. Do not use for isolated physics calculations or a single-paper summary unless the user asks to expand it into a broader literature review."
---

# Survey Physics Literature

Run an evidence-traceable literature review for high-energy physics and gravity. Keep internal records in English, interact in the user's language, and generate only the requested report language.

## Start the Review

1. Detect whether the request is a new review, seed-paper expansion, or incremental update.
2. Collect or confirm these protocol fields before retrieval:
   - research question;
   - arXiv categories;
   - date range or explicit `all-time`;
   - inclusion criteria;
   - exclusion criteria.
3. Accept seed identifiers, user-supplied terms, an existing review directory, and `report_language` as optional inputs.
4. Normalize report language to `zh`, `en`, or `bilingual`:
   - map `中文`, `Chinese`, and Chinese-only requests to `zh`;
   - map `英文`, `English`, and English-only requests to `en`;
   - map `中英双语`, `双语`, and `bilingual` to `bilingual`.
5. If the language is absent, ask once. In a non-interactive run, default to `bilingual`.
6. Use `literature-reviews/<topic-slug>/` as the review directory. Preserve an existing directory for incremental work.

Before creating or modifying review data, read [references/data-contracts.md](references/data-contracts.md). Initialize a new directory with:

```text
python scripts/literature_pipeline.py init <review-dir> \
  --question "<research question>" \
  --categories hep-th gr-qc \
  --date-range all-time \
  --include "<criterion>" \
  --exclude "<criterion>" \
  --language bilingual
```

Add the reviewed source-specific queries to `protocol.json` before live retrieval.

## Run the Workflow Gates

Complete each gate in order. Do not describe a review as systematic or complete while a required gate remains open.

### Gate 1: Freeze the protocol

- Record the question, scope, categories, dates, criteria, seed papers, exact queries, sources, and language in `protocol.json`.
- Separate search concepts into synonym groups. Include established English terminology even when the user asks in Chinese.
- Record any post-search protocol change with a reason; never silently rewrite the original scope.

### Gate 2: Retrieve and normalize

- Read [references/source-guides.md](references/source-guides.md) before querying live sources.
- Search arXiv and INSPIRE independently. Use Crossref only to enrich DOI and journal metadata.
- Run `python scripts/literature_pipeline.py search <review-dir>`.
- Cache responses, log exact queries and counts, respect source limits, and expose truncation or partial failures.
- Merge by normalized DOI, version-independent arXiv ID, and INSPIRE recid before fuzzy title matching.
- Preserve existing record IDs and BibTeX keys during incremental updates.

### Gate 3: Screen candidates

- Read [references/methodology.md](references/methodology.md).
- Screen title and abstract against frozen criteria. Record one decision and reason per candidate in `screening.csv`.
- Use citation counts only to order work, never as an inclusion rule.
- Mark ambiguous records `uncertain`; do not force a decision without evidence.

### Gate 4: Retrieve and assess full text

- Run `python scripts/literature_pipeline.py download <review-dir>` after title/abstract screening.
- Download only lawfully accessible versions. Never bypass a paywall, authentication, robots policy, or access control.
- Use abstracts for screening only. Require a page, section, equation, figure, or table locator for substantive claims.
- Record full-text decisions and quality appraisal. Distinguish preprints, published articles, reviews, lectures, and proceedings.

### Gate 5: Expand citations and reach saturation

- Trace backward and forward citations for included and high-value uncertain records.
- Add discovered records through the same normalization and screening gates.
- Stop only when the frozen scope is covered and a documented expansion round adds no new theme or conclusion-changing evidence.

### Gate 6: Build the evidence matrix

- Add one `evidence.csv` row per material claim-paper relationship.
- Paraphrase evidence; retain precise locators and short verification notes rather than long quotations.
- Record assumptions, regime of validity, limitations, evidence type, direction, and confidence.
- Represent disagreements as separate evidence rows. Never collapse conflicting results into a false consensus.

### Gate 7: Synthesize and report

- Read [references/reporting.md](references/reporting.md).
- Derive the report hierarchy from the research question, evidence topology, audience, and report scale. Do not impose a universal chapter list.
- Treat scope, methods, synthesis, disagreement, limitations, provenance, and auditability as content obligations, not required headings. Merge, rename, relocate, or omit sections when justified by the review.
- Run `python scripts/literature_pipeline.py render-audit <review-dir>` after screening and evidence extraction to generate optional audit fragments. Insert them only where they improve the report; the underlying audit files remain mandatory.
- Generate only the outputs selected by `report_language`:
  - `zh`: `report_zh.tex` and `report_zh.pdf`;
  - `en`: `report_en.tex` and `report_en.pdf`;
  - `bilingual`: both independent report pairs.
- Use one shared `references.bib` and evidence set. For `bilingual`, write evidence-equivalent reports rather than paragraph-by-paragraph translations.
- Mark substantive statements with `\Evidence{<claim_id>}` and cite the supporting papers.

### Gate 8: Audit and compile

Run:

```text
python scripts/audit_review.py <review-dir> --require-reports
python scripts/compile_reports.py <review-dir>
python scripts/audit_review.py <review-dir> --require-reports --require-pdfs
```

- Reject missing citation keys, unknown evidence IDs, evidence without locators, invalid screening values, inconsistent language outputs, and unresolved LaTeX citations.
- Render representative PDF pages and inspect typography, mathematics, tables, links, any included selection flow, and bibliography.
- If XeLaTeX or BibTeX is unavailable, retain valid sources and report the missing executable explicitly. Do not install a TeX distribution automatically.

## Handle Updates

- Run search with `--refresh` for an incremental review.
- Preserve prior records, decisions, evidence IDs, citation keys, and protocol history.
- Summarize added records, changed metadata, publication-status changes, and evidence impact in `update_summary.md`.
- If `report_language` changes, initialize the new templates and archive obsolete language outputs instead of deleting them.

## Completion Contract

Deliver the requested TeX/PDF reports plus `references.bib`, `protocol.json`, `records.jsonl`, `screening.csv`, `evidence.csv`, `search_runs.jsonl`, `update_summary.md`, and the full-text provenance manifest. State source failures, inaccessible papers, unresolved uncertainty, and compilation limitations. Never claim exhaustive coverage when a query was truncated, a required source failed, or full-text verification is incomplete.

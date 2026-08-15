# Systematic Physics Literature Review

[English](README.md) | [简体中文](README.zh-CN.md)

An auditable Codex Skill for systematic and updateable literature reviews in high-energy physics and gravitational physics, especially `hep-*` and `gr-qc` research.

The Skill combines bilingual intent handling, reproducible metadata retrieval, full-text evidence tracking, incremental updates, and Chinese or English LaTeX reporting. Report structure is adaptive: the research question and evidence determine the outline instead of a fixed chapter template.

## Highlights

- Triggers from equivalent Chinese and English review requests.
- Supports new reviews, seed-paper citation expansion, and incremental updates.
- Searches arXiv and INSPIRE, then enriches DOI and journal metadata with Crossref.
- Uses deterministic Python standard-library scripts for retrieval, caching, parsing, deduplication, export, and validation.
- Deduplicates by normalized DOI, version-independent arXiv ID, and INSPIRE recid before title-author-year similarity.
- Separates abstract screening from full-text evidence extraction.
- Requires a section, page, equation, figure, or table locator for substantive claims.
- Preserves stable record IDs, evidence IDs, screening decisions, and BibTeX keys across updates.
- Generates Chinese, English, or separate evidence-equivalent bilingual reports.
- Compiles with XeLaTeX and BibTeX when those tools are available.
- Keeps the report hierarchy adaptive rather than prescribing universal chapters.

The methodology is PRISMA-inspired and auditable, but it does not claim formal PRISMA 2020 compliance.

## Intended use

Use this Skill for requests such as:

- systematic physics literature reviews;
- research-landscape and progress surveys;
- finding related papers across HEP or `gr-qc`;
- expanding a review from seed papers;
- updating an existing review directory;
- comparing agreements, contradictions, assumptions, limitations, and research gaps.

It should not activate for an isolated physics calculation or a summary of one paper unless the request explicitly expands into a broader literature review.

## Installation

This repository keeps the authored Skill at:

```text
.codex/skills/survey-physics-literature/
```

Current OpenAI documentation lists `.agents/skills/` as the local discovery location for standalone Codex Skills. Copy the Skill directory into a repository-scoped location:

```text
<your-project>/.agents/skills/survey-physics-literature/
```

For example, after cloning this repository:

```bash
mkdir -p <your-project>/.agents/skills
cp -R survey-physics-literature/.codex/skills/survey-physics-literature \
  <your-project>/.agents/skills/
```

PowerShell:

```powershell
New-Item -ItemType Directory -Force <your-project>\.agents\skills
Copy-Item -Recurse survey-physics-literature\.codex\skills\survey-physics-literature `
  <your-project>\.agents\skills\survey-physics-literature
```

Codex detects Skill changes automatically in supported discovery locations. Restart Codex if the Skill does not appear. See [OpenAI's Build skills documentation](https://learn.chatgpt.com/docs/build-skills) for the current discovery and invocation behavior.

## Invocation

Invoke the Skill explicitly:

```text
$survey-physics-literature
```

Codex can also invoke it implicitly when the request matches the bilingual description in `SKILL.md`.

Chinese example:

```text
请使用 $survey-physics-literature 调研黑洞信息问题中的岛公式。
研究问题：岛公式在半经典引力中解决 Page curve 问题的证据、假设和主要争议是什么？
arXiv 分类：hep-th, gr-qc
时间范围：all-time
纳入：原创论文、综述、讲义和相关会议论文
排除：只在摘要中提及 island、但正文没有实质讨论的文献
报告语言：中文
```

English example:

```text
Use $survey-physics-literature to review the island formula in the black-hole information problem.
Research question: What evidence, assumptions, and major disputes surround the island formula and the Page curve in semiclassical gravity?
arXiv categories: hep-th, gr-qc
Date range: all-time
Include: original papers, reviews, lectures, and relevant proceedings
Exclude: papers that mention islands only in the abstract without substantive full-text treatment
Report language: English
```

## Review settings

| Setting | Required | Description |
| --- | --- | --- |
| Research question | Yes | A focused, answerable physics question. |
| arXiv categories | Yes | One or more categories such as `hep-th`, `hep-ph`, or `gr-qc`. |
| Date range | Yes | An explicit range or `all-time`. |
| Inclusion criteria | Yes | Eligible document types, systems, methods, and scope. |
| Exclusion criteria | Yes | Explicit reasons for rejecting otherwise related works. |
| Seed-paper identifiers | No | arXiv IDs, DOIs, or INSPIRE recids for citation expansion. |
| User search terms | No | Concepts, names, observables, or alternate terminology. |
| Existing review directory | No | Enables an incremental update that preserves stable identifiers. |
| `report_language` | No | `zh`, `en`, or `bilingual`; the Skill asks once if unspecified and otherwise falls back to `bilingual`. |

Accepted language labels include `中文`, `英文`, `中英双语`, `Chinese`, `English`, and `bilingual`. The normalized value is recorded in `protocol.json`.

## Workflow

```mermaid
flowchart LR
    A[Parse bilingual intent] --> B[Freeze protocol]
    B --> C[Expand concepts and queries]
    C --> D[Search arXiv and INSPIRE]
    D --> E[Enrich with Crossref]
    E --> F[Normalize and deduplicate]
    F --> G[Screen titles and abstracts]
    G --> H[Retrieve lawful full text]
    H --> I[Full-text screening and citation expansion]
    I --> J[Build evidence matrix]
    J --> K[Adaptive synthesis]
    K --> L[Audit citations and compile requested reports]
```

The Skill uses abstracts only for screening. Substantive report claims must map to a full-text evidence record and a precise locator.

## Outputs

Each review is stored under `literature-reviews/<topic-slug>/` and includes:

```text
references.bib
protocol.json
records.jsonl
screening.csv
evidence.csv
search_runs.jsonl
update_summary.md
fulltext/
  manifest.jsonl
```

Language-dependent outputs are exact:

| Mode | Generated reports |
| --- | --- |
| `zh` | `report_zh.tex`, `report_zh.pdf` |
| `en` | `report_en.tex`, `report_en.pdf` |
| `bilingual` | Both complete TeX/PDF pairs |

Changing the language mode archives obsolete report variants so stale outputs are not mistaken for current results.

## Adaptive report structure

The Skill does not impose a fixed list of chapters. It chooses a conceptual, methodological, chronological, comparative, controversy-led, or other suitable structure after examining the question, evidence clusters, audience, and report scale.

Scope, search provenance, evidence-backed synthesis, disagreement, uncertainty, limitations, citations, and auditability remain content obligations. They may be integrated into the main text, combined, renamed, moved to appendices, or retained in external audit files as appropriate.

Generated search summaries, selection flows, and included-study tables are optional LaTeX fragments rather than mandatory appendices.

## Data sources and access policy

- [arXiv API](https://info.arxiv.org/help/api/user-manual.html) is a primary preprint source.
- [INSPIRE REST API](https://github.com/inspirehep/rest-api-doc) is a primary HEP metadata and citation source.
- [Crossref REST API](https://support.crossref.org/hc/en-us/articles/214320426-REST-API) enriches DOI and publication metadata.

The retrieval layer uses caching, request spacing, retry handling, and source-specific provenance. It downloads only lawfully accessible full text and never bypasses authentication, paywalls, or access controls.

## Deterministic command-line tools

The scripts do not make scientific inclusion decisions or write the synthesis. They maintain reproducible data operations around those review judgments.

Initialize a review:

```bash
python .codex/skills/survey-physics-literature/scripts/literature_pipeline.py init \
  literature-reviews/island-formula \
  --question "What evidence and assumptions support the island formula?" \
  --categories hep-th gr-qc \
  --date-range all-time \
  --include "Original papers, reviews, lectures, and proceedings" \
  --exclude "Abstract-only mentions without substantive treatment" \
  --language en
```

After freezing exact queries in `protocol.json`:

```bash
python .codex/skills/survey-physics-literature/scripts/literature_pipeline.py search literature-reviews/island-formula
python .codex/skills/survey-physics-literature/scripts/literature_pipeline.py download literature-reviews/island-formula
python .codex/skills/survey-physics-literature/scripts/literature_pipeline.py render-audit literature-reviews/island-formula
```

Audit and compile:

```bash
python .codex/skills/survey-physics-literature/scripts/audit_review.py literature-reviews/island-formula --require-reports
python .codex/skills/survey-physics-literature/scripts/compile_reports.py literature-reviews/island-formula
python .codex/skills/survey-physics-literature/scripts/audit_review.py literature-reviews/island-formula --require-reports --require-pdfs
```

If XeLaTeX or BibTeX is unavailable, the compiler leaves valid sources in place and returns an explicit diagnostic. It does not install a TeX distribution automatically.

## Validation

Run the offline regression suite:

```bash
python -B .codex/skills/survey-physics-literature/scripts/test_skill_scripts.py
```

The tests cover language normalization, bilingual triggers, arXiv and INSPIRE parsing, old arXiv identifiers, collaboration authors, Unicode, deduplication, caching, HTTP 429 retries, conditional language outputs, and audit failures.

The Skill has also been validated with the official `quick_validate.py` checker and representative XeLaTeX -> BibTeX -> XeLaTeX x2 builds for Chinese and English reports.

## Repository layout

```text
.codex/skills/survey-physics-literature/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── assets/
│   ├── report_en.tex
│   ├── report_zh.tex
│   └── review-macros.tex
├── references/
│   ├── data-contracts.md
│   ├── methodology.md
│   ├── reporting.md
│   └── source-guides.md
└── scripts/
    ├── audit_review.py
    ├── compile_reports.py
    ├── literature_pipeline.py
    └── test_skill_scripts.py
```

## Scientific and operational limits

- Search coverage is broad but cannot guarantee discovery of every relevant work.
- Metadata services may be incomplete, delayed, or temporarily unavailable.
- Abstracts are insufficient evidence for substantive scientific claims.
- Full-text retrieval depends on lawful availability.
- Automated normalization and deduplication must remain auditable and reviewable.
- The final synthesis still requires domain judgment; deterministic scripts support that judgment but do not replace it.

## Acknowledgements

This Skill follows OpenAI's progressive-disclosure design for reusable workflows and uses the official arXiv, INSPIRE, and Crossref interfaces for literature metadata.

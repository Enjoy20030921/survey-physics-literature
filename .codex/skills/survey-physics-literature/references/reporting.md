# Reporting and LaTeX Contract

Read this file before generating report prose or editing the LaTeX templates.

## Language modes

- `zh`: generate only `report_zh.tex` and `report_zh.pdf`.
- `en`: generate only `report_en.tex` and `report_en.pdf`.
- `bilingual`: generate two complete, separate, evidence-equivalent reports.

Keep bibliography keys, claim IDs, figures, tables, screening totals, and scientific scope aligned across bilingual reports. Write each language naturally; do not translate sentence by sentence.

## Adaptive report architecture

- Choose the outline only after understanding the research question, evidence clusters, chronology or method topology, intended audience, and useful report length.
- Do not start from a universal chapter template. Use chapters, sections, subsections, or a compact article-like structure as appropriate.
- Include a section only when it improves the answer. Merge, rename, reorder, relocate, or omit sections freely.
- Organize the synthesis conceptually, methodologically, chronologically, comparatively, around controversies, or with another structure justified by the evidence.
- Treat the following as information obligations rather than required headings: scope and protocol provenance; search and screening disclosure proportionate to the claimed rigor; evidence-backed synthesis; disagreements and uncertainty; limitations and coverage gaps; citations and evidence identifiers; and sufficient audit material to reproduce or inspect the review.
- Integrate audit information into the main text, place it in appendices, or leave detailed material in the generated audit records according to readability and review scale.
- Treat `generated/search-summary-*.tex`, `generated/selection-flow-*.tex`, and `generated/included-studies-*.tex` as optional building blocks. Insert only the fragments that help the report.
- In `bilingual` mode, keep the scientific coverage and evidence equivalent, but allow natural language-specific headings and organization rather than literal structural translation.

## Claim and citation discipline

- Add `\Evidence{C001}` immediately after each material synthesis claim.
- Cite the papers that support, contradict, or qualify the claim.
- Use a precise evidence locator in `evidence.csv`; do not place long quotations in the report.
- Distinguish paper-reported facts, review-level synthesis, and the reviewer's inference.
- Label an inference explicitly when it is not a direct conclusion of the cited papers.
- Do not cite a search-result snippet, metadata page, or abstract as full-text evidence.

## LaTeX rules

- Compile with XeLaTeX, BibTeX, XeLaTeX, XeLaTeX.
- Use `ctexrep` for Chinese and `report` for English.
- Keep shared packages and macros in `review-macros.tex`.
- Use `natbib` with numeric, sorted, compressed citations and `unsrtnat` bibliography style.
- Escape LaTeX special characters in generated prose and metadata without breaking valid mathematics.
- Use `booktabs` and `longtable` for audit tables; avoid vertical rules.
- Use vector graphics or TikZ where practical.
- Keep hyperlinks active and visually restrained.
- Do not suppress overfull boxes, missing glyphs, undefined references, or undefined citations without fixing or disclosing them.

## Visual verification

After compilation, render representative pages and inspect:

- title and abstract pages;
- table of contents, when present;
- a mathematics-heavy page;
- the widest and longest tables;
- the selection-flow figure, when included;
- bibliography pages;
- Chinese punctuation and line breaking;
- link appearance and page headers.

Treat clipped content, unreadable tables, missing glyphs, unresolved references, or materially inconsistent bilingual evidence coverage as failures.

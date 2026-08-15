# Auditable Physics Review Methodology

Use this method for screening, appraisal, evidence extraction, and saturation. It is PRISMA-inspired but does not claim formal PRISMA 2020 compliance.

## Screening order

1. Deduplicate before screening.
2. Apply the frozen criteria to title and abstract.
3. Retrieve lawful full text for `include` and high-value `uncertain` candidates.
4. Apply the criteria again to the full paper.
5. Record one reason code for the primary exclusion reason.
6. Preserve all decision revisions as appended rows.

Recommended exclusion reason codes:

- `out_of_scope`
- `outside_date_range`
- `wrong_document_type`
- `duplicate`
- `no_substantive_result`
- `full_text_unavailable`
- `language_unusable`
- `superseded_version`
- `other`

Do not exclude a work solely for low citation count, recent publication, preprint status, author identity, institution, or disagreement with the emerging synthesis.

## Publication status

Use one of:

- `preprint`
- `published`
- `accepted`
- `proceedings`
- `lecture_notes`
- `review`
- `thesis`
- `unknown`

Treat status as context, not an automatic quality score. Prefer the latest arXiv version while retaining the original submission date and any journal publication metadata.

## Appraise theoretical work

Assess:

- explicit assumptions and physical regime;
- mathematical consistency and derivation transparency;
- limiting cases, symmetries, gauge or coordinate issues where relevant;
- consistency with established results;
- dependence on conjectures, boundary conditions, or semiclassical approximations;
- whether conclusions exceed the demonstrated regime;
- independent reproduction, critique, or extension.

## Appraise numerical work

Assess:

- equations, discretization, algorithms, and convergence tests;
- initial and boundary conditions;
- parameter coverage and sensitivity;
- numerical errors and stability;
- code or data availability;
- comparison with analytic expectations and independent implementations.

## Appraise experimental or observational work

Assess:

- dataset, detector or instrument, exposure, and selection;
- calibration, backgrounds, and systematic uncertainties;
- statistical model, priors, look-elsewhere effects, and robustness tests;
- model dependence and degeneracies;
- reproducibility and data or analysis availability;
- consistency with independent measurements.

## Extract evidence

Create a stable claim before writing prose. For each supporting or conflicting paper, record:

- a paraphrased result;
- evidence type and direction;
- precise locator;
- assumptions and regime;
- limitations;
- confidence in the extraction, not confidence in the theory as a whole.

Use `high` only after direct full-text verification with an unambiguous locator. Use `medium` for a verified but assumption-sensitive result. Use `low` for unclear extraction, inaccessible supporting details, or unresolved interpretation.

## Synthesize disagreements

Separate disagreements caused by:

- different definitions or observables;
- different physical regimes;
- different approximations or boundary conditions;
- numerical or statistical methodology;
- corrected or superseded results;
- genuine unresolved conflict.

Present competing positions with their strongest evidence. Do not count papers as votes.

## Determine saturation

Document each citation-expansion round. Treat the search as saturated only when:

- all frozen concept paths have been searched;
- included papers have undergone backward and forward tracing where metadata permits;
- the latest expansion round adds no new theme, method class, or conclusion-changing evidence;
- all required-source failures and query truncations are resolved or explicitly disclosed.

Saturation does not imply that no relevant paper exists. State the operational stopping rule and search date.

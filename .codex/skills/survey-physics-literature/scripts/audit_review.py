#!/usr/bin/env python3
"""Audit a survey-physics-literature review directory."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

from literature_pipeline import (
    EVIDENCE_HEADER,
    LANGUAGES,
    SCREENING_HEADER,
    PipelineError,
    current_screening_decisions,
    load_json,
    read_csv,
    read_jsonl,
    validate_protocol,
)


SCREENING_STAGES = {"title_abstract", "full_text"}
SCREENING_DECISIONS = {"include", "exclude", "uncertain"}
EVIDENCE_TYPES = {"analytic", "numerical", "experimental", "review", "conceptual"}
EVIDENCE_DIRECTIONS = {"supports", "contradicts", "qualifies", "context"}
CONFIDENCE_VALUES = {"high", "medium", "low"}


def csv_header(path: Path) -> list[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


def strip_tex_comments(text: str) -> str:
    return "\n".join(re.sub(r"(?<!\\)%.*$", "", line) for line in text.splitlines())


def tex_citation_keys(text: str) -> set[str]:
    clean = strip_tex_comments(text)
    keys: set[str] = set()
    pattern = re.compile(r"\\cite[a-zA-Z*]*\s*(?:\[[^\]]*\]\s*){0,2}\{([^}]*)\}")
    for match in pattern.finditer(clean):
        keys.update(key.strip() for key in match.group(1).split(",") if key.strip())
    return keys


def tex_evidence_ids(text: str) -> set[str]:
    return set(re.findall(r"\\Evidence\{([^}]+)\}", strip_tex_comments(text)))


def bibtex_keys(text: str) -> list[str]:
    return re.findall(r"@[A-Za-z]+\s*\{\s*([^,\s]+)\s*,", text)


def expected_languages(language: str) -> list[str]:
    if language == "bilingual":
        return ["zh", "en"]
    return [language]


def add_duplicate_errors(values: Iterable[str], label: str, errors: list[str]) -> None:
    duplicates = [value for value, count in Counter(values).items() if value and count > 1]
    if duplicates:
        errors.append(f"Duplicate {label}: {', '.join(sorted(duplicates))}")


def audit_review(review_dir: Path, require_reports: bool, require_pdfs: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        protocol = load_json(review_dir / "protocol.json")
        validate_protocol(protocol)
    except PipelineError as exc:
        return [str(exc)], warnings

    language = protocol.get("report_language")
    if language not in LANGUAGES:
        errors.append("protocol.report_language is invalid")
        return errors, warnings
    requested = set(expected_languages(language))
    obsolete = {"zh", "en"} - requested

    records = read_jsonl(review_dir / "records.jsonl")
    record_ids = [str(record.get("record_id") or "") for record in records]
    if any(not record_id for record_id in record_ids):
        errors.append("Every record requires a non-empty record_id")
    add_duplicate_errors(record_ids, "record IDs", errors)

    record_map = {str(record.get("record_id")): record for record in records if record.get("record_id")}
    stored_bib_keys = [str(record.get("bibtex_key") or "") for record in records]
    if records and any(not key for key in stored_bib_keys):
        errors.append("Every record requires a stable bibtex_key")
    add_duplicate_errors(stored_bib_keys, "record BibTeX keys", errors)

    bib_path = review_dir / "references.bib"
    if not bib_path.exists():
        errors.append("references.bib is missing")
        bibliography_keys: set[str] = set()
    else:
        parsed_bib_keys = bibtex_keys(bib_path.read_text(encoding="utf-8"))
        add_duplicate_errors(parsed_bib_keys, "BibTeX entries", errors)
        bibliography_keys = set(parsed_bib_keys)
        missing_entries = sorted(set(stored_bib_keys) - bibliography_keys)
        if missing_entries:
            errors.append("records.jsonl keys missing from references.bib: " + ", ".join(missing_entries))

    if csv_header(review_dir / "screening.csv") != SCREENING_HEADER:
        errors.append("screening.csv header does not match the data contract")
    screening = read_csv(review_dir / "screening.csv")
    for row_number, row in enumerate(screening, start=2):
        record_id = row.get("record_id", "")
        if record_id not in record_map:
            errors.append(f"screening.csv row {row_number} references an unknown record: {record_id}")
        if row.get("stage") not in SCREENING_STAGES:
            errors.append(f"screening.csv row {row_number} has invalid stage: {row.get('stage')}")
        if row.get("decision") not in SCREENING_DECISIONS:
            errors.append(f"screening.csv row {row_number} has invalid decision: {row.get('decision')}")

    if csv_header(review_dir / "evidence.csv") != EVIDENCE_HEADER:
        errors.append("evidence.csv header does not match the data contract")
    evidence = read_csv(review_dir / "evidence.csv")
    claim_ids = [row.get("claim_id", "") for row in evidence]
    evidence_claims = set(claim_ids)
    for row_number, row in enumerate(evidence, start=2):
        if not row.get("claim_id"):
            errors.append(f"evidence.csv row {row_number} has no claim_id")
        if row.get("record_id") not in record_map:
            errors.append(f"evidence.csv row {row_number} references an unknown record: {row.get('record_id')}")
        if row.get("evidence_type") not in EVIDENCE_TYPES:
            errors.append(f"evidence.csv row {row_number} has invalid evidence_type: {row.get('evidence_type')}")
        if row.get("direction") not in EVIDENCE_DIRECTIONS:
            errors.append(f"evidence.csv row {row_number} has invalid direction: {row.get('direction')}")
        if row.get("confidence") not in CONFIDENCE_VALUES:
            errors.append(f"evidence.csv row {row_number} has invalid confidence: {row.get('confidence')}")
        if not row.get("locator", "").strip():
            errors.append(f"evidence.csv row {row_number} has no full-text locator")
        if not row.get("claim_summary", "").strip():
            errors.append(f"evidence.csv row {row_number} has no claim summary")

    current = current_screening_decisions(screening)
    screened = {record_id for record_id, stage in current if stage == "title_abstract"}
    full_text = {record_id for record_id, stage in current if stage == "full_text"}
    included = {
        record_id
        for (record_id, stage), row in current.items()
        if stage == "full_text" and row.get("decision") == "include"
    }
    if len(screened) > len(record_map):
        errors.append("Title/abstract screening count exceeds the canonical record count")
    if len(full_text) > len(screened):
        warnings.append("More full-text decisions than title/abstract decisions; verify imported screening history")
    if len(included) > len(full_text):
        errors.append("Included count exceeds the full-text assessment count")

    if require_reports:
        if not evidence:
            errors.append("A completed review requires at least one evidence row")
        for suffix in sorted(requested):
            tex_path = review_dir / f"report_{suffix}.tex"
            if not tex_path.exists():
                errors.append(f"Requested report source is missing: {tex_path.name}")
                continue
            text = tex_path.read_text(encoding="utf-8")
            placeholders = [
                "待填写",
                "在此撰写结构化摘要",
                "To be completed",
                "Write a structured abstract",
            ]
            remaining = [placeholder for placeholder in placeholders if placeholder in text]
            if remaining:
                errors.append(f"{tex_path.name} still contains template placeholders")
            cited = tex_citation_keys(text)
            missing_citations = sorted(cited - bibliography_keys)
            if missing_citations:
                errors.append(f"{tex_path.name} cites missing BibTeX keys: {', '.join(missing_citations)}")
            evidence_ids = tex_evidence_ids(text)
            unknown_evidence = sorted(evidence_ids - evidence_claims)
            if unknown_evidence:
                errors.append(f"{tex_path.name} uses unknown evidence IDs: {', '.join(unknown_evidence)}")
            if not cited:
                errors.append(f"{tex_path.name} contains no citations")
            if not evidence_ids:
                errors.append(f"{tex_path.name} contains no evidence markers")
            if require_pdfs and not (review_dir / f"report_{suffix}.pdf").exists():
                errors.append(f"Requested compiled PDF is missing: report_{suffix}.pdf")

        for suffix in sorted(obsolete):
            for extension in ["tex", "pdf"]:
                stale = review_dir / f"report_{suffix}.{extension}"
                if stale.exists():
                    errors.append(f"Stale language output is present: {stale.name}")

    for suffix in requested:
        final_log = review_dir / "build" / f"report_{suffix}" / f"report_{suffix}.log"
        if not final_log.exists():
            continue
        log_text = final_log.read_text(encoding="utf-8", errors="replace")
        unresolved_patterns = [
            "There were undefined references",
            "Citation `",
            "undefined citations",
            "Reference `",
        ]
        if any(pattern in log_text for pattern in unresolved_patterns):
            errors.append(f"Compilation log contains unresolved citations or references: {final_log.name}")

    logs = read_jsonl(review_dir / "search_runs.jsonl")
    required_failures = [
        log for log in logs if log.get("source") in {"arxiv", "inspire"} and log.get("status") != "ok"
    ]
    if required_failures:
        warnings.append(
            f"{len(required_failures)} primary-source search runs are partial or failed; do not claim exhaustive coverage"
        )
    return errors, warnings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir")
    parser.add_argument("--require-reports", action="store_true")
    parser.add_argument("--require-pdfs", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    review_dir = Path(args.review_dir).resolve()
    try:
        errors, warnings = audit_review(review_dir, args.require_reports, args.require_pdfs)
    except (PipelineError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        print(f"Audit failed with {len(errors)} error(s) and {len(warnings)} warning(s)", file=sys.stderr)
        return 1
    print(f"Audit passed with {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

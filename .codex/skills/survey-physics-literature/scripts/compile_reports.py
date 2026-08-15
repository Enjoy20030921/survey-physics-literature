#!/usr/bin/env python3
"""Compile requested survey reports with XeLaTeX and BibTeX."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from literature_pipeline import PipelineError, load_json, validate_protocol


INTERMEDIATE_SUFFIXES = ["aux", "bbl", "blg", "log", "out", "toc", "lof", "lot", "fls", "fdb_latexmk"]


def expected_languages(language: str) -> list[str]:
    return ["zh", "en"] if language == "bilingual" else [language]


def run_command(command: list[str], cwd: Path) -> tuple[int, str]:
    process = subprocess.run(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return process.returncode, process.stdout


def compile_one(review_dir: Path, suffix: str, xelatex: str, bibtex: str) -> None:
    stem = f"report_{suffix}"
    tex_path = review_dir / f"{stem}.tex"
    if not tex_path.exists():
        raise PipelineError(f"Requested report source is missing: {tex_path}")
    commands = [
        [xelatex, "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
        [bibtex, stem],
        [xelatex, "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
        [xelatex, "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
    ]
    combined: list[str] = []
    pass_outputs: list[str] = []
    for command in commands:
        return_code, output = run_command(command, review_dir)
        pass_outputs.append(output)
        combined.extend(["$ " + " ".join(command), output, ""])
        if return_code != 0:
            build_dir = review_dir / "build"
            build_dir.mkdir(exist_ok=True)
            (build_dir / f"{stem}.combined.log").write_text("\n".join(combined), encoding="utf-8")
            raise PipelineError(f"Compilation command failed for {stem}: {' '.join(command)}")

    combined_text = "\n".join(combined)
    build_dir = review_dir / "build"
    build_dir.mkdir(exist_ok=True)
    (build_dir / f"{stem}.combined.log").write_text(combined_text, encoding="utf-8")
    unresolved = [
        "There were undefined references",
        "undefined citations",
        "Citation `",
        "Reference `",
    ]
    final_output = pass_outputs[-1] if pass_outputs else ""
    if any(marker in final_output for marker in unresolved):
        raise PipelineError(f"Compilation completed with unresolved citations or references in {stem}")
    pdf_path = review_dir / f"{stem}.pdf"
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise PipelineError(f"Compilation did not produce {pdf_path.name}")

    intermediate_dir = build_dir / stem
    intermediate_dir.mkdir(exist_ok=True)
    for suffix_name in INTERMEDIATE_SUFFIXES:
        source = review_dir / f"{stem}.{suffix_name}"
        if source.exists():
            destination = intermediate_dir / source.name
            if destination.exists():
                destination.unlink()
            shutil.move(str(source), str(destination))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    review_dir = Path(args.review_dir).resolve()
    try:
        protocol = load_json(review_dir / "protocol.json")
        validate_protocol(protocol)
        xelatex = shutil.which("xelatex")
        bibtex = shutil.which("bibtex")
        missing = [name for name, path in [("xelatex", xelatex), ("bibtex", bibtex)] if not path]
        if missing:
            raise PipelineError(
                "Missing TeX executables: " + ", ".join(missing) + ". Sources were retained; install a TeX distribution manually."
            )
        for language in expected_languages(protocol["report_language"]):
            compile_one(review_dir, language, xelatex, bibtex)
            print(f"Compiled report_{language}.pdf")
        return 0
    except (PipelineError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

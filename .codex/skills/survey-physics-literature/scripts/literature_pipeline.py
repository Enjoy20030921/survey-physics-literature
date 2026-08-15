#!/usr/bin/env python3
"""Deterministic data operations for survey-physics-literature.

The script uses only the Python standard library. It does not make inclusion
decisions or write scientific synthesis; those remain explicit review tasks.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import difflib
import hashlib
import html
import json
import os
import re
import shutil
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
LANGUAGES = {"zh", "en", "bilingual"}
LANGUAGE_ALIASES = {
    "zh": "zh",
    "cn": "zh",
    "chinese": "zh",
    "中文": "zh",
    "中文报告": "zh",
    "en": "en",
    "english": "en",
    "英文": "en",
    "英文报告": "en",
    "bilingual": "bilingual",
    "both": "bilingual",
    "中英双语": "bilingual",
    "双语": "bilingual",
    "中英文": "bilingual",
}
SCREENING_HEADER = [
    "record_id",
    "stage",
    "decision",
    "reason_code",
    "reason_detail",
    "reviewer",
    "decided_at",
]
EVIDENCE_HEADER = [
    "claim_id",
    "record_id",
    "claim_summary",
    "evidence_type",
    "direction",
    "locator",
    "assumptions",
    "limitations",
    "confidence",
    "verified_at",
]
USER_AGENT = "survey-physics-literature/1.0 (+https://openai.com/)"
ARXIV_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
    "arxiv": "http://arxiv.org/schemas/atom",
}


class PipelineError(RuntimeError):
    """Raise for deterministic, user-actionable pipeline failures."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_id() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="")
    os.replace(temporary, path)


def write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(f"Required file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(f"Invalid JSON in {path}: {exc}") from exc


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    values: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PipelineError(f"Invalid JSONL in {path} at line {number}: {exc}") from exc
        if not isinstance(value, dict):
            raise PipelineError(f"Expected an object in {path} at line {number}")
        values.append(value)
    return values


def write_jsonl(path: Path, values: Iterable[dict[str, Any]]) -> None:
    lines = [json.dumps(value, ensure_ascii=False, sort_keys=True) for value in values]
    atomic_write_text(path, "\n".join(lines) + ("\n" if lines else ""))


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def initialize_csv(path: Path, header: list[str]) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        csv.writer(handle).writerow(header)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def normalize_language(value: str) -> str:
    normalized = re.sub(r"\s+", "", value.strip().lower())
    if normalized in LANGUAGE_ALIASES:
        return LANGUAGE_ALIASES[normalized]
    if "双语" in normalized or ("中文" in normalized and "英文" in normalized):
        return "bilingual"
    if "中文" in normalized:
        return "zh"
    if "英文" in normalized:
        return "en"
    raise PipelineError(
        f"Unsupported report language {value!r}; use zh, en, bilingual, 中文, 英文, or 中英双语"
    )


def parse_date_range(value: str) -> dict[str, Any]:
    if value.strip().lower() == "all-time":
        return {"mode": "all-time", "from": None, "to": None}
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2}):(\d{4}-\d{2}-\d{2})", value.strip())
    if not match:
        raise PipelineError("Use all-time or YYYY-MM-DD:YYYY-MM-DD for --date-range")
    start = dt.date.fromisoformat(match.group(1))
    end = dt.date.fromisoformat(match.group(2))
    if start > end:
        raise PipelineError("The date-range start must not be after the end")
    return {"mode": "bounded", "from": start.isoformat(), "to": end.isoformat()}


def strip_markup(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"<[^>]+>", " ", html.unescape(value))
    return re.sub(r"\s+", " ", text).strip() or None


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    text = html.unescape(value).strip().lower()
    text = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", text)
    text = text.rstrip(". ,;)")
    return text or None


def normalize_arxiv(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    text = html.unescape(value).strip()
    text = re.sub(r"^https?://(?:export\.)?arxiv\.org/(?:abs|pdf)/", "", text, flags=re.I)
    text = re.sub(r"^arxiv:\s*", "", text, flags=re.I)
    text = re.sub(r"\.pdf$", "", text, flags=re.I)
    text = text.split("?", 1)[0].split("#", 1)[0]
    match = re.fullmatch(r"(.+?)(v\d+)", text, flags=re.I)
    if match:
        return match.group(1), match.group(2).lower()
    return text or None, None


def normalized_title(value: str | None) -> str:
    if not value:
        return ""
    text = strip_markup(value) or ""
    text = re.sub(r"\\[A-Za-z]+", " ", text)
    text = unicodedata.normalize("NFKD", text).casefold()
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).strip()


def ascii_token(value: str, fallback: str = "Anon") -> str:
    text = unicodedata.normalize("NFKD", value)
    text = "".join(character for character in text if not unicodedata.combining(character))
    token = re.sub(r"[^A-Za-z0-9]+", "", text)
    return token or fallback


def first_author_family(authors: list[str]) -> str:
    if not authors:
        return "Anon"
    first = authors[0].strip()
    if "," in first:
        family = first.split(",", 1)[0]
    else:
        family = first.split()[-1] if first.split() else "Anon"
    return ascii_token(family)


def fallback_record_id(record: dict[str, Any]) -> str:
    basis = "|".join(
        [
            normalized_title(record.get("title")),
            str(record.get("year") or ""),
            first_author_family(record.get("authors") or []),
        ]
    )
    return "title:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def choose_record_id(record: dict[str, Any]) -> str:
    if record.get("record_id"):
        return str(record["record_id"])
    if record.get("arxiv_id"):
        return f"arxiv:{record['arxiv_id']}"
    if record.get("doi"):
        return f"doi:{record['doi']}"
    if record.get("inspire_recid"):
        return f"inspire:{record['inspire_recid']}"
    return fallback_record_id(record)


def blank_record() -> dict[str, Any]:
    return {
        "record_id": None,
        "title": None,
        "authors": [],
        "year": None,
        "published_date": None,
        "updated_date": None,
        "abstract": None,
        "doi": None,
        "arxiv_id": None,
        "arxiv_version": None,
        "inspire_recid": None,
        "categories": [],
        "publication_type": "unknown",
        "publication_status": "unknown",
        "journal_title": None,
        "volume": None,
        "pages": None,
        "citation_count": None,
        "citation_count_without_self_citations": None,
        "bibtex_key": None,
        "inspire_texkeys": [],
        "urls": {"abstract": None, "pdf": None, "doi": None, "inspire": None},
        "source_records": [],
        "retrieved_at": utc_now(),
    }


def publication_status_rank(value: str | None) -> int:
    ranks = {
        "unknown": 0,
        "preprint": 1,
        "lecture_notes": 2,
        "proceedings": 3,
        "thesis": 3,
        "review": 4,
        "accepted": 5,
        "published": 6,
    }
    return ranks.get(value or "unknown", 0)


def unique_values(values: Iterable[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        marker = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
        if marker not in seen:
            seen.add(marker)
            result.append(value)
    return result


def merge_records(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    merged["record_id"] = existing.get("record_id") or incoming.get("record_id")

    for key in [
        "title",
        "year",
        "published_date",
        "updated_date",
        "doi",
        "arxiv_id",
        "arxiv_version",
        "inspire_recid",
        "journal_title",
        "volume",
        "pages",
        "publication_type",
        "bibtex_key",
    ]:
        if not merged.get(key) and incoming.get(key):
            merged[key] = incoming[key]

    if len(incoming.get("abstract") or "") > len(merged.get("abstract") or ""):
        merged["abstract"] = incoming["abstract"]
    if len(incoming.get("authors") or []) > len(merged.get("authors") or []):
        merged["authors"] = incoming["authors"]

    for key in ["categories", "inspire_texkeys", "source_records"]:
        merged[key] = unique_values((merged.get(key) or []) + (incoming.get(key) or []))

    merged_urls = dict(merged.get("urls") or {})
    for key, value in (incoming.get("urls") or {}).items():
        if value and not merged_urls.get(key):
            merged_urls[key] = value
    merged["urls"] = merged_urls

    for key in ["citation_count", "citation_count_without_self_citations"]:
        values = [value for value in [merged.get(key), incoming.get(key)] if isinstance(value, int)]
        merged[key] = max(values) if values else merged.get(key) or incoming.get(key)

    if publication_status_rank(incoming.get("publication_status")) > publication_status_rank(
        merged.get("publication_status")
    ):
        merged["publication_status"] = incoming["publication_status"]

    merged["retrieved_at"] = max(
        str(existing.get("retrieved_at") or ""), str(incoming.get("retrieved_at") or "")
    ) or utc_now()
    return merged


def records_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    for key in ["doi", "arxiv_id", "inspire_recid"]:
        if left.get(key) and right.get(key) and left[key] == right[key]:
            return True
    left_title = normalized_title(left.get("title"))
    right_title = normalized_title(right.get("title"))
    if not left_title or not right_title:
        return False
    left_year, right_year = left.get("year"), right.get("year")
    if isinstance(left_year, int) and isinstance(right_year, int) and abs(left_year - right_year) > 1:
        return False
    similarity = difflib.SequenceMatcher(None, left_title, right_title).ratio()
    if similarity < 0.94:
        return False
    left_family = first_author_family(left.get("authors") or []).casefold()
    right_family = first_author_family(right.get("authors") or []).casefold()
    return left_family == "anon" or right_family == "anon" or left_family == right_family


def merge_record_sets(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = [dict(record) for record in existing]
    for record in incoming:
        record["doi"] = normalize_doi(record.get("doi"))
        record["arxiv_id"], detected_version = normalize_arxiv(record.get("arxiv_id"))
        record["arxiv_version"] = record.get("arxiv_version") or detected_version
        matched_index = next((index for index, current in enumerate(records) if records_match(current, record)), None)
        if matched_index is None:
            record["record_id"] = choose_record_id(record)
            records.append(record)
        else:
            records[matched_index] = merge_records(records[matched_index], record)
    return records


def assign_bibtex_keys(records: list[dict[str, Any]]) -> None:
    used = {str(record["bibtex_key"]) for record in records if record.get("bibtex_key")}
    for record in sorted(records, key=lambda item: item.get("record_id") or ""):
        if record.get("bibtex_key"):
            continue
        preferred = next((str(key) for key in record.get("inspire_texkeys") or [] if key), None)
        if preferred and preferred not in used:
            key = preferred
        else:
            title_words = [word for word in normalized_title(record.get("title")).split() if len(word) > 2]
            token = ascii_token(title_words[0] if title_words else "work", "work")[:24]
            base = f"{first_author_family(record.get('authors') or [])}:{record.get('year') or 'nd'}{token}"
            key = base
            if key in used:
                suffix = hashlib.sha256(str(record.get("record_id")).encode("utf-8")).hexdigest()[:6]
                key = f"{base}-{suffix}"
        record["bibtex_key"] = key
        used.add(key)


def bibtex_escape(value: str | None) -> str:
    if not value:
        return ""
    result: list[str] = []
    in_math = False
    previous = ""
    replacements = {"&": r"\&", "%": r"\%", "#": r"\#", "_": r"\_"}
    for character in value:
        if character == "$" and previous != "\\":
            in_math = not in_math
            result.append(character)
        elif not in_math and character in replacements and previous != "\\":
            result.append(replacements[character])
        else:
            result.append(character)
        previous = character
    return re.sub(r"\s+", " ", "".join(result)).strip()


def record_to_bibtex(record: dict[str, Any]) -> str:
    publication_type = str(record.get("publication_type") or "").lower()
    if record.get("journal_title") or publication_type in {"article", "journal article"}:
        entry_type = "article"
    elif publication_type in {"conference paper", "proceedings"}:
        entry_type = "inproceedings"
    elif publication_type == "thesis":
        entry_type = "phdthesis"
    else:
        entry_type = "misc"
    fields: list[tuple[str, str]] = []
    if record.get("authors"):
        fields.append(("author", " and ".join(bibtex_escape(author) for author in record["authors"])))
    if record.get("title"):
        fields.append(("title", "{" + bibtex_escape(record["title"]) + "}"))
    if record.get("journal_title"):
        fields.append(("journal", bibtex_escape(record["journal_title"])))
    for source_key, bib_key in [("volume", "volume"), ("pages", "pages")]:
        if record.get(source_key):
            fields.append((bib_key, bibtex_escape(str(record[source_key]))))
    if record.get("year"):
        fields.append(("year", str(record["year"])))
    if record.get("doi"):
        fields.append(("doi", str(record["doi"])))
    if record.get("arxiv_id"):
        fields.extend(
            [
                ("eprint", str(record["arxiv_id"])),
                ("archivePrefix", "arXiv"),
            ]
        )
        categories = record.get("categories") or []
        if categories:
            fields.append(("primaryClass", str(categories[0])))
    url = (record.get("urls") or {}).get("doi") or (record.get("urls") or {}).get("abstract")
    if url:
        fields.append(("url", str(url)))
    lines = [f"@{entry_type}{{{record['bibtex_key']},"]
    lines.extend(f"  {name} = {{{value}}}," for name, value in fields)
    lines.append("}")
    return "\n".join(lines)


def write_bibtex(path: Path, records: list[dict[str, Any]]) -> None:
    entries = [record_to_bibtex(record) for record in sorted(records, key=lambda item: item["bibtex_key"])]
    atomic_write_text(path, "\n\n".join(entries) + ("\n" if entries else ""))


def parse_arxiv_atom(payload: bytes, query_id: str, retrieved_at: str | None = None) -> tuple[list[dict[str, Any]], int]:
    retrieved_at = retrieved_at or utc_now()
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise PipelineError(f"Invalid arXiv Atom response: {exc}") from exc
    total_text = root.findtext("opensearch:totalResults", default="0", namespaces=ARXIV_NS)
    try:
        total = int(total_text)
    except ValueError:
        total = 0
    records: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", ARXIV_NS):
        record = blank_record()
        raw_id = entry.findtext("atom:id", default="", namespaces=ARXIV_NS)
        arxiv_id, version = normalize_arxiv(raw_id)
        published = entry.findtext("atom:published", default="", namespaces=ARXIV_NS)
        updated = entry.findtext("atom:updated", default="", namespaces=ARXIV_NS)
        doi = normalize_doi(entry.findtext("arxiv:doi", default="", namespaces=ARXIV_NS))
        journal_ref = strip_markup(entry.findtext("arxiv:journal_ref", default="", namespaces=ARXIV_NS))
        links: dict[str, str | None] = {"abstract": raw_id or None, "pdf": None, "doi": None, "inspire": None}
        for link in entry.findall("atom:link", ARXIV_NS):
            href = link.attrib.get("href")
            if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
                links["pdf"] = href
            if link.attrib.get("title") == "doi" and href:
                links["doi"] = href
        if doi and not links["doi"]:
            links["doi"] = f"https://doi.org/{doi}"
        categories = unique_values(
            category.attrib.get("term")
            for category in entry.findall("atom:category", ARXIV_NS)
            if category.attrib.get("term")
        )
        authors = [
            re.sub(r"\s+", " ", name).strip()
            for name in [author.findtext("atom:name", default="", namespaces=ARXIV_NS) for author in entry.findall("atom:author", ARXIV_NS)]
            if name.strip()
        ]
        record.update(
            {
                "title": strip_markup(entry.findtext("atom:title", default="", namespaces=ARXIV_NS)),
                "authors": authors,
                "year": int(published[:4]) if re.match(r"^\d{4}", published) else None,
                "published_date": published[:10] or None,
                "updated_date": updated[:10] or None,
                "abstract": strip_markup(entry.findtext("atom:summary", default="", namespaces=ARXIV_NS)),
                "doi": doi,
                "arxiv_id": arxiv_id,
                "arxiv_version": version,
                "categories": categories,
                "publication_type": "article" if journal_ref or doi else "preprint",
                "publication_status": "published" if journal_ref or doi else "preprint",
                "journal_title": journal_ref,
                "urls": links,
                "source_records": [{"source": "arxiv", "query_id": query_id, "source_id": arxiv_id}],
                "retrieved_at": retrieved_at,
            }
        )
        record["record_id"] = choose_record_id(record)
        records.append(record)
    return records, total


def first_list_value(value: Any) -> Any:
    return value[0] if isinstance(value, list) and value else None


def parse_inspire_json(payload: dict[str, Any], query_id: str, retrieved_at: str | None = None) -> tuple[list[dict[str, Any]], int]:
    retrieved_at = retrieved_at or utc_now()
    hits_container = payload.get("hits") or {}
    hits = hits_container.get("hits") or []
    total_value = hits_container.get("total", 0)
    if isinstance(total_value, dict):
        total_value = total_value.get("value", 0)
    try:
        total = int(total_value)
    except (TypeError, ValueError):
        total = len(hits)
    records: list[dict[str, Any]] = []
    for hit in hits:
        metadata = hit.get("metadata") or {}
        record = blank_record()
        recid = str(hit.get("id") or metadata.get("control_number") or "") or None
        title_value = first_list_value(metadata.get("titles")) or {}
        title = title_value.get("title") if isinstance(title_value, dict) else str(title_value)
        authors = [author.get("full_name") for author in metadata.get("authors") or [] if author.get("full_name")]
        for collaboration in metadata.get("collaborations") or []:
            name = collaboration.get("value") if isinstance(collaboration, dict) else str(collaboration)
            if name and name not in authors:
                authors.append("{" + name + "}")
        arxiv_entry = first_list_value(metadata.get("arxiv_eprints")) or {}
        arxiv_value = arxiv_entry.get("value") if isinstance(arxiv_entry, dict) else None
        arxiv_id, version = normalize_arxiv(arxiv_value)
        doi_entry = first_list_value(metadata.get("dois")) or {}
        doi = normalize_doi(doi_entry.get("value") if isinstance(doi_entry, dict) else None)
        abstract_entry = first_list_value(metadata.get("abstracts")) or {}
        abstract = strip_markup(abstract_entry.get("value") if isinstance(abstract_entry, dict) else None)
        publication = first_list_value(metadata.get("publication_info")) or {}
        earliest = str(metadata.get("earliest_date") or "")
        year = publication.get("year") if isinstance(publication, dict) else None
        if not year and re.match(r"^\d{4}", earliest):
            year = int(earliest[:4])
        document_types = metadata.get("document_type") or []
        publication_type = str(first_list_value(document_types) or "unknown")
        lower_type = publication_type.lower()
        if "review" in lower_type:
            status = "review"
        elif "conference" in lower_type:
            status = "proceedings"
        elif "thesis" in lower_type:
            status = "thesis"
        elif publication or doi:
            status = "published"
        elif arxiv_id:
            status = "preprint"
        else:
            status = "unknown"
        pages = None
        if isinstance(publication, dict):
            pages = publication.get("artid") or publication.get("page_start")
            if publication.get("page_start") and publication.get("page_end"):
                pages = f"{publication['page_start']}--{publication['page_end']}"
        links = hit.get("links") or {}
        urls: dict[str, str | None] = {
            "abstract": f"https://inspirehep.net/literature/{recid}" if recid else None,
            "pdf": None,
            "doi": f"https://doi.org/{doi}" if doi else None,
            "inspire": links.get("self") or (f"https://inspirehep.net/api/literature/{recid}" if recid else None),
        }
        for document in metadata.get("documents") or []:
            if not isinstance(document, dict):
                continue
            candidate = document.get("url") or document.get("fulltext")
            if candidate and (document.get("key") or "").lower().endswith(".pdf"):
                urls["pdf"] = candidate
                break
        if not urls["pdf"] and arxiv_id:
            urls["pdf"] = f"https://arxiv.org/pdf/{arxiv_id}"
        record.update(
            {
                "title": strip_markup(title),
                "authors": authors,
                "year": int(year) if str(year).isdigit() else None,
                "published_date": earliest[:10] or None,
                "updated_date": str(hit.get("updated") or "")[:10] or None,
                "abstract": abstract,
                "doi": doi,
                "arxiv_id": arxiv_id,
                "arxiv_version": version,
                "inspire_recid": recid,
                "categories": unique_values(arxiv_entry.get("categories") or []) if isinstance(arxiv_entry, dict) else [],
                "publication_type": publication_type,
                "publication_status": status,
                "journal_title": publication.get("journal_title") if isinstance(publication, dict) else None,
                "volume": publication.get("journal_volume") if isinstance(publication, dict) else None,
                "pages": pages,
                "citation_count": metadata.get("citation_count"),
                "citation_count_without_self_citations": metadata.get("citation_count_without_self_citations"),
                "inspire_texkeys": metadata.get("texkeys") or [],
                "urls": urls,
                "source_records": [{"source": "inspire", "query_id": query_id, "source_id": recid}],
                "retrieved_at": retrieved_at,
            }
        )
        record["record_id"] = choose_record_id(record)
        records.append(record)
    return records, total


def crossref_date(message: dict[str, Any]) -> tuple[int | None, str | None]:
    for key in ["published-print", "published-online", "published", "issued"]:
        date_parts = ((message.get(key) or {}).get("date-parts") or [])
        if date_parts and date_parts[0]:
            parts = [int(part) for part in date_parts[0]]
            year = parts[0]
            while len(parts) < 3:
                parts.append(1)
            try:
                return year, dt.date(parts[0], parts[1], parts[2]).isoformat()
            except ValueError:
                return year, str(year)
    return None, None


def enrich_from_crossref(record: dict[str, Any], message: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(record)
    year, published_date = crossref_date(message)
    title = first_list_value(message.get("title"))
    authors = []
    for author in message.get("author") or []:
        family = author.get("family") or ""
        given = author.get("given") or ""
        name = f"{family}, {given}".strip(" ,")
        if name:
            authors.append(name)
    candidate = blank_record()
    candidate.update(
        {
            "title": strip_markup(title),
            "authors": authors,
            "year": year,
            "published_date": published_date,
            "abstract": strip_markup(message.get("abstract")),
            "doi": normalize_doi(message.get("DOI")),
            "publication_type": message.get("type") or "article",
            "publication_status": "published",
            "journal_title": first_list_value(message.get("container-title")),
            "volume": message.get("volume"),
            "pages": message.get("page") or message.get("article-number"),
            "urls": {"doi": message.get("URL")},
            "source_records": [{"source": "crossref", "query_id": "doi-enrichment", "source_id": message.get("DOI")}],
            "retrieved_at": utc_now(),
        }
    )
    return merge_records(enriched, candidate)


class ApiClient:
    def __init__(self, cache_root: Path, contact_email: str | None = None) -> None:
        self.cache_root = cache_root
        self.contact_email = contact_email
        self.last_request: dict[str, float] = {}
        self.minimum_delay = {"arxiv": 3.0, "inspire": 0.4, "crossref": 1.0, "fulltext": 1.0}

    def cache_path(self, url: str, source: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        suffix = ".xml" if source == "arxiv" else ".json" if source in {"inspire", "crossref"} else ".bin"
        return self.cache_root / source / f"{digest}{suffix}"

    def get_bytes(
        self,
        url: str,
        source: str,
        *,
        refresh: bool = False,
        offline: bool = False,
    ) -> tuple[bytes, bool, str | None]:
        cache_path = self.cache_path(url, source)
        if cache_path.exists() and (offline or not refresh):
            return cache_path.read_bytes(), True, None
        if offline:
            raise PipelineError(f"Offline cache miss for {source}: {url}")

        headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        if source == "crossref" and self.contact_email:
            headers["User-Agent"] = f"{USER_AGENT} mailto:{self.contact_email}"
        error_message: str | None = None
        for attempt in range(4):
            elapsed = time.monotonic() - self.last_request.get(source, 0.0)
            delay = self.minimum_delay.get(source, 1.0)
            if elapsed < delay:
                time.sleep(delay - elapsed)
            request = urllib.request.Request(url, headers=headers)
            try:
                self.last_request[source] = time.monotonic()
                with urllib.request.urlopen(request, timeout=45) as response:
                    payload = response.read()
                    content_type = response.headers.get_content_type()
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = cache_path.with_name(cache_path.name + ".tmp")
                temporary.write_bytes(payload)
                os.replace(temporary, cache_path)
                return payload, False, content_type
            except urllib.error.HTTPError as exc:
                error_message = f"HTTP {exc.code}: {exc.reason}"
                if exc.code != 429 and not 500 <= exc.code < 600:
                    raise PipelineError(f"Request failed for {url}: {error_message}") from exc
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                wait = max(5.0, float(retry_after)) if retry_after and retry_after.isdigit() else 5.0 * (2**attempt)
                time.sleep(wait)
            except (urllib.error.URLError, TimeoutError) as exc:
                error_message = str(exc)
                time.sleep(2.0 * (2**attempt))
        if cache_path.exists():
            return cache_path.read_bytes(), True, None
        raise PipelineError(f"Request failed after retries for {url}: {error_message}")

    def get_json(self, url: str, source: str, **kwargs: Any) -> tuple[dict[str, Any], bool]:
        payload, cache_used, _ = self.get_bytes(url, source, **kwargs)
        try:
            value = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PipelineError(f"Invalid JSON response from {url}: {exc}") from exc
        if not isinstance(value, dict):
            raise PipelineError(f"Expected a JSON object from {url}")
        return value, cache_used


def arxiv_query_with_date(query: str, protocol: dict[str, Any]) -> str:
    date_range = protocol.get("date_range") or {}
    if date_range.get("mode") != "bounded":
        return query
    start = str(date_range["from"]).replace("-", "") + "0000"
    end = str(date_range["to"]).replace("-", "") + "2359"
    return f"({query}) AND submittedDate:[{start} TO {end}]"


def retrieve_arxiv(
    client: ApiClient,
    query_spec: dict[str, Any],
    protocol: dict[str, Any],
    *,
    refresh: bool,
    offline: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    limit = int((protocol.get("limits") or {}).get("max_results_per_query", 1000))
    query = arxiv_query_with_date(str(query_spec["query"]), protocol)
    records: list[dict[str, Any]] = []
    total = 0
    cache_any = False
    first_url = ""
    page_size = min(100, limit)
    start = 0
    while start < limit:
        params = {
            "search_query": query,
            "start": start,
            "max_results": min(page_size, limit - start),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)
        first_url = first_url or url
        payload, cache_used, _ = client.get_bytes(url, "arxiv", refresh=refresh, offline=offline)
        cache_any = cache_any or cache_used
        page_records, page_total = parse_arxiv_atom(payload, str(query_spec["query_id"]))
        total = max(total, page_total)
        records.extend(page_records)
        if not page_records or len(page_records) < params["max_results"] or len(records) >= total:
            break
        start += len(page_records)
    return records[:limit], {
        "request_url": first_url,
        "result_count": total,
        "retrieved_count": min(len(records), limit),
        "truncated": total > limit,
        "cache_used": cache_any,
    }


def retrieve_inspire(
    client: ApiClient,
    query_spec: dict[str, Any],
    protocol: dict[str, Any],
    *,
    refresh: bool,
    offline: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    limit = int((protocol.get("limits") or {}).get("max_results_per_query", 1000))
    page_size = min(100, limit)
    page = 1
    records: list[dict[str, Any]] = []
    total = 0
    cache_any = False
    first_url = ""
    while len(records) < limit:
        params = {"q": str(query_spec["query"]), "size": min(page_size, limit - len(records)), "page": page}
        url = "https://inspirehep.net/api/literature?" + urllib.parse.urlencode(params)
        first_url = first_url or url
        payload, cache_used = client.get_json(url, "inspire", refresh=refresh, offline=offline)
        cache_any = cache_any or cache_used
        page_records, page_total = parse_inspire_json(payload, str(query_spec["query_id"]))
        total = max(total, page_total)
        records.extend(page_records)
        if not page_records or len(page_records) < params["size"] or len(records) >= total:
            break
        page += 1
    return records[:limit], {
        "request_url": first_url,
        "result_count": total,
        "retrieved_count": min(len(records), limit),
        "truncated": total > limit,
        "cache_used": cache_any,
    }


def enrich_crossref_records(
    client: ApiClient,
    records: list[dict[str, Any]],
    *,
    refresh: bool,
    offline: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    attempted = 0
    succeeded = 0
    cache_any = False
    errors: list[str] = []
    for record in records:
        if not record.get("doi"):
            enriched.append(record)
            continue
        needs_enrichment = not record.get("journal_title") or not record.get("year")
        if not needs_enrichment:
            enriched.append(record)
            continue
        attempted += 1
        encoded = urllib.parse.quote(str(record["doi"]), safe="")
        url = f"https://api.crossref.org/v1/works/{encoded}"
        try:
            payload, cache_used = client.get_json(url, "crossref", refresh=refresh, offline=offline)
            cache_any = cache_any or cache_used
            message = payload.get("message") or {}
            enriched.append(enrich_from_crossref(record, message))
            succeeded += 1
        except PipelineError as exc:
            errors.append(f"{record.get('record_id')}: {exc}")
            enriched.append(record)
    return enriched, {
        "attempted": attempted,
        "succeeded": succeeded,
        "cache_used": cache_any,
        "errors": errors,
    }


def validate_protocol(protocol: dict[str, Any], require_queries: bool = False) -> None:
    required = [
        "research_question",
        "categories",
        "date_range",
        "inclusion_criteria",
        "exclusion_criteria",
        "report_language",
    ]
    missing = [key for key in required if not protocol.get(key)]
    if missing:
        raise PipelineError("Protocol fields are missing or empty: " + ", ".join(missing))
    if protocol.get("report_language") not in LANGUAGES:
        raise PipelineError("protocol.report_language must be zh, en, or bilingual")
    if require_queries:
        queries = [query for query in protocol.get("queries") or [] if query.get("enabled", True)]
        if not queries:
            raise PipelineError("protocol.queries must contain at least one enabled source query")
        for query in queries:
            if query.get("source") not in {"arxiv", "inspire"}:
                raise PipelineError(f"Unsupported query source: {query.get('source')!r}")
            if not query.get("query_id") or not query.get("query"):
                raise PipelineError("Every enabled query requires query_id and query")


def asset_root() -> Path:
    return Path(__file__).resolve().parents[1] / "assets"


def copy_language_assets(review_dir: Path, language: str, *, overwrite_templates: bool = False) -> None:
    assets = asset_root()
    macros_target = review_dir / "review-macros.tex"
    if overwrite_templates or not macros_target.exists():
        shutil.copyfile(assets / "review-macros.tex", macros_target)
    requested = ["zh", "en"] if language == "bilingual" else [language]
    for suffix in requested:
        target = review_dir / f"report_{suffix}.tex"
        if overwrite_templates or not target.exists():
            shutil.copyfile(assets / f"report_{suffix}.tex", target)


def archive_obsolete_outputs(review_dir: Path, language: str) -> list[str]:
    requested = {"zh", "en"} if language == "bilingual" else {language}
    obsolete = [suffix for suffix in ["zh", "en"] if suffix not in requested]
    moved: list[str] = []
    archive_dir = review_dir / "runs" / run_id() / "archived_outputs"
    for suffix in obsolete:
        for extension in ["tex", "pdf", "aux", "bbl", "blg", "log", "out", "toc"]:
            source = review_dir / f"report_{suffix}.{extension}"
            if source.exists():
                archive_dir.mkdir(parents=True, exist_ok=True)
                destination = archive_dir / source.name
                shutil.move(str(source), str(destination))
                moved.append(str(destination.relative_to(review_dir)))
    return moved


def init_review(args: argparse.Namespace) -> int:
    review_dir = Path(args.review_dir).resolve()
    protocol_path = review_dir / "protocol.json"
    if protocol_path.exists():
        raise PipelineError(f"Review already exists: {protocol_path}; use the language or search command")
    language = normalize_language(args.language)
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "fulltext").mkdir(exist_ok=True)
    (review_dir / "generated").mkdir(exist_ok=True)
    (review_dir / "runs").mkdir(exist_ok=True)
    timestamp = utc_now()
    protocol = {
        "schema_version": SCHEMA_VERSION,
        "topic_slug": review_dir.name,
        "research_question": args.question.strip(),
        "categories": unique_values(args.categories),
        "date_range": parse_date_range(args.date_range),
        "inclusion_criteria": args.include,
        "exclusion_criteria": args.exclude,
        "seed_papers": args.seed or [],
        "report_language": language,
        "queries": [],
        "sources": {"arxiv": True, "inspire": True, "crossref": True},
        "limits": {"max_results_per_query": args.max_results},
        "contact_email": args.contact_email,
        "created_at": timestamp,
        "updated_at": timestamp,
        "protocol_history": [],
    }
    validate_protocol(protocol)
    write_json(protocol_path, protocol)
    write_jsonl(review_dir / "records.jsonl", [])
    write_jsonl(review_dir / "search_runs.jsonl", [])
    write_jsonl(review_dir / "fulltext" / "manifest.jsonl", [])
    initialize_csv(review_dir / "screening.csv", SCREENING_HEADER)
    initialize_csv(review_dir / "evidence.csv", EVIDENCE_HEADER)
    atomic_write_text(review_dir / "references.bib", "")
    atomic_write_text(review_dir / "update_summary.md", "# Update Summary\n\nInitial review created.\n")
    copy_language_assets(review_dir, language)
    print(f"Initialized review at {review_dir}")
    print("Add exact arXiv and INSPIRE queries to protocol.json before running search.")
    return 0


def set_language(args: argparse.Namespace) -> int:
    review_dir = Path(args.review_dir).resolve()
    protocol_path = review_dir / "protocol.json"
    protocol = load_json(protocol_path)
    validate_protocol(protocol)
    language = normalize_language(args.language)
    old_language = protocol["report_language"]
    if old_language == language:
        print(f"Report language is already {language}")
        return 0
    moved = archive_obsolete_outputs(review_dir, language)
    copy_language_assets(review_dir, language)
    changed_at = utc_now()
    protocol.setdefault("protocol_history", []).append(
        {
            "changed_at": changed_at,
            "field": "report_language",
            "from": old_language,
            "to": language,
            "reason": args.reason,
        }
    )
    protocol["report_language"] = language
    protocol["updated_at"] = changed_at
    write_json(protocol_path, protocol)
    print(f"Changed report language from {old_language} to {language}")
    if moved:
        print("Archived obsolete outputs: " + ", ".join(moved))
    return 0


def record_fingerprint(record: dict[str, Any]) -> str:
    tracked = {
        key: record.get(key)
        for key in [
            "title",
            "authors",
            "year",
            "doi",
            "arxiv_id",
            "arxiv_version",
            "inspire_recid",
            "publication_status",
            "journal_title",
            "citation_count",
            "citation_count_without_self_citations",
        ]
    }
    return hashlib.sha256(json.dumps(tracked, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def write_update_summary(
    path: Path,
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    failures: list[str],
) -> None:
    before_map = {record["record_id"]: record for record in before}
    after_map = {record["record_id"]: record for record in after}
    added = sorted(set(after_map) - set(before_map))
    changed = sorted(
        record_id
        for record_id in set(after_map) & set(before_map)
        if record_fingerprint(after_map[record_id]) != record_fingerprint(before_map[record_id])
    )
    status_changes = [
        (record_id, before_map[record_id].get("publication_status"), after_map[record_id].get("publication_status"))
        for record_id in changed
        if before_map[record_id].get("publication_status") != after_map[record_id].get("publication_status")
    ]
    lines = [
        "# Update Summary",
        "",
        f"- Updated at: {utc_now()}",
        f"- Records before: {len(before)}",
        f"- Records after: {len(after)}",
        f"- Added records: {len(added)}",
        f"- Metadata changes: {len(changed)}",
        f"- Source failures: {len(failures)}",
        "",
        "## Added records",
        "",
    ]
    lines.extend([f"- `{record_id}` — {after_map[record_id].get('title') or 'Untitled'}" for record_id in added] or ["- None"])
    lines.extend(["", "## Publication-status changes", ""])
    lines.extend(
        [f"- `{record_id}`: `{old}` → `{new}`" for record_id, old, new in status_changes] or ["- None"]
    )
    lines.extend(["", "## Other metadata changes", ""])
    other_changes = [record_id for record_id in changed if record_id not in {item[0] for item in status_changes}]
    lines.extend([f"- `{record_id}`" for record_id in other_changes] or ["- None"])
    lines.extend(["", "## Source failures", ""])
    lines.extend([f"- {failure}" for failure in failures] or ["- None"])
    atomic_write_text(path, "\n".join(lines) + "\n")


def search_review(args: argparse.Namespace) -> int:
    review_dir = Path(args.review_dir).resolve()
    protocol = load_json(review_dir / "protocol.json")
    validate_protocol(protocol, require_queries=True)
    before = read_jsonl(review_dir / "records.jsonl")
    client = ApiClient(review_dir / ".cache" / "api", protocol.get("contact_email"))
    incoming: list[dict[str, Any]] = []
    failures: list[str] = []
    current_run_id = run_id()

    for query_spec in protocol.get("queries") or []:
        if not query_spec.get("enabled", True):
            continue
        source = str(query_spec["source"])
        if not (protocol.get("sources") or {}).get(source, True):
            continue
        started = utc_now()
        log = {
            "run_id": current_run_id,
            "query_id": query_spec["query_id"],
            "source": source,
            "query": query_spec["query"],
            "request_url": None,
            "started_at": started,
            "completed_at": None,
            "result_count": 0,
            "retrieved_count": 0,
            "truncated": False,
            "cache_used": False,
            "status": "failed",
            "error": None,
        }
        try:
            if source == "arxiv":
                records, details = retrieve_arxiv(
                    client, query_spec, protocol, refresh=args.refresh, offline=args.offline
                )
            else:
                records, details = retrieve_inspire(
                    client, query_spec, protocol, refresh=args.refresh, offline=args.offline
                )
            incoming.extend(records)
            log.update(details)
            log["status"] = "partial" if details["truncated"] else "ok"
            if details["truncated"]:
                failures.append(f"{query_spec['query_id']}: result set truncated at the protocol limit")
        except PipelineError as exc:
            log["error"] = str(exc)
            failures.append(f"{query_spec['query_id']}: {exc}")
        log["completed_at"] = utc_now()
        append_jsonl(review_dir / "search_runs.jsonl", log)

    merged = merge_record_sets(before, incoming)
    if (protocol.get("sources") or {}).get("crossref", True):
        merged, crossref_details = enrich_crossref_records(
            client, merged, refresh=args.refresh, offline=args.offline
        )
        if crossref_details["errors"]:
            failures.extend(crossref_details["errors"])
        append_jsonl(
            review_dir / "search_runs.jsonl",
            {
                "run_id": current_run_id,
                "query_id": "crossref-doi-enrichment",
                "source": "crossref",
                "query": "DOI metadata enrichment",
                "request_url": "https://api.crossref.org/v1/works/<doi>",
                "started_at": utc_now(),
                "completed_at": utc_now(),
                "result_count": crossref_details["attempted"],
                "retrieved_count": crossref_details["succeeded"],
                "truncated": False,
                "cache_used": crossref_details["cache_used"],
                "status": "partial" if crossref_details["errors"] else "ok",
                "error": "; ".join(crossref_details["errors"][:5]) or None,
            },
        )
    assign_bibtex_keys(merged)
    merged.sort(key=lambda record: (record.get("year") or 0, record.get("title") or "", record["record_id"]))
    write_jsonl(review_dir / "records.jsonl", merged)
    write_bibtex(review_dir / "references.bib", merged)
    write_update_summary(review_dir / "update_summary.md", before, merged, failures)
    protocol["updated_at"] = utc_now()
    write_json(review_dir / "protocol.json", protocol)
    print(f"Stored {len(merged)} canonical records ({len(merged) - len(before):+d} net new)")
    if failures:
        print(f"Completed with {len(failures)} partial or failed operations", file=sys.stderr)
        return 2
    return 0


def current_screening_decisions(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    current: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        current[(row.get("record_id", ""), row.get("stage", ""))] = row
    return current


def download_fulltext(args: argparse.Namespace) -> int:
    review_dir = Path(args.review_dir).resolve()
    protocol = load_json(review_dir / "protocol.json")
    validate_protocol(protocol)
    records = read_jsonl(review_dir / "records.jsonl")
    decisions = current_screening_decisions(read_csv(review_dir / "screening.csv"))
    candidates: list[dict[str, Any]] = []
    for record in records:
        record_id = record["record_id"]
        full_text = decisions.get((record_id, "full_text"))
        title_abstract = decisions.get((record_id, "title_abstract"))
        decision = (full_text or title_abstract or {}).get("decision")
        if decision in {"include", "uncertain"}:
            candidates.append(record)
    if not candidates:
        print("No include or uncertain screening candidates require full-text retrieval")
        return 0

    client = ApiClient(review_dir / ".cache" / "api", protocol.get("contact_email"))
    fulltext_dir = review_dir / "fulltext"
    fulltext_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = fulltext_dir / "manifest.jsonl"
    failures = 0
    updated_records: list[dict[str, Any]] = []
    candidate_ids = {record["record_id"] for record in candidates}
    for record in records:
        if record["record_id"] not in candidate_ids:
            updated_records.append(record)
            continue
        url = (record.get("urls") or {}).get("pdf")
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", record["record_id"]) + ".pdf"
        target = fulltext_dir / safe_name
        entry = {
            "record_id": record["record_id"],
            "url": url,
            "status": "failed",
            "path": None,
            "sha256": None,
            "content_type": None,
            "retrieved_at": utc_now(),
            "error": None,
        }
        if target.exists() and target.read_bytes()[:4] == b"%PDF" and not args.refresh:
            payload = target.read_bytes()
            entry.update(
                {
                    "status": "cached",
                    "path": str(target.relative_to(review_dir)),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "content_type": "application/pdf",
                }
            )
        elif not url:
            entry.update({"status": "unavailable", "error": "No lawful PDF URL is recorded"})
            failures += 1
        else:
            try:
                source = "arxiv" if "arxiv.org" in urllib.parse.urlparse(url).netloc else "fulltext"
                payload, cache_used, content_type = client.get_bytes(
                    url, source, refresh=args.refresh, offline=args.offline
                )
                if payload[:4] != b"%PDF":
                    raise PipelineError(f"The retrieved content is not a PDF ({content_type or 'unknown type'})")
                target.write_bytes(payload)
                entry.update(
                    {
                        "status": "cached" if cache_used else "downloaded",
                        "path": str(target.relative_to(review_dir)),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "content_type": content_type or "application/pdf",
                    }
                )
            except PipelineError as exc:
                entry["error"] = str(exc)
                failures += 1
        append_jsonl(manifest_path, entry)
        updated = dict(record)
        updated["fulltext"] = {
            key: entry[key] for key in ["status", "path", "url", "sha256", "retrieved_at"]
        }
        updated_records.append(updated)

    write_jsonl(review_dir / "records.jsonl", updated_records)
    print(f"Processed {len(candidates)} full-text candidates with {failures} unavailable or failed")
    return 2 if failures else 0


def tex_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in text)


def current_included_ids(review_dir: Path) -> set[str]:
    decisions = current_screening_decisions(read_csv(review_dir / "screening.csv"))
    return {
        record_id
        for (record_id, stage), row in decisions.items()
        if stage == "full_text" and row.get("decision") == "include"
    }


def render_search_summary(logs: list[dict[str, Any]], language: str) -> str:
    headers = ["Query", "Source", "Results", "Retrieved", "Status"]
    if language == "zh":
        headers = ["查询编号", "来源", "结果数", "获取数", "状态"]
    lines = [
        r"\begin{longtable}{@{}p{0.24\textwidth}p{0.12\textwidth}rrp{0.18\textwidth}@{}}",
        r"\toprule",
        " & ".join(headers) + r" \\",
        r"\midrule",
        r"\endfirsthead",
        r"\toprule",
        " & ".join(headers) + r" \\",
        r"\midrule",
        r"\endhead",
    ]
    for log in logs:
        row = [
            tex_escape(log.get("query_id")),
            tex_escape(log.get("source")),
            str(log.get("result_count", 0)),
            str(log.get("retrieved_count", 0)),
            tex_escape(log.get("status")),
        ]
        lines.append(" & ".join(row) + r" \\")
    lines.extend([r"\bottomrule", r"\end{longtable}"])
    return "\n".join(lines) + "\n"


def render_selection_flow(counts: dict[str, int], language: str) -> str:
    labels = {
        "identified": "Records identified",
        "screened": "Title/abstract screened",
        "fulltext": "Full text assessed",
        "included": "Works included",
    }
    if language == "zh":
        labels = {
            "identified": "检索与扩展所得记录",
            "screened": "标题与摘要筛选",
            "fulltext": "全文评估",
            "included": "最终纳入文献",
        }
    return "\n".join(
        [
            r"\begin{center}",
            r"\begin{tikzpicture}[node distance=9mm, every node/.style={font=\small}, box/.style={draw=ReviewBlue, rounded corners, fill=ReviewLight, minimum width=8cm, minimum height=10mm, align=center}, arrow/.style={-{Latex[length=2.5mm]}, thick, ReviewBlue}]",
            rf"\node[box] (identified) {{{tex_escape(labels['identified'])}: {counts['identified']}}};",
            rf"\node[box, below=of identified] (screened) {{{tex_escape(labels['screened'])}: {counts['screened']}}};",
            rf"\node[box, below=of screened] (fulltext) {{{tex_escape(labels['fulltext'])}: {counts['fulltext']}}};",
            rf"\node[box, below=of fulltext] (included) {{{tex_escape(labels['included'])}: {counts['included']}}};",
            r"\draw[arrow] (identified) -- (screened);",
            r"\draw[arrow] (screened) -- (fulltext);",
            r"\draw[arrow] (fulltext) -- (included);",
            r"\end{tikzpicture}",
            r"\end{center}",
            "",
        ]
    )


def render_included_table(records: list[dict[str, Any]], included_ids: set[str], language: str) -> str:
    headers = ["Citation key", "Year", "Status", "Title"]
    if language == "zh":
        headers = ["引用键", "年份", "状态", "题目"]
    lines = [
        r"\begin{longtable}{@{}p{0.20\textwidth}p{0.08\textwidth}p{0.13\textwidth}p{0.50\textwidth}@{}}",
        r"\toprule",
        " & ".join(headers) + r" \\",
        r"\midrule",
        r"\endfirsthead",
        r"\toprule",
        " & ".join(headers) + r" \\",
        r"\midrule",
        r"\endhead",
    ]
    for record in records:
        if record["record_id"] not in included_ids:
            continue
        row = [
            tex_escape(record.get("bibtex_key")),
            tex_escape(record.get("year")),
            tex_escape(record.get("publication_status")),
            tex_escape(record.get("title")),
        ]
        lines.append(" & ".join(row) + r" \\")
    lines.extend([r"\bottomrule", r"\end{longtable}"])
    return "\n".join(lines) + "\n"


def render_audit_tex(args: argparse.Namespace) -> int:
    review_dir = Path(args.review_dir).resolve()
    protocol = load_json(review_dir / "protocol.json")
    validate_protocol(protocol)
    records = read_jsonl(review_dir / "records.jsonl")
    logs = read_jsonl(review_dir / "search_runs.jsonl")
    screening = read_csv(review_dir / "screening.csv")
    decisions = current_screening_decisions(screening)
    included_ids = current_included_ids(review_dir)
    counts = {
        "identified": len(records),
        "screened": len({record_id for (record_id, stage) in decisions if stage == "title_abstract"}),
        "fulltext": len({record_id for (record_id, stage) in decisions if stage == "full_text"}),
        "included": len(included_ids),
    }
    generated = review_dir / "generated"
    generated.mkdir(exist_ok=True)
    languages = ["zh", "en"] if protocol["report_language"] == "bilingual" else [protocol["report_language"]]
    for language in languages:
        atomic_write_text(generated / f"search-summary-{language}.tex", render_search_summary(logs, language))
        atomic_write_text(generated / f"selection-flow-{language}.tex", render_selection_flow(counts, language))
        atomic_write_text(
            generated / f"included-studies-{language}.tex",
            render_included_table(records, included_ids, language),
        )
    print(f"Generated optional audit fragments for {', '.join(languages)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize an auditable review directory")
    init_parser.add_argument("review_dir")
    init_parser.add_argument("--question", required=True)
    init_parser.add_argument("--categories", nargs="+", required=True)
    init_parser.add_argument("--date-range", required=True)
    init_parser.add_argument("--include", action="append", required=True)
    init_parser.add_argument("--exclude", action="append", required=True)
    init_parser.add_argument("--language", default="bilingual")
    init_parser.add_argument("--seed", action="append")
    init_parser.add_argument("--max-results", type=int, default=1000)
    init_parser.add_argument("--contact-email")
    init_parser.set_defaults(handler=init_review)

    language_parser = subparsers.add_parser("language", help="Change and normalize report language")
    language_parser.add_argument("review_dir")
    language_parser.add_argument("language")
    language_parser.add_argument("--reason", default="User requested a report-language change")
    language_parser.set_defaults(handler=set_language)

    search_parser = subparsers.add_parser("search", help="Run frozen arXiv and INSPIRE queries")
    search_parser.add_argument("review_dir")
    search_parser.add_argument("--refresh", action="store_true")
    search_parser.add_argument("--offline", action="store_true")
    search_parser.set_defaults(handler=search_review)

    download_parser = subparsers.add_parser("download", help="Retrieve lawful candidate full text")
    download_parser.add_argument("review_dir")
    download_parser.add_argument("--refresh", action="store_true")
    download_parser.add_argument("--offline", action="store_true")
    download_parser.set_defaults(handler=download_fulltext)

    audit_tex_parser = subparsers.add_parser("render-audit", help="Generate optional LaTeX audit fragments")
    audit_tex_parser.add_argument("review_dir")
    audit_tex_parser.set_defaults(handler=render_audit_tex)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (PipelineError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

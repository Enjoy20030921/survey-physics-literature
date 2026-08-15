#!/usr/bin/env python3
"""Offline unit tests for the survey-physics-literature scripts."""

from __future__ import annotations

import argparse
import csv
import io
import json
import tempfile
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from unittest import mock

import audit_review
import literature_pipeline as lp


ARXIV_FIXTURE = b"""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns='http://www.w3.org/2005/Atom'
      xmlns:opensearch='http://a9.com/-/spec/opensearch/1.1/'
      xmlns:arxiv='http://arxiv.org/schemas/atom'>
  <opensearch:totalResults>1</opensearch:totalResults>
  <entry>
    <id>https://arxiv.org/abs/1911.12333v2</id>
    <updated>2020-01-02T00:00:00Z</updated>
    <published>2019-11-27T00:00:00Z</published>
    <title>Replica Wormholes &amp; the Black Hole Interior</title>
    <summary>  A test abstract with   whitespace. </summary>
    <author><name>Doe, Jane</name></author>
    <arxiv:doi>10.1000/TEST.DOI</arxiv:doi>
    <arxiv:primary_category term='hep-th'/>
    <category term='hep-th'/><category term='gr-qc'/>
    <link href='https://arxiv.org/abs/1911.12333v2' rel='alternate' type='text/html'/>
    <link title='pdf' href='https://arxiv.org/pdf/1911.12333v2' rel='related' type='application/pdf'/>
  </entry>
</feed>"""

INSPIRE_FIXTURE = {
    "hits": {
        "total": 1,
        "hits": [
            {
                "id": "999",
                "updated": "2021-01-01T00:00:00Z",
                "links": {"self": "https://inspirehep.net/api/literature/999"},
                "metadata": {
                    "titles": [{"title": "Replica Wormholes and the Black Hole Interior"}],
                    "authors": [{"full_name": "Doe, Jane"}],
                    "arxiv_eprints": [{"value": "1911.12333", "categories": ["hep-th", "gr-qc"]}],
                    "dois": [{"value": "https://doi.org/10.1000/test.doi"}],
                    "abstracts": [{"value": "<p>A longer test abstract.</p>"}],
                    "earliest_date": "2019-11-27",
                    "document_type": ["article"],
                    "publication_info": [{"year": 2020, "journal_title": "Test Journal", "journal_volume": "1", "artid": "1"}],
                    "citation_count": 12,
                    "citation_count_without_self_citations": 10,
                    "texkeys": ["Doe:2019abc"],
                },
            }
        ],
    }
}


class LanguageTests(unittest.TestCase):
    def test_language_aliases(self) -> None:
        expected = {
            "中文": "zh",
            "Chinese": "zh",
            "英文": "en",
            "English": "en",
            "中英双语": "bilingual",
            "bilingual": "bilingual",
        }
        for value, normalized in expected.items():
            with self.subTest(value=value):
                self.assertEqual(lp.normalize_language(value), normalized)

    def test_invalid_language(self) -> None:
        with self.assertRaises(lp.PipelineError):
            lp.normalize_language("Esperanto")


class ParserAndMergeTests(unittest.TestCase):
    def test_arxiv_parser(self) -> None:
        records, total = lp.parse_arxiv_atom(ARXIV_FIXTURE, "q1", "2026-01-01T00:00:00Z")
        self.assertEqual(total, 1)
        self.assertEqual(records[0]["arxiv_id"], "1911.12333")
        self.assertEqual(records[0]["arxiv_version"], "v2")
        self.assertEqual(records[0]["doi"], "10.1000/test.doi")
        self.assertEqual(records[0]["categories"], ["hep-th", "gr-qc"])

    def test_inspire_parser_and_deduplication(self) -> None:
        arxiv_records, _ = lp.parse_arxiv_atom(ARXIV_FIXTURE, "q1")
        inspire_records, total = lp.parse_inspire_json(INSPIRE_FIXTURE, "q2")
        self.assertEqual(total, 1)
        merged = lp.merge_record_sets([], arxiv_records + inspire_records)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["inspire_recid"], "999")
        self.assertEqual(merged[0]["journal_title"], "Test Journal")
        lp.assign_bibtex_keys(merged)
        self.assertEqual(merged[0]["bibtex_key"], "Doe:2019abc")

    def test_old_arxiv_identifier(self) -> None:
        identifier, version = lp.normalize_arxiv("https://arxiv.org/abs/hep-th/9901001v3")
        self.assertEqual(identifier, "hep-th/9901001")
        self.assertEqual(version, "v3")

    def test_bibtex_escapes_text_but_preserves_math(self) -> None:
        value = lp.bibtex_escape("A & B with $x_i$ and 10%")
        self.assertEqual(value, r"A \& B with $x_i$ and 10\%")


class FakeResponse:
    def __init__(self, payload: bytes, content_type: str = "application/octet-stream") -> None:
        self.buffer = io.BytesIO(payload)
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> bool:
        return False

    def read(self) -> bytes:
        return self.buffer.read()


class ApiClientTests(unittest.TestCase):
    def test_offline_cache_hit_and_miss(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            client = lp.ApiClient(Path(temporary) / "cache")
            url = "https://example.invalid/arxiv"
            cache_path = client.cache_path(url, "arxiv")
            cache_path.parent.mkdir(parents=True)
            cache_path.write_bytes(ARXIV_FIXTURE)
            payload, cache_used, _ = client.get_bytes(url, "arxiv", offline=True)
            self.assertEqual(payload, ARXIV_FIXTURE)
            self.assertTrue(cache_used)
            with self.assertRaises(lp.PipelineError):
                client.get_bytes("https://example.invalid/missing", "arxiv", offline=True)

    def test_http_429_is_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            client = lp.ApiClient(Path(temporary) / "cache")
            url = "https://example.invalid/retry"
            rate_limit = urllib.error.HTTPError(url, 429, "Too Many Requests", Message(), None)
            success = FakeResponse(b"ok", "text/plain")
            with mock.patch("literature_pipeline.urllib.request.urlopen", side_effect=[rate_limit, success]), mock.patch(
                "literature_pipeline.time.sleep"
            ):
                payload, cache_used, content_type = client.get_bytes(url, "fulltext", refresh=True)
            self.assertEqual(payload, b"ok")
            self.assertFalse(cache_used)
            self.assertEqual(content_type, "text/plain")


class ReviewDirectoryTests(unittest.TestCase):
    def make_args(self, review_dir: Path, language: str) -> argparse.Namespace:
        return argparse.Namespace(
            review_dir=str(review_dir),
            question="Test research question?",
            categories=["hep-th", "gr-qc"],
            date_range="all-time",
            include=["Directly addresses the question"],
            exclude=["No substantive result"],
            language=language,
            seed=None,
            max_results=10,
            contact_email=None,
        )

    def test_conditional_outputs_and_archival(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            review_dir = Path(temporary) / "review"
            self.assertEqual(lp.init_review(self.make_args(review_dir, "中文")), 0)
            self.assertTrue((review_dir / "report_zh.tex").exists())
            self.assertFalse((review_dir / "report_en.tex").exists())
            args = argparse.Namespace(review_dir=str(review_dir), language="English", reason="test")
            self.assertEqual(lp.set_language(args), 0)
            self.assertTrue((review_dir / "report_en.tex").exists())
            self.assertFalse((review_dir / "report_zh.tex").exists())
            archived = list((review_dir / "runs").glob("*/archived_outputs/report_zh.tex"))
            self.assertEqual(len(archived), 1)

    def test_audit_detects_unknown_evidence_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            review_dir = Path(temporary) / "review"
            lp.init_review(self.make_args(review_dir, "en"))
            with (review_dir / "evidence.csv").open("a", encoding="utf-8-sig", newline="") as handle:
                csv.writer(handle).writerow(
                    ["C001", "missing", "Claim", "analytic", "supports", "Sec. 2", "", "", "high", lp.utc_now()]
                )
            errors, _ = audit_review.audit_review(review_dir, False, False)
            self.assertTrue(any("unknown record" in error for error in errors))


class TriggerMetadataTests(unittest.TestCase):
    def test_frontmatter_contains_bilingual_triggers_and_negative_scope(self) -> None:
        skill_path = Path(__file__).resolve().parents[1] / "SKILL.md"
        text = skill_path.read_text(encoding="utf-8")
        for phrase in ["literature review", "citation expansion", "物理文献调研", "系统性综述", "从种子论文扩展"]:
            self.assertIn(phrase, text)
        self.assertIn("Do not use for isolated physics calculations", text)

    def test_report_templates_do_not_prescribe_chapters(self) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        for template_name in ["report_zh.tex", "report_en.tex"]:
            text = (skill_root / "assets" / template_name).read_text(encoding="utf-8")
            self.assertNotIn(r"\chapter{", text)
            self.assertNotIn(r"\appendix", text)
            self.assertIn("REVIEW_BODY_START", text)
            self.assertIn("REVIEW_BODY_END", text)

        reporting = (skill_root / "references" / "reporting.md").read_text(encoding="utf-8")
        self.assertNotIn("## Required report structure", reporting)
        self.assertIn("## Adaptive report architecture", reporting)


if __name__ == "__main__":
    unittest.main(verbosity=2)

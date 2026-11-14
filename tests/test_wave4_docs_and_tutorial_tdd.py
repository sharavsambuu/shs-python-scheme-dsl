"""Locked Frontier TDD suite for Wave 4 (D-01..D-03): README, existing tutorials, and Ch.29-30."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TUTORIAL = ROOT / "docs" / "lisp_tutorial"


def test_d01_readme_documents_new_srfis_and_plugin_cli() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for token in ("125", "132", "64", "180", "28", "152", "--plugin", "SHS_PLUGINS"):
        assert token in text, f"README.md must document {token}"


def test_d02_existing_tutorial_chapters_updated() -> None:
    ch13 = (TUTORIAL / "13-dictionaries-alists-and-hash-tables.md").read_text(encoding="utf-8")
    for token in ("srfi 125", "hash-table-contains?", "hash-table-size", "alist->hash-table"):
        assert token in ch13, f"Chapter 13 must document {token}"

    ch28 = (TUTORIAL / "28-embedding-in-python.md").read_text(encoding="utf-8")
    for token in ("--plugin", "SHS_PLUGINS", "format_traceback", "measure_calls"):
        assert token in ch28, f"Chapter 28 must document {token}"


def test_d03_new_tutorial_chapters_29_and_30_and_links() -> None:
    ch29 = TUTORIAL / "29-sorting-json-and-formatting.md"
    ch30 = TUTORIAL / "30-testing-and-debugging-srfi-64.md"
    assert ch29.is_file(), "Missing Chapter 29: 29-sorting-json-and-formatting.md"
    assert ch30.is_file(), "Missing Chapter 30: 30-testing-and-debugging-srfi-64.md"

    t29 = ch29.read_text(encoding="utf-8")
    for token in ("srfi 132", "list-sort", "srfi 180", "json-read", "json-write", "srfi 28", "format", "srfi 152", "string-split"):
        assert token in t29, f"Chapter 29 must cover {token}"

    t30 = ch30.read_text(encoding="utf-8")
    for token in ("srfi 64", "test-begin", "test-equal", "test-error", "format_traceback", "measure_calls"):
        assert token in t30, f"Chapter 30 must cover {token}"

    tut_readme = (TUTORIAL / "README.md").read_text(encoding="utf-8")
    assert "29-sorting-json-and-formatting.md" in tut_readme
    assert "30-testing-and-debugging-srfi-64.md" in tut_readme

    appendix_a = (TUTORIAL / "appendix-a-reference.md").read_text(encoding="utf-8")
    for token in ("srfi 125", "srfi 132", "srfi 64", "srfi 180", "srfi 28", "srfi 152"):
        assert token in appendix_a, f"appendix-a-reference.md must list {token}"

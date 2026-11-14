"""Locked Frontier TDD suite for Wave 5 (D-04..D-06): practical_tutorial, quant_stuffs, and capabilities."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRACTICAL = ROOT / "docs" / "practical_tutorial"
QUANT = ROOT / "docs" / "quant_stuffs" / "README.md"
CAPABILITIES = ROOT / "docs" / "capabilities.md"


def test_d04_practical_tutorial_updated_for_new_runtime_and_srfi64() -> None:
    readme = (PRACTICAL / "README.md").read_text(encoding="utf-8")
    assert "28 chapters" not in readme, "practical_tutorial/README.md still says 28 chapters"
    assert "no profiler" not in readme.lower(), "practical_tutorial/README.md still claims there is no profiler"
    assert "measure_calls" in readme

    p1 = (PRACTICAL / "p1-when-things-go-wrong.md").read_text(encoding="utf-8")
    assert "format_traceback" in p1

    p4 = (PRACTICAL / "p4-features-and-the-walls.md").read_text(encoding="utf-8")
    assert "no profiler" not in p4.lower(), "p4-features-and-the-walls.md still claims there is no profiler"
    assert "measure_calls" in p4

    p5 = (PRACTICAL / "p5-shipping-an-extension.md").read_text(encoding="utf-8")
    for token in ("--plugin", "SHS_PLUGINS"):
        assert token in p5, f"p5-shipping-an-extension.md must document {token}"

    p6 = (PRACTICAL / "p6-testing-lisp-from-the-host.md").read_text(encoding="utf-8")
    for token in ("srfi 64", "test-begin", "test-equal", "test-end"):
        assert token in p6, f"p6-testing-lisp-from-the-host.md must document {token}"


def test_d05_quant_stuffs_updated_for_r01_r03_and_s14_s18() -> None:
    text = QUANT.read_text(encoding="utf-8")
    assert "(the S14 candidate)" not in text, "quant_stuffs §17 still calls S14 an unbuilt candidate"
    for token in (
        "--plugin",
        "SHS_PLUGINS",
        "format_traceback",
        "measure_calls",
        "srfi 125",
        "srfi 132",
        "srfi 64",
        "srfi 180",
        "srfi 28",
    ):
        assert token in text, f"docs/quant_stuffs/README.md must cover {token}"


def test_d06_capabilities_documents_plugin_cli() -> None:
    text = CAPABILITIES.read_text(encoding="utf-8")
    for token in ("--plugin", "SHS_PLUGINS"):
        assert token in text, f"docs/capabilities.md must document {token}"

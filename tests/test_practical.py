"""``docs/practical_tutorial/`` under the same contract as the main tutorial.

The handbook's own ledger (`docs/practical_tutorial/README.md`) makes a
promise: a chapter lands only when its examples ship machine-checked. This
file is that promise, kept. It reuses the main tutorial harness's
block-parsing and output contract (`tests/test_tutorial.py`) — one definition
of an executable example, two tracks — and adds the checks the handbook's
gates name: links resolve, examples run and match their ``text`` blocks, every
chapter states its metadata and carries a Try it and an exercise, and no
chapter is orphaned from the index.

One difference from the main tutorial: examples run with ``script_args=[]``,
so a chapter can show ``*command-line-args*`` exactly as ``shs run script.scm``
with no arguments binds it.
"""
from __future__ import annotations

import io
import pathlib
import re

import pytest

from test_docs import _LINK, _PATH_REF, _basenames
from test_tutorial import _executable_blocks, _normalise
from shslisp.__main__ import run_script

#: ``shs-python-scheme-dsl/``.
ROOT = pathlib.Path(__file__).resolve().parents[1]
#: ``docs/practical_tutorial/``.
HANDBOOK = ROOT / "docs" / "practical_tutorial"


def _pages() -> list[pathlib.Path]:
    return sorted(HANDBOOK.glob("*.md"))


def _chapters() -> list[pathlib.Path]:
    """The teaching pages (``p0-…``), not the index."""
    return [p for p in _pages() if re.match(r"^p\d", p.name)]


@pytest.mark.parametrize("path", _pages(), ids=lambda p: p.stem)
def test_every_local_link_resolves(path: pathlib.Path) -> None:
    """A link to a moved page is a dead end mid-lesson."""
    broken = []
    for target in _LINK.findall(path.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        target = target.split("#", 1)[0]
        if not target:
            continue
        if not (path.parent / target).resolve().exists():
            broken.append(target)
    assert not broken, f"{path.name} links to files that do not exist: {broken}"


@pytest.mark.parametrize("path", _pages(), ids=lambda p: p.stem)
def test_referenced_paths_exist(path: pathlib.Path) -> None:
    """A ``dir/file.ext`` in backticks must point at a real file."""
    roots = (path.parent, ROOT, ROOT / "examples", ROOT / "docs")
    by_basename = _basenames()
    missing = []
    for ref in sorted(set(_PATH_REF.findall(path.read_text(encoding="utf-8")))):
        if any((root / ref).exists() for root in roots):
            continue
        if "/" not in ref and ref in by_basename:
            continue
        missing.append(ref)
    assert not missing, f"{path.name} references files that do not exist: {missing}"


@pytest.mark.parametrize("path", _chapters(), ids=lambda p: p.stem)
def test_every_executable_example_runs(
    path: pathlib.Path, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``Try it`` block must run — and print what the page says it prints."""
    monkeypatch.chdir(ROOT)
    offenders: list[str] = []
    ran = 0
    for line, source, expected, _tetris in _executable_blocks(path):
        script = tmp_path / f"{path.stem}-{line}.scm"
        script.write_text(source, encoding="utf-8")
        buffer = io.StringIO()
        try:
            run_script(str(script), out=buffer, script_args=[])
            printed = buffer.getvalue()
        except BaseException as error:  # noqa: BLE001 — a page can raise anything
            offenders.append(
                f"line {line}: {type(error).__name__}: {error} "
                f"(a reader who pastes this gets an error)"
            )
            continue
        ran += 1
        if expected is None:
            offenders.append(
                f"line {line}: no ```text block follows this example — a "
                f"reader who pastes it is owed the output they should see"
            )
        elif _normalise(printed) != _normalise(expected):
            offenders.append(
                f"line {line}: the page shows:\n"
                f"      {_normalise(expected)!r}\n"
                f"    but the program prints:\n"
                f"      {_normalise(printed)!r}"
            )
    assert not offenders, (
        f"{path.name} has examples that do not hold:\n  " + "\n  ".join(offenders)
    )
    assert ran >= 1, (
        f"{path.name} has no executable ``Try it`` example. The handbook's "
        f"gates require every chapter to let the reader paste a program and "
        f"watch it work."
    )


@pytest.mark.parametrize("path", _chapters(), ids=lambda p: p.stem)
def test_every_chapter_carries_its_contract(path: pathlib.Path) -> None:
    """Metadata, a Try it, and exercises — the handbook's own gates."""
    text = path.read_text(encoding="utf-8")
    for marker in ("**Before this:**", "**Time:**", "**After this you can:**"):
        assert marker in text, f"{path.name} is missing the {marker!r} line"
    assert re.search(r"^##\s+Try it", text, re.MULTILINE), (
        f"{path.name} has no ``## Try it`` section"
    )
    assert re.search(r"^##\s+Exercise", text, re.MULTILINE), (
        f"{path.name} has no ``## Exercises`` section"
    )


def test_every_chapter_is_indexed() -> None:
    """No chapter may be orphaned; the index is the map."""
    index = (HANDBOOK / "README.md").read_text(encoding="utf-8")
    unlisted = [p.name for p in _chapters() if p.name not in index]
    assert not unlisted, f"these chapters are not linked from the handbook index: {unlisted}"


def test_the_number_of_executable_examples_is_not_drifting() -> None:
    """A floor, so a chapter losing its runnable example is a visible number."""
    executable = sum(1 for path in _pages() for _ in _executable_blocks(path))
    assert executable >= 7, (
        f"only {executable} executable examples remain in the handbook; one "
        f"per chapter is the contract, so this number should never fall"
    )

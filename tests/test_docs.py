"""The top-level documentation, held to the same standard as the tutorial.

``tests/test_tutorial.py`` guards ``docs/lisp_tutorial/`` — every link, every
referenced file, every cited test. The top-level pages (``README.md`` and the
``docs/*.md`` matrices) had no such guard, and it cost the project: three of
them cite task ledgers (``docs/R7RS_TASKS.md``, ``docs/SRFI_TASKS.md``) that
were never committed, and the full suite stayed green while the documents
pointed at files that did not exist. This file is the machine that catches
that class of drift.

Three checks, each of which can catch a real rot:

1. **Every local markdown link resolves.** The pages link to each other, to
   the tutorial, and to the tests; a rename breaks prose silently, and a
   broken link is a dead end for a reader.
2. **Every backticked path exists.** A `` `lisp/builtins.py` `` in prose must
   point at a file that exists somewhere real — pages name files from the
   reader's point of view, so several roots are tried.
3. **Every cited test file exists.** The matrices measure themselves against
   ``tests/test_*.py``; a rename would make the citation a lie.

What this deliberately does *not* check: whether the prose is *right*. The
matrices are the checkable truth and the tests are the final word; this file
only keeps the documents pointing at things that exist.

Scope: ``README.md`` and ``docs/*.md``. ``docs/lisp_tutorial/`` is the tutorial
harness's job, and its checks are stricter there (it runs the examples).
"""
from __future__ import annotations

import pathlib
import re
from functools import lru_cache

import pytest

#: ``shs-python-scheme-dsl/`` — the pages are written from inside it.
ROOT = pathlib.Path(__file__).resolve().parents[1]

#: A fenced ``[label](target)`` markdown link.
_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")

#: A ``path/to/file.ext`` or ``path/to/file.ext:12`` in backticks.
_PATH_REF = re.compile(
    r"`([A-Za-z0-9_./-]+\.(?:py|md|scm|toml|txt|json|ini|cfg|yml|yaml))(?::\d+)?`"
)

#: A ``test_snake_case.py`` (or ``tests/test_snake_case.py``) cited in prose.
_TEST_FILE_REF = re.compile(r"`((?:tests/)?test_[a-z0-9_]+\.py)`")


def _pages() -> list[pathlib.Path]:
    """The guarded pages: the README and every top-level doc."""
    return [ROOT / "README.md"] + sorted((ROOT / "docs").glob("*.md"))


@lru_cache(maxsize=1)
def _basenames() -> frozenset[str]:
    """Every file name in the repository, read once."""
    return frozenset(
        candidate.name
        for candidate in ROOT.rglob("*")
        if candidate.is_file() and "__pycache__" not in candidate.parts
    )


@pytest.mark.parametrize("path", _pages(), ids=lambda p: str(p.relative_to(ROOT)))
def test_every_local_link_resolves(path: pathlib.Path) -> None:
    """A markdown link to a file that moved is a dead end mid-claim."""
    broken = []
    for target in _LINK.findall(path.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        target = target.split("#", 1)[0]
        if not target:
            continue
        if not (path.parent / target).resolve().exists():
            broken.append(target)
    assert not broken, f"{path.relative_to(ROOT)} links to files that do not exist: {broken}"


@pytest.mark.parametrize("path", _pages(), ids=lambda p: str(p.relative_to(ROOT)))
def test_referenced_paths_exist(path: pathlib.Path) -> None:
    """A `` `dir/file.ext` `` must point at a file that exists somewhere real.

    Roots are tried from the reader's point of view — the page's own
    directory, the project root, and the directories the pages actually talk
    about — and a bare filename is accepted if it exists anywhere in the
    repository, because the pages name files both ways on purpose.
    """
    roots = (
        path.parent,
        ROOT,
        ROOT / "docs",
        ROOT / "docs" / "lisp_tutorial",
        ROOT / "lisp",
        ROOT / "tests",
        ROOT / "examples",
    )
    by_basename = _basenames()
    missing = []
    for ref in sorted(set(_PATH_REF.findall(path.read_text(encoding="utf-8")))):
        if any((root / ref).exists() for root in roots):
            continue
        if "/" not in ref and ref in by_basename:
            continue
        missing.append(ref)
    assert not missing, (
        f"{path.relative_to(ROOT)} references files that do not exist: {missing}"
    )


@pytest.mark.parametrize("path", _pages(), ids=lambda p: str(p.relative_to(ROOT)))
def test_referenced_test_files_exist(path: pathlib.Path) -> None:
    """A cited ``test_*.py`` must be a real file in this suite."""
    missing = []
    for ref in sorted(set(_TEST_FILE_REF.findall(path.read_text(encoding="utf-8")))):
        if (ROOT / ref).exists() or (path.parent / ref).exists():
            continue
        if pathlib.Path(ref).name in _basenames():
            continue
        missing.append(ref)
    assert not missing, (
        f"{path.relative_to(ROOT)} cites test files that do not exist: {missing}"
    )
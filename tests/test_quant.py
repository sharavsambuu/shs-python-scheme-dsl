"""``docs/quant_stuffs/`` under the same contract as the tutorial pages.

The quant playbook makes a claim prose pages should not make lightly: *every
Scheme snippet on the page was evaluated against this build, and the outputs
shown are the real ones.* That was true the day it was written and would rot
on the next change to ``srfi160.py``, ``srfi19.py`` or the prelude. This file
is the machine that keeps it true.

Four checks, each of which can catch a real rot:

1. **Every Scheme fence runs, and answers what the page says it answers.** The
   fences are concatenated in document order and evaluated as one program —
   the page leans on earlier definitions by design — and every ``;; =>`` claim
   is diffed against the value the build actually returns. The comparison uses
   ``write`` formatting, the reader-friendly form the page's ``;; =>``
   comments use (a string is shown ``"like this"`` even though the REPL echoes
   it bare; chapter 02 of the tutorial explains why).
2. **Every claim sits beside a form** — a ``;; =>`` with no expression before
   it has lost the expression it claims about.
3. **The page is reachable** — ``README.md`` links to it, so it cannot be
   orphaned by a rename.
4. **Every fence is closed** — an unclosed fence parses as prose, and none of
   the checks above would see the snippet it swallowed.

The first is the promise the page makes; the last three keep it honest about
what it is reading.

What this deliberately does *not* check: the Python fences. They are host
programs — numpy/pandas/numba are host dependencies, not repository ones
(``shslisp/embed.py``'s contract) — so they are not executed. The one
primitive the page installs itself, ``make-close-vector``, is rebuilt here:
that is the Scheme half of the seam, and it is checkable. The page's links,
backticked paths and cited test files are guarded by ``tests/test_docs.py``,
which counts this page among its pages.
"""
from __future__ import annotations

import array
import pathlib
import re

import pytest

from shslisp import evaluate_program, install_primitives, make_env, to_string
from shslisp.reader import read_all
from shslisp.types import Srfi160Vector

#: ``shs-python-scheme-dsl/`` — the page is written from inside it.
ROOT = pathlib.Path(__file__).resolve().parents[1]
#: The page under guard.
PAGE = ROOT / "docs" / "quant_stuffs" / "README.md"

#: A fenced block: the info string, the body (``test_tutorial.py``'s shape).
_FENCE = re.compile(r"^```([^\n]*)\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)

#: The page's value claim: ``;; => <value>`` — the trailing text is the value.
_CLAIM = re.compile(r";;[ \t]*=>[ \t]*(.*)")

#: A floor, not an exact count: the page must keep enough claims to be a page
#: of measured answers. If fences are lost, this is the tripwire.
MIN_CLAIMS = 20


def _fences(info_wanted: str = "scheme") -> list[str]:
    """The bodies of every fence whose info string is *info_wanted*."""
    return [
        body
        for info, body in _FENCE.findall(PAGE.read_text(encoding="utf-8"))
        if info.strip() == info_wanted
    ]


def _spans(block: str) -> list[tuple[str, str | None]]:
    """Split a fence into ``(code, claim)`` spans.

    A ``;; =>`` claim describes the *last* form in the code before it — the
    shape every snippet on the page is written in. The final span has no
    claim (the code after the last marker, if any).
    """
    spans: list[tuple[str, str | None]] = []
    position = 0
    for marker in _CLAIM.finditer(block):
        spans.append((block[position : marker.start()], marker.group(1).strip()))
        position = marker.end()
    spans.append((block[position:], None))
    return spans


def _host_primitive(closes):
    """The host function the page installs, rebuilt for the harness."""
    return Srfi160Vector("f64", array.array("d", closes))


@pytest.fixture(scope="module")
def evaluated() -> list[tuple[int, str, str, str]]:
    """Run the page in document order: ``(block, code, claim, actual)``.

    One environment for the whole page, because that is how the page is
    written — a later snippet leans on an earlier definition, and a reader
    pasting the fences top to bottom gets exactly this. ``actual`` is the
    rendered value of the last form in each span (or the error text, so a
    failure says what went wrong, not just that it did).
    """
    env = make_env()
    install_primitives(env, [("make-close-vector", _host_primitive)])
    results: list[tuple[int, str, str, str]] = []
    for block_number, block in enumerate(_fences(), start=1):
        for code, claim in _spans(block):
            forms = read_all(code)
            for index, form in enumerate(forms):
                try:
                    value = evaluate_program([form], env)
                    actual = to_string(value, write=True)
                except BaseException as error:  # noqa: BLE001 — page code may raise anything
                    actual = f"<{type(error).__name__}: {error}>"
                if claim is not None and index == len(forms) - 1:
                    results.append((block_number, code.strip(), claim, actual))
    return results


def test_every_scheme_snippet_runs_and_matches_its_output(evaluated) -> None:
    """A ``;; =>`` value that drifted from the build is a lie in prose."""
    offenders = [
        f"block {block}: the page shows {claim!r}, the build answers {actual!r}\n"
        f"    in: {code[-200:]!r}"
        for block, code, claim, actual in evaluated
        if claim != actual
    ]
    assert not offenders, (
        f"{PAGE.relative_to(ROOT)} has claims that do not hold:\n  "
        + "\n  ".join(offenders)
    )
    assert len(evaluated) >= MIN_CLAIMS, (
        f"{PAGE.relative_to(ROOT)} yielded only {len(evaluated)} checked claims "
        f"(expected at least {MIN_CLAIMS}); the fences or ``;; =>`` markers "
        "moved, and this guard is no longer reading the page."
    )


def test_every_claim_sits_beside_a_form() -> None:
    """A claim with no form before it has silently lost its expression."""
    offenders = []
    for block_number, block in enumerate(_fences(), start=1):
        for index, (code, claim) in enumerate(_spans(block), start=1):
            if claim is not None and not read_all(code):
                offenders.append(
                    f"block {block_number}, span {index}: no expression before "
                    f"{claim!r}"
                )
    assert not offenders, (
        f"{PAGE.relative_to(ROOT)} has orphaned claims:\n  "
        + "\n  ".join(offenders)
    )


def test_the_page_is_reachable_from_the_readme() -> None:
    """An orphaned page is a dead end, however good it is."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/quant_stuffs/README.md" in readme, (
        "README.md no longer links to docs/quant_stuffs/README.md — the page "
        "is unreachable from the docs index"
    )


def test_every_fence_is_closed() -> None:
    """An unclosed fence turns the rest of a page into prose — no guard sees it."""
    text = PAGE.read_text(encoding="utf-8")
    fences = len(re.findall(r"^```", text, re.MULTILINE))
    assert fences % 2 == 0, (
        f"{PAGE.relative_to(ROOT)} has {fences} fence markers — odd means one "
        "fence never closed and its snippet is prose, not code"
    )
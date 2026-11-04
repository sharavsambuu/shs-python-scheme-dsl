"""The guided tutorial, held to the same standard as the code.

``docs/lisp_tutorial/`` is load-bearing: this repository's own Tier-4 rule
(``docs/TODO.md``) says a teaching page "is not done until a reader can paste
its example and watch it work, and until the example is checked by a test that
fails when the code moves". The tutorial was written by hand and then verified
by hand once; nothing stopped it from rotting on the next commit to
``lisp/prelude.scm`` or ``tetris/registry.py``. This file is the machine that
does.

Five checks, each of which can catch a real drift:

1. **Every executable example runs, and prints what the page says it prints.**
   Every ``## Try it`` block must carry a ```text`` block beside it — the page
   shows the program, then the block a reader should see — and the harness runs
   the Lisp and diffs the two. A block with no expected output is a block that
   makes no claim about what it does, which is not a lesson; the pairing is
   required, not optional.
2. **Every chapter is reachable and complete.** Each numbered chapter is linked
   from the index, carries its metadata line (before / time / after), has a
   ``## Try it`` and an ``## Exercises`` section.
3. **Every referenced file exists.** Renames break prose silently; this is the
   cheapest guard against it.
4. **Every referenced test name exists.** Nine chapters cite ``test_*.py``
   fences; a rename would make the citation a lie.
5. **Every local link resolves.** The chapters link to each other and to the
   appendices; a broken link is a dead end for a reader.

What this deliberately does *not* check: whether the prose is *right* about a
mechanism. The harness proves the examples execute and the references resolve;
the argument a page makes is still a human judgement. See the note on the voice
in ``README.md`` — where a claim and a comment disagree, the code wins, and
this file is how the code gets to say so.
"""
from __future__ import annotations

import io
import pathlib
import re
from functools import lru_cache

import pytest

from lisp.__main__ import run_script

#: ``shs-python-scheme-dsl/`` — the tutorial is written from inside it.
ROOT = pathlib.Path(__file__).resolve().parents[1]
#: Kept as an alias: the "repository root" is the project root here.
REPO = ROOT
#: ``docs/lisp_tutorial/``.
TUT = ROOT / "docs" / "lisp_tutorial"

#: A fenced block: the info string, the body, and where it starts.
_FENCE = re.compile(r"^```([^\n]*)\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)

#: The heredoc body of an executable ``Try it`` block.
_HEREDOC = re.compile(r"<<'EOF'\n(.*?)\n[ \t]*EOF[ \t]*$", re.DOTALL)

#: A ``## Try it`` heading, and any ``##`` heading that closes its span.
_TRY_IT = re.compile(r"^##\s+Try it", re.MULTILINE)
_ANY_H2 = re.compile(r"^##\s+", re.MULTILINE)


#: A ``test_snake_case`` in prose.
_TEST_NAME = re.compile(r"`(test_[a-z0-9_]+)`")

#: A ``path/to/file.ext`` or ``path/to/file.ext:12`` in prose.
_PATH_REF = re.compile(
    r"`([A-Za-z0-9_./-]+\.(?:py|rs|json|md|toml|lisp|txt))(?::\d+)?`"
)

#: ``[label](target)`` — a markdown link.
_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _pages() -> list[pathlib.Path]:
    return sorted(TUT.glob("*.md"))


def _chapters() -> list[pathlib.Path]:
    """The numbered teaching pages, not the index or the appendices."""
    return sorted(p for p in _pages() if p.name[0].isdigit())


def _blocks(path: pathlib.Path) -> list[tuple[str, str, int]]:
    """``(info, body, line)`` for every fenced block on a page."""
    text = path.read_text(encoding="utf-8")
    return [
        (match.group(1).strip(), match.group(2),
         text[: match.start()].count("\n") + 1)
        for match in _FENCE.finditer(text)
    ]


def _try_it_spans(text: str) -> list[tuple[int, int]]:
    """The ``(start_line, end_line)`` spans of every ``## Try it`` section."""
    lines = text.splitlines()
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for number, line in enumerate(lines, 1):
        if _TRY_IT.match(line):
            start = number
        elif start is not None and _ANY_H2.match(line):
            spans.append((start, number - 1))
            start = None
    if start is not None:
        spans.append((start, len(lines)))
    return spans


def _executable_blocks(path: pathlib.Path):
    """Every executable ``Try it`` example, as ``(line, source, expected, tetris)``.

    Two shapes carry a program, and both are held to the same output contract —
    the expected text is the *next* fenced block, and it must be tagged
    ``text``: the page shows the program, then the block a reader should see.

    * A ``sh`` block running the program from stdin through a heredoc — kept
      for examples whose *point* is the command line itself.
    * A bare ``scheme`` block inside a ``## Try it`` section — the common
      case: the program itself, syntax-highlighted, runnable by pasting it
      into a file or the REPL.

    ``tetris`` is false when the block says ``--no-tetris``, so a
    language-only example is run without the game.
    """
    text = path.read_text(encoding="utf-8")
    found = _blocks(path)
    spans = _try_it_spans(text)

    def in_try_it(line: int) -> bool:
        return any(a <= line <= b for a, b in spans)

    for index, (info, body, line) in enumerate(found):
        expected = None
        if index + 1 < len(found) and found[index + 1][0] == "text":
            expected = found[index + 1][1]
        if info == "sh" and "run /dev/stdin" in body:
            heredoc = _HEREDOC.search(body)
            if heredoc is None:
                continue
            yield line, heredoc.group(1), expected, "--no-tetris" not in body
        elif info == "scheme" and in_try_it(line):
            yield line, body, expected, "--no-tetris" not in body



def _normalise(text: str) -> str:
    """Trailing whitespace and the final newline are not the lesson."""
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


@pytest.mark.parametrize("path", _pages(), ids=lambda p: p.stem)
def test_every_executable_example_runs(
    path: pathlib.Path, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``Try it`` block must run — and print what the page says it prints.

    This is the check the hand-verified commit (``docs(lisp): correct tutorial
    claims verified against the code``) stood in for. The rule is the one the
    repo applies to its Python concept pages: a reader who pastes an example
    gets a working result, and a rename that breaks it fails the build.
    """
    # The pages all begin ``cd python_tetris_lisp``, and one of the facts a page
    # reports is the length of the search path — which includes the working
    # directory. Run every example from the directory the page names.
    monkeypatch.chdir(ROOT)
    offenders: list[str] = []
    ran = 0
    for line, source, expected, _tetris in _executable_blocks(path):
        script = tmp_path / f"{path.stem}-{line}.scm"
        script.write_text(source, encoding="utf-8")
        buffer = io.StringIO()
        try:
            # Auto mode: a host edition is included only if one is installed,
            # so the same call runs the examples in a host checkout and here.
            run_script(str(script), out=buffer)
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
    if path.name[0].isdigit():
        assert ran >= 1, (
            f"{path.name} has no executable ``Try it`` example. Every chapter "
            f"must let the reader paste a program and watch it work."
        )


def test_the_number_of_executable_examples_is_not_drifting() -> None:
    """Count the examples the harness actually executed.

    A floor, stated so that a chapter losing its runnable example is a visible
    number rather than a silent subtraction. It can rise freely.
    """
    executable = sum(1 for path in _pages() for _ in _executable_blocks(path))
    assert executable >= 18, (
        f"only {executable} executable examples remain in the tutorial; one per "
        f"chapter is the contract, so this number should never fall"
    )


@pytest.mark.parametrize("path", _chapters(), ids=lambda p: p.stem)
def test_every_chapter_carries_its_metadata(path: pathlib.Path) -> None:
    """Before this / time / after this — a reader has to be able to pace
    themselves and to skip.

    The ``What this chapter teaches`` box says *what*; it does not say whether
    the reader is ready for it or what they can do at the end. A self-directed
    learner needs both, and their absence was a real gap.
    """
    text = path.read_text(encoding="utf-8")
    for marker in ("**Before this:**", "**Time:**", "**After this you can:**"):
        assert marker in text, (
            f"{path.name} is missing the {marker!r} metadata line. Every "
            f"numbered chapter states its prerequisite, its length, and what "
            f"the reader gains."
        )


@pytest.mark.parametrize("path", _chapters(), ids=lambda p: p.stem)
def test_every_chapter_has_a_try_it_and_an_exercise(path: pathlib.Path) -> None:
    """A chapter that teaches and does not let the reader *check* is a lecture."""
    text = path.read_text(encoding="utf-8")
    assert re.search(r"^##\s+Try it", text, re.MULTILINE), (
        f"{path.name} has no ``## Try it`` section"
    )
    assert re.search(r"^##\s+Exercise", text, re.MULTILINE | re.IGNORECASE), (
        f"{path.name} has no ``## Exercises`` section — a way for the reader to "
        f"find out whether it landed"
    )


def test_every_chapter_is_indexed() -> None:
    """No chapter may be orphaned; the index is the map."""
    index = (TUT / "README.md").read_text(encoding="utf-8")
    unlisted = [p.name for p in _chapters() if p.name not in index]
    assert not unlisted, (
        f"these chapters are not linked from docs/lisp_tutorial/README.md: "
        f"{unlisted}"
    )


@pytest.mark.parametrize("path", _pages(), ids=lambda p: p.stem)
def test_every_local_link_resolves(path: pathlib.Path) -> None:
    """A link to a chapter that moved is a dead end mid-lesson."""
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


def _known_tests() -> frozenset[str]:
    return _test_names()


@lru_cache(maxsize=1)
def _test_names() -> frozenset[str]:
    """Every ``test_*`` defined anywhere in this suite, read once."""
    return frozenset(
        match.group(1)
        for source in (ROOT / "tests").rglob("*.py")
        if "__pycache__" not in source.parts
        for match in re.finditer(r"def (test_[a-z0-9_]+)", source.read_text("utf-8"))
    )


@lru_cache(maxsize=1)
def _basenames() -> frozenset[str]:
    """Every file name under the project and the repository, read once."""
    names = set()
    for base in (ROOT, REPO):
        for candidate in base.rglob("*"):
            if candidate.is_file() and "__pycache__" not in candidate.parts:
                names.add(candidate.name)
    return frozenset(names)


@pytest.mark.parametrize("path", _pages(), ids=lambda p: p.stem)
def test_referenced_test_names_exist(path: pathlib.Path) -> None:
    """A `` `test_foo` `` in prose must be a real test in this suite."""
    known = _known_tests()
    missing = sorted(set(_TEST_NAME.findall(path.read_text(encoding="utf-8"))) - known)
    assert not missing, f"{path.name} names tests that do not exist: {missing}"


@pytest.mark.parametrize("path", _pages(), ids=lambda p: p.stem)
def test_referenced_paths_exist(path: pathlib.Path) -> None:
    """A `` `dir/file.ext` `` must point at a file that exists somewhere real.

    Roots are tried from the reader's point of view — the chapter's own
    directory, ``python_tetris_lisp/``, and the repository root — and a bare
    filename is accepted if it exists anywhere under the project, because the
    tutorial names files both ways on purpose.
    """
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

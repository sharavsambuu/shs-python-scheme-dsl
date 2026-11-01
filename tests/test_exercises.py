"""The tutorial's exercises, run — the answer keys, in the suite.

``docs/lisp_tutorial/`` ends most chapters with an exercise. An exercise with
no answer is a dead end for a self-directed learner, and this repository's other
teaching pages keep their answer keys *in the tests* rather than in an appendix
(``LEARNING_PATH.md`` §5). This file does the same for the Lisp tutorial: every
worked answer under ``docs/lisp_tutorial/exercises/`` is loaded here and checked,
so an exercise cannot rot into something that no longer runs.

The distinction from ``test_tutorial.py``: that file checks the chapters'
``Try it`` blocks; this one checks the *exercises*, which are separate files a
reader is invited to write.
"""
from __future__ import annotations

import io
import pathlib

import pytest

from lisp.__main__ import run_script
from lisp.evaluator import apply_procedure
from lisp.runtime import make_env
from lisp.types import intern

#: Where the worked answers live.
ROOT = pathlib.Path(__file__).resolve().parents[1]
EXERCISES = ROOT / "docs" / "lisp_tutorial" / "exercises"

#: The answer keys that need no host: plain Lisp exercises.


def _run(name: str, tetris: bool = False):
    """Run an exercise file; return ``(printed, env)``."""
    buffer = io.StringIO()
    _value, env = run_script(str(EXERCISES / name), out=buffer, tetris=tetris)
    return buffer.getvalue(), env


def test_the_exercises_exist() -> None:
    """A floor on the answer-key set, so an exercise cannot quietly lose its key."""
    keys = sorted(p.name for p in EXERCISES.glob("*.scm"))
    assert keys, "docs/lisp_tutorial/exercises/ has no answer keys"
    for expected in (
        "unless-not.scm", "greeting.scm", "shapes.scm", "rename-pipeline.scm",
        "expand-and-flatten.scm",
    ):
        assert expected in keys, f"the answer key {expected} is missing"


def test_unless_not_is_hygienic() -> None:
    """Chapter 06: the macro runs the body on false, and leaves `t` alone."""
    printed, _env = _run("unless-not.scm")
    assert printed.splitlines() == ["ran", "()", "99"]


def test_greeting_loads_once_by_bare_name() -> None:
    """Chapter 07: a module on the search path loads once, however often asked."""
    env = make_env(install_tetris=False, search_paths=[EXERCISES], out=io.StringIO())
    env.loader.load_one("greeting")
    env.loader.load_one("greeting")
    hello = env.lookup(intern("hello"))
    assert apply_procedure(hello, ["world"]) == "hello, world"
    loaded = [path for path in env.loader.modules() if path.endswith("greeting.scm")]
    assert len(loaded) == 1, f"greeting loaded {len(loaded)} times: {loaded}"


def test_shapes_extend_and_refuse() -> None:
    """Chapter 09: a new tag works, and a missing clause names the whole set."""
    printed, _env = _run("shapes.scm")
    assert "12" in printed
    assert "(circle rect triangle)" in printed
    assert "this shape is one of circle rect triangle" in printed


def test_rename_pipeline_short_circuits() -> None:
    """Chapter 10: an early refusal skips the rest, and left identity holds."""
    printed, _env = _run("rename-pipeline.scm")
    assert "(ok HI!)" in printed
    assert "(err has space)" in printed
    assert "(err empty)" in printed
    assert "#t" in printed


def test_expand_and_flatten_is_variadic_and_flat() -> None:
    """Chapter 06: a dotted tail splices, stacked ellipses flatten, and a
    macroexpanded form is real code that `eval` runs."""
    printed, _env = _run("expand-and-flatten.scm")
    assert printed.splitlines() == ["11", "(1 2 3 4 5)", "42", "(if #t 1 2)"]

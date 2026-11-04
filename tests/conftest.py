"""Shared fixtures for the ``python_tetris_lisp`` suite.

Two environments are offered, because the language is meant to stand on its
own: ``env`` is a plain Scheme (no game), ``tenv`` has the Tetris vocabulary.
The ``ev``/``tev`` fixtures are those environments' evaluators, so a test reads
as a sequence of Lisp forms.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

# Make ``shslisp`` and ``tetris`` importable no matter where pytest is invoked.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shslisp.evaluator import evaluate_program  # noqa: E402
from shslisp.reader import read_all  # noqa: E402
from shslisp.runtime import make_env  # noqa: E402


def evaluate_source(env, source: str):
    return evaluate_program(read_all(source), env)


@pytest.fixture
def env():
    """A fresh, strict environment: the R7RS conformance target.

    ``profile="r7rs"`` pre-imports no SRFI — the core and the prelude are the
    whole language. The SRFI tests build their own DSL-profile environments.
    """
    return make_env(install_tetris=False, profile="r7rs")


@pytest.fixture
def tenv():
    """A fresh environment with the tetris bridge installed."""
    return make_env(install_tetris=True, profile="dsl")


@pytest.fixture
def ev(env):
    """``ev("(+ 1 2)")`` → evaluate Lisp source in the language-only env."""
    return lambda source: evaluate_source(env, source)


@pytest.fixture
def tev(tenv):
    """``tev("(new-game)")`` → evaluate Lisp source with tetris available."""
    return lambda source: evaluate_source(tenv, source)


@pytest.fixture
def buffered_env():
    """``(env, buffer)`` where the env's ``display`` writes into the buffer."""
    buffer = io.StringIO()
    return make_env(install_tetris=False, out=buffer), buffer

"""H8: call/cc is escape-only — the one-shot exit works, re-entry does not.

Pins the Tier-1 deliberate gap on docs/HARDENING_TASKS.md H8. This is not a
bug to fix in this round; it is the contract a reader must not re-discover.
Short-lived escape inside the dynamic extent works; invoking a captured
continuation after the extent ends raises ContinuationJump. Coroutines /
green threads built on re-entrant continuations are therefore not available,
and make-coroutine-generator / make-for-each-generator fail loudly by design.
"""
from __future__ import annotations

import pytest

from shslisp.errors import ContinuationJump
from shslisp.runtime import make_env, run as lisp_run


def test_escape_inside_extent_works() -> None:
    env = make_env()
    assert lisp_run("(call/cc (lambda (k) (k 99) 1))", env) == 99


def test_escape_outside_extent_does_not_reenter() -> None:
    env = make_env()
    # Capture succeeds inside extent, but invoking after it is an error.
    lisp_run(
        "(define k #f) (call/cc (lambda (c) (set! k c) 1))",
        env,
    )
    with pytest.raises(ContinuationJump):
        lisp_run("(k 99)", env)


def test_make_coroutine_generator_works_via_fiber() -> None:
    env = make_env()
    assert (
        lisp_run(
            """
            (import (srfi 158))
            (define g (make-coroutine-generator
                       (lambda (yield) (yield 1) (yield 2))))
            (list (g) (g) (eof-object? (g)))
            """,
            env,
        )
        == [1, 2, True]
    )

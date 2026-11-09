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


def test_make_coroutine_generator_fails_loudly() -> None:
    env = make_env()
    # generators.scm:200 — bound but fails loudly by design (escape-only).
    with pytest.raises(Exception) as excinfo:
        lisp_run(
            "(import (srfi 158)) (make-coroutine-generator (lambda () 1))",
            make_env(),
        )
    assert "make-coroutine-generator" in str(excinfo.value)
    # Silence here would be the bug: this must never answer a generator.
    # The live env form hits the same binder.
    with pytest.raises(Exception) as excinfo2:
        lisp_run("(make-coroutine-generator (lambda () 1))", env)
    assert "make-coroutine-generator" in str(excinfo2.value)

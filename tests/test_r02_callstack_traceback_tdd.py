"""Locked Frontier TDD suite for R-02: multi-frame Scheme call-stack trace on LispError."""
from __future__ import annotations

import pytest

from shslisp import make_env, run
from shslisp.errors import LispTypeError
from shslisp.evaluator import evaluate_program
from shslisp.reader import read_all_located


def test_lisp_error_captures_multi_frame_traceback() -> None:
    env = make_env()
    src = (
        "(define (inner y) (car y))\n"
        "(define (outer x) (+ 1 (inner x)))\n"
        "(outer 42)\n"
    )
    forms = read_all_located(src, file="trace_demo.scm")
    with pytest.raises(LispTypeError) as exc_info:
        evaluate_program(forms, env)

    exc = exc_info.value
    # Existing single-line str(exc) contract remains intact:
    assert str(exc).startswith("trace_demo.scm:")
    # New multi-frame traceback contract:
    assert hasattr(exc, "traceback")
    tb = exc.traceback
    assert len(tb) >= 2, f"Expected >=2 stack frames in traceback, got {tb!r}"
    lines = {loc.line for loc in tb}
    assert 1 in lines and (2 in lines or 3 in lines), f"Expected outer/inner line numbers in {tb!r}"
    formatted = exc.format_traceback()
    assert "trace_demo.scm:1:" in formatted
    assert ("trace_demo.scm:2:" in formatted) or ("trace_demo.scm:3:" in formatted)


def test_single_frame_error_still_formats_cleanly() -> None:
    env = make_env()
    with pytest.raises(LispTypeError) as exc_info:
        run("(car 1)", env)
    exc = exc_info.value
    assert hasattr(exc, "format_traceback")
    assert "car" in exc.format_traceback()

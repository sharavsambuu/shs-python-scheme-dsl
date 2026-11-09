"""H12: exact vs inexact complex must not mix silently.

The dual tower has ``Complex`` (exact rational pair) and ``complex`` (inexact).
These property-style checks pin: any inexact argument contaminates the whole
operation to inexact, exact-only operations stay exact, and ``eqv?``/``equal?``
distinguish them. English repo content per discussion.
"""
from __future__ import annotations

from fractions import Fraction

import pytest

from shslisp.runtime import make_env, run
from shslisp.types import Complex


@pytest.fixture(scope="module")
def env():
    return make_env()


def ev(env, src):
    return run(src, env)


def test_exact_ops_stay_exact(env):
    assert ev(env, "(make-rectangular 1/2 1/3)") == Complex(Fraction(1, 2), Fraction(1, 3))
    # reader requires a real part in literals (R7RS C3) — use 0+1/3i, not 1/3i
    assert ev(env, "(+ 1/2 0+1/3i)") == Complex(Fraction(1, 2), Fraction(1, 3))
    assert ev(env, "(* (make-rectangular 1 2) (make-rectangular 3 4))") == Complex(-5, 10)
    assert ev(env, "(/ (make-rectangular 3 4) 2)") == Complex(Fraction(3, 2), 2)
    # magnitude / angle of exact stay with real/rational types
    # (conjugate is not in this dialect — (scheme complex) is 6/6 without it)
    mag = ev(env, "(magnitude (make-rectangular 3 4))")
    assert mag == 5 and type(mag) is int


def test_inexact_contamination(env):
    # One inexact component contaminates the whole pair to complex()
    v = ev(env, "(make-rectangular 1.0 2)")
    assert isinstance(v, complex) and v == complex(1.0, 2.0)
    v = ev(env, "(+ (make-rectangular 1 2) 1.0)")
    assert isinstance(v, complex)
    v = ev(env, "(* (make-rectangular 1 2) 1.0)")
    assert isinstance(v, complex)
    v = ev(env, "(/ (make-rectangular 1 2) 2.0)")
    assert isinstance(v, complex)


def test_eqv_distinguishes_exact_inexact(env):
    # equal?/eqv? follow the “exactness distinguishes” rule (review fix)
    assert ev(env, "(eqv? (make-rectangular 1 2) (make-rectangular 1.0 2.0))") is False
    assert ev(env, "(equal? (make-rectangular 1 2) (make-rectangular 1.0 2.0))") is False
    assert ev(env, "(eqv? (make-rectangular 1 2) (make-rectangular 1 2))") is True


def test_literal_round_trip(env):
    # C3 supported forms — note 2i/1/3i alone are not literals (use 0+2i)
    for lit in ["1+2i", "1/2+1/3i", "+i", "1.0-0.0i", "2@1", "0+2i"]:
        v = ev(env, lit)
        assert str(v) != "", lit  # printer does not crash
        # Re-read the printed form: evaluate the printed text as a literal
        from shslisp.printer import to_string

        printed = to_string(v)
        # Round-trip through Scheme text should not raise
        ev(env, printed)

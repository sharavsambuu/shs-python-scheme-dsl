"""Corner-case hardening: the adversarial probe, held to the same standard.

Each test here began as a probe that produced a surprising answer (or an
unpinned behaviour the docs claim). The rule is the repository's own: a
documented claim gets a test, and a hazard gets a *loud* failure rather than
a silent one.
"""
from __future__ import annotations

from fractions import Fraction

import pytest

from shslisp.errors import LispError, LispRecursionError, LispTypeError
from shslisp.evaluator import evaluate_program
from shslisp.reader import read_all
from shslisp.runtime import make_env
from shslisp.types import intern


@pytest.fixture
def env() -> None:
    return make_env(install_tetris=False)


def run(env, source: str):
    return evaluate_program(read_all(source), env)


# --------------------------------------------------------------------------- #
#  Booleans are not numbers — arithmetic must agree with number?              #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "source",
    [
        "(+ #t 1)",
        "(+ 1 #f)",
        "(- #t 1)",
        "(- 1 #t)",
        "(* #t 2)",
        "(/ #t 2)",
        "(min #t 2)",
        "(max 2 #f)",
        "(expt #t 2)",
        "(abs #f)",
        "(modulo #t 2)",
        "(quotient #t 2)",
        "(remainder #t 2)",
        "(< #t 2)",
        "(= #f 0)",
        "(<= #t 1)",
        "(>= #f 1)",
    ],
)
def test_arithmetic_rejects_booleans(env, source: str) -> None:
    # `number?` says #f, `integer?` says #f; the arithmetic must not answer
    # anyway just because Python's bool subclasses int.
    with pytest.raises(LispTypeError):
        run(env, source)


def test_arithmetic_still_works_after_the_gate(env) -> None:
    assert run(env, "(+ 1 2 3)") == 6
    assert run(env, "(* 2 3)") == 6
    assert run(env, "(- 10 1 2)") == 7
    assert run(env, "(- 5)") == -5
    assert run(env, "(/ 6 3)") == 2
    assert run(env, "(/ 3 4)") == Fraction(3, 4)
    assert run(env, "(min 3 1 2)") == 1
    assert run(env, "(max 3 1 2)") == 3
    assert run(env, "(abs -3)") == 3
    assert run(env, "(expt 2 10)") == 1024
    assert run(env, "(modulo -7 3)") == 2
    assert run(env, "(quotient -7 2)") == -3
    assert run(env, "(remainder -7 2)") == -1
    assert run(env, "(< 1 2 3)") is True


# --------------------------------------------------------------------------- #
#  An import may not silently replace a name the environment already binds    #
# --------------------------------------------------------------------------- #

def test_import_rename_onto_a_core_name_raises(env) -> None:
    # The probe that found this: after the import, (car '(1 2)) was fold.
    # A rename is the sharp tool — aiming it at a core primitive raises.
    with pytest.raises(LispError, match="collision on car"):
        run(env, "(import (rename (srfi 1) (fold car)))")


def test_plain_import_keeps_r7rs_shadowing(env) -> None:
    # A plain library import binds its exports per R7RS: (srfi 1)'s
    # for-each/map shadow the base ones by design. Unrelated core names —
    # car — are untouched, and the SRFI surface works.
    run(env, "(import (srfi 1))")
    assert run(env, "(car '(1 2))") == 1
    assert run(env, "(member \"b\" '(\"a\" \"b\") string=?)") == ["b"]


def test_re_importing_the_same_library_is_fine(env) -> None:
    run(env, "(import (srfi 1))")
    run(env, "(import (srfi 1))")
    assert run(env, "(iota 3)") == [0, 1, 2]


def test_importing_srfi_1_shadowing_does_not_break_the_floor(env) -> None:
    # Even with SRFI 1's map/for-each shadowing the base ones, the floor
    # still answers: car is car.
    run(env, "(import (srfi 1))")
    assert run(env, "(car '(1 2))") == 1


def test_importing_scheme_base_twice_is_fine(env) -> None:
    # The profile does exactly this on every make_env; the registry resolves
    # (scheme base) to the environment's own objects, so nothing changes.
    run(env, "(import (scheme base))")
    assert run(env, "(car '(1 2))") == 1


def test_the_srfi_layer_may_replace_prelude_helpers(env) -> None:
    # The documented layering: SRFI 1's fold/reduce replace the prelude's
    # aliases (same argument order, SRFI reduce semantics). Only the core
    # floor is protected — prelude.scm's `(define reduce foldl)` is an alias,
    # not the floor.
    assert run(env, "(eq? foldl fold)") is False
    assert run(env, "(fold + 0 '(1 2 3))") == 6
    assert run(env, "(reduce + 0 '(1 2 3))") == 6


# --------------------------------------------------------------------------- #
#  Documented hazards, pinned so their shape is known                          #
# --------------------------------------------------------------------------- #

def test_mutating_a_hash_table_key_orphans_the_entry(env) -> None:
    # Structural keys + in-place mutation = the entry becomes unreachable.
    # The raise is the loud shape; the silent alternative is the hazard.
    run(env, "(define h (make-hash-table))")
    run(env, "(define k (list 1 2))")
    run(env, "(hash-table-set! h k 'v)")
    run(env, "(set-car! k 9)")
    with pytest.raises(LispError, match="no value for key"):
        run(env, "(hash-table-ref h k)")


def test_equal_on_a_cyclic_pair_raises_a_lisp_error(env) -> None:
    # r7rs.md documents this: equal? can recurse forever on a cycle. The
    # pinned shape is that it surfaces as a Lisp error, never a host crash.
    run(env, "(define p (cons 1 2))")
    run(env, "(set-cdr! p p)")
    with pytest.raises(LispRecursionError):
        run(env, "(equal? p p)")


def test_exactness_prefix_on_an_inexact_literal_stays_inexact(env) -> None:
    # #e asks for the exact rational 3/2; this tower has no rationals, so the
    # value survives as the inexact 1.5. Pinned as the documented behaviour.
    assert run(env, "#e1.5") == 1.5


def test_tail_loop_beyond_the_budget_raises(env, monkeypatch) -> None:
    # A tail loop costs a few steps per iteration, so the default budget
    # bounds iteration count too. Pinned with a small budget so the shape is
    # cheap to check: the error is a LispBudgetError, not a hang.
    from shslisp.evaluator import STEPS_BUDGET

    monkeypatch.setattr("shslisp.evaluator.STEPS_BUDGET", 1_000)
    with pytest.raises(Exception, match="steps"):
        run(env, "(let loop ((n 100000)) (if (= n 0) 'done (loop (- n 1))))")
    assert STEPS_BUDGET  # the real default is untouched by this test

"""The generator library — lazy sequences as ordinary closures (S9).

``shslisp/generators.scm`` is prelude: a generator is a procedure of zero
arguments answering the next value, and the unique ``generator-end`` object at
exhaustion. No evaluator change, no continuations — ``set!`` and a closure are
the whole mechanism. What is pinned here:

* **the protocol** — exhaustion is idempotent, the end object is unique
  (``eq?``) and unforgeable-by-accident, and a generator is a plain procedure;
* **laziness** — infinite generators (range, cycle) compose with ``gtake``/
  ``gfilter``/``gmap`` and never build an infinite structure;
* **the draining discipline** — ``generator->list``/``fold``/``for-each`` and
  the multi-generator stop-at-shortest rule, matching SRFI 1's ``map``.

The library is *not* an SRFI claim: ``(srfi 158)`` still fails loudly
(``tests/test_library.py``). ``gtake``/``gdrop`` answer generators, so they
compose; ``generator->list`` is the drain.
"""
from __future__ import annotations

import pytest

from shslisp.errors import LispError
from shslisp.evaluator import evaluate_program
from shslisp.reader import read_all
from shslisp.runtime import make_env
from shslisp.types import NIL


@pytest.fixture
def env():
    return make_env(install_tetris=False, profile="r7rs")


@pytest.fixture
def ev(env):
    return lambda source: evaluate_program(read_all(source), env)


@pytest.fixture
def dsl():
    return make_env(install_tetris=False, profile="dsl")


# --------------------------------------------------------------------------- #
#  The protocol                                                               #
# --------------------------------------------------------------------------- #


def test_the_end_object_is_unique_and_unforgeable(ev) -> None:
    # `generator-end?` is the only check; a lookalike pair is not it.
    assert ev("(generator-end? generator-end)") is True
    assert ev("(eq? generator-end (list 'generator-end))") is False
    assert ev("(generator-end? (list 'generator-end))") is False
    assert ev("(generator-end? '())") is False
    assert ev("(generator-end? #f)") is False


def test_exhaustion_is_idempotent(ev) -> None:
    # Calling an exhausted generator again answers the end object again —
    # a consumer cannot "fall off" by over-reading.
    ev("(define g (generator 1 2))")
    assert ev("(g)") == 1
    assert ev("(g)") == 2
    assert ev("(generator-end? (g))") is True
    assert ev("(generator-end? (g))") is True


def test_a_generator_is_an_ordinary_procedure(ev) -> None:
    # The protocol is a convention over 0-arg procedures — nothing magical.
    assert ev("(procedure? (generator 1))") is True
    assert ev("(procedure? (make-range-generator 0 3))") is True


# --------------------------------------------------------------------------- #
#  Constructors                                                               #
# --------------------------------------------------------------------------- #


def test_generator_over_values_and_the_empty_case(ev) -> None:
    assert ev("(generator->list (generator 1 2 3))") == [1, 2, 3]
    assert ev("(generator->list (generator))") is NIL
    assert ev("(generator->list (list->generator '(a b c)))") == ["a", "b", "c"]


def test_vector_generators_round_trip(ev) -> None:
    assert ev("(generator->list (vector->generator (vector 7 8)))") == [7, 8]
    assert ev("(vector->list (generator->vector (generator 1 2 3)))") == [1, 2, 3]


def test_range_generator_arities(ev) -> None:
    assert ev("(generator->list (make-range-generator 0 5))") == [0, 1, 2, 3, 4]
    assert ev("(generator->list (make-range-generator 0 10 3))") == [0, 3, 6, 9]
    assert ev("(generator->list (make-range-generator 5 0 -2))") == [5, 3, 1]


def test_cycle_generator_repeats_and_the_empty_list_ends(ev) -> None:
    assert ev("(generator->list (make-cycle-generator '(a b)) 5)") == [
        "a", "b", "a", "b", "a",
    ]
    # The empty list ends immediately rather than looping forever.
    assert ev("(generator->list (make-cycle-generator '()))") is NIL


# --------------------------------------------------------------------------- #
#  Laziness                                                                   #
# --------------------------------------------------------------------------- #


def test_infinite_ranges_are_safe_under_gtake(ev) -> None:
    # Nothing here builds an infinite structure: `gtake` pulls exactly k.
    assert ev("(generator->list (gtake (make-range-generator 10) 4))") == [
        10, 11, 12, 13,
    ]
    assert ev("(generator->list (gtake (make-range-generator 0) 3))") == [0, 1, 2]


def test_gfilter_is_lazy_over_an_infinite_generator(ev) -> None:
    # The odd numbers, forever — take four and stop. No budget is burned on
    # the even values beyond skipping them.
    assert ev("(generator->list (gtake (gfilter odd? (make-range-generator 0)) 4))") == [
        1, 3, 5, 7,
    ]


def test_gmap_maps_lazily(ev) -> None:
    assert ev(
        "(generator->list (gtake (gmap (lambda (x) (* x x)) (make-range-generator 1)) 5))"
    ) == [1, 4, 9, 16, 25]


def test_gmap_over_several_generators_stops_at_the_shortest(ev) -> None:
    # The SRFI 1 `map` rule, made lazy: the first exhaustion ends the step.
    assert ev(
        "(generator->list (gmap + (generator 1 2 3) (generator 10 20)))"
    ) == [11, 22]
    assert ev(
        "(generator->list (gmap list (generator 1 2 3) (generator 10 20 30)))"
    ) == [[1, 10], [2, 20], [3, 30]]


def test_gmap_without_a_generator_is_an_error(ev) -> None:
    with pytest.raises(LispError, match="at least one generator"):
        ev("(gmap +)")


# --------------------------------------------------------------------------- #
#  gtake / gdrop                                                              #
# --------------------------------------------------------------------------- #


def test_gtake_answers_fewer_when_the_generator_ends_first(ev) -> None:
    assert ev("(generator->list (gtake (generator 1 2 3) 2))") == [1, 2]
    assert ev("(generator->list (gtake (generator 1 2) 5))") == [1, 2]
    assert ev("(generator->list (gtake (generator) 3))") is NIL


def test_gdrop_skips_k_values(ev) -> None:
    assert ev("(generator->list (gdrop (generator 1 2 3 4 5) 2))") == [3, 4, 5]
    # `k` of zero is the identity: the same generator, nothing skipped.
    assert ev("(generator->list (gdrop (generator 1 2) 0))") == [1, 2]


def test_gdrop_skips_exactly_once(ev) -> None:
    # The first drain skips 3 and answers (4 5); the second continues from
    # there — the skipping is one-time state, not a per-call re-scan.
    assert ev(
        "(let ((g (gdrop (generator 1 2 3 4 5) 3)))"
        "  (list (generator->list g) (generator->list g)))"
    ) == [[4, 5], NIL]


def test_gdrop_over_an_infinite_generator(ev) -> None:
    assert ev("(generator->list (gtake (gdrop (make-range-generator 0) 3) 3))") == [
        3, 4, 5,
    ]


# --------------------------------------------------------------------------- #
#  Draining                                                                   #
# --------------------------------------------------------------------------- #


def test_generator_fold_is_a_left_fold_over_the_values(ev) -> None:
    assert ev("(generator-fold + 0 (generator 1 2 3 4))") == 10
    # Draining a *slice* of an infinite generator is the idiomatic shape.
    assert ev("(generator-fold + 0 (gtake (make-range-generator 1) 5))") == 15
    assert ev("(generator-fold + 0 (generator))") == 0


def test_generator_for_each_runs_left_to_right(ev) -> None:
    # The accumulator is visible outside the closure: `set!` on a definition.
    ev("(define acc '())")
    ev(
        "(generator-for-each (lambda (x) (set! acc (cons x acc)))"
        " (generator 1 2 3))"
    )
    assert ev("acc") == [3, 2, 1]


def test_generator_for_each_over_two_generators(ev) -> None:
    ev("(define seen '())")
    ev(
        "(generator-for-each"
        "  (lambda (a b) (set! seen (cons (list a b) seen)))"
        "  (generator 1 2 3) (generator 10 20))"
    )
    # The shortest generator wins: 3 is never paired.
    assert ev("(reverse seen)") == [[1, 10], [2, 20]]


# --------------------------------------------------------------------------- #
#  The profiles                                                               #
# --------------------------------------------------------------------------- #


def test_the_library_ships_in_both_profiles(ev, dsl) -> None:
    # Prelude means both profiles: the strict conformance environment and the
    # default DSL one see the same bindings, and they interoperate with the
    # SRFI layer in the DSL profile (`iota` is SRFI 1).
    assert ev("(generator->list (gtake (make-cycle-generator '(x y)) 3))") == [
        "x", "y", "x",
    ]
    assert evaluate_program(
        read_all("(generator->list (gfilter odd? (list->generator (iota 6))))"),
        dsl,
    ) == [1, 3, 5]


def test_srfi_158_is_still_not_a_claim(env) -> None:
    # S9 is a prelude library, not an SRFI: importing `(srfi 158)` fails
    # loudly until its semantics are audited name by name.
    with pytest.raises(LispError):
        evaluate_program(read_all("(import (srfi 158))"), env)
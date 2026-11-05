"""The generator library — generators and accumulators (S9 + S12).

``shslisp/generators.scm`` is prelude: a generator is a procedure of zero
arguments answering the next value, and the **eof-object** at exhaustion —
SRFI 158's protocol, since S12 (S9 originally used a custom ``generator-end``
pair; the object still exists and the library still accepts it, so pre-S12
code keeps running). No evaluator change, no continuations — ``set!`` and a
closure are the whole mechanism. What is pinned here:

* **the protocol** — exhaustion is idempotent and answered by the core's
  eof-object; the deprecated sentinel is still accepted by every consumer;
* **laziness** — infinite generators (range, cycle, circular) compose with
  ``gtake``/``gfilter``/``gmap`` and never build an infinite structure;
* **the SRFI 158 surface** — the combinators, the multi-generator drains,
  the searching half, and the accumulators;
* **the loud deviations** — ``make-coroutine-generator`` and
  ``make-for-each-generator`` need re-entrant continuations and fail loudly.

The plan this implements is S12 in ``docs/SRFI_TASKS.md``; the matrix row is
in ``docs/srfi.md``.
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
    # `generator-end?` still answers its own object; a lookalike pair is not it.
    assert ev("(generator-end? generator-end)") is True
    assert ev("(eq? generator-end (list 'generator-end))") is False
    assert ev("(generator-end? (list 'generator-end))") is False
    assert ev("(generator-end? '())") is False
    assert ev("(generator-end? #f)") is False


def test_exhaustion_is_the_eof_object_and_is_idempotent(ev) -> None:
    # S12's protocol: the core's eof-object, exactly as `read` signals an
    # empty input. Calling an exhausted generator again answers it again —
    # a consumer cannot "fall off" by over-reading.
    ev("(define g (generator 1 2))")
    assert ev("(g)") == 1
    assert ev("(g)") == 2
    assert ev("(eof-object? (g))") is True
    assert ev("(eof-object? (g))") is True


def test_the_deprecated_sentinel_is_still_accepted_by_the_drains(ev) -> None:
    # A pre-S12 generator that answers `generator-end` keeps working: every
    # consumer accepts both exhaustion markers.
    ev(
        "(define old (let ((vals '(7 8)))"
        "  (lambda () (if (null? vals) generator-end"
        "               (let ((v (car vals))) (set! vals (cdr vals)) v)))))"
    )
    assert ev("(generator->list old)") == [7, 8]
    # ...and the old sentinel is still what *it* answers on exhaustion:
    assert ev("(generator-end? (old))") is True


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


def test_srfi_158_is_now_the_claim(env, ev) -> None:
    # S12: the audit landed, `(srfi 158)` imports and binds the audited
    # surface over the same prelude bindings.
    evaluate_program(read_all("(import (srfi 158))"), env)
    assert ev("(generator->list (gtake (make-range-generator 1) 3))") == [1, 2, 3]


# --------------------------------------------------------------------------- #
#  The S12 additions: constructors, combinators, searching, accumulators      #
# --------------------------------------------------------------------------- #


def test_the_srfi_158_constructors(ev) -> None:
    assert ev("(generator->list (make-iota-generator 4))") == [0, 1, 2, 3]
    assert ev("(generator->list (make-iota-generator 3 10 5))") == [10, 15, 20]
    assert ev("(generator->list (gtake (circular-generator 'x 'y) 4))") == [
        "x", "y", "x", "y",
    ]
    # Characters answer as characters — compare through equal? in Lisp:
    assert ev(
        "(equal? (generator->list (string->generator \"ab\")) (string->list \"ab\"))"
    ) is True
    assert ev("(generator->list (bytevector->generator (bytevector 9 8)))") == [9, 8]
    assert ev(
        "(generator->list (reverse-vector->generator (vector 1 2 3)))"
    ) == [3, 2, 1]
    assert ev(
        "(generator->list (make-unfold-generator (lambda (s) (> s 3))"
        "  (lambda (s) (* s s)) (lambda (s) (+ s 1)) 1))"
    ) == [1, 4, 9]


def test_the_two_coroutine_constructors_fail_loudly(ev) -> None:
    # They need re-entrant continuations, which this dialect deliberately
    # does not have (docs/r7rs.md); the failure names the limitation.
    with pytest.raises(LispError, match="re-entrant continuations"):
        ev("(make-coroutine-generator (lambda (yield) (yield 1)))")
    with pytest.raises(LispError, match="re-entrant continuations"):
        ev("(make-for-each-generator (lambda (proc obj) obj) '())")


def test_gcons_star_and_gappend(ev) -> None:
    assert ev("(generator->list (gcons* 1 2 (generator 3 4)))") == [1, 2, 3, 4]
    assert ev("(generator->list (gappend (generator 1) (generator) (generator 2)))") == [1, 2]
    assert ev("(generator->list (gappend))") is NIL


def test_gflatten_ggroup_and_gstate_filter(ev) -> None:
    assert ev("(generator->list (gflatten (generator '(1 2) '(3) '())))") == [1, 2, 3]
    assert ev("(generator->list (ggroup (generator 1 2 3 4 5) 2))") == [
        [1, 2], [3, 4], [5],
    ]
    assert ev("(generator->list (ggroup (generator 1 2 3 4 5) 2 0))") == [
        [1, 2], [3, 4], [5, 0],
    ]
    # A stateful filter: keep the value while the running sum stays below 3.
    assert ev(
        "(generator->list (gstate-filter"
        "  (lambda (v s) (values (< (+ v s) 3) (+ v s))) 0 (generator 1 1 1 1 1)))"
    ) == [1, 1]


def test_gremove_gdelete_and_gdelete_neighbor_dups(ev) -> None:
    assert ev("(generator->list (gremove odd? (generator 1 2 3 4)))") == [2, 4]
    assert ev("(generator->list (gdelete 2 (generator 1 2 3 2 4)))") == [1, 3, 4]
    assert ev("(generator->list (gdelete 2 (generator 1 2 3 2 4) =))") == [1, 3, 4]
    assert ev(
        "(generator->list (gdelete-neighbor-dups (generator 1 1 2 2 2 3 1)))"
    ) == [1, 2, 3, 1]
    assert ev(
        "(generator->list (gdelete-neighbor-dups (generator \"a\" \"A\" \"b\") string-ci=?))"
    ) == ["a", "b"]


def test_gindex_gselect_and_gcombine(ev) -> None:
    assert ev(
        "(generator->list (gindex (generator 'a 'b 'c 'd) (generator 0 2)))"
    ) == ["a", "c"]
    assert ev(
        "(generator->list (gselect (generator 1 2 3 4) (generator #f #t #f #t)))"
    ) == [2, 4]
    # gcombine folds with a seed, threading two values through each step:
    assert ev(
        "(generator->list (gcombine (lambda (v s) (values (+ v s) (+ v s)))"
        "  0 (generator 1 2 3)))"
    ) == [1, 3, 6]


def test_gmerge_merges_sorted_generators(ev) -> None:
    assert ev(
        "(generator->list (gmerge < (generator 1 3 5) (generator 2 3 6)))"
    ) == [1, 2, 3, 3, 5, 6]
    assert ev(
        "(generator->list (gmerge < (generator 5 6) (generator 1 2) (generator 3)))"
    ) == [1, 2, 3, 5, 6]


def test_gtake_padding_and_gdrop_while(ev) -> None:
    assert ev("(generator->list (gtake (generator 1) 3 'pad))") == [1, "pad", "pad"]
    assert ev("(generator->list (gtake (generator 1 2) 5))") == [1, 2]
    assert ev(
        "(generator->list (gdrop-while (lambda (x) (< x 3)) (generator 1 2 3 1 2)))"
    ) == [3, 1, 2]
    assert ev(
        "(generator->list (gdrop-while (lambda (x) #t) (generator 1 2)))"
    ) is NIL


def test_the_multi_generator_drains(ev) -> None:
    # One-generator fold keeps its shape; several generators fold left to
    # right and stop at the shortest.
    assert ev("(generator-fold + 0 (generator 1 2 3))") == 6
    assert ev("(generator-fold + 0 (generator 1 2) (generator 10 20 30))") == 33
    assert ev("(generator-map->list + (generator 1 2 3) (generator 10 20))") == [11, 22]
    ev("(define seen '())")
    ev("(generator-for-each (lambda (a b) (set! seen (cons (list a b) seen)))"
    "  (generator 1 2) (generator 10 20))")
    assert ev("(reverse seen)") == [[1, 10], [2, 20]]
    # generator->vector! answers how many values it wrote:
    ev("(define sink (make-vector 5 'x))")
    assert ev("(generator->vector! sink 1 (generator 7 8 9))") == 3
    assert ev("(vector->list sink)") == ["x", 7, 8, 9, "x"]
    assert ev("(generator->string (string->generator \"abc\") 2)") == "ab"


def test_the_searching_half(ev, env) -> None:
    assert ev("(generator-find even? (generator 1 3 4 5))") == 4
    assert ev("(generator-find even? (generator 1 3))") is False
    assert ev("(generator-count odd? (generator 1 2 3 4 5))") == 3
    assert ev("(generator-any even? (generator 1 3 4))") is True
    assert ev("(generator-any even? (generator 1 3))") is False
    assert ev("(generator-every odd? (generator 1 3))") is True
    assert ev("(generator-every odd? (generator 1 4))") is False
    assert ev("(generator-every odd? (generator))") is True
    # generator-unfold drives the user's unfold, SRFI 1-shaped — the unfold
    # arrives as an argument, so the library bakes in no dependency:
    evaluate_program(read_all("(import (srfi 1))"), env)
    assert ev("(generator-unfold (make-range-generator 1 5) unfold)") == [1, 2, 3, 4]


def test_the_accumulators(ev) -> None:
    assert ev(
        "(let ((acc (count-accumulator)))"
        "  (for-each acc '(1 2 3)) (acc (eof-object)))"
    ) == 3
    assert ev(
        "(let ((acc (list-accumulator))) (acc 1) (acc 2) (acc (eof-object)))"
    ) == [1, 2]
    assert ev(
        "(let ((acc (reverse-list-accumulator))) (acc 1) (acc 2) (acc (eof-object)))"
    ) == [2, 1]
    assert ev(
        "(vector->list (let ((acc (vector-accumulator)))"
        "  (acc 1) (acc 2) (acc (eof-object))))"
    ) == [1, 2]
    assert ev(
        "(vector->list (let ((acc (reverse-vector-accumulator)))"
        "  (acc 1) (acc 2) (acc (eof-object))))"
    ) == [2, 1]
    assert ev(
        "(let ((acc (string-accumulator))) (acc #\\a) (acc #\\b) (acc (eof-object)))"
    ) == "ab"
    ev("(define bv (let ((acc (bytevector-accumulator))) (acc 1) (acc 2) (acc (eof-object))))")
    assert ev("(list (bytevector-u8-ref bv 0) (bytevector-u8-ref bv 1))") == [1, 2]
    assert ev(
        "(let ((acc (sum-accumulator))) (acc 1) (acc 2) (acc 10) (acc (eof-object)))"
    ) == 13
    assert ev(
        "(let ((acc (product-accumulator))) (acc 2) (acc 3) (acc (eof-object)))"
    ) == 6
    # The ! accumulators fill a pre-made structure from an offset:
    ev("(define v (make-vector 5 'x))")
    ev("(define sink (vector-accumulator! v 1))")
    ev("(sink 'a) (sink 'b)")
    assert ev("(vector->list v)") == ["x", "a", "b", "x", "x"]
    assert ev("(eq? (sink (eof-object)) v)") is True


def test_make_accumulator_builds_a_custom_one(ev) -> None:
    assert ev(
        "(let ((acc (make-accumulator (lambda (obj state) (+ obj state)) 0 (lambda (x) x))))"
        "  (acc 5) (acc 6) (acc (eof-object)))"
    ) == 11


def test_srfi_158_ships_in_both_profiles(env, dsl) -> None:
    assert evaluate_program(
        read_all("(import (srfi 158)) (generator->list (gtake (make-range-generator 1) 2))"),
        env,
    ) == [1, 2]
    assert evaluate_program(
        read_all("(let ((acc (count-accumulator))) (acc 1) (acc 2) (acc (eof-object)))"),
        dsl,
    ) == 2


def test_gmerge_consumes_nothing_until_the_merged_generator_is_called(ev) -> None:
    # SRFI 158: generator operations "return a new generator without
    # consuming any elements from the source generator(s)". Constructing the
    # merge pulls nothing; the first call arms the two heads.
    assert ev(
        "(define calls 0)"
        "(define (counting-gen)"
        "  (let ((n 0))"
        "    (lambda ()"
        "      (set! calls (+ calls 1))"
        "      (set! n (+ n 1))"
        "      (if (< n 3) n (eof-object)))))"
        "(define merged (gmerge < (counting-gen) (counting-gen)))"
        "(define before calls)"
        "(list before (generator->list merged) calls)"
    ) == [0, [1, 1, 2, 2], 6]


def test_variadic_gmerge_is_lazy_at_every_pairing_step(ev) -> None:
    # The variadic branch builds pairwise merges before returning; none of
    # those constructions may pull a value. Three generators, built ahead of
    # the first call, still see zero calls.
    assert ev(
        "(define calls 0)"
        "(define (counting-gen)"
        "  (let ((n 0))"
        "    (lambda ()"
        "      (set! calls (+ calls 1))"
        "      (set! n (+ n 1))"
        "      (if (< n 3) n (eof-object)))))"
        "(define merged (gmerge < (counting-gen) (counting-gen) (counting-gen)))"
        "(define before calls)"
        "(list before (generator->list merged) calls)"
    ) == [0, [1, 1, 1, 2, 2, 2], 9]


def test_gmerge_ties_go_left_and_the_empty_edges_terminate(ev) -> None:
    # The comparator is strict (<): equal heads keep the left generator's
    # value first, so the merge is stable.
    assert ev(
        "(generator->list (gmerge (lambda (a b) (< (car a) (car b)))"
        "  (generator '(1 10) '(2 10))"
        "  (generator '(1 20) '(3 20))))"
    ) == [[1, 10], [1, 20], [2, 10], [3, 20]]
    # One generator is returned untouched; both-empty answers EOF at once.
    assert ev("(generator->list (gmerge < (generator 1 2)))") == [1, 2]
    assert ev("(generator->list (gmerge < (generator)))") is NIL
    assert ev("(generator->list (gmerge < (generator) (generator)))") is NIL
    assert ev("(generator->list (gmerge < (generator 1) (generator)))") == [1]
    assert ev("(generator->list (gmerge < (generator) (generator 2)))") == [2]
    with pytest.raises(LispError, match="at least one generator"):
        ev("(gmerge <)")
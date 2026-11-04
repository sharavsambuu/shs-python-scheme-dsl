"""Recursion and functional programming: the parts a program is *written* with.

Two conformance decisions are pinned here because they are easy to get wrong
quietly: R7RS ``apply`` takes leading arguments before the list it spreads, and
a multi-list ``map`` refuses lists of different lengths rather than truncating
them. The rest is the toolkit: variadic composition, partial application and
currying, the threading macros, and the linear list helpers.

The helpers are deliberately linear. A proper list is a host list and ``cdr``
copies its tail, so structural recursion is O(n²); the last test here is the
guard against drifting back to it.
"""
from __future__ import annotations

import time

import pytest

from shslisp.errors import LispError, LispTypeError
from shslisp.types import NIL, is_nil


# --------------------------------------------------------------------------- #
#  apply, map, for-each — the R7RS shapes                                      #
# --------------------------------------------------------------------------- #

def test_apply_takes_leading_arguments(ev) -> None:
    assert ev("(apply + 1 2 (list 3 4))") == 10
    assert ev("(apply + (list 1 2))") == 3
    assert ev("(apply list 1 2 '())") == [1, 2]
    assert is_nil(ev("(apply list '())"))


def test_apply_spreads_only_its_last_argument(ev) -> None:
    with pytest.raises(LispTypeError):
        ev("(apply + 1 2)")
    with pytest.raises(LispTypeError):
        ev("(apply +)")


def test_map_walks_one_or_many_lists(ev) -> None:
    assert ev("(map inc (list 1 2 3))") == [2, 3, 4]
    assert ev("(map + (list 1 2 3) (list 10 20 30))") == [11, 22, 33]
    assert ev("(map list (list 1 2) (list 3 4) (list 5 6))") == [
        [1, 3, 5],
        [2, 4, 6],
    ]
    assert is_nil(ev("(map inc '())"))


def test_map_refuses_lists_of_different_lengths(ev) -> None:
    with pytest.raises(LispError):
        ev("(map + (list 1 2 3) (list 10 20))")
    with pytest.raises(LispError):
        ev("(map +)")


def test_for_each_walks_one_or_many_lists(ev) -> None:
    assert ev(
        "(define seen '())"
        " (for-each (lambda (x) (push! seen x)) (list 1 2))"
        " (reverse seen)"
    ) == [1, 2]
    assert ev(
        "(define sums '())"
        " (for-each (lambda (a b) (push! sums (+ a b)))"
        "           (list 1 2) (list 10 20))"
        " (reverse sums)"
    ) == [11, 22]


# --------------------------------------------------------------------------- #
#  Composition and partial application                                         #
# --------------------------------------------------------------------------- #

def test_compose_is_variadic_and_right_to_left(ev) -> None:
    assert ev("((compose inc inc) 1)") == 3
    assert ev("((compose inc inc inc) 0)") == 3
    assert ev("((compose inc) 5)") == 6
    assert ev("((compose) 5)") == 5
    # The innermost call receives every argument; the rest take one.
    assert ev("((compose inc +) 1 2)") == 4


def test_pipe_reads_left_to_right(ev) -> None:
    assert ev("((pipe inc inc) 0)") == 2
    assert ev("((pipe (partial + 1) (partial * 2)) 3)") == 8


def test_flip_reverses_the_arguments(ev) -> None:
    assert ev("((flip -) 1 10)") == 9
    assert ev("((flip list) 1 2 3)") == [3, 2, 1]


def test_complement_negates_a_predicate(ev) -> None:
    assert ev("((complement even?) 3)") is True
    assert ev("((complement even?) 4)") is False


def test_partial_binds_leading_arguments(ev) -> None:
    assert ev("((partial + 1 2) 3)") == 6
    assert ev("(map (partial * 2) (list 1 2 3))") == [2, 4, 6]


def test_curry_steps_one_argument_at_a_time(ev) -> None:
    assert ev("((((curry + 3) 1) 2) 3)") == 6
    assert ev("(map ((curry + 2) 10) (list 1 2 3))") == [11, 12, 13]


def test_curry_infers_a_closures_arity(ev) -> None:
    assert ev("((((curry (lambda (a b c) (+ a b c))) 1) 2) 3)") == 6


def test_curry_needs_an_arity_for_a_host_primitive(ev) -> None:
    """A primitive is an opaque Python callable; ask for its arity or be told."""
    with pytest.raises(LispError):
        ev("(curry +)")


def test_procedure_arity(ev) -> None:
    assert ev("(procedure-arity (lambda (a b) a))") == 2
    assert ev("(procedure-arity (lambda (a . rest) a))") is False
    assert ev("(procedure-arity +)") is False
    assert ev("(procedure-arity 3)") is False


# --------------------------------------------------------------------------- #
#  Threading macros                                                            #
# --------------------------------------------------------------------------- #

def test_thread_first_threads_into_the_first_argument(ev) -> None:
    assert ev("(-> 5 inc)") == 6
    assert ev("(-> 5 inc (expt 2))") == 36
    assert ev("(-> 5 (- 2))") == 3  # (- 5 2)
    assert ev("(-> 5)") == 5


def test_thread_last_threads_into_the_last_argument(ev) -> None:
    assert ev("(->> 5 (expt 2))") == 32  # (expt 2 5)
    assert ev("(->> 5 (expt 2) inc)") == 33
    assert ev("(->> 5)") == 5


def test_threading_is_a_pipeline_you_can_read(ev) -> None:
    # `filter` and `foldl` take their list last, so the reads-like-data
    # threading is `->>` here.
    assert ev(
        "(->> (list 1 2 3 4)"
        "     (filter even?)"
        "     (map (partial * 10))"
        "     (foldl + 0))"
    ) == 60


# --------------------------------------------------------------------------- #
#  Linear list helpers                                                         #
# --------------------------------------------------------------------------- #

def test_take_while_and_drop_while(ev) -> None:
    assert ev("(take-while even? (list 2 4 5 6))") == [2, 4]
    assert ev("(drop-while even? (list 2 4 5 6))") == [5, 6]
    assert is_nil(ev("(take-while even? (list 1 2))"))
    assert ev("(drop-while even? (list 1 2))") == [1, 2]
    assert is_nil(ev("(take-while even? '())"))


def test_span_and_partition(ev) -> None:
    assert ev("(span even? (list 2 4 5 6))") == [[2, 4], [5, 6]]
    assert ev("(partition even? (list 1 2 3 4))") == [[2, 4], [1, 3]]
    assert ev("(partition even? '())") == [NIL, NIL]


def test_distinct_keeps_the_first_occurrence(ev) -> None:
    assert ev("(distinct (list 1 2 1 3 2))") == [1, 2, 3]
    # Keys are structural, so equal lists collapse and unequal ones do not.
    assert ev("(distinct (list (list 1 2) (list 1 2) (list 3)))") == [
        [1, 2],
        [3],
    ]


def test_map_index_and_enumerate(ev) -> None:
    assert ev("(map-index (lambda (i x) (list i x)) (list \"a\" \"b\"))") == [
        [0, "a"],
        [1, "b"],
    ]
    assert ev("(enumerate (list \"a\" \"b\"))") == [[0, "a"], [1, "b"]]
    assert is_nil(ev("(map-index list '())"))


def test_filter_map_drops_false_results(ev) -> None:
    assert ev(
        "(filter-map (lambda (x) (if (even? x) (* x 10) #f)) (list 1 2 3 4))"
    ) == [20, 40]


def test_flatten_and_flat_map(ev) -> None:
    assert ev("(flatten (list 1 (list 2 (list 3 4)) 5))") == [1, 2, 3, 4, 5]
    assert is_nil(ev("(flatten '())"))
    assert ev("(flat-map (lambda (x) (list x x)) (list 1 2))") == [1, 1, 2, 2]


def test_product_and_iterate(ev) -> None:
    assert ev("(product (list 1 2 3 4))") == 24
    assert ev("(product '())") == 1
    assert ev("(iterate inc 0 5)") == [0, 1, 2, 3, 4]


# --------------------------------------------------------------------------- #
#  Sorting and grouping by a key                                               #
# --------------------------------------------------------------------------- #

def test_sort_by(ev) -> None:
    assert ev(
        "(sort-by car < (list (list 3 \"c\") (list 1 \"a\") (list 2 \"b\")))"
    ) == [[1, "a"], [2, "b"], [3, "c"]]


def test_max_by_and_min_by(ev) -> None:
    assert ev(
        "(max-by car < (list (list 3 \"c\") (list 1 \"a\") (list 2 \"b\")))"
    ) == [3, "c"]
    assert ev(
        "(min-by car < (list (list 3 \"c\") (list 1 \"a\") (list 2 \"b\")))"
    ) == [1, "a"]
    with pytest.raises(LispError):
        ev("(max-by car < '())")


def test_group_by_keeps_first_seen_order(ev) -> None:
    assert ev("(group-by even? (list 1 2 3 4))") == [
        [False, [1, 3]],
        [True, [2, 4]],
    ]
    # Each entry is a two-element alist entry, so `alist-ref` reads it.
    assert ev("(alist-ref (group-by even? (list 1 2 3 4)) #t)") == [2, 4]


# --------------------------------------------------------------------------- #
#  Memoisation                                                                 #
# --------------------------------------------------------------------------- #

def test_memoize_caches_by_value(ev) -> None:
    assert ev(
        "(define calls 0)"
        " (define (slow x) (set! calls (+ calls 1)) (* x x))"
        " (define fast (memoize slow))"
        " (list (fast 4) (fast 4) (fast 5) calls)"
    ) == [16, 16, 25, 2]
    # Two arguments are one key; equal lists are equal keys.
    assert ev(
        "(define n 0)"
        " (define (pair-sum xs) (set! n (+ n 1)) (foldl + 0 xs))"
        " (define memo (memoize pair-sum))"
        " (list (memo (list 1 2)) (memo (list 1 2)) n)"
    ) == [3, 3, 1]


# --------------------------------------------------------------------------- #
#  The linearity guard                                                         #
# --------------------------------------------------------------------------- #

def test_list_helpers_stay_linear(ev) -> None:
    """Fifty thousand elements must not take quadratic time.

    Structural recursion over the same list costs ~12 s here (``cdr`` copies
    the tail); a linear walk is well under a second. The bound is deliberately
    generous — it is a drift detector, not a benchmark — and sits at 8.0 s
    because slower machines have measured the linear walk at 5.4–5.8 s.
    """
    started = time.monotonic()
    assert ev("(length (map-index (lambda (i x) x) (range 50000)))") == 50000
    assert ev("(length (distinct (map (partial * 2) (range 50000))))") == 50000
    # ``take``/``drop`` are primitives: the recursive spelling copied the tail
    # at every cons, so a full take of 10k cost ~0.65 s.
    assert ev("(length (take (range 50000) 50000))") == 50000
    assert ev("(length (drop (range 50000) 25000))") == 25000
    elapsed = time.monotonic() - started
    assert elapsed < 8.0, f"list helpers look quadratic: {elapsed:.1f}s"

"""The SRFI 160 numeric vector libraries — the numpy bridge (S11).

``(srfi 160 base)`` is the SRFI-4 eight plus the ``@?`` predicate for all
twelve types; ``(srfi 160 f64)`` is the full SRFI-133-shaped operation set.
The payload is a Python ``array.array`` (``shslisp/types.py``'s
``Srfi160Vector``), so the buffer protocol is the numpy seam. What is pinned
here:

* **construction and access** — the reader literal ``#f64(...)``, the
  constructors, ``ref``/``set!`` range and domain checks (an exact ``1`` is
  not an ``f64`` element — the spec's rule, enforced loudly);
* **the operation set** — fold's state-first ``kons``, map/for-each across
  several vectors (shortest wins), cumulate, searching, partition's two
  values, and the copy family;
* **the deviations** — ``f64vector-comparator`` does not exist (SRFI 128 is
  not scheduled), and the other ten per-type full libraries do not exist yet.

The plan this implements is S11 in ``docs/SRFI_TASKS.md``; the matrix rows
are in ``docs/srfi.md``.
"""
from __future__ import annotations

import pytest

from shslisp.errors import LispError, LispTypeError
from shslisp.evaluator import evaluate_program
from shslisp.reader import read_all
from shslisp.runtime import make_env


def run(env, source: str):
    return evaluate_program(read_all(source), env)


@pytest.fixture
def env():
    return make_env(install_tetris=False)


@pytest.fixture
def ev(env):
    return lambda source: run(env, source)


# --------------------------------------------------------------------------- #
#  (srfi 160 base): twelve types, the SRFI-4 eight, and the @? predicates     #
# --------------------------------------------------------------------------- #


def test_base_construction_and_access_for_all_twelve_types(ev) -> None:
    for tc, fill, elems in (
        ("u8", 0, [1, 2, 255]), ("s8", -1, [-128, 127, 0]),
        ("u16", 0, [65535, 1]), ("s16", -1, [-32768, 32767]),
        ("u32", 0, [4294967295, 7]), ("s32", -1, [-2147483648, 8]),
        ("f32", 0.0, [1.5, 2.5]), ("f64", 0.0, [1.5, -2.5]),
    ):
        elems_src = " ".join(str(e) for e in elems)
        assert ev(f"({tc}vector? (make-{tc}vector 3))") is True
        assert ev(f"({tc}vector-length (make-{tc}vector 3 {fill}))") == 3
        assert ev(f"({tc}vector->list (list->{tc}vector '({elems_src})))") == elems
        assert ev(f"({tc}? (car ({tc}vector->list (list->{tc}vector '({elems_src})))))") is True


def test_complex_types_store_interleaved_parts(ev) -> None:
    assert ev("(c64vector->list (c64vector 1.5 2.5))") == [complex(1.5), complex(2.5)]
    assert ev("(c64? (c64vector-ref (c64vector 1.5) 0))") is True
    assert ev("(c128vector-length (make-c128vector 2 0.0))") == 2


def test_the_validity_predicates_ask_the_spec_question(ev) -> None:
    assert ev("(u8? 255)") is True
    assert ev("(u8? 256)") is False
    assert ev("(u8? -1)") is False
    assert ev("(s8? -128)") is True
    assert ev("(s8? 128)") is False
    assert ev("(u64? 18446744073709551615)") is True
    # A float vector's element is an *inexact* real — an exact 1 is not one:
    assert ev("(f64? 1.5)") is True
    assert ev("(f64? 1)") is False
    assert ev("(f32? 1)") is False
    # ...and a bool is not an exact integer here:
    assert ev("(u8? #t)") is False


def test_construction_rejects_invalid_elements_loudly(ev) -> None:
    with pytest.raises(LispTypeError, match="not a valid f64 element"):
        ev("(f64vector 1)")
    with pytest.raises(LispTypeError, match="not a valid u8 element"):
        ev("(u8vector 300)")
    with pytest.raises(LispTypeError, match="out of range"):
        ev("(f64vector-ref (f64vector 1.0) 5)")


def test_the_reader_reads_the_external_representations(ev) -> None:
    assert ev("(f64vector->list #f64(1.5 2.5 -3.0))") == [1.5, 2.5, -3.0]
    assert ev("(u16vector->list #u16(1 2 65535))") == [1, 2, 65535]
    assert ev("(s8vector->list #s8(-128 127))") == [-128, 127]
    # `#u8(` remains the R7RS bytevector:
    assert ev("(bytevector? #u8(1 2))") is True
    assert ev("(u8vector? #u8(1 2))") is False


def test_the_printer_writes_what_the_reader_reads(ev) -> None:
    from shslisp.printer import to_string

    written = to_string(ev("#f64(1.0 +inf.0 -2.5)"), write=True)
    assert written == "#f64(1.0 +inf.0 -2.5)"
    assert ev(f"(equal? (list->f64vector (f64vector->list {written})) {written})") is True


def test_equal_is_elementwise_by_type(ev) -> None:
    assert ev("(equal? (f64vector 1.0 2.0) (f64vector 1.0 2.0))") is True
    assert ev("(equal? (f64vector 1.0) (f64vector 2.0))") is False
    assert ev("(f64vector= (f64vector 1.0 2.0) (f64vector 1.0 2.0) (f64vector 1.0 2.0))") is True
    assert ev("(f64vector= (f64vector 1.0) (f64vector 1.0 2.0))") is False


# --------------------------------------------------------------------------- #
#  (srfi 160 f64): the SRFI-133-shaped operation set                          #
# --------------------------------------------------------------------------- #


def test_unfold_builds_from_a_seed_and_runs_right_to_left_when_asked(ev) -> None:
    assert ev(
        "(f64vector->list (f64vector-unfold (lambda (i s) (values (* 1.0 i) (+ s 1))) 4 0.0))"
    ) == [0.0, 1.0, 2.0, 3.0]
    # unfold-right fills from the right: same final vector for an index-based
    # f, but the calls (and the state threading) run right to left — pinned
    # by capturing the call order (most recent cons'd first).
    ev("(define order '())")
    assert ev(
        "(f64vector->list (f64vector-unfold-right"
        "  (lambda (i s) (set! order (cons i order)) (values (* 1.0 i) (+ s 1))) 4 0.0))"
    ) == [0.0, 1.0, 2.0, 3.0]
    assert ev("order") == [0, 1, 2, 3]


def test_fold_is_state_first_as_srfi_133_spells_it(ev) -> None:
    # (kons accum elem) — the spec's "state first and the element second".
    assert ev("(f64vector-fold (lambda (acc x) (cons x acc)) '() (f64vector 1.0 2.0 3.0))") == [
        3.0, 2.0, 1.0,
    ]
    assert ev("(f64vector-fold-right (lambda (acc x) (cons x acc)) '() (f64vector 1.0 2.0 3.0))") == [
        1.0, 2.0, 3.0,
    ]
    # Multi-vector folds stop at the shortest:
    assert ev(
        "(f64vector-fold (lambda (acc a b) (+ acc (* a b))) 0.0"
        " (f64vector 1.0 2.0 3.0) (f64vector 10.0 20.0))"
    ) == 50.0


def test_map_and_for_each_across_vectors(ev) -> None:
    assert ev("(f64vector->list (f64vector-map (lambda (x) (* x x)) (f64vector 1.0 2.0 3.0)))") == [
        1.0, 4.0, 9.0,
    ]
    assert ev(
        "(f64vector->list (f64vector-map + (f64vector 1.0 2.0 3.0) (f64vector 10.0 20.0)))"
    ) == [11.0, 22.0]
    ev("(define v (f64vector 1.0 2.0 3.0))")
    ev("(f64vector-map! (lambda (x) (* x 10.0)) v)")
    assert ev("(f64vector->list v)") == [10.0, 20.0, 30.0]
    ev("(define seen '())")
    ev("(f64vector-for-each (lambda (x) (set! seen (cons x seen))) (f64vector 1.0 2.0))")
    assert ev("seen") == [2.0, 1.0]


def test_cumulate_answers_the_running_totals(ev) -> None:
    assert ev("(f64vector->list (f64vector-cumulate + 0.0 (f64vector 1.0 2.0 3.0)))") == [
        1.0, 3.0, 6.0,
    ]


def test_take_drop_segment_and_the_copy_family(ev) -> None:
    ev("(define v (f64vector 1.0 2.0 3.0 4.0 5.0))")
    assert ev("(f64vector->list (f64vector-take v 2))") == [1.0, 2.0]
    assert ev("(f64vector->list (f64vector-take-right v 2))") == [4.0, 5.0]
    assert ev("(f64vector->list (f64vector-drop v 2))") == [3.0, 4.0, 5.0]
    assert ev("(f64vector->list (f64vector-drop-right v 2))") == [1.0, 2.0, 3.0]
    assert ev("(map f64vector->list (f64vector-segment v 2))") == [
        [1.0, 2.0], [3.0, 4.0], [5.0],
    ]
    assert ev("(f64vector->list (f64vector-copy v 1 4))") == [2.0, 3.0, 4.0]
    assert ev("(f64vector->list (f64vector-reverse-copy v))") == [5.0, 4.0, 3.0, 2.0, 1.0]
    assert ev("(f64vector->list (f64vector-append (f64vector 1.0) (f64vector 2.0 3.0)))") == [
        1.0, 2.0, 3.0,
    ]
    assert ev("(f64vector->list (f64vector-concatenate (list (f64vector 1.0) (f64vector 2.0))))") == [
        1.0, 2.0,
    ]
    assert ev(
        "(f64vector->list (f64vector-append-subvectors (f64vector 1.0 2.0 3.0) 1 3 (f64vector 9.0) 0 1))"
    ) == [2.0, 3.0, 9.0]


def test_searching_and_partition(ev) -> None:
    ev("(define v (f64vector 1.0 2.0 3.0 1.0))")
    assert ev("(f64vector-index (lambda (x) (> x 2.5)) v)") == 2
    assert ev("(f64vector-index-right (lambda (x) (> x 2.5)) v)") == 2
    assert ev("(f64vector-index (lambda (x) #f) v)") is False
    assert ev("(f64vector-skip (lambda (x) (< x 2.0)) v)") == 1
    assert ev("(f64vector-count (lambda (x) (< x 3.0)) v)") == 3
    assert ev("(f64vector-any (lambda (x) (and (> x 2.5) x)) v)") == 3.0
    assert ev("(f64vector-every (lambda (x) (> x 0.0)) v)") is True
    assert ev("(f64vector->list (f64vector-take-while (lambda (x) (< x 3.0)) v))") == [1.0, 2.0]
    assert ev("(f64vector->list (f64vector-drop-while (lambda (x) (< x 3.0)) v))") == [3.0, 1.0]
    assert ev("(f64vector->list (f64vector-filter (lambda (x) (> x 1.5)) v))") == [2.0, 3.0]
    assert ev("(f64vector->list (f64vector-remove (lambda (x) (> x 1.5)) v))") == [1.0, 1.0]
    # partition answers two values: a full-length vector (yes-part first,
    # then the no-part) and the yes count.
    assert ev(
        "(call-with-values (lambda () (f64vector-partition (lambda (x) (> x 1.5)) v))"
        "  (lambda (kept yes) (list (f64vector->list kept) yes)))"
    ) == [[2.0, 3.0, 1.0, 1.0], 2]


def test_mutators(ev) -> None:
    ev("(define v (f64vector 1.0 2.0 3.0))")
    ev("(f64vector-swap! v 0 2)")
    assert ev("(f64vector->list v)") == [3.0, 2.0, 1.0]
    ev("(f64vector-fill! v 9.0 1 3)")
    assert ev("(f64vector->list v)") == [3.0, 9.0, 9.0]
    ev("(f64vector-reverse! v)")
    assert ev("(f64vector->list v)") == [9.0, 9.0, 3.0]
    ev("(define w (make-f64vector 4 0.0))")
    ev("(f64vector-copy! w 1 v 0 2)")
    assert ev("(f64vector->list w)") == [0.0, 9.0, 9.0, 0.0]
    ev("(define x (make-f64vector 3 0.0))")
    ev("(f64vector-reverse-copy! x 0 v 0 3)")
    assert ev("(f64vector->list x)") == [3.0, 9.0, 9.0]
    ev("(f64vector-unfold! (lambda (i s) (values (* 1.0 i) s)) x 0 3 0)")
    assert ev("(f64vector->list x)") == [0.0, 1.0, 2.0]


def test_conversions_and_the_generator(ev) -> None:
    assert ev("(f64vector->list (vector->f64vector (vector 1.0 2.0)))") == [1.0, 2.0]
    assert ev("(vector? (f64vector->vector (f64vector 1.0 2.0)))") is True
    assert ev("(f64vector->list (reverse-list->f64vector '(1.0 2.0 3.0)))") == [3.0, 2.0, 1.0]
    assert ev("(reverse-f64vector->list (f64vector 1.0 2.0 3.0))") == [3.0, 2.0, 1.0]
    assert ev(
        "(let ((g (make-f64vector-generator (f64vector 1.5 2.5))))"
        "  (list (g) (g) (eof-object? (g))))"
    ) == [1.5, 2.5, True]


def test_write_f64vector_renders_the_literal(ev) -> None:
    ev("(define out (open-output-string))")
    ev("(write-f64vector (f64vector 1.0 2.5) out)")
    assert ev("(get-output-string out)") == "#f64(1.0 2.5)"


# --------------------------------------------------------------------------- #
#  The documented deviations, loudly, and the wiring                          #
# --------------------------------------------------------------------------- #


def test_there_is_no_f64vector_comparator(ev) -> None:
    from shslisp.errors import LispNameError

    with pytest.raises(LispNameError):
        ev("f64vector-comparator")


def test_the_other_full_libraries_do_not_exist_yet(env) -> None:
    # The kernel is generic, but only f64 has its full library: importing
    # (srfi 160 u8) fails loudly rather than binding a partial surface.
    with pytest.raises(LispError, match="no such library"):
        run(env, "(import (srfi 160 u8))")


def test_both_libraries_import_and_the_default_profile_preimports_them() -> None:
    env = make_env(install_tetris=False)
    run(env, "(import (srfi 160 base) (srfi 160 f64))")
    dsl = make_env(install_tetris=False)
    assert run(dsl, "(f64vector->list (f64vector 1.0 2.0))") == [1.0, 2.0]
    assert run(dsl, "(f64? 1.0)") is True


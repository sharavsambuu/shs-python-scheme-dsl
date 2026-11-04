"""The standard libraries — ``shslisp/prelude.scm`` and ``tetris/prelude.scm``.

Everything under test here is written in the DSL itself, so a failure points at
a Lisp definition rather than at the host.
"""
from __future__ import annotations

import io

import pytest

from shslisp.reader import read_all
from shslisp.evaluator import evaluate_program
from shslisp.runtime import make_env
from shslisp.types import NIL, intern, is_nil


# --------------------------------------------------------------------------- #
#  The language prelude                                                        #
# --------------------------------------------------------------------------- #

def test_combinators(ev) -> None:
    assert ev("(identity 7)") == 7
    assert ev("((compose inc inc) 1)") == 3
    assert ev("((flip -) 1 10)") == 9
    assert ev("((const 5) 'anything)") == 5


def test_list_accessors(ev) -> None:
    assert ev("(first (list 1 2 3))") == 1
    assert ev("(second (list 1 2 3))") == 2
    assert ev("(caddr (list 1 2 3))") == 3
    assert ev("(rest (list 1 2 3))") == [2, 3]
    assert ev("(last (list 1 2 3))") == 3


def test_repeat_calls_a_thunk_n_times(ev) -> None:
    assert ev("(define n 0) (repeat 5 (lambda () (set! n (+ n 1)))) n") == 5
    assert is_nil(ev("(repeat 0 (lambda () 1))"))


def test_alist_helpers(ev) -> None:
    assert ev("(alist-ref (list (list 'a 1)) 'a)") == 1
    assert ev("(alist-ref (list (list 'a 1)) 'b)") is False
    assert ev("(alist-has? (list (list 'a 1)) 'a)") is True


# --------------------------------------------------------------------------- #
#  Promises and parameters                                                      #
# --------------------------------------------------------------------------- #

def test_force_memoises(ev) -> None:
    ev("(define n 0)")
    ev("(define p (delay (begin (set! n (+ n 1)) 42)))")
    assert ev("(force p)") == 42
    assert ev("(force p)") == 42
    assert ev("n") == 1  # the thunk ran exactly once


def test_force_passes_a_non_promise_through(ev) -> None:
    assert ev("(force 7)") == 7


def test_delay_force_flattens(ev) -> None:
    ev("(define n 0)")
    ev("(define p (delay-force (delay (begin (set! n (+ n 1)) 5))))")
    assert ev("(force p)") == 5
    assert ev("n") == 1


def test_parameters_read_set_and_restore(ev) -> None:
    ev("(define p (make-parameter 10))")
    assert ev("(p)") == 10
    assert ev("(parameterize ((p 20)) (p))") == 20
    assert ev("(p)") == 10


def test_parameterize_restores_after_a_raise(ev) -> None:
    ev("(define q (make-parameter 1))")
    assert ev('(guard (e (#t (q))) (parameterize ((q 99)) (error "boom")))') == 1
    assert ev("(q)") == 1


def test_parameterize_nests(ev) -> None:
    ev("(define r (make-parameter 0))")
    assert ev("(parameterize ((r 1)) (parameterize ((r 2)) (r)))") == 2
    assert ev("(parameterize ((r 1)) (parameterize ((r 2)) (r)) (r))") == 1

"""Wave 2 (C-02) TDD tests: SRFI 158 coroutine generators and SRFI 190 syntax."""
from __future__ import annotations

from shslisp.runtime import make_env, run as lisp_run


def test_make_coroutine_generator_yields_and_finishes_with_eof() -> None:
    env = make_env()
    assert (
        lisp_run(
            """
            (import (srfi 158))
            (define g
              (make-coroutine-generator
               (lambda (yield)
                 (for-each (lambda (x) (yield (* x 10))) '(1 2 3)))))
            (list (g) (g) (g) (eof-object? (g)) (eof-object? (g)))
            """,
            env,
        )
        == [10, 20, 30, True, True]
    )


def test_make_for_each_generator_lazily_drives_collection() -> None:
    env = make_env()
    assert (
        lisp_run(
            """
            (import (srfi 158))
            (define seen '())
            (define g
              (make-for-each-generator
               (lambda (f xs)
                 (for-each (lambda (x)
                             (set! seen (cons x seen))
                             (f x))
                           xs))
               '(a b c)))
            (define first (g))
            (define after-one (length seen))
            (define rest (generator->list g))
            (list first after-one rest)
            """,
            env,
        )
        == ["a", 1, ["b", "c"]]
    )


def test_srfi190_coroutine_generator_and_define_coroutine_generator() -> None:
    env = make_env()
    assert (
        lisp_run(
            """
            (import (srfi 158) (srfi 190))
            (define-coroutine-generator (range-gen n)
              (let loop ((i 0))
                (when (< i n)
                  (yield i)
                  (loop (+ i 1)))))
            (define g2
              (coroutine-generator
               (yield 'x)
               (yield 'y)))
            (list (generator->list (range-gen 4))
                  (generator->list g2))
            """,
            env,
        )
        == [[0, 1, 2, 3], ["x", "y"]]
    )

"""Wave 1 (C-01) TDD tests: SRFI 226 delimited continuations & prompts."""
from __future__ import annotations

import pytest

from shslisp.errors import LispError
from shslisp.runtime import make_env, run as lisp_run


def test_prompt_tag_predicates_and_default_tag() -> None:
    env = make_env()
    assert (
        lisp_run(
            """
            (import (srfi 226))
            (define t1 (make-continuation-prompt-tag 'alpha))
            (define t2 (make-continuation-prompt-tag 'alpha))
            (list (continuation-prompt-tag? (default-continuation-prompt-tag))
                  (continuation-prompt-tag? t1)
                  (eq? t1 t2)
                  (continuation-prompt-tag? 42))
            """,
            env,
        )
        == [True, True, False, False]
    )


def test_call_with_prompt_and_abort_custom_and_default_handlers() -> None:
    env = make_env()
    assert (
        lisp_run(
            """
            (import (srfi 226))
            (define tag (make-continuation-prompt-tag 'p))
            (list
             (call-with-continuation-prompt
              (lambda ()
                (+ 1 (abort-current-continuation tag 10 20)))
              tag
              (lambda (a b) (+ a b)))
             (call-with-continuation-prompt
              (lambda ()
                (abort-current-continuation
                 (default-continuation-prompt-tag)
                 (lambda () 77)))))
            """,
            env,
        )
        == [30, 77]
    )


def test_continuation_prompt_available_and_barrier() -> None:
    env = make_env()
    assert (
        lisp_run(
            """
            (import (srfi 226))
            (define tag (make-continuation-prompt-tag 'b))
            (list
             (continuation-prompt-available? tag)
             (call-with-continuation-prompt
              (lambda ()
                (list
                 (continuation-prompt-available? tag)
                 (call-with-continuation-barrier
                  (lambda () (continuation-prompt-available? tag)))))
              tag
              (lambda (x) x)))
            """,
            env,
        )
        == [False, [True, False]]
    )

    with pytest.raises(LispError):
        lisp_run(
            """
            (import (srfi 226))
            (define tag (make-continuation-prompt-tag 'b2))
            (call-with-continuation-prompt
             (lambda ()
               (call-with-continuation-barrier
                (lambda ()
                  (abort-current-continuation tag 1))))
             tag
             (lambda (x) x))
            """,
            env,
        )


def test_composable_continuation_suspends_and_resumes_through_map() -> None:
    env = make_env()
    assert (
        lisp_run(
            """
            (import (srfi 226))
            (define tag (make-continuation-prompt-tag 'yield))
            (define saved #f)
            (define r1
              (call-with-continuation-prompt
               (lambda ()
                 (map (lambda (x)
                        (+ x (call-with-composable-continuation
                              (lambda (k)
                                (set! saved k)
                                (abort-current-continuation tag x))
                              tag)))
                      '(10 20)))
               tag
               (lambda (v) (list 'paused v))))
            (define r2
              (call-with-continuation-prompt
               (lambda () (saved 1))
               tag
               (lambda (v) (list 'paused v))))
            (define r3
              (call-with-continuation-prompt
               (lambda () (saved 2))
               tag
               (lambda (v) (list 'paused v))))
            (list r1 r2 r3)
            """,
            env,
        )
        == [["paused", 10], ["paused", 20], [11, 22]]
    )

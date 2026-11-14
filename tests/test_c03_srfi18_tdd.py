"""Wave 3 (C-03) TDD tests: SRFI 18 cooperative fibers, mutexes, and condition variables."""
from __future__ import annotations

from shslisp.runtime import make_env, run as lisp_run


def test_thread_lifecycle_start_yield_join_and_predicates() -> None:
    env = make_env()
    assert (
        lisp_run(
            """
            (import (srfi 18))
            (define log '())
            (define (push! x) (set! log (cons x log)))
            (define t1
              (make-thread
               (lambda ()
                 (push! 't1-a)
                 (thread-yield!)
                 (push! 't1-b)
                 42)
               'worker-1))
            (define t2
              (make-thread
               (lambda ()
                 (push! 't2-a)
                 (thread-yield!)
                 (push! 't2-b)
                 99)
               'worker-2))
            (thread-start! t1)
            (thread-start! t2)
            (define r1 (thread-join! t1))
            (define r2 (thread-join! t2))
            (list (thread? t1)
                  (thread? (current-thread))
                  (thread-name t1)
                  r1
                  r2
                  (reverse log))
            """,
            env,
        )
        == [True, True, "worker-1", 42, 99, ["t1-a", "t2-a", "t1-b", "t2-b"]]
    )


def test_mutex_and_condition_variable_coordination() -> None:
    env = make_env()
    assert (
        lisp_run(
            """
            (import (srfi 18))
            (define m (make-mutex 'm1))
            (define cv (make-condition-variable 'cv1))
            (define ready #f)
            (define observed #f)
            (define consumer
              (make-thread
               (lambda ()
                 (mutex-lock! m)
                 (let loop ()
                   (if ready
                       (begin
                         (set! observed ready)
                         (mutex-unlock! m))
                       (begin
                         (mutex-unlock! m cv)
                         (mutex-lock! m)
                         (loop)))))))
            (define producer
              (make-thread
               (lambda ()
                 (mutex-lock! m)
                 (set! ready 'payload)
                 (condition-variable-signal! cv)
                 (mutex-unlock! m))))
            (thread-start! consumer)
            (thread-yield!)
            (thread-start! producer)
            (thread-join! consumer)
            (thread-join! producer)
            (list (mutex? m) (condition-variable? cv) observed)
            """,
            env,
        )
        == [True, True, "payload"]
    )

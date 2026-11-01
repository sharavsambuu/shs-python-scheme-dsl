"""Deep recursion: the ceiling, the thread that pays for it, and the error.

The interpreter promises a million nested *non-tail* calls. Tail calls are
flat, so they never touch this; what is tested here is the budget the host
stack has to back, and the fact that running out is still a Lisp error.

:func:`lisp.stack.run_with_deep_stack` is the mechanism: a worker thread with a
large stack reserved, so the promise does not depend on the host's default
stack size. These tests check the mechanism itself (thread, exceptions,
idempotence) and then that a script really gets it end to end.
"""
from __future__ import annotations

import io
import threading

import pytest

from lisp import evaluator
from lisp.errors import LispBudgetError, LispRecursionError
from lisp.evaluator import evaluate_program
from lisp.reader import read_all
from lisp.runtime import make_env
from lisp.stack import STACK_BYTES, on_deep_stack, run_with_deep_stack
from lisp.__main__ import run_script

SUM_TO = "(define (s n) (if (= n 0) 0 (+ n (s (- n 1)))))"


# --------------------------------------------------------------------------- #
#  The mechanism                                                               #
# --------------------------------------------------------------------------- #

def test_it_runs_on_its_own_thread_with_a_reserved_stack() -> None:
    seen = {}

    def record() -> int:
        seen["name"] = threading.current_thread().name
        seen["deep"] = on_deep_stack()
        return 42

    assert run_with_deep_stack(record) == 42
    assert seen["name"] == "lisp-program"
    assert seen["deep"] is True
    # The caller's own thread is untouched.
    assert on_deep_stack() is False


def test_the_reservation_is_big_enough_to_matter() -> None:
    assert STACK_BYTES >= 64 * 1024 * 1024


def test_nested_entry_points_do_not_spawn_another_thread() -> None:
    def inner() -> str:
        return threading.current_thread().name

    def outer():
        return threading.current_thread().name, run_with_deep_stack(inner)

    assert run_with_deep_stack(outer) == ("lisp-program", "lisp-program")


def test_a_returned_value_crosses_back() -> None:
    assert run_with_deep_stack(lambda a, b=0: a + b, 1, b=2) == 3


def test_an_exception_crosses_back_unchanged() -> None:
    class Boom(Exception):
        pass

    def explode() -> None:
        raise Boom("from the worker")

    with pytest.raises(Boom, match="from the worker"):
        run_with_deep_stack(explode)


def test_a_lisp_error_crosses_back_as_that_error(monkeypatch) -> None:
    monkeypatch.setattr(evaluator, "DEPTH_LIMIT", 100)
    env = make_env(install_tetris=False)

    def run() -> None:
        evaluate_program(read_all(SUM_TO + " (s 500)"), env)

    with pytest.raises(LispRecursionError):
        run_with_deep_stack(run)


# --------------------------------------------------------------------------- #
#  Deep recursion, on the stack that was reserved                              #
# --------------------------------------------------------------------------- #

def test_a_hundred_and_fifty_thousand_nested_calls_fit() -> None:
    env = make_env(install_tetris=False)

    def run() -> int:
        evaluate_program(read_all(SUM_TO), env)
        return evaluate_program(read_all("(s 150000)"), env)

    assert run_with_deep_stack(run) == 150000 * 150001 // 2


def test_run_script_gives_a_script_the_deep_stack(tmp_path) -> None:
    path = tmp_path / "deep.scm"
    path.write_text(SUM_TO + "\n(s 150000)\n", encoding="utf-8")
    result, _env = run_script(str(path), out=io.StringIO(), tetris=False)
    assert result == 150000 * 150001 // 2


# --------------------------------------------------------------------------- #
#  The step budget                                                              #
# --------------------------------------------------------------------------- #
#  The companion ceiling. Tail calls are *flat*, so a runaway loop costs no
#  depth — the stack budget cannot see it. Each root evaluation instead counts
#  its trampoline steps against STEPS_BUDGET, and the raise is still a Lisp
#  error: the program ends, the host never hangs.

def test_a_runaway_tail_loop_ends_as_a_lisp_error() -> None:
    # Depth stays at 1 the whole time: the loop is in tail position forever.
    # Only the step budget can see it, and it does — naming the shape of
    # what ran away, not a bare crash.
    env = make_env(install_tetris=False)
    with pytest.raises(LispBudgetError, match="endless loop"):
        evaluate_program(
            read_all("(define (loop n) (loop (+ n 1))) (loop 0)"), env
        )


def test_the_budget_is_per_root_call() -> None:
    # A spent evaluation does not poison the next one: each root starts a
    # fresh counter, so one bad frame cannot starve the frames after it.
    env = make_env(install_tetris=False)
    broken = "(define (loop n) (loop (+ n 1)))"
    evaluate_program(read_all(broken), env)
    with pytest.raises(LispBudgetError):
        evaluate_program(read_all("(loop 0)"), env)
    assert evaluate_program(read_all("(+ 40 2)"), env) == 42


def test_a_non_tail_recursion_meets_some_budget_first() -> None:
    # The two budgets overlap by design: depth costs steps, so a deep
    # non-tail recursion can meet the step budget before the stack one —
    # either way the program gets a Lisp error naming *its* ceiling, never a
    # half-raised Python exception.
    env = make_env(install_tetris=False)
    evaluate_program(read_all("(define (f n) (+ 1 (f n)))"), env)
    with pytest.raises((LispRecursionError, LispBudgetError)):
        evaluate_program(read_all("(f 0)"), env)

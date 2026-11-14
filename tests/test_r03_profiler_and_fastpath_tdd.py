"""Locked Frontier TDD suite for R-03: per-procedure step hotspot profiler & _run fast-path."""
from __future__ import annotations

from shslisp import make_env, run
from shslisp.evaluator import measure_calls, measure_steps


def test_measure_calls_reports_per_procedure_counts_and_steps() -> None:
    env = make_env()
    run("(define (leaf x) (+ x 1))", env)
    run("(define (branch n) (if (= n 0) 0 (+ (leaf n) (branch (- n 1)))))", env)

    result, steps, counts = measure_calls(lambda: run("(branch 5)", env))
    assert result == 20  # (5+1)+(4+1)+(3+1)+(2+1)+(1+1) = 20
    assert steps > 0
    assert counts["branch"] == 6
    assert counts["leaf"] == 5


def test_measure_calls_is_isolated_from_outer_measure_steps() -> None:
    env = make_env()
    run("(define (inc x) (+ x 1))", env)

    def outer() -> int:
        res, _steps, counts = measure_calls(lambda: run("(inc 10)", env))
        assert counts["inc"] == 1
        return res

    res, outer_steps = measure_steps(outer)
    assert res == 11
    assert outer_steps >= 0


def test_syntax_rules_macro_in_loop_stays_exact() -> None:
    env = make_env()
    run(
        "(define-syntax my-add "
        "  (syntax-rules () ((_ a b) (+ a b))))",
        env,
    )
    run(
        "(define (sum-loop n acc) "
        "  (if (= n 0) acc (sum-loop (- n 1) (my-add acc n))))",
        env,
    )
    res, _steps, counts = measure_calls(lambda: run("(sum-loop 10 0)", env))
    assert res == 55
    assert counts["sum-loop"] == 11

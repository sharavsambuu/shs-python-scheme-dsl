"""Performance smoke: the wall stated, not measured, is not measured.

H2 from docs/HARDENING_TASKS.md. Tree-walking interpreter on CPython is
host-dependent; these numbers are upper bounds with 10× headroom, not
benchmarks. They catch *regressions* (a trampoline becoming recursive, the
budget collapsing) not *optimizations*.

Bounded: fib 20 (~6765 calls), tail loop 10k, map 1k — well under a second
on a laptop, well above CI noise.
"""
from __future__ import annotations

import time

from shslisp import run


def test_perf_tail_loop_under_bound():
    # Tail loop must not hit the depth/step budget and must be fast.
    t0 = time.time()
    v = run("(define (loop n) (if (= n 0) 0 (loop (- n 1)))) (loop 10000)")
    dt = time.time() - t0
    assert v == 0
    # Generous: 10k tail iterations on CPython tree-walker ~0.05–0.2s. 5s is
    # flaky-proof but still catches a trampoline regression (which would be
    # ~100× slower or RecursionError).
    assert dt < 5.0, f"tail loop 10k took {dt:.2f}s"


def test_perf_fib20_under_bound():
    t0 = time.time()
    v = run("(define (fib n) (if (< n 2) n (+ (fib (- n 1)) (fib (- n 2))))) (fib 20)")
    dt = time.time() - t0
    assert v == 6765
    # fib 20 ~13529 calls; tree-walk ~0.3–0.8s locally. 10s is the regression
    # sentinel (a trampoline collapse would blow past it).
    assert dt < 10.0, f"fib 20 took {dt:.2f}s"


def test_perf_map_iota_under_bound():
    t0 = time.time()
    v = run("(map (cut * 2 <>) (iota 1000))")  # SRFI 26 + SRFI 1
    dt = time.time() - t0
    # Cross-check length without importing internals.
    assert len(v) == 1000  # type: ignore[arg-type]
    assert dt < 5.0, f"map iota 1000 took {dt:.2f}s"

"""parallel_map.py — CPU-bound work on many cores, via processes.

Run with:  python examples/concurrency/05-parallel-map/parallel_map.py

This is the example where the "multi-core" promise is kept literally. Threads
cannot do it — CPython's GIL serializes CPU-bound Python code, which is why
04-structured-concurrency counts waiting, not computing. *Processes* each get
their own interpreter and their own GIL, so N cores really do work at once.

The pattern it teaches — `parallel-map` over a pool of env-per-process
workers — is the multiprocessing shape of this example set's design rule:
- each worker process builds its OWN `make_env()` once (envs are cheap and
  self-contained; there is no shared state to break);
- the Scheme function is shipped to workers as SOURCE (a string) — closures
  do not cross process boundaries, source does;
- tasks and results are plain data (numbers), the only thing that pickles
  cleanly across the seam.

The workload: counting primes in eight ranges, with a trial-division
`prime?` written in Scheme. Deliberately naive — the point is honest CPU
work, not number theory.
"""

import multiprocessing as mp
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # the repo root

from lisp import make_env, run

# --- the Scheme side: shipped to every worker as source ------------------------

WORKER_SOURCE = """
(define (prime? n)
  (if (< n 2)
      #f
      (let loop ((d 2))
        (cond ((> (* d d) n) #t)
              ((= 0 (modulo n d)) #f)
              (else (loop (+ d 1)))))))

(define (count-primes start end)
  (let loop ((n start) (count 0))
    (if (>= n end)
        count
        (loop (+ n 1) (if (prime? n) (+ count 1) count)))))
"""

# the workload: the integers [2, 20000), split into eight contiguous ranges
RANGE_START, RANGE_END, TASKS = 2, 20000, 8
_step = (RANGE_END - RANGE_START) // TASKS
BOUNDS = [
    (lo, min(lo + _step, RANGE_END))
    for lo in range(RANGE_START, RANGE_END, _step)
]

# --- the worker side: one env per PROCESS ---------------------------------------

ENV = None  # built once per worker process, in the initializer


def worker_init() -> None:
    global ENV
    ENV = make_env(install_tetris=False)
    run(WORKER_SOURCE, ENV)


def score(bounds: tuple[int, int]) -> tuple[int, int, float]:
    start, end = bounds
    began = time.perf_counter()
    count = run(f"(count-primes {start} {end})", ENV)
    return start, end, count, time.perf_counter() - began


def main() -> None:
    cores = mp.cpu_count()
    print(f"== counting primes in [{RANGE_START}, {RANGE_END}) on {cores} cores ==")
    print(f"(main) {TASKS} ranges: {BOUNDS[0][0]}-{BOUNDS[-1][1]}, "
          f"one Scheme evaluation each\n")

    # --- the parallel run: a pool of env-per-process workers --------------------
    began = time.perf_counter()
    with mp.Pool(processes=TASKS, initializer=worker_init) as pool:
        parallel = pool.map(score, BOUNDS, chunksize=1)
    par_time = time.perf_counter() - began

    for start, end, count, spent in parallel:
        print(f"  [{start:>6}, {end:>6})  primes: {count:>5}   ({spent:.3f}s in a worker)")

    # --- the sequential run: the same evaluations, one process ------------------
    print()
    seq_env = make_env(install_tetris=False)
    run(WORKER_SOURCE, seq_env)
    began = time.perf_counter()
    for start, end, _, _ in parallel:  # same ranges, one after the other
        run(f"(count-primes {start} {end})", seq_env)
    seq_time = time.perf_counter() - began

    total = sum(count for _, _, count, _ in parallel)
    print(f"  primes found: {total} (parallel and sequential agree)")
    print(f"\n  sequential: {seq_time:7.3f}s  (one core)")
    print(f"  pool:       {par_time:7.3f}s  ({TASKS} processes on {cores} cores)")
    print(f"  speedup:    {seq_time / par_time:7.2f}x")
    print("\n  Open a system monitor during the pool phase: that is your"
          "\n  multi-core CPU, honestly busy, computing Scheme.")


if __name__ == "__main__":
    main()

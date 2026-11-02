"""nursery.py — structured concurrency: a Python nursery, a Scheme macro.

Run with:  python examples/concurrency/04-structured-concurrency/nursery.py

A *nursery* is the Trio-flavored shape of structured concurrency: tasks are
spawned against a scope, and the scope does not exit until every task has —
values come back in task order, and the first error propagates only after
all siblings have been joined. Nothing can outlive the block that started it.

Division of labor, per the example set's design rule:
- Python owns the mechanism: threads, the join-all, the error channel;
- Scheme owns the discipline: `with-parallel` (in structured.scm) is a macro,
  so the structure is visible in the source and checked by the expander;
- the tasks are pure — that is the price of sharing one read-mostly env
  across the nursery's threads (docs/capabilities.md: never share a live env
  when tasks mutate).

Also demonstrated: the two halves of error handling. The raw LispError
crossing the seam into Python's `except`, and — one level up — the same
nursery failure caught *in Scheme* by `guard`, as data.
"""

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # the repo root

from lisp import load_file, make_env, run, to_string
from lisp.errors import LispError
from lisp.evaluator import apply_procedure
from lisp.types import NIL, make_list


# --- the nursery primitive -------------------------------------------------------
# (nursery-run thunks) — thunks is a Scheme list of zero-argument procedures.
# One thread per thunk, all sharing the environment (safe because the tasks
# are pure). Joins every thread, then answers the values in task order — or
# re-raises the first error, after the join, so no task is abandoned.

def nursery_run(thunks) -> None:
    if isinstance(thunks, list):          # the `list` builtin builds these
        items = list(thunks)
    else:                                 # a proper Scheme list of Pairs
        items = []
        rest = thunks
        while rest is not NIL:
            items.append(rest.car)
            rest = rest.cdr

    results: list = [None] * len(items)
    errors: list[Exception] = []

    def run_one(index: int, thunk) -> None:
        try:
            results[index] = apply_procedure(thunk, [])
        except Exception as exc:  # noqa: BLE001 — re-raised below, after join
            errors.append(exc)

    threads = [
        threading.Thread(target=run_one, args=(i, t), daemon=True)
        for i, t in enumerate(items)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()          # <-- the whole idea: the block cannot exit early

    if errors:
        raise errors[0]   # first error wins, but only after everyone joined
    return make_list(results)


def main() -> None:
    env = make_env(install_tetris=False)
    load_file(env, Path(__file__).with_name("structured.scm"))
    from lisp import install_primitives
    install_primitives(env, [
        ("nursery-run", nursery_run),
        ("spin-ms", lambda ms: time.sleep(ms / 1000)),  # stand-in for real I/O
    ])

    def timed(source: str):
        start = time.perf_counter()
        value = run(source, env)
        return value, time.perf_counter() - start

    print("== four services, sequential vs one nursery ==")
    # Sequential baseline: four separate evaluations, one service at a time
    # (see the note in structured.scm on the per-evaluation step budget).
    services = [("auth", 900), ("billing", 1200), ("search", 700), ("notify", 500)]
    seq_time = 0.0
    for name, ms in services:
        _, spent = timed(f'(io-service "{name}" {ms})')
        seq_time += spent
    par_value, par_time = timed("(parallel-results)")

    print(f"  results: {to_string(par_value)}")

    print(f"\n  sequential: {seq_time:6.3f}s  (one thread waits for everyone)")
    print(f"  nursery:    {par_time:6.3f}s  (the waits overlap; slowest bounds it)")
    print(f"  speedup:    {seq_time / par_time:6.2f}x")
    print("  (the nursery is the block's join point; time = slowest sibling)")

    print("\n== the failure case: one poisoned task ==")
    try:
        run("(parallel-fail)", env)
        print("  (unreachable — the nursery must propagate the error)")
    except LispError as exc:
        print(f"  Python caught it after the join-all: {exc}")

    print("\n== the same failure, caught in Scheme by guard ==")
    caught = run("(guarded-fail)", env)
    print(f"  Scheme caught it as data: {to_string(caught)}")
    print("\nEither way: every sibling was joined before the error surfaced —"
          "\nno task outlives the block that started it.")


if __name__ == "__main__":
    main()

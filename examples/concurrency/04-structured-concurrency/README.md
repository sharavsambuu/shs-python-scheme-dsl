# 04 · structured concurrency — `with-parallel`, a nursery with a macro on top

```sh
python examples/concurrency/04-structured-concurrency/nursery.py
```

A *nursery* (Trio's shape of structured concurrency): tasks are spawned
against a scope, and the scope cannot exit until every task has. Values
come back in task order; the first error propagates **after** the join-all,
so no task is ever abandoned. Here the structure is a Scheme macro:

```scheme
(with-parallel
  (io-service "auth" 900)
  (io-service "billing" 1200)
  ...)
```

Python owns the mechanism (threads, join, error channel); the macro owns
the discipline — the block shape is visible in source and checked by the
expander.

## What to notice

- **2.74x measured**: sequential 3.314s vs nursery 1.210s — exactly the
  slowest sibling (1200ms), because waits overlap. The tasks are I/O-shaped
  on purpose: this example originally used CPU loops and measured **0.85x**
  — the GIL made the nursery slower than sequential. That is the honest
  boundary between 03/04 (threads, waiting) and 05/06 (processes, cores).
- The failure case runs twice: the raw `LispError` crossing the seam into
  Python's `except`, and the same failure caught *in Scheme* by `guard`,
  as data: `(nursery-caught billing: card declined)`.
- Tasks must be **pure** (no `define`/`set!` on shared bindings) — that is
  the price of one read-mostly env across the nursery's threads.
- The sequential baseline is timed as four separate evaluations: the step
  budget is per evaluation, and one program computing all four services
  back-to-back would trip it (documented in structured.scm).

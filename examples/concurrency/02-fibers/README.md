# 02 · fibers — cooperative multitasking over the generator protocol

```sh
python -m lisp run examples/concurrency/02-fibers/fibers.scm
```

A fiber is a **generator**: call it and it runs to its next yield point,
answers one value, and parks with all local state intact (`set!`-captured
closures are state enough). A round-robin loop over a set of generators is
therefore a cooperative scheduler. The example runs three — a lazy prime
finder, a fibonacci stream, a heartbeat — and prints the interleaved
transcript: every line is a different fiber making progress, each resuming
exactly where it parked.

## Why this shape (and not `call/cc`)

This dialect's `call/cc` is escape-only (docs/r7rs.md), so the classic
continuation-based coroutine is out. The generator protocol is the same
route modern runtimes took for coroutines anyway — and it is honest about
what a fiber is: a parked computation plus a scheduler that resumes it.

## What to notice

- The fibonacci fiber yields 0, 1, 1, 2, 3 — state is real and it survives
  parking.
- Fibers **cannot block** (a fiber that waits would stall the whole
  scheduler); they yield and let the scheduler decide. Waiting work belongs
  in `03-channels` or `04-structured-concurrency`.
- The whole runtime — fibers plus scheduler — is ~40 lines of pure Scheme,
  zero interpreter changes.

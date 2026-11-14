# 02 · fibers — cooperative multitasking over the generator protocol

```sh
python -m shslisp run examples/concurrency/02-fibers/fibers.scm
```

A fiber is a **generator**: call it and it runs to its next yield point,
answers one value, and parks with all local state intact (`set!`-captured
closures are state enough). A round-robin loop over a set of generators is
therefore a cooperative scheduler. The example runs three — a lazy prime
finder, a fibonacci stream, a heartbeat — and prints the interleaved
transcript: every line is a different fiber making progress, each resuming
exactly where it parked.

## Why this shape (and not `call/cc`)

This dialect's R7RS `call/cc` is escape-only (`docs/r7rs.md`), so this
example shows how to build a lightweight cooperative scheduler from closures
and `set!`. For `shslisp` v0.3.0+'s built-in baton-scheduled fibers, delimited
prompts, and `yield` coroutines (`(srfi 226)`, `(srfi 190)`, `(srfi 18)`), see
`09-srfi-coroutines-and-fibers`.

## What to notice

- The fibonacci fiber yields 0, 1, 1, 2, 3 — state is real and it survives
  parking.
- Fibers **cannot block** (a fiber that waits would stall the whole
  scheduler); they yield and let the scheduler decide. Waiting work belongs
  in `03-channels` or `04-structured-concurrency`.
- The whole runtime — fibers plus scheduler — is ~40 lines of pure Scheme,
  zero interpreter changes.

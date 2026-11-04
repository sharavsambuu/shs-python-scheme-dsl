# P4 — Features and the walls

**Before this:** [P1](p1-when-things-go-wrong.md) — you know the budget wall
exists.
**Time:** 20 minutes.
**After this you can:** write one script that adapts to the runtime it finds
itself in (`features`, `cond-expand`), answer what a procedure accepts
(`procedure-arity`), and state exactly where this interpreter's ceilings are.

There is no profiler in this interpreter — this page will not pretend there is
one. What it has instead is a *known ceiling*: you can measure wall-clock time
with `(scheme time)`, and the interpreter's own limits are small, named, and
honest. For a DSL embedded in a host program, that is usually the right trade —
the host has the profiler.

## `features` and `cond-expand`: one script, many runtimes

`(features)` answers the runtime's identity as a list of symbols — the
platform, the numeric guarantees, and which SRFI layer is loaded. `(cond-expand)`
dispatches on it at *read time*:

```scheme
(cond-expand
  (srfi-197 (display "chain and nest are loaded"))
  (else     (display "strict R7RS: no SRFI layer")))
(newline)
```

```text
chain and nest are loaded
```

Under the default `dsl` profile the first clause fires; run the same file with
`shs --profile r7rs` and the `else` answers. That is the whole portability
story: the script adapts to the vocabulary it is given, instead of crashing on
a name that is not there.

Ask about a feature directly when `cond-expand` is too heavy:

```scheme
(display (if (memq 'srfi-1 (features)) "yes" "no"))
(newline)
```

```text
yes
```

## `procedure-arity`: what does this accept?

A lambda answers its fixed arity; anything that cannot pin one down — a
builtin, a variadic — answers `#f` rather than guessing:

```scheme
(display (procedure-arity (lambda (x y) x)))
(newline)
(display (procedure-arity (lambda args args)))
(newline)
(display (procedure-arity car))
(newline)
```

```text
2
#f
#f
```

Handy at the REPL when a higher-order call fails and you want to know whether
the procedure or your call is wrong.

## The walls, named

Two ceilings bound every evaluation, and both fail *loudly* with a message that
says which wall it was:

- **The depth limit** — non-tail recursion only. Tail calls cost no depth (the
  trampoline, chapter [03](../lisp_tutorial/03-evaluating.md)), so a tail loop
  never hits it.
- **The step budget** — every root evaluation counts its trampoline steps;
  past the budget, the evaluation ends with:

```sh
$ shs -e '(let loop () (loop))'
shs: one evaluation spent more than 5,000,000 steps — an endless loop?
(tail calls cost no depth, so only this budget can see it)
```

Neither is catchable by `guard` — see [P1](p1-when-things-go-wrong.md) for why
that is a feature. The constants live in `lisp/evaluator.py`
(`DEPTH_LIMIT`, `STEPS_BUDGET`).

## Measuring time, honestly

`(scheme time)` gives the wall clock:

```scheme
(import (scheme time))
(define (timed thunk)
  (let ((start (current-second)))
    (thunk)
    (- (current-second) start)))
```

The *answer* is a float that differs every run — which is exactly why no
`Try it` block in this handbook prints one. Time real work with `timed`, read
the order of magnitude, and do not trust a benchmark smaller than its own
noise. For deeper questions, the truth is the host's profiler — see
[P5](p5-shipping-an-extension.md).

## Try it

A script that reports the vocabulary it actually got:

```scheme
(define (layer)
  (cond-expand
    (srfi-241 "the SRFI layer")
    (else "the strict core")))
(display (string-append "this runtime ships " (layer)))
(newline)
```

```text
this runtime ships the SRFI layer
```

Arity as a debugging tool — the fixed case answers, the open case declines:

```scheme
(display (procedure-arity (lambda (a b c) a)))
(newline)
(display (procedure-arity (lambda (a . rest) a)))
(newline)
```

```text
3
#f
```

## Exercises

1. Write `(run-if-available 'srfi-26 then else)` that uses `cond-expand`… or,
   once you see why that cannot work at runtime, rewrite it with `memq` and
   explain the read-time/runtime difference.
2. Time `(fold + 0 (iota 100000))` with `timed` — then time it again and
   explain the difference between the two numbers.
3. Find the depth limit empirically: double a non-tail recursion's input until
   the error names the wall. Then rewrite the same function tail-recursively
   with an accumulator and push past where the first version died.
4. Explain why `(procedure-arity car)` answering `#f` is more honest than
   answering a number.

## See also

- [03 Evaluating](../lisp_tutorial/03-evaluating.md) — the trampoline that
  makes the walls necessary
- [P1 — When things go wrong](p1-when-things-go-wrong.md) — what the walls
  look like from a `guard`
- The budgets: `lisp/evaluator.py` (`DEPTH_LIMIT`, `STEPS_BUDGET`); the
  profile's feature list: `lisp/profile.py`

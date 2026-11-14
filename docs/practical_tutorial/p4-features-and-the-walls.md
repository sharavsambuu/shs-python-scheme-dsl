# P4 — Features and the walls

**Before this:** [P1](p1-when-things-go-wrong.md) — you know the budget wall
exists.
**Time:** 20 minutes.
**After this you can:** write one script that adapts to the runtime it finds
itself in (`features`, `cond-expand`), answer what a procedure accepts
(`procedure-arity`), and state exactly where this interpreter's ceilings are.

This interpreter ships its own profilers, and this page uses them: measure
wall-clock time with `(scheme time)`, count trampoline work with
`measure_steps`, and find the procedures spending it with `measure_calls`. The
interpreter's limits are also small, named, and honest — a known ceiling is
easier to work under than a mysterious one, and a measured hotspot is easier to
fix than a guessed one. The host keeps the profiler for everything *below* the
seam.

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
$ shs -e "(let loop () (loop))"
shs: one evaluation spent more than 5,000,000 steps — an endless loop?
(tail calls cost no depth, so only this budget can see it)
```

*(Quoted with double quotes — on Windows, single quotes are not shell quotes,
and the form would be space-split into several arguments.)*

Neither is catchable by `guard` — see [P1](p1-when-things-go-wrong.md) for why
that is a feature. The constants live in `shslisp/evaluator.py`
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
noise. For "which procedure is expensive?", the interpreter answers below; for
everything underneath the seam (I/O, allocation, Python primitives), the host's
profiler is still the tool — see [P5](p5-shipping-an-extension.md).

## Profiling: steps and calls

Two hooks in `shslisp/evaluator.py` answer the interpreter-level question —
*where did the trampoline work go?* — without a wall clock in sight:

| Hook | Answers |
| --- | --- |
| `measure_steps(thunk)` | `(result, steps)` — the trampoline steps the thunk spent |
| `measure_calls(thunk)` | `(result, steps, counts)` — the same, plus applications per named closure and primitive |

Both run the thunk under a **private** budget: your own evaluation is neither
charged nor counted, and the usual `STEPS_BUDGET` guard still ends a runaway
excerpt with a clean `LispBudgetError`. When profiling is off, the hook costs
one `is not None` test on the hot path — measuring never changes what the
program computes.

Why steps rather than microseconds? A wall clock answers "how long on this
machine, today"; a step is one trampoline transition — a literal, a tail jump,
one special-form dispatch — so the count is reproducible and tells you *which
procedure* is expensive. Use `timed` for the human-scale answer and these for
the engineering one.

```python
from shslisp import make_env, run
from shslisp.evaluator import measure_calls, measure_steps

env = make_env(install_tetris=False)
run("(define (leaf x) (+ x 1))", env)
run("(define (branch n) (if (= n 0) 0 (+ (leaf n) (branch (- n 1)))))", env)

result, steps, counts = measure_calls(lambda: run("(branch 5)", env))
print(result, steps)                        # 20 109
print(counts["branch"], counts["leaf"])      # 6 5
print(sorted(counts.items(), key=lambda kv: -kv[1])[:3])
# [('+', 10), ('branch', 6), ('=', 6)]
```

A tail call is one application, so six `branch` calls for `(branch 5)` is the
recursion depth, not the number of Python frames. And the same thunk under the
steps-only hook:

```python
result, steps = measure_steps(lambda: run("(branch 5)", env))
print(result, steps)                        # 20 109
```

What the hooks do *not* do: time Python primitives, attribute memory, or sample
a long run. Those remain the host's job (`cProfile`, `py-spy`, the host's own
instrumentation) — the interpreter counts its own steps, and the host owns
everything underneath.

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
5. Profile `(fold + 0 (iota 100000))` with `measure_calls`. Which name sits at
   the top of `counts`, and is that what you expected for a fold over a list?
   Then rewrite the same sum with a named recursive helper and profile again —
   what moved, and what stayed?

## See also

- [03 Evaluating](../lisp_tutorial/03-evaluating.md) — the trampoline that
  makes the walls necessary
- [30 Testing and debugging](../lisp_tutorial/30-testing-and-debugging-srfi-64.md)
  — the same profiler beside a test suite and a traceback
- [P1 — When things go wrong](p1-when-things-go-wrong.md) — what the walls
  look like from a `guard`
- The budgets and the profilers: `shslisp/evaluator.py` (`DEPTH_LIMIT`,
  `STEPS_BUDGET`, `measure_steps`, `measure_calls`); the profile's feature
  list: `shslisp/profile.py`

# 30 — Testing and debugging: `(srfi 64)`

> **What this chapter teaches.** How to write a test suite *in* this language
> with `(srfi 64)` — assertion macros, groups, and the simple runner — and, for
> the failures that are not assertion failures, how the host reads a Scheme
> stack (`format_traceback()`) and finds the procedures spending the steps
> (`measure_calls`).
>
> **Before this:** 21, 28. · **Time:** ~20 min.
> **After this you can:** write a Scheme spec that runs from the CLI or a host
> Python test, read a failing assertion's output, print a bounded Scheme
> traceback instead of a one-line message, and profile a slow excerpt by
> procedure.

## Why the language ships a test API

A host project written in this language has an obvious testing question: where
do the specs live? The answer used by the trading lab — one prelude of its
own — is exactly the boilerplate `(srfi 64)` standardizes. Importing the
library means a host project writes specs against a standard shape instead of
re-inventing one, and the runner's output is the same everywhere.

`(srfi 64)` is **not** pre-imported; it is one line away in either profile:

```scheme
(import (srfi 64))
```

| Form | What it does |
| --- | --- |
| `(test-begin name)` / `(test-end name)` | bracket a run; `test-end` prints one summary line and returns the runner |
| `(test-group name body ...)` | `test-begin`, the body, `test-end` — a nested group |
| `(test-assert expr)` | the expression must be true |
| `(test-equal expected expr)` | `equal?` comparison |
| `(test-eqv expected expr)` / `(test-eq expected expr)` | `eqv?` / `eq?` comparison |
| `(test-error expr)` | the expression must raise; the condition is caught, never printed as a crash |
| `(test-error pred expr)` | …and `pred` must accept the caught condition |
| `(test-runner-current)` / `(test-runner-simple)` | read (or install) the runner / make a fresh one |

Every assertion also takes an optional leading **name** —
`(test-equal "one lot" 100 (* 1 100))` — which is what the FAIL line prints.
Without one, the name is the form's own (`test-equal`), so the position in the
file is the only clue; name the assertion you would want to see fail.

## Why the assertions are syntax

`(test-error (car 1))` cannot be a procedure call: a procedure's arguments are
evaluated **before** it runs, so the error would escape before the assertion
could catch it. `test-error` (and `test-assert`, `test-equal`, `test-eqv`,
`test-eq`) are `syntax-rules` macros: each wraps the expression in
`(lambda () …)` and hands the thunk to a private checker, which catches a
condition with `guard`.

That has a second payoff: an assertion whose expression *raises* is reported as
a test **error** and the suite continues. A test file that stops at the first
broken expression teaches you one bug per run; this one teaches you all of
them.

## The runner

`test-runner-current` answers the runner — a vector
`#(kind passed failed total)`, ordinary data you can read — and with one
argument installs a new one. `(test-runner-simple)` constructs a fresh runner:

```scheme
(import (srfi 64))

(test-runner-current (test-runner-simple))   ; start from zero
(test-runner-current)                        ;=> #(simple 0 0 0)
```

`test-end` prints the **running** totals (`;; name: P passed, F failed, T
total`), not just the last group's. That is deliberate: the final line is the
run's verdict, and a group nested inside another reports the cumulative count
at the point it ends.

## Try it

```scheme
(import (srfi 64))

(test-begin "ledger")

(test-group "totals"
  (test-equal 6 (+ 1 2 3))
  (test-equal "one lot" 100 (* 1 100))
  (test-assert (> 10 3))
  (test-error (car '())))

(test-eqv 4 (+ 2 2))
(test-eq 'buy 'buy)
(test-equal "a deliberate failure" 5 (+ 2 2))

(test-end "ledger")
```

```text
;; begin ledger
;; begin totals
;; totals: 4 passed, 0 failed, 4 total
FAIL: a deliberate failure
  expected: 5
  actual:   4
;; ledger: 6 passed, 1 failed, 7 total
```

Read the shape of that output: the failing assertion prints the value it
expected and the value it got, the suite **keeps going** (the run ends 6 passed,
1 failed rather than stopping at the failure), and the last line is the
verdict. In a real suite the deliberate failure is the one thing you would
delete — but the point of this page is that you can see it.

## When a test fails: `format_traceback()`

An assertion tells you *that* it failed. A raised error tells you *where it
was raised*, and that is a host-side question with a host-side answer: every
`LispError` carries the innermost source span in `exc.source`, and `str(exc)`
stays **one line** — `file:line:col: message` — because that is what a script's
stderr and the REPL print. When you want the frames too, ask for them:

```python
from shslisp import make_env, run
from shslisp.errors import LispError

env = make_env()
try:
    run(
        "(define (inner y) (car y))\n"
        "(define (outer x) (+ 1 (inner x)))\n"
        "(outer 42)",
        env,
    )
except LispError as exc:
    print(exc.format_traceback())
```

```text
Scheme traceback (innermost first):
  at <string>:1:19
  at <string>:2:19
<string>:1:19: car: expected a non-empty list
```

The frames are deduplicated, innermost first, and bounded
(`TRACEBACK_FRAMES = 32`) so a deep recursion cannot pin memory in one string.
A form the reader never saw — a macro expansion, a form built with `list` — has
no recorded span and simply contributes no frame; an error with no frames
formats as its message. Nothing about `str(exc)` changed, which is why every
program that matched on it before still works.

## Where the steps went: `measure_calls`

`measure_steps` answers *how much* trampoline work a thunk spent.
`measure_calls` (`shslisp.evaluator`) also answers *which procedures spent it* —
applications per named closure and primitive:

```python
from shslisp import make_env, run
from shslisp.evaluator import measure_calls

env = make_env()
run("(define (leaf x) (+ x 1))", env)
run("(define (branch n) (if (= n 0) 0 (+ (leaf n) (branch (- n 1)))))", env)

result, steps, counts = measure_calls(lambda: run("(branch 5)", env))
print(result, steps)                        # 20 109
print(counts["branch"], counts["leaf"])      # 6 5
print(sorted(counts.items(), key=lambda kv: -kv[1])[:4])
# [('+', 10), ('branch', 6), ('=', 6), ('leaf', 5)]
```

Two facts make the number trustworthy:

- **The profiler owns its budget.** The thunk runs under a fresh `_Budget`, so
  the caller's own steps are neither charged nor disturbed — and the usual
  `STEPS_BUDGET` guard still ends a runaway excerpt with a clean
  `LispBudgetError`.
- **Nothing is counted when the profiler is off.** `_Budget.calls` is `None`
  for ordinary evaluation, so the hook costs one `is not None` test on the hot
  path. Profiling never changes what the program computes.

A tail call is one application, which is why `(branch 5)` reports 6 `branch`
calls rather than counting Python frames: 5, 4, 3, 2, 1, 0 — six calls, five of
which reach `leaf`.

## Exercises

1. **Name every assertion.** Add a name to each assertion in the Try-it
   program, run it, and compare the FAIL line with the unnamed version. Which
   spelling would you want in a suite of two hundred assertions?
2. **Prove the catch.** Replace `(test-error (car '()))` with
   `(test-error (> 1 2))`. Read what the runner prints, and explain why the
   suite still finishes.
3. **One failing group.** Move the deliberate failure into the `"totals"`
   group and predict the two summary lines before you run it. Which line is the
   group's, and which is the run's?
4. **Profile a loop.** Write `(define (sum-to n) (if (= n 0) 0 (+ n (sum-to (- n
   1)))))`, profile `(sum-to 10)`, and read the counts. Then profile
   `(sum-to 20)`. Which entries double, and which stay the same? Say what that
   tells you about where the work is.

## The shape you copy

> Assertions are syntax so they can catch; the runner is data so you can read
> it; the summary is the run's verdict, not the last group's. When a failure is
> an error rather than an assertion, leave the one-line message to the REPL and
> give the host `format_traceback()`; when the failure is *slowness*, ask
> `measure_calls` which procedure is spending the steps.

Next: [31 — Coroutines, fibers, and delimited control](31-coroutines-fibers-and-delimited-control.md).
If you want a quick lookup reference, see [Appendix A — Reference](appendix-a-reference.md).

# P1 — When things go wrong

**Before this:** [P0](p0-the-repl-as-a-workbench.md) — you can work at the
prompt and you have seen an `error:` line.
**Time:** 25 minutes.
**After this you can:** read any failure this interpreter produces — tell the
three kinds apart, pull the message and irritants out of an error object, and
know which errors a `guard` can catch and which it cannot.

An error you can read is a hint; an error you cannot read is a wall. This
chapter is about turning every failure into a hint.

## The three kinds

| Kind | When it happens | What it looks like |
| --- | --- | --- |
| **Read** | the text is not Lisp — an unbalanced paren, a runaway string | `error: unterminated string literal` |
| **Name** | a symbol is used before it is bound | `error: unbound symbol: total` |
| **Runtime** | a form is valid but the values are wrong — type, arity, a failed `error` call | `error: car: expected 1 argument(s), got 0` |

All three are `LispError` subclasses (`shslisp/errors.py`) — the reader raises
`LispSyntaxError`, the evaluator raises `LispNameError`, `LispTypeError`,
`LispArityError`. That one base class is the whole contract: a REPL, a script,
or a `guard` can tell "the program is wrong" from "the host is wrong".

## Error objects: the message and the irritants

`(error message irritant ...)` builds an *error object* — a value with a
message and a list of everything you attached. A `guard` can take it apart:

```scheme
(guard (e
        (else (display (error-object-message e)) (newline)
              (display (error-object-irritants e)) (newline)))
  (error "payment declined" (list 'order 7) 'card))
```

```text
payment declined
((order 7) card)
```

A plain `(raise value)` carries any value at all — a symbol, a number, a
variant — and `guard` hands it to you raw:

```scheme
(guard (e (else (display e) (newline)))
  (raise 'boom))
```

```text
boom
```

That is the condition system's whole shape: `raise`/`error` put a value in
flight, `guard` decides what it means, and ROP (chapter
[22](../lisp_tutorial/22-railway-oriented.md)) builds the railway on top.

## What a guard cannot catch

Two things sail past `guard`, on purpose:

- **The step budget.** An endless loop ends with a message naming the budget —
  see [P4](p4-features-and-the-walls.md). A catchable endless loop would be a
  "retry the infinite loop" button.
- **A continuation invoked outside its extent.** If a continuation captured in
  an earlier form is invoked after its `call/cc` is gone, the REPL answers
  `error: continuation invoked outside its extent` and stands.

## Two honest warts

- Arity errors on builtins currently surface a Python signature
  (`car: _car() missing 1 required positional argument: 'xs'`) — readable, but
  it leaks the host. Fixing it is a real backlog item; knowing it is a wart
  beats wondering if you did something exotic.
- A *read* error mid-file names the problem but not the line number. At the
  REPL this rarely matters (the buffer is on your screen); in a large file it
  is worth splitting the file until the error is local — which [P2](p2-programs-across-files.md)
  makes cheap.

## The host's view: one line, or the whole stack

The one-line message is the *program's* view — the `error:` line at the prompt,
a script's stderr, the text a `guard` handler reads. A host that wants to know
*how the interpreter got there* asks the error for its frames:

```python
from shslisp import make_env, run
from shslisp.errors import LispError

try:
    run("(define (inner y) (car y))\n"
        "(define (outer x) (+ 1 (inner x)))\n"
        "(outer 42)", make_env())
except LispError as exc:
    print(str(exc))                # the one-line contract, unchanged
    print(exc.format_traceback())  # innermost-first frames, then that line
```

```text
<string>:1:19: car: expected a non-empty list
Scheme traceback (innermost first):
  at <string>:1:19
  at <string>:2:19
<string>:1:19: car: expected a non-empty list
```

Three properties make that safe to print into a log:

- **`str(exc)` never changes.** The one-line `file:line:col: message` is what
  every script, the REPL, and the suite's substring assertions have always
  matched. The traceback is opt-in; a host that never calls it pays nothing.
- **The frames are deduplicated, innermost first, and bounded.** At most
  `TRACEBACK_FRAMES = 32` of them, so a deep recursion cannot pin memory in one
  string, and the head of the stack is the part you read.
- **A form the reader never saw contributes no frame.** Macro expansions and
  forms built with `list` have no recorded span; an error with none formats as
  its message alone. Each frame is a real `file:line:col`, not a guess.

`exc.source` is the innermost span on its own when you want the location
without the stack. And `read_all_located` / `evaluate_program` accept the
`(form, location)` pairs that the located reader returns, so a host can read a
file with spans and run it without unpacking anything.

## Try it

Catch an error object and pull it apart — the exact pattern a payment flow
would use:

```scheme
(define (charge amount)
  (if (< amount 0)
      (error "amount must not be negative" amount)
      (* amount 100)))

(display
  (guard (e
          ((error-object? e)
           (string-append "refused: " (error-object-message e))))
    (charge -5)))
(newline)
(display (charge 3))
(newline)
```

```text
refused: amount must not be negative
300
```

The same `guard` handles a `raise` — one rail for both:

```scheme
(define (withdraw amount)
  (if (> amount 100)
      (raise 'over-limit)
      'ok))

(display
  (guard (e ((symbol? e) (string-append "blocked: " (symbol->string e))))
    (withdraw 500)))
(newline)
```

```text
blocked: over-limit
```

## Exercises

1. Write `(divide a b)` that raises `'divide-by-zero` when `b` is zero, and a
   `guard` that turns it into the string `"cannot divide by zero"`.
2. Provoke each of the three kinds at the REPL — an unbalanced paren, a
   misspelled name, `(car 5)` — and say which kind each one was *before*
   pressing Enter.
3. Build an error with three irritants and display only the second one.
4. Explain, in one sentence each, why the step budget is not catchable and why
   `raise` is.
5. **Ask for the frames.** Run the `format_traceback()` snippet above, then
   break the rule in a way that nests one call deeper. Which line moved, and
   why did the top frame move with it? Then delete the `print(...)` line and
   confirm `str(exc)` still says everything the log needs.

## See also

- [P4 — Features and the walls](p4-features-and-the-walls.md) — the budgets,
  from the inside
- [22 Railway-oriented programming](../lisp_tutorial/22-railway-oriented.md) —
  the design pattern built on all of this
- [30 Testing and debugging](../lisp_tutorial/30-testing-and-debugging-srfi-64.md)
  — the traceback beside a Scheme test suite and the profiler
- The error classes: `shslisp/errors.py`; the recoveries: `tests/test_repl.py`

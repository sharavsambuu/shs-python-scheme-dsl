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

All three are `LispError` subclasses (`lisp/errors.py`) — the reader raises
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
[21](../lisp_tutorial/21-railway-oriented.md)) builds the railway on top.

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

## See also

- [P4 — Features and the walls](p4-features-and-the-walls.md) — the budgets,
  from the inside
- [21 Railway-oriented programming](../lisp_tutorial/21-railway-oriented.md) —
  the design pattern built on all of this
- The error classes: `lisp/errors.py`; the recoveries: `tests/test_repl.py`

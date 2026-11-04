# P6 — Testing Lisp from the host

**Before this:** [P1](p1-when-things-go-wrong.md) and [P5](p5-shipping-an-extension.md)
— you know `guard`, and you know the host can call the guest.
**Time:** 25 minutes.
**After this you can:** test a Lisp program from pytest with the same
`run_script` call the interpreter's own harness uses, write guest-side
self-checks that print `ok` lines a CI log can read, and choose which side a
given test belongs on.

This repository tests its Lisp every day — the tutorial's examples run as tests
(`tests/test_tutorial.py`), the exercises run as tests
(`tests/test_exercises.py`), the R7RS surface is measured against a manifest
(`tests/test_r7rs.py`). This chapter teaches the pattern they all share, so
your embedded Lisp gets the same safety net your Python does.

## The host side: one call

`run_script` is the whole API: it loads a file, evaluates form by form, prints
only what the program `display`s, and returns the last value.

```python
from shslisp.__main__ import run_script

def test_total(tmp_path):
    program = tmp_path / "total.scm"
    program.write_text(
        "(define (total xs) (fold + 0 xs))\n"
        "(display (total '(10 20 12)))\n"
    )
    import io
    buffer = io.StringIO()
    run_script(str(program), out=buffer)
    assert buffer.getvalue() == "42\n"
```

The shape is always the same: *write the program, run it, read what it
displayed*. Testing through the printed output — not the return value — is
deliberate: it tests the program exactly as a user experiences it, banner and
all. (The tutorial harness goes one step further and fails when a `Try it`
block's output stops matching its page — the docs cannot silently rot.)

For pure functions, skip the file entirely and evaluate forms in a fresh
environment:

```python
from shslisp import make_env, run

def test_total_pure():
    env = make_env(install_tetris=False)
    assert run("(fold + 0 '(10 20 12))", env) == 42
```

`run` answers the value directly — the right tool when the thing under test is
a function, not a program.

## The guest side: self-checks a CI log can read

A Lisp file can carry its own checks, in the vocabulary of [P1](p1-when-things-go-wrong.md)'s
`checked` helper: one line per assertion, `ok` when it holds:

```scheme
(define (checked name actual expected)
  (display name) (display ": ")
  (display (if (equal? actual expected)
               "ok"
               (list "FAIL" actual "wanted" expected)))
  (newline))

(checked "add" (+ 1 2) 3)
(checked "join" (string-append "see" "sharp") "seesharp")
```

```text
add: ok
join: ok
```

The failure shape is the honest part — a failing check prints *both* numbers,
so the log answers "what did we get?" without a re-run:

```scheme
(display (list "FAIL" 5 "wanted" 3))
(newline)
```

```text
(FAIL 5 wanted 3)
```

Guard the whole run so one failed check cannot take the batch down mid-file —
collect, then summarize.

## Which side, which test

| Test on the host (`pytest`) when | Test on the guest (`checked`) when |
| --- | --- |
| the assertion needs Python data or state | the check belongs with the code it checks |
| you are testing the *seam* (P5's contract) | the file is a program someone runs alone |
| the failure should fail the build | the failure should fail loudly at run time |

The repository's own split is the example: `tests/test_embed.py` tests the
crossing from the host's side; the prelude's pure Lisp is tested from Python
too (`tests/test_language.py`); and a shipped script that misbehaves fails
when a human runs it, so the scripts get a lint — `shslisp/profile.py`'s `lint`
loads every shipped `.scm` under the default profile.

## Try it

A self-checking module — the pattern to paste at the top of any Lisp file that
must answer for itself:

```scheme
(define (factorial n)
  (if (= n 0) 1 (* n (factorial (- n 1)))))

(define (checked name actual expected)
  (display name) (display ": ")
  (display (if (equal? actual expected)
               "ok"
               (list "FAIL" actual "wanted" expected)))
  (newline))

(checked "0!" (factorial 0) 1)
(checked "5!" (factorial 5) 120)
```

```text
0!: ok
5!: ok
```

## Exercises

1. Add a `checked` line that fails on purpose, run the file, and read the
   `(FAIL ... wanted ...)` line. Then fix it and watch the log go green.
2. Write the pytest twin: a test that runs this file through `run_script` and
   asserts both `ok` lines appear in the output.
3. Write `(checked-raises name thunk)` — a check that passes only when the
   body raises. You will need `guard` and a sentinel.
4. Decide, for your own project, the rule for which tests live on which side —
   write it down in one sentence and follow it for a week.

## See also

- [P1 — When things go wrong](p1-when-things-go-wrong.md) — `guard`, the
  self-check's engine
- [P5 — Shipping an extension](p5-shipping-an-extension.md) — the seam these
  tests guard
- The exemplars: `tests/test_tutorial.py`, `tests/test_exercises.py`,
  `tests/test_embed.py`

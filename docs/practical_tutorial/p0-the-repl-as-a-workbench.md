# P0 — The REPL as a workbench

**Before this:** the [main tutorial's](../lisp_tutorial/README.md) chapters
00–03, or just the ten-minute chapter — you can read a Lisp form.
**Time:** 20 minutes.
**After this you can:** develop a Lisp program by talking to it — type a form,
see its value, keep the definition, and recover from a mistake without leaving
the prompt.

The tutorial taught you the language. This chapter teaches the room you will
actually work in: `shs`, the read-eval-print loop. The REPL has one problem a
script does not have — it must know when a form is *finished* — and one promise
a script does not make: every value you produce comes back to you immediately.

## Three doors, one language

```sh
shs                      # the REPL: talk to your program
shs -e "(+ 1 2)"         # one shot: evaluate, print, leave
shs run program.scm      # a file: no echo, only what it displays
```

*(The `-e` expression is quoted with double quotes — on Windows, single quotes
are not shell quotes, and the form would be space-split into several
arguments.)*

The difference between the first door and the other two is *echo*. The REPL
prints every value — including a `define`'s, which answers with the name it
just bound:

```sh
shs — a small Scheme-flavored Lisp.  (,help  ,quit)
lisp> (+ 1 2)
3
lisp> (define (greet who)
  ...   (string-append "Hello, " who))
greet
lisp> (greet "Ada")
Hello, Ada
```

*(A real session shows the continuation prompt on its own line; the transcript
above is condensed to fit. What matters is the shape: multi-line definitions
just work — the REPL reads lines until the parentheses balance.)*

A script is the opposite: it prints only what you explicitly `display`. That is
not a limitation, it is the contract — a program's output is its output, not
its plumbing.

## The commands

Everything starting with `,` is a REPL command, not Lisp:

- **`,help`** — the command list, plus a few forms worth trying
- **`,load PATH`** — load a library file into the running session (relative to
  the file, then the search path; loaded once — see
  [P2](p2-programs-across-files.md))
- **`,quit`** — leave (also `,q`, or typing `quit`)

## Mistakes are lines, not crashes

The REPL is built to survive you. Every one of these comes back as an
`error:` line with the prompt standing:

- a stray `)` — `error: unexpected )`
- an unbound name — `error: unbound symbol: frobnicate`
- a wrong argument count — `error: car: expected 1 argument(s), got 0`

And if a form is still *open* — an unbalanced `(`, an unterminated string, a
`#\` waiting for its character — the REPL asks for another line instead of
guessing. A form you never close comes back as an error when you leave
(Ctrl-D / Ctrl-Z), not as silence. Ctrl+C starts a fresh form; it does not end
the session. The recoveries are pinned by `tests/test_repl.py`, which exists
because every one of them used to be a crash.

One error deserves its own sentence: an *endless* loop is not a crash either —
it ends, cleanly, when the interpreter's step budget runs out:

```sh
$ shs -e "(let loop () (loop))"
shs: one evaluation spent more than 5,000,000 steps — an endless loop?
(tail calls cost no depth, so only this budget can see it)
```

The wall is deliberate and it is not catchable by `guard` — see
[P4](p4-features-and-the-walls.md) for the other walls.

## Try it

Type this at the prompt — one line at a time or pasted whole; the REPL does not
care:

```scheme
(define (fact n)
  (if (= n 0) 1 (* n (fact (- n 1)))))
(display (fact 20))
(newline)
```

```text
2432902008176640000
```

Definitions persist at the prompt — `fact` from the last entry is still bound
when you type the next one. A block below shows a whole file's worth at once,
because that is how a script (and this handbook's own harness) sees it — one
unit, every definition it needs:

```scheme
(define (fact n)
  (if (= n 0) 1 (* n (fact (- n 1)))))
(define (report n)
  (string-append "20! is " (number->string n)))
(display (fact 20))
(newline)
(display (report (fact 20)))
(newline)
```

```text
2432902008176640000
20! is 2432902008176640000
```

## Exercises

1. Define `cube`, then call it on 7. The REPL should echo `cube` when you
   define it and `343` when you call it.
2. Type `(+
   1
   2)` across three lines and watch the continuation prompt hold the form open
   until the parentheses balance.
3. Type a stray `)` on its own line. Read the error, then continue with
   `(* 6 7)` — the session should answer `42` as if nothing happened.
4. Run `,help` and try two of the forms it suggests.

## See also

- [P1 — When things go wrong](p1-when-things-go-wrong.md) — reading the error
  you just provoked
- [P2 — Programs across files](p2-programs-across-files.md) — `,load` and the
  library system behind it
- The REPL itself: `lisp/repl.py`; its guarantees: `tests/test_repl.py`

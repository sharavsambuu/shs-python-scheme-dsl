# 01 — The pipeline: from Python to a Lisp runtime

> **What this chapter teaches.** The one route every Lisp program takes through
> this project — text becomes data, data becomes behaviour — and the map of the
> modules that make it happen.
>
> **Before this:** chapter 00, or none — this is the map. · **Time:** ~12 min.
> **After this you can:** name the three stages every form goes through, and say
> where the game stops being part of the language.

## A Lisp is a small machine with a big library

Most languages grow by adding syntax. A Lisp grows by adding *functions and
macros*, because it has almost no syntax to begin with. The whole grammar is:

- `(a b c)` is a **list** — call `a` with `b` and `c`;
- `x` is a **symbol** — look it up;
- `42`, `"hi"`, `#t` are **literals** — themselves.

That is it. Everything else — `let`, `cond`, `match`, class-like variants,
railway pipelines — is either a *special form* the evaluator knows by name, or a
*macro* that rewrites itself into those, or a *function* in the standard library.

This is why the project can be a tutorial. Once you have seen the reader, the
evaluator, and the standard library, you have seen all of it. The game on top is
a library, not a language feature.

## One route through the machine

```
        text                    forms                   values
   "(+ 1 (* 2 3))"  ──reader──▶  ['+', 1, ['*', 2, 3]]  ──evaluator──▶  7
        ▲                                                        ▲
        │                                                        │
     shslisp/reader.py                                    shslisp/evaluator.py
                                                       (with shslisp/env.py)
```

Three stages, three modules:

1. **`shslisp/reader.py` — text → data.** It does not care what the text *means*;
   it only knows how to make lists and atoms. `'x` is not special syntax to the
   evaluator — the reader has already turned it into `(quote x)` before anything
   is evaluated. That single decision is what makes macros possible: by the time
   a program runs, code *is* data.
2. **`shslisp/types.py` — what the values are.** A number, a string, a symbol, an
   empty list, a proper list, an improper pair, a vector, a hash table, a tagged
   value, a closure, a primitive. Every one is an ordinary Python value the host
   can inspect.
3. **`shslisp/evaluator.py` — data → behaviour.** A tail-calling loop: it reads a
   form, decides what kind of form it is, and either returns a value or rebinds
   `expr`/`env` and loops. Closures capture an environment (`shslisp/env.py`), so
   scope is lexical.

Everything else is a library written on top: `shslisp/prelude.scm` (the standard
library), `shslisp/syntax.py` (hygienic macros), `shslisp/rope.scm` (railway-oriented
programming), and the game.

## The map

Read the `shslisp/` package roughly in this order (the package docstring in
`shslisp/__init__.py` gives the same tour in brief):

| Module | Lines | Its one job |
| --- | --- | --- |
| `shslisp/reader.py` | ~350 | Text → forms. Quote sugar, literals, comments, dotted pairs. |
| `shslisp/types.py` | ~580 | The value universe, and the helpers that build lists and pairs. |
| `shslisp/evaluator.py` | ~1100 | The trampoline, the special forms, closures, `match`, variants. |
| `shslisp/stack.py` | ~90 | A host stack deep enough for the language's own recursion. |
| `shslisp/env.py` | ~64 | A scope: a dict plus a parent pointer. |
| `shslisp/errors.py` | ~95 | `LispError` and its purpose-named subclasses. |
| `shslisp/builtins.py` | ~870 | The Python floor: pure functions, plus a few named host holes. |
| `shslisp/syntax.py` | ~480 | `define-syntax` / `syntax-rules` — hygienic macros. |
| `shslisp/prelude.scm` | ~400 | The standard library. **In Lisp.** |
| `shslisp/rope.scm` | ~160 | `Result`, Kleisli composition, do-notation. **In Lisp.** |
| `shslisp/loader.py` | ~180 | `(load "path")`: resolve, load once, detect cycles. |
| `shslisp/runtime.py` | ~90 | Assemble a ready-to-run environment. |
| `shslisp/repl.py` | ~135 | The read-eval-print loop, and the file runner. |
| `shslisp/printer.py` | ~115 | Writing values back out (the `write`/`display` split). |
| `shslisp/__main__.py` | ~250 | The CLI: `shs` — REPL, `run`, `-e`, profiles. |

That is the whole language. A *host edition* — a separate project that embeds
the language and installs its own vocabulary — adds its own modules beside
these, never inside them.

## Three layers of an environment

`shslisp/runtime.py` builds an environment in three layers, each optional:

1. **core** — the primitives from `shslisp/builtins.py`;
2. **prelude** — `prelude.scm` and `rope.scm`, evaluated in Lisp itself;
3. **the SRFI profile and extensions** — the pre-imported SRFI layer
   (`--profile dsl`, the default), then whatever the host passes in
   `extensions=[…]`, plus a host edition when one is installed.

```python
make_env(profile="r7rs")     # the strict R7RS-small subset, no SRFIs preloaded
make_env(profile="dsl")      # the default: the SRFI layer pre-imported
make_env()                   # auto: a host edition is added only if installed
```

That last default is the thesis of the whole project: the language never
learns a host word in its own source, so a project that installs (or
vendor-copies) `shslisp/` gets a plain Scheme. The *shell* — `runtime.py` and
`__main__.py` — is the only place a host can be wired in, by name and only at
the caller's request. Chapter [28](28-embedding-in-python.md) shows a host of
your own taking that place.

## A trace: what happens to `(square 5)`

Suppose the reader has already produced the forms `(define (square x) (* x x))`
and `(square 5)`, and the evaluator has evaluated the first, binding `square` to
a `Closure`. Now evaluate `(square 5)`:

1. The evaluator sees a list whose head `square` is **not** a special form, so it
   checks whether `square` is a macro. It is not.
2. It evaluates the head: `square` looks up to a `Closure`.
3. It evaluates the arguments: `5` is a literal, so it is itself.
4. The head is a `Closure`, so the evaluator **rebinds `env` to the closure's
   captured scope extended with `x = 5`, rebinds `expr` to the body `(* x x)`,
   and loops** — no new Python call frame. That is a tail call.
5. `(* x x)` is an application of the primitive `*`; it returns `25`.

The loop in step 4 is the "trampoline". It is why recursive Lisp programs work
in a host (Python) that has no tail-call elimination of its own. Chapter
[03](03-evaluating.md) reads it line by line.

## The two halves, and the seam

```
your Python project     the host — knows your domain, and Python
  ▲
  │  shslisp.embed: a declared crossing — your functions, named once
  ▼
shslisp/                   the language — knows nothing about your domain
```

The rest of this tutorial walks that picture from the bottom up: the language
first, then the crossing, then the program you write in Lisp.

## Try it

```scheme
;; What does the reader see? Ask it directly.
(display (read-string "(+ 1 2)"))
(newline)
(display (read-string "'(a b)"))
(newline)
(display (read-string "(a b . c)"))
```

```text
(+ 1 2)
(quote (a b))
(a b . c)
```

The first line prints `(+ 1 2)`; the second prints `(quote (a b))` — the reader
has already applied the quote sugar. That is the whole trick.

## Exercises

1. **Predict, then check.** Write down what `(read-string "#(1 2)")` will print
   before you run it. (It prints `#(1 2)`: a vector is already a value the
   reader can make, so there is nothing to expand.)
2. **Break the sugar.** At the REPL, type `'(a b)` and then `(quote (a b))`.
   They are the *same form*, and the reader is why: nothing in the evaluator has
   a `'` case. Find the line in `shslisp/reader.py` that rewrites one into the
   other.
3. **Find the seam.** Open `shslisp/runtime.py` and `shslisp/__main__.py` and confirm
   they are the only two files under `shslisp/` that name a host edition. The
   language itself never does — that discipline is what makes it embeddable,
   and chapter [28](28-embedding-in-python.md) shows the other side of the
   seam.

## The shape you copy

> A language is a small *machine* (reader, evaluator, environment) plus a large
> *library* written in the language. A domain becomes a library by declaring a
> narrow crossing — not by changing the machine.

Next: [02 Values and reading](02-values-and-reading.md).

# Learning this Lisp

This is a tutorial, not a reference. It teaches the Lisp dialect that `shs`
runs by reading the code that *is* it, and it teaches that code by using it to
write Lisp. The two threads are deliberately braided:

1. **How Python becomes a Lisp runtime.** A reader turns text into data; a
   trampoline turns data into behaviour; a standard library and a macro system
   are written *in the language itself*; a module loader splits a program across
   files. That is the whole machine, and it is about five thousand lines you can
   read in an afternoon.
2. **How that Lisp scripts a host.** The language is one installable package;
   your project installs its own vocabulary through a declared seam and the
   program you write in Lisp does the rest.

By the end you will have written a program of your own over a Python host and
understand every mechanism between your domain and the Lisp that drives it.

The language contract — the R7RS-small subset, the ingested SRFIs, the default
profile, and the Python seam — is the separate
[DSL specification](../lisp-dsl.md), and the one-stop reference with verified
examples is the [language guide](../language.md). This tutorial teaches the
language; the specification states what it promises.

## Who this is for

You can program, but you have not written Lisp. You may also be curious how a
small interpreter is built, and how one embeds a domain without a framework.
No prior Lisp, no prior interpreter theory. Python readability helps for the
first part; after that everything is Lisp.

## How to read it

Read Part I in order — each chapter builds the vocabulary the next one uses.
Part II is the language you will actually write day to day. Chapter
[21](21-embedding-in-python.md) is the way out: how to take this language and put
it over a project of your own. Chapters [22–27](22-srfi-1-the-list-library.md)
are the SRFI layer — the standard batteries that ship pre-imported — one
chapter per SRFI.

Every numbered chapter opens with **Before this / Time / After this you can**,
and ends with **Try it** (a program you can paste and run) and **Exercises**.
Worked answers live in [`exercises/`](exercises/), and the test suite runs them
(see below). **The shape you copy** is the one idea to keep.

## The chapters

| Part | Chapter | What it teaches |
| --- | --- | --- |
| **Part I — the machine** | | |
| | [00 Lisp in ten minutes](00-lisp-in-ten-minutes.md) | The whole language, fast |
| | [01 The pipeline](01-the-pipeline.md) | Reader → evaluator → printer, and the map of `lisp/` |
| | [02 Values and reading](02-values-and-reading.md) | What a value *is*, and how text becomes one |
| | [03 Evaluating](03-evaluating.md) | The trampoline: data becomes behaviour |
| | [04 Primitives](04-primitives.md) | The Python floor, and the named impure doors |
| | [05 The standard library](05-standard-library.md) | `prelude.scm`: the batteries, in Lisp |
| | [06 Macros](06-macros.md) | `define-syntax` / `syntax-rules`, hygienic |
| | [07 Modules](07-modules.md) | `(load ...)`: programs across files |
| **Part II — the language you write** | | |
| | [08 Lisp by example](08-lisp-by-example.md) | Programs worth stealing |
| | [09 Typed control flow](09-typed-control-flow.md) | `define-variant` and `match` |
| | [10 Railway-oriented programming](10-railway-oriented.md) | `Result`, Kleisli arrows, do-notation |
| **Part III — out of the repository** | | |
| | [21 Embedding in Python](21-embedding-in-python.md) | The host seam: `install_primitives`, extensions, packaging |
| | [22 SRFI 1 — the list library](22-srfi-1-the-list-library.md) | Folds, constructors, searching, set ops |
| | [23 SRFI 26 — cut and cute](23-srfi-26-cut-and-cute.md) | Specialized calls without the lambda boilerplate |
| | [24 SRFI 88 — keywords](24-srfi-88-keywords.md) | `host:` — the self-evaluating name |
| | [25 SRFI 89 — optional and named parameters](25-srfi-89-optional-and-named-parameters.md) | `define*`/`lambda*` and the keyword call syntax |
| | [26 SRFI 197 — chain and nest](26-srfi-197-chain-and-nest.md) | Pipelines, early exit, and lexical substitution |
| | [27 SRFI 241 — match](27-srfi-241-match.md) | Quasiquote patterns, guards, ellipsis, catamorphism |
| **Appendix** | [A Reference](appendix-a-reference.md) | Signatures, common mistakes, CLI |
| | [B Glossary](appendix-b-glossary.md) | The terms, and where each one lives |

## Run it

Install, then everything in this tutorial is a paste away:

```sh
pip install .        # from a checkout of this project

shs                  # the REPL — try (fact 20) after ,help
shs -e '(+ 1 2)'
shs run examples/fizzbuzz.scm
```

For the test suite (including the checks on this tutorial itself):

```sh
python -m pytest -q
```

## Exercises and answer keys

Each chapter ends with exercises. Where a worked answer is clearer as a file, it
ships in [`exercises/`](exercises/) — they are run by
`tests/test_exercises.py`, which is the answer key in the sense this project
uses the phrase: the test is what says the exercise still works.

You do not need to write your answers where the shipped ones live. Read the
exercise, close the file, and write your own first.

## The two tests that keep this honest

`tests/test_tutorial.py` is an architecture test for the prose. It runs every
executable `Try it` block and compares its output with the `text` block beside
it; it checks that every chapter is indexed, carries its metadata, and has a
`Try it` and an `Exercises` section; and it checks that every file path and
`test_*` name the prose mentions still exists. `tests/test_exercises.py` loads
the worked answers and checks their claims.

This is the project's rule applied to itself: a teaching page is not done until
a reader can paste its example and watch it work, and until a test fails when
the code moves.

## A note on the voice

The code in this repository explains itself in its docstrings and comments —
they are not decoration, they are the argument. Where this tutorial quotes a
file, the quote is the real text; where it shows output, the output is what the
interpreter really printed (and a test enforces that). If a claim here and a
comment there disagree, the code wins, and you have found a bug worth reporting.

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
Part II is the language you will actually write day to day, arranged from the
mechanical to the expressive: chapter [08](08-lisp-by-example.md) is programs
worth stealing; chapters [09–13](09-rosetta-data-structures.md) are the
data-structures track — Python's list, tuple, dict, set, and class, rebuilt in
this Lisp; chapters [14–19](14-srfi-241-match.md) are the rest of the
language — the SRFIs this dialect ships in its prelude (match, cut, keywords,
optional and named parameters), the generator library, and chain/nest — one
chapter per feature, each placed right after the topic it deepens. Part III
is the design track, and it assumes all of that: chapters
[20–21](20-typed-control-flow.md) teach typed control flow and
railway-oriented programming, chapters [22–23](22-functional-foundations.md)
the functional-programming foundations and the FP answers to the classic
design patterns, chapter [24](24-bounded-contexts.md) applies them to
domain-driven design — bounded contexts, aggregates over events, and the
context map — and chapter [25](25-functional-core-imperative-shell.md) names
the architecture the whole series has been building toward: a functional core
inside an imperative shell. Chapter [26](26-the-gala-checkout.md) is the
capstone: one checkout pipeline where typed control flow, pattern matching,
contracts, monadic pipelines, railway-oriented programming, bounded contexts,
and the core/shell split all run in a single program. Chapter
[27](27-embedding-in-python.md) is the way out: how to take this language and
put it over a project of your own.

## The chapters

| Part | Chapter | What it teaches |
| --- | --- | --- |
| **Part I — the machine** | | |
| | [00 Lisp in ten minutes](00-lisp-in-ten-minutes.md) | The whole language, fast |
| | [01 The pipeline](01-the-pipeline.md) | Reader → evaluator → printer, and the map of `shslisp/` |
| | [02 Values and reading](02-values-and-reading.md) | What a value *is*, and how text becomes one |
| | [03 Evaluating](03-evaluating.md) | The trampoline: data becomes behaviour |
| | [04 Primitives](04-primitives.md) | The Python floor, and the named impure doors |
| | [05 The standard library](05-standard-library.md) | `prelude.scm`: the batteries, in Lisp |
| | [06 Macros](06-macros.md) | `define-syntax` / `syntax-rules`, hygienic |
| | [07 Modules](07-modules.md) | `(load ...)`: programs across files |
| **Part II — the language, step by step** | | |
| | [08 Lisp by example](08-lisp-by-example.md) | Programs worth stealing |
| | [09 Rosetta: Python's data structures](09-rosetta-data-structures.md) | The list/tuple/dict/set/class map, truthiness, equality |
| | [10 Lists and vectors in depth](10-lists-and-vectors.md) | The comprehension moves, sort/group, and the mutable sequence |
| | [11 SRFI 1 — the list library](11-srfi-1-the-list-library.md) | Folds, constructors, searching, set ops |
| | [12 Dictionaries: alists and hash tables](12-dictionaries-alists-and-hash-tables.md) | The two dictionary shapes, and the counting/grouping recipes |
| | [13 Modeling data](13-records-variants-and-objects.md) | Records, variants, and closures as the three "custom classes" |
| | [14 SRFI 241 — match](14-srfi-241-match.md) | Quasiquote patterns, guards, ellipsis, catamorphism |
| | [15 SRFI 26 — cut and cute](15-srfi-26-cut-and-cute.md) | Specialized calls without the lambda boilerplate |
| | [16 SRFI 88 — keywords](16-srfi-88-keywords.md) | `host:` — the self-evaluating name |
| | [17 SRFI 89 — optional and named parameters](17-srfi-89-optional-and-named-parameters.md) | `define*`/`lambda*` and the keyword call syntax |
| | [18 Generators](18-generators.md) | Lazy sequences: infinite ranges, `gmap`/`gfilter`/`gtake`/`gdrop`, the drains |
| | [19 SRFI 197 — chain and nest](19-srfi-197-chain-and-nest.md) | Pipelines, early exit, and lexical substitution |
| **Part III — the design track** | | |
| | [20 Typed control flow](20-typed-control-flow.md) | `define-variant` and `match` |
| | [21 Railway-oriented programming](21-railway-oriented.md) | `Result`, Kleisli arrows, do-notation |
| | [22 Functional programming: foundations](22-functional-foundations.md) | Purity, folds as recursion schemes, point-free style, currying |
| | [23 FP design patterns](23-fp-design-patterns.md) | The strategy, closures as modules, memoisation, lazy pipelines, bind |
| | [24 Bounded contexts](24-bounded-contexts.md) | DDD: ubiquitous language, aggregates over events, context maps, repositories |
| | [25 Functional core, imperative shell](25-functional-core-imperative-shell.md) | Decisions as data, one door for every effect, the countable impurity audit |
| | [26 The gala: one checkout, eight ideas](26-the-gala-checkout.md) | The capstone: typed lifecycle, contracts, ROP, matched failures, contexts — one program |
| **Part IV — out of the repository** | | |
| | [27 Embedding in Python](27-embedding-in-python.md) | The host seam: `install_primitives`, extensions, packaging |
| **Appendix** | [A Reference](appendix-a-reference.md) | Signatures, common mistakes, CLI |
| | [B Glossary](appendix-b-glossary.md) | The terms, and where each one lives |

## Run it

Install, then everything in this tutorial is a paste away:

```sh
pip install .        # from a checkout of this project

shs                  # the REPL — try (fact 20) after ,help
shs -e "(+ 1 2)"
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

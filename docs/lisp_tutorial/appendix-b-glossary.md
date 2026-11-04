# Appendix B — Glossary

> The terms this tutorial uses, each with where it lives in the code.

## The language

**Reader** — `shslisp/reader.py`. Turns text into forms. Expands quote sugar; knows
nothing of meaning.

**Form / datum** — a value the reader produced. Because code is data, a form is
also a datum: a list, a symbol, or a literal.

**Special form** — a form the evaluator handles by name: `if`, `define`, `lambda`,
`match`, … (the literal `_SPECIAL_FORMS` set). Not a primitive and not a macro.

**Macro** — a procedure from forms to a form, run at expansion time. Raw
(`defmacro`) or hygienic (`define-syntax`/`syntax-rules`). `shslisp/syntax.py`.

**Hygiene** — a macro's template binders are renamed and its free identifiers are
captured by resolution, so a macro cannot capture a caller's names and vice
versa. Chapter [06](06-macros.md).

**Closure** — a `lambda`'s value: code plus the environment it captured.
`shslisp/types.py`.

**Environment / scope** — `shslisp/env.py`. A dict plus a parent pointer; captures
lexically.

**Tail call** — an application in last position. The evaluator rebounds `expr` and
`env` and loops instead of recursing, so it costs no host stack.

**Trampoline** — the `while True` in `_run`. `shslisp/evaluator.py`.

**Budget** — two bounds on runaway: `DEPTH_LIMIT` (nested evaluation →
`LispRecursionError`) and `STEPS_BUDGET` (trampoline steps → `LispBudgetError`).

**Primitive** — a Python function exposed as a Lisp value. `shslisp/builtins.py`.

**Host hole** — the few primitives that touch the outside world (`display`,
`error`, `eval`, `read-string`, `load`, `quit!`, `sound!`). Chapter
[04](04-primitives.md).

**Prelude** — the standard library, written in Lisp. `shslisp/prelude.scm`.

**Loader** — `shslisp/loader.py`. `(load …)` with three rules: resolution, load-once,
cycle error.

**Variant** — a closed union of tagged cases, declared with `define-variant`.

**Tag** — a variant case's name; a value views as `(tag . fields)`.

**`match`** — the SRFI 241 pattern matcher (quasiquote-shaped patterns, `,x`
binds). The project's tag-dispatch matcher is the separate `variant-match`;
`case` is the older, literal-equality dispatcher.

**`variant-match`** — dispatch on a `define-variant` value's tag, binding its
fields, and naming a case you forgot. Chapter [20](20-typed-control-flow.md).

**Profile** — the SRFI layer an environment is born with: `"dsl"` (the
default; every mandatory SRFI pre-imported), `"r7rs"` (strict core + prelude),
or none. `(features)` and `cond-expand` report it.

**Keyword** — a SRFI 88 keyword object, read with the suffix colon (`host:`);
self-evaluating, interned, distinct from symbols. SRFI 89's named parameters
are supplied with them.

**Result** — the closed variant `(ok value) | (err reason)`. `shslisp/rope.scm`.

**Monad / Kleisli arrow** — `result-bind` is the monad; `>=>` composes arrows
(`A -> Result`). `pipe-results`, `result-do`. Chapter
[21](21-railway-oriented.md).

**ROP (railway-oriented programming)** — writing a fallible computation as a chain
that short-circuits on the first refusal.

## Architecture (the words the codebase uses)

**Bounded context** — a module that knows one thing and nothing else.

**Aggregate root** — the mutable object a front end holds.

**Value object** — frozen data describing something.

**Anti-corruption layer** — the boundary that keeps two vocabularies apart.
In this project: the seam itself. `shslisp/embed.py` is the whole crossing
surface, and nothing inside `shslisp/` reaches into a host.

**Domain** — the *rule* layer: pure, host-independent.

**Adapter** — code that translates one vocabulary to another and holds no
policy.

**Fence** — an architecture boundary pinned as a test.

## The seam

**Crossing** — the declared list of Lisp names a host publishes: the `table`
passed to `install_primitives`.

**Vocabulary** — the published spellings: what a host's names look like on
the Lisp side of the seam.

**Host edition** — a separate Python project that embeds the language and
installs a vocabulary. The Tetris edition is the worked example.

**Extension** — an object with `install(env)` that a host passes to
`make_env(extensions=[…])`; it may load its own Lisp prelude.

**Primitive** — a Python function bound into the environment under a
declared name.

**Door** — a one-way call into the FX pod from the script:
`(burst! …)`, `(flash! …)`, `(thud! …)`. The script decides, the pod executes.

## Refusals and rails

**Rail** — a value that carries success or failure instead of raising; the
language's own is the `Result` variant (`ok`/`err`), in `shslisp/rope.scm`.

**Refusal** — a failure *as data*: a value a program can branch on, name, and
compose, rather than an exception it must remember to catch.

**Journal** — the ordered record of what a step did, as data a program can
inspect.

## The tutorial itself

**Track** — one of the three reading paths in the [index](README.md): write Lisp,
build a runtime, or see the whole product. The tracks share examples; they
differ in how much of the runtime you read.

**Try it** — the executable example that ends every chapter. The `sh` block is
the program; the `text` block beside it is the output, and
`tests/test_tutorial.py` compares the two.

**Exercises** — the end-of-chapter work. Where a worked answer is clearer as a
file, it ships in `exercises/`; `tests/test_exercises.py` is what checks it.

**Answer key** — in this repository, the *test* that checks an exercise, not a
prose solution. If the exercise changes, the test changes with it.

---

Back to the [map](README.md).

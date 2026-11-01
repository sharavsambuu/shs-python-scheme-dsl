# The Language — a guide to the Scheme-based DSL

> **What this is.** The DSL (the package's import name is `lisp`, the project
> name is `lisppy`) is a Scheme-flavoured Lisp with a small, readable Python
> runtime. It uses **R7RS-small as its base language** — an honest, documented
> *subset*, not a claim of full conformance — adds a mandatory **SRFI layer**
> that is enabled by default, and keeps a declared **Python seam** so a host
> project can publish its own functions as first-class primitives.
>
> This page is the one-stop language guide. The checkable truth behind it
> lives in [`r7rs.md`](r7rs.md) (the R7RS matrix), [`srfi.md`](srfi.md) (the
> SRFI matrix), and the tests; the long-form teaching text is the
> [tutorial](lisp_tutorial/README.md). Every code example below was verified
> against the real interpreter.

## What it is for

The language exists to make **domain-driven design**, **railway-oriented
programming** (ROP), **monadic pipelines**, and **typed control flow**
pleasant, in files that read like Lisp and run on a Python core:

```scheme
;; pure domain code — no game, no hooks
(define (double x) (* x 2))
(define* (greet name (greeting: g "hello")) (string-append g ", " name))
```

The interpreter is deliberately small: a reader, an evaluator with a trampoline
and a deep-stack runner, a library system, a loader, and a handful of Python
modules. Everything else — the standard library, ROP, the SRFIs — is written
in the language itself (`lisp/prelude.scm`, `lisp/rope.scm`, `lisp/srfi*.scm`),
which makes those files the first worked examples.

## Quick start

From `python_tetris_lisp/` (the project runs in place; `P` is the interpreter):

```sh
cd python_tetris_lisp
P=../python_tetris/env/bin/python

$P -m lisp                          # REPL (default), with the game loaded
$P -m lisp repl --no-tetris         # REPL, language only
$P -m lisp run FILE                 # run a .scm file
$P -m lisp run FILE --no-tetris     # run without the game
$P -m lisp demo                     # guided tour of the domain
$P -m lisp rope                     # guided tour of Result / ROP
$P -m lisp play                     # pygame window, default design
$P -m lisp play --design arcade     # pick a design by name
$P -m lisp play --list              # the gallery of designs
$P -m lisp play --validate          # every design, headless
$P -m lisp play --seed 7            # reproducible
```

In Python, the same language is two calls away:

```python
from lisp import make_env, run

env = make_env()          # the default DSL profile, no game needed
run("(fold + 0 '(1 2 3 4))", env)   # -> 10
```

## The profiles: two dialects, one interpreter

`make_env(profile=...)` selects what is pre-imported. The interpreter ships in
two dialects:

| Profile | What it is | Who uses it |
| --- | --- | --- |
| `"dsl"` (the default) | core + prelude + the SRFI layer, pre-imported with collision resolutions applied | the REPL, `run`, `demo`/`rope`, the game, embedded hosts |
| `"r7rs"` | the strict subset: core + prelude only. The SRFIs exist as libraries but are not pre-imported | the conformance harness; checking whether a program is portable |
| `None` | no profile at all | tests that need the bare machinery |

The DSL profile is **additive**: it binds no name the core already binds, so
nothing existing changes meaning. It is exactly this import list:

```scheme
(scheme base)
(scheme write)
(rename (srfi 1) (map srfi-1:map) (for-each srfi-1:for-each))
(srfi 26)
(srfi 88)
(srfi 89)
(srfi 197)
(srfi 241)
```

`(features)` reports what is true of the host and the dialect — under the
default profile, on this machine:

```scheme
(features)
;; => (lisppy posix darwin arm64 ieee-float
;;     dsl-profile srfi-1 srfi-26 srfi-88 srfi-89 srfi-197 srfi-241)
```

and `cond-expand` answers the same question (R7RS §4.2.1 grammar):

```scheme
(cond-expand (dsl-profile 'dsl) (else 'strict))            ;=> dsl
(cond-expand ((library (srfi 1)) 'srfi-there) (else 'no))  ;=> srfi-there
```

The interpreter deliberately does **not** report the feature `r7rs`: it is a
documented subset, and a program branching on `r7rs` should not be told it may
rely on the whole report.

## Reading: the external representations

The reader (`lisp/reader.py`) and printer (`lisp/printer.py`) are a matched
pair: `write` emits text that `read` accepts, and re-writing the result is
stable. The sugar the reader applies first:

- `'x` → `(quote x)`, `` `x `` → `(quasiquote x)`, `,x` → `(unquote x)`,
  `,@x` → `(unquote-splicing x)`
- `#(1 2 3)` a vector, `#u8(1 2 3)` a bytevector, `#\a` a character
- `(a . b)` a dotted pair, `#;form` a discarded datum, `#| … |#` a block
  comment
- numeric prefixes `#b #o #d #x #e #i`, in either order:

  ```scheme
  #e#x10        ;=> 16
  ```

  plus the inexact specials `+inf.0 -inf.0 +nan.0`
- `|quoted symbols|` (case and spaces preserved); a symbol that is not a plain
  identifier prints between bars
- string escapes `\" \\ \a \b \t \n \r \| \x…;` and line continuations;
  `#!fold-case` / `#!no-fold-case` directives (off by default)

**Keywords** (SRFI 88) are read with the suffix colon: `host:` is the keyword
named `host`, and a lone `:`, `:host`, and `foo:bar` are symbols. There is no
`#:foo` prefix spelling and no `|...|` quoted keywords.

## Core forms

The special forms (`lisp/evaluator.py`):

```
quote  quasiquote  if  define  set!  lambda  let  let*  letrec  letrec*
case-lambda  begin  cond  when  unless  and  or  defmacro  case  guard
let-values  let*-values  define-values  define-syntax  let-syntax
letrec-syntax  match  define-variant  define-record-type  cond-expand
define-library  import  include  include-ci  syntax-error
```

Everything ordinary Scheme gives you is here and behaves per the report:

```scheme
(let-values (((a b) (values 1 2))) (+ a b))     ;=> 3
((case-lambda ((a) a) ((a b) (+ a b))) 1 2)     ;=> 3
(guard (e ((symbol? e) 'caught)) (raise 'oops)) ;=> caught
`(1 ,(+ 1 1) ,@(list 3 4))                      ;=> (1 2 3 4)
```

`define-record-type` is supported; a record is a distinct type with a
predicate, accessors, and an equality that follows the report.

## Macros: hygienic and classic

Two macro systems coexist by design:

- **`define-syntax` / `syntax-rules`** — hygienic R7RS macros. A pattern
  variable and a template binding cannot capture each other. Most of the
  standard library's syntax (`delay`, `parameterize`, `let-values`,
  `result-do`) is built with it.
- **`defmacro`** — the classic unhygienic macro, for code that wants to
  construct forms by hand. It is a deliberate, documented extension and is
  marked as such in [`r7rs.md`](r7rs.md).

`macroexpand-1` and `macroexpand` take a form and hand back the expanded form,
so a macro can be inspected from the REPL. Hygiene is visible in the output —
the `|…|` name is the gensym that keeps the template's internals from
capturing yours:

```scheme
(macroexpand '(delay (foo 1)))
;; => (|make-promise#h1| (lambda () (foo 1)))
```

`MACROEXPAND_LIMIT = 1_000` bounds how many steps `macroexpand` will take
before it calls a macro divergent.

## Typed control flow: variants and match

`define-variant` declares a **closed** set of tagged cases. One declaration
gives you the constructors, the accessors, the predicate, and the closed tag
list as data:

```scheme
(define-variant shape
  (circle r)
  (rect w h))

(variant-tags 'shape)     ;=> (circle rect)
```

`variant-match` dispatches on the tag, binds the fields, and — because the set
is closed — names a case you forgot instead of quietly defaulting:

```scheme
(variant-match (circle 3)
  ((circle r) (* 3.14 r r))
  ((rect w h) (* w h)))     ;=> 28.26 (inexact; 3.14 is inexact)
```

The project's tag-dispatch matcher is deliberately named `variant-match`
because **`match` is SRFI 241**, whose patterns are quasiquote-shaped: a
literal matches itself and `,x` binds:

```scheme
(match '(1 2 3) [(,a ,b ,c) (+ a b c)])        ;=> 6
(match '(1 2 3 4) [(1 ,_ ,b . ,r) (list b r)]) ;=> (3 (4))
(match '(ok 5)   [(ok ,v) v])                  ;=> 5
```

Two documented SRFI 241 deviations: the catamorphism's recursion is a nested
interpreter call (bounded by the data's depth), and a quasiquote template
followed by *multiple* ellipses does not distribute. Both are in
[`srfi.md`](srfi.md).

## Railway-oriented programming: Result

`lisp/rope.scm` defines a closed `Result` variant and builds the whole ROP
vocabulary on one primitive, `result-bind`:

```scheme
(result-bind (ok 41) (lambda (x) (ok (+ x 1)))) ;=> (ok 42)
(result-bind (err "halt") (lambda (x) (ok (+ x 1))))  ;=> (err halt)
```

A *Kleisli arrow* is a function `A -> Result`. `>=>` composes two of them,
`pipe-results` threads a value through any number, and both short-circuit on
the first refusal:

```scheme
(pipe-results 2
  (lambda (x) (ok (* x 10)))
  (lambda (x) (err "too big")))               ;=> (err too big)
```

`result-do` is do-notation: it reads like imperative code but is
`result-bind` all the way down (`_` discards a step):

```scheme
(result-do
  (a <- (ok 1))
  (b <- (ok 2))
  (ok (+ a b)))                               ;=> (ok 3)
```

`attempt` joins a *raising* computation to the pipeline by putting the raised
value on the failure rail:

```scheme
(attempt (lambda () (error "boom")))          ;=> (err #<error "boom">)
```

The rest of the vocabulary — `result-map`, `result-map-err`, `result-map2`,
`result-bimap`, `result-fold`, `result-unwrap`, `result-unwrap-or`,
`result-expect`, `result->list`, `sequence-results`, `traverse-results`,
`ok-values`, `err-reasons`, `first-err`, `count-errs` — is built from the same
two ideas. The monad laws are pinned by `tests/test_rop.py`.

## The standard library

**Core primitives** (`lisp/builtins.py`) are the R7RS `(scheme base)` registry
plus the numeric, char, string, vector, bytevector, port, and file surface —
see [`r7rs.md`](r7rs.md) for the per-library matrix and
[Appendix A](lisp_tutorial/appendix-a-reference.md) for the full name list.
A few shapes worth knowing:

- **Numbers.** Exact integers and inexact reals only — no exact rationals, no
  complex tower. `(/ 3 4)` is `0.75` (never `0`); `round` is ties-to-even and
  preserves inexactness; `exact` of a non-integral float raises.
- **Pairs vs. host lists.** A proper list is a host list; `Pair` is reserved
  for dotted structure. `set-cdr!` works on `Pair` cells only, which is why a
  proper list's tail cannot be mutated in place.
- **Equality.** `eq?`/`eqv?`/`equal?` per the report, plus `boolean=?`.

**The prelude** (`lisp/prelude.scm`) is ordinary Lisp you could have typed at
the REPL — no Python, no hooks. Its vocabulary:

- combinators: `identity inc dec const compose pipe flip complement partial
  curry`
- list sugar: `first second rest last caar cadr caddr`
- association lists — the language's record shape — with `alist-*` helpers
- hash tables: `make-hash-table`, `hash-table-ref/default`,
  `hash-table-has-key?`, `hash-table-set!`, `hash-table-delete!`,
  `hash-table-count`, `hash-table-keys`, `hash-table-for-each`
- promises: `delay`, `delay-force`, `force`
- parameters: `make-parameter`, `parameterize` — dynamically scoped cells
  whose restoration happens inside `dynamic-wind`'s after thunk, so it holds
  on a normal return, on a `raise`, and across escape continuations
- the current ports: `(current-output-port)` and friends are parameters, so
  `parameterize` redirects `display`/`write`/`newline` — and the redirection
  is undone on every exit from the extent
- file conveniences: `call-with-output-file`, `with-output-to-file`,
  `call-with-input-file`, `with-input-from-file`
- misc: `range`, `sort`, `delete-duplicates`

A trailing `!` (`show!`, `set!`) is a convention, not syntax: "this procedure
exists for its effect".

## The SRFI layer

The SRFI layer is a set of R7RS *libraries* on top of the library system, and
it is what makes functional pipelines and typed domain code pleasant. Every
library either meets its SRFI's semantics — audited name by name, with the
tests to show it — or fails loudly as "not implemented yet". Nothing is
aliased into pretending.

| Library | What it gives you | Where it lives |
| --- | --- | --- |
| `(srfi 1)` | the list library: `fold`/`fold-right`/`reduce`, lset operations, `iota`, `count`, `find`, `partition`, `member`/`assoc` with an optional comparator | `lisp/srfi1.scm` (pure Lisp) |
| `(srfi 26)` | `cut` / `cute` — partial application with placeholders | `lisp/srfi26.scm` (pure Lisp) |
| `(srfi 88)` | keyword objects, reader-level | core: reader, evaluator, printer |
| `(srfi 89)` | `define*` / `lambda*`: optional positional and named parameters | `lisp/srfi89.scm` (pure Lisp) |
| `(srfi 197)` | the `chain` pipeline family | `lisp/srfi197.scm` (pure Lisp) |
| `(srfi 241)` | `match` — quasiquote-style pattern matching | core: `evaluator.py` |
| `(srfi 204)` | **withdrawn** — importing it fails, naming SRFI 241 | — |

A few examples (all verified against the interpreter):

```scheme
((cut + 1 <>) 41)                                  ;=> 42
(chain '(1 2 3) (map (lambda (x) (* x x)) _) (fold + 0 _))  ;=> 14
(member "b" '("a" "b") string=?)                   ;=> (b)
(call-with-values (lambda () (partition odd? '(1 2 3 4))) list)  ;=> ((1 3) (2 4))
```

Optional and named parameters (`define*` / `lambda*`): the formals have three
sections — positional (`v`, then `(v default)`), named (`(keyword v)`, then
`(keyword v default)`), rest (`. r`) — and named arguments at the call site
are SRFI 88 keywords:

```scheme
(define* (greet name (greeting: g "hello"))
  (string-append g ", " name))

(greet "ada")             ;=> "hello, ada"
(greet "ada" greeting: "hi")   ;=> "hi, ada"
```

Two SRFI 1 names differ from `(scheme base)` and are renamed in the default
profile: `(srfi 1)`'s `map`/`for-each` **stop at the shortest list**, while
the base ones require equal lengths and raise. When you want SRFI 1's
behaviour, name it explicitly:

```scheme
(srfi-1:map + '(1 2 3) '(10 20))    ;=> (11 22) — the base map raises here
```

## Modules, libraries, and files

There are two ways to split a program, and they answer different questions.

**The loader** (`(load ...)`) is the project's own mechanism for splitting
files. Its rules:

- **Resolution** — a relative path is tried against the *loading* file's own
  directory first, then each search path; the `.scm` suffix is optional — a
  bare name tries `.scm`, then `.lisp` for older modules, then the path as
  written.
- **Load once** — a module is read and evaluated at most once per
  environment; the second `(load ...)` returns the first result and defines
  nothing again. The cache is keyed by the resolved absolute path, so
  `domains/x.scm` and `./domains/x.scm` are one module.
- **Cycles are errors** — `a -> b -> a` raises, naming the chain, instead of
  looping forever.
- `(loaded-modules)` reports the resolved paths, in load order.

So a library can say `(load "hud")` next to itself, and a script can say
`(load "domains/planning/one-ply")` from anywhere.

**`define-library` / `import`** are the R7RS library system (A13). A library
has an explicit export list; importing binds exactly those names, an export
that is not bound is an error at import time, and the import sets
`only`/`except`/`prefix`/`rename` are supported:

```scheme
(define-library (demo math)
  (export double)
  (import (scheme base))
  (begin (define (double x) (* x 2))))

(import (demo math))
(double 21)     ;=> 42
```

Note that `define-library` does **not** leak names into the surrounding
environment — only `import` binds. The R7RS `(scheme ...)` libraries are
themselves entries in the same registry, and the SRFIs ride on it too.

## The Python seam

The Python seam is a first-class feature, not an escape hatch. A host project
declares its own functions as primitives:

```python
from lisp import install_primitives, make_env, run

env = make_env()                       # a general Scheme, no game needed
install_primitives(env, [("double", lambda n: n * 2)], source="myproject")
run("(double 21)", env)                # -> 42
```

- `install_primitives(env, table, source=…)` binds a declared list (or map) of
  `name -> callable`, refusing a duplicate or a non-callable *at install time*.
- An **extension** is any callable `env -> env` or object with `install(env)`;
  pass them to `make_env(extensions=[…])`.
- An extension sees the environment **after** the prelude, so it can build on
  the language's own vocabulary — which is exactly what the Tetris edition
  does.
- The package installs with `pip install -e python_tetris_lisp`; the import
  name is `lisp`.

Environment assembly (`lisp/runtime.py`) is the generality story in miniature:

1. **core** — `lisp/builtins.py`;
2. **prelude** — `lisp/prelude.scm`, `lisp/rope.scm`;
3. **profile** — the SRFI layer, pre-imported (`profile="dsl"` by default);
4. **extensions** — whatever the host passed, then the Tetris edition when it
   is present (`install_tetris=None` — *auto* — means "include the game only
   if the `tetris` package is importable", which is why a project that
   vendor-copies `lisp/` gets the language and nothing else).

## Architecture conventions (the worked example)

The Tetris tree is the worked example of the conventions the language
supports:

- `scripts/domains/` holds pure, hook-free *rules*: gravity, planning,
  scoring, feedback, campaign data.
- `scripts/edges/` holds *adapters* and the designs that wire them: keymaps,
  status lines, menus, the pygame edge.
- **The fence: edges may load rules; rules may not load edges** — enforced by
  `tests/test_architecture.py`.
- A **design** is one file directly under `scripts/edges/` that defines the
  five hooks (and, optionally, `design-meta` for the launcher);
  `play --list` and `play --validate` are the gallery and the headless sweep.
- The SRFI layer never learns a game word: the architecture tests import the
  SRFI libraries in a language-only environment, so the layer stays
  game-agnostic.

The lint in `lisp/profile.py` keeps the "mandatory SRFI layer" rule with
teeth: every shipped `.scm` file must load under the default profile, and a
file that does not turns `tests/test_profile.py` red.

## Errors, limits, and budgets

| Limit | Meaning | Error |
| --- | --- | --- |
| `DEPTH_LIMIT = 1_000_000` | nested evaluation depth | `LispRecursionError` |
| `STEPS_BUDGET = 5_000_000` | trampoline steps | `LispBudgetError` |
| `MACROEXPAND_LIMIT = 1_000` | `macroexpand` steps | `LispBudgetError` |

Everything else follows the report: `error` raises a condition `guard` can
catch, a missing name is a loud `LispNameError` (never a silent `#f`), a
syntax problem is a `LispSyntaxError` naming the form.

## Deviations from R7RS-small (the ones that matter)

The full table lives in [`r7rs.md`](r7rs.md); the short version:

| Area | Deviation |
| --- | --- |
| Continuations | `call/cc` is escape-only; re-entry after the `dynamic-wind` extent ends does not work. `guard`, `dynamic-wind`, and escape continuations do. |
| Numbers | Exact integers + inexact reals; no exact rationals, no complex tower. |
| Strings | Literals are immutable; mutate a `make-string`/`string-copy` result. |
| Cycles | No datum labels (`#1=`); cyclic data cannot be read or printed. |
| Libraries | `define-library`/`import` supported; `(load ...)` remains the loader's own mechanism. |

**Non-goals:** full R7RS-small conformance, re-entrant `call/cc`, SRFI 204
(withdrawn; use SRFI 241), and implementing every SRFI in the catalog. The
project extensions (`define-variant`, the ROP vocabulary, `->`/`->>`,
`partial`/`curry`, the prelude) are the DSL's own vocabulary, documented in
[Appendix A](lisp_tutorial/appendix-a-reference.md) and in
[`lisp-dsl.md`](lisp-dsl.md) — never claimed as R7RS.

## Where to read next

- [The tutorial](lisp_tutorial/README.md) — 27 chapters, from the pipeline to
  the bridge, with worked answers in [`exercises/`](lisp_tutorial/exercises/).
- [Appendix A — reference](lisp_tutorial/appendix-a-reference.md) — the
  lookup sheet: every special form, primitive, and hook, verified against the
  code.
- [`r7rs.md`](r7rs.md) — the R7RS-small matrix: supported, missing, deviations.
- [`srfi.md`](srfi.md) — the SRFI matrix, per-library semantics and collisions.
- [`lisp-dsl.md`](lisp-dsl.md) — the umbrella contract the three pages
  implement.
- [`capabilities.md`](capabilities.md) — the capability assessment against the
  modern-language checklist: parity, gaps, and the roadmap.
- The tests are documentation with teeth: `tests/test_r7rs.py`,
  `tests/test_srfi.py`, `tests/test_profile.py`, `tests/test_rop.py`,
  `tests/test_architecture.py`, `tests/test_tutorial.py`.





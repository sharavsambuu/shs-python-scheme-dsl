# SRFIs: the supported layer

> **The claim, in one paragraph.** The SRFI layer is a set of R7RS *libraries*
> on top of the library system (A13): `(srfi 1)`, `(srfi 26)`, `(srfi 88)`,
> `(srfi 89)`, `(srfi 197)`, and `(srfi 241)`. A library either meets its
> SRFI's semantics — audited name by name, with the tests to show it — or it
> fails loudly as "not implemented yet". Nothing is aliased into pretending.
> The plan and the per-name audit live in
> [`docs/SRFI_TASKS.md`](../../docs/SRFI_TASKS.md); the umbrella language
> contract is [`lisp-dsl.md`](lisp-dsl.md); the base-language matrix is
> [`r7rs.md`](r7rs.md).

## Status

| Library | Status | Where it lives | Tests |
| --- | --- | --- | --- |
| `(scheme base)` | supported | Python registry generated from the A0 manifest | `tests/test_library.py` |
| `(scheme write)` | supported | Python registry generated from the A0 manifest | `tests/test_library.py` |
| `(srfi 1)` | supported | `lisp/srfi1.scm` (pure Lisp) | `tests/test_srfi.py` |
| `(srfi 26)` | supported | `lisp/srfi26.scm` (pure Lisp, `defmacro`) | `tests/test_srfi.py` |
| `(srfi 88)` | supported | core: reader, evaluator, printer, `builtins.py` | `tests/test_srfi.py` |
| `(srfi 89)` | supported | `lisp/srfi89.scm` (pure Lisp, `defmacro`) | `tests/test_srfi.py` |
| `(srfi 197)` | supported | `lisp/srfi197.scm` (pure Lisp, `defmacro`) | `tests/test_srfi.py` |
| `(srfi 241)` | supported | core: `evaluator.py` (the global `match`) | `tests/test_srfi.py`, `tests/test_rop.py` |
| `(srfi 204)` | withdrawn | — | importing it fails, naming SRFI 241 |

## Layout and the "supported subset" rule

- **Libraries are the A13 registry.** Every library has an explicit export
  list; importing binds exactly those names, and an export that is not bound
  in the library is an error at import time. The export list is a checked
  constant next to the implementation (`_SRFI1_EXPORTS` in
  `lisp/library.py`), and a test asserts every exported name is bound in the
  library's own environment.
- **Pure-Lisp libraries** (`srfi1.scm`, `srfi26.scm`) load into a private
  scope whose parent is the owning environment. The private scope is
  instantiated *before* its exports are read (a `define-library`'s export
  list only exists after its definitions run), and self-imports hit the
  circular-instantiation guard.
- **Core-backed libraries** (`(srfi 88)`) register the names of primitives
  that already exist in the base environment; the library scopes them, it
  does not duplicate them.
- **A declared but unimplemented library** fails `(import ...)` with
  "not implemented yet", and `(srfi 204)` fails naming SRFI 241 (204 is
  withdrawn; 241 is the target).

## `(srfi 1)` — the list library

Implemented in `lisp/srfi1.scm`; a pure-Lisp audit-and-complete of the SRFI 1
procedure index. Semantics follow the SRFI, not the prelude's historical
helpers:

- **Fold direction and argument order.** `fold` is SRFI 1's left-to-right
  `fold` with `(f elt acc)`; `fold-right` mirrors it. `reduce` is SRFI 1's
  `reduce` (an empty list answers the init; `(reduce + 0 '(1 2 3))` is 6).
- **Variadic map/for-each stop at the shortest list.** The `(scheme base)`
  `map`/`for-each` still require equal lengths and raise; the SRFI 1 ones are
  distinct bindings, renamed in the default profile (see the collision table
  below).
- **`member`/`assoc` accept the optional comparator** — `(member "b" '("a"
  "b") string=?)` — and are the *same binding objects* as the base ones
  (`(eq? member srfi-1:member)`), so combined imports never collide.
- **lset operations take `elt=` as their first argument**: `(lset-union
  equal? '(1 2) '(2 3))`. `lset-union` preserves the first list's order and
  appends each later list's new elements in order.
- **`iota` takes `start` and `step`**: `(iota 5 10 -2)` is `(10 8 6 4 2)`.
- **Dotted and circular lists.** `cons*` builds dotted lists;
  `proper-list?`/`circular-list?`/`dotted-list?` partition all values;
  `length+` answers `#f` on a circular list. `circular-list` builds a true
  cycle.
- **Mutation** uses `set-car!`/`set-cdr!` (core primitives). **Limitation:**

## `(srfi 26)` — `cut` / `cute`

Implemented in `lisp/srfi26.scm` as `defmacro`s (the raw tool): the macro
scans its form and generates a fresh lambda parameter list, with every
generated name a `gensym`, so caller variables are safe.

- `(cut cons (+ a 1) <>)` ≡ `(lambda (g) (cons (+ a 1) g))` — non-slot
  expressions re-evaluate on every call.
- `(cute cons (+ a 1) <>)` ≡ `(let ((t (+ a 1))) (lambda (g) (cons t g)))` —
  non-slot expressions evaluate once, at construction.
- `<...>` is the rest slot; it must be last and must immediately follow a
  `<>`. `(cut list 1 <> 3 <...>)` ≡ `(lambda (g . r) (apply list 1 g 3 r))`.
- `cut`/`cute` are syntax, not procedures: `(procedure? cut)` is an error.
- `partial` and `curry` remain project **extensions** — procedures, not
  syntax — and are not part of the SRFI claim.

## `(srfi 88)` — keyword objects

Keywords are a core data type, exposed through the library:

- **Reader:** a token ending in `:` is a keyword — `host:`, `port:`, `foo:`.
  A lone `:` is a symbol; `:host` is a symbol (SRFI 88's spelling is the
  suffix colon); `foo:bar` is an ordinary identifier; `|host:|` is a symbol.
- **Values:** a keyword is self-evaluating, interned (`(eq? (string->keyword
  "a") (string->keyword "a"))`), and distinct from symbols and strings:
  `(keyword? host:)` but `(symbol? host:)` and `(string? host:)` are false,
  and `(equal? host: 'host)` is false.
- **Printer:** a keyword writes back with its colon, so it reads round-trip.
## `(srfi 89)` — `define*` / `lambda*`

Implemented in `lisp/srfi89.scm` as `defmacro`s, following SRFI 89's
recommended expansion shape: `lambda*` becomes an ordinary `lambda` over one
rest parameter, a runtime split of the arguments, and a single `let*` that
binds every parameter in formals order. `Closure`, `_bind`, `apply`, and
`procedure-arity` are untouched, and pure R7RS formals expand directly to
`lambda` with no overhead.

- **Sections, in either order:** required `v`, optional `(v default)`;
  named `(keyword v)` (required) or `(keyword v default)` (optional); a
  trailing `. r` rest. All variables are distinct; all keywords are distinct.
- **Keyword arguments may appear anywhere** in a call; each must be known,
  followed by a value, and supplied at most once. Unknown keyword, duplicate
  keyword, missing value, missing required keyword, too few, and too many
  arguments (without a rest) are all clear errors.
- **Defaults are evaluated left to right, at most once per call**, in the
  scope of the parameters bound before them — positional and named alike —
  because every default sits behind a generated `if` inside one `let*`.
- The library's private helpers are embedded in the expansion as closure
  *values*, not names: the expansion runs in the caller's scope, where the
  library's names are not visible (the same sealing rule SRFI 26 hit).


## `(srfi 197)` — pipeline operators

Implemented in `lisp/srfi197.scm` as `defmacro`s. Every macro does its work
entirely at *expansion* time — the generated code references only core names
(`apply`, `call-with-values`, `lambda`, `let`, `if`) — so expansions are safe
in any scope and no library helper has to be embedded as a value.

- **`chain`** evaluates steps left to right, threading the pipeline value(s).
  A step's `_` placeholders are replaced by the previous step's values in
  order, so multiple values fan out across multiple placeholders; a step with
  no placeholder still evaluates and replaces the pipeline value; a trailing
  `_ ...` collects all remaining values into an `apply`. The expansion is a
  nest of `call-with-values`, so steps may return multiple values and the
  last step's values are the result.
- **`chain-and`** checks each step's value (even for steps without a
  placeholder) and stops with `#f` on the first false one, without evaluating
  later steps; at most one placeholder per step and no ellipsis.
- **`chain-when`** steps are `(guard step)` or `(step)`; a false guard skips
  the step without evaluating it and reuses the previous pipeline value.
- **`chain-lambda`** takes its arity from the first step's placeholders; a
  trailing `_ ...` makes it variadic. The first step's value feeds the
  remaining steps as a chain.
- **`nest` / `nest-reverse`** substitute *lexically* (top level of each step,
  exactly one placeholder per step) and evaluate once at the end — which is
  what lets them build quoted data (`(nest '_ (1 2 _) (3 _ 5) (_) 4)` is
  `'(1 2 (3 (4) 5))`) and contain special forms like `if`/`let`/`lambda`.
  Nesting a `nest` inside a `nest` works via a custom placeholder.
- **Custom placeholder/ellipsis:** a symbol second argument to `chain` (and
  the third for the ellipsis) overrides `_`/`...`; `chain-lambda` and
  `nest-reverse` likewise.
- `->` / `->>` remain project **extensions** with their Clojure-style
  semantics; they are not part of the SRFI claim. `chain` is not suitable for
  pipelines containing `if`/`let` — use `nest`.

## `(srfi 241)` — the standard `match`

Implemented as a Python pattern compiler in `lisp/evaluator.py` — `match` is a
global special form (like SRFI 88's core-backed primitives, the `(srfi 241)`
Library entry only scopes the name for the import/collision rules). The
project's tag-dispatch matcher is renamed **`variant-match`** and keeps its
exact old semantics for the Tetris scripts.

- **Patterns:** `,_` (wildcard), `,x` — a pattern variable, which the reader
  spells `(unquote x)` — pattern symbols and other constants by `equal?`,
  `()`, proper and dotted list patterns, vector patterns `#(...)`, and one
  ellipsis `pe ...` per list (fixed patterns take the first elements; the
  ellipsis pattern takes the rest, deterministically, no backtracking).
- **Ellipsis binding:** each element's bindings are collected in order, so a
  variable bound by the ellipsis pattern becomes a list; variables are
  pre-bound to `()`, so zero elements still bind the empty list. Nested
  ellipses collect lists of lists.
- **Guards:** a clause's second element headed by the auxiliary symbol
  `guard` is the guard; a false guard skips the clause without leaking its
  bindings. The auxiliary syntax (`guard`, `_`, `...`, `->`, `unquote`) is
  recognized structurally and is *not* exported — exporting only `match`
  avoids a needless collision with `(scheme base)`.
- **Reader:** square brackets `[` / `]` are list delimiters exactly like
  parentheses (SRFI 241's clause syntax reads as written). Symbols containing
  brackets are therefore no longer valid tokens.
- **Catamorphism** (S6b): `,[op -> x ...]` evaluates *op* in the environment
  extended by the pattern's bindings and invokes it on the matched value;
  `,[x ...]` (no operator) defaults to the match itself, re-entered with the
  matched value as the new input. The cata variables are bound left to right
  after the operators are evaluated; a cata variable bound inside an ellipsis
  collects its results into a list. A repeated pattern variable becomes an
  equality constraint (`(match '(1 1) [(,a ,a) 'same])` matches; `(1 2)`
  does not). **Deviation:** the cata recursion is a nested interpreter call,
  not a trampolined tail call — bounded by the data's depth, not the stack.
- **Ellipsis-aware quasiquote (S6b):** inside a `match` body, `` ` `` is
  ellipsis-aware: `...` after a subform splices the list its commas evaluate
  to (`` `(a ,(+ 1 2) ,expr ... b) `` splices), `(... form)` disables
  ellipsis meaning inside *form* (commas still evaluate), `,@` is `,`
  followed by `...`, and the dotted tail continues the list. A template
  followed by *multiple* ellipses does not distribute — a documented
  deviation. The global `quasiquote` is unchanged.
- The dotted pattern matches a proper list's tail (an improper `Pair` is not
  a sequence in this dialect, so `(1 . 2)` patterns match no value here).

## Collision resolution

Shared names between `(scheme base)` and `(srfi 1)`:

| Name | Resolution |
| --- | --- |
| `map`, `for-each` | **Divergent semantics** — R7RS requires equal lengths, SRFI 1 stops at the shortest. Both bindings exist; importing both without renaming raises a collision error naming the name. The documented combined import renames them to `srfi-1:map`/`srfi-1:for-each`. |
| `member`, `assoc` | One binding, extended with the optional comparator; re-exported by `(srfi 1)` as the *same object* (`(eq? member srfi-1:member)`). |
| `car`, `cdr`, `filter`, and the rest of the shared set | Re-exported as the same binding objects; no collision. |

`(srfi 26)`'s `cut`/`cute` and `(srfi 88)`'s keyword names collide with
nothing in the base language.

**Note:** the *default* DSL profile (S8) pre-imports the SRFI libraries with
the renames above, so `(cut ...)`, `host:`, `define*`, and `chain` work
without an import preamble. `make_env(profile="r7rs")` is the strict
conformance target: the core and the prelude only, no SRFI pre-import —
programs say `(import (srfi 26))` there.

- **Procedures:** `keyword?`, `keyword->string` (the name without the
  colon), `string->keyword`.
- **Import prefixes:** `(prefix (only (scheme base) car) base:)` still binds
  `base:car` — the prefix accepts a keyword and re-attaches its colon.
- Keywords hash separately from symbols and strings, so they key a
  `hash-table` under `equal?` semantics.

  `set-cdr!` works on `Pair` cells only — proper lists are host lists, so a
  proper list's tail cannot be changed in place and `set-cdr!` on one raises
  a type error. The linear-update family (`append!`, `reverse!`, `map!`,
  `delete!`, ...) is allowed to alias its input and returns the same values.

## Deviations

Every claim above is checkable; these are the deliberate departures from the
SRFIs as written. Nothing was silently dropped: a name that is not supported
appears here with a reason.

- **`(srfi 204)`** is not implemented and never will be: it is withdrawn, and
  its subject is this project's `(srfi 241)`. Importing it fails, naming
  SRFI 241.
- **`(srfi 1)`** linear-update procedures (`append!`, `reverse!`, `map!`,
  `delete!`, ...) may be pure; they return the same values. `map`/`for-each`
  differ from `(scheme base)` on unequal lengths (SRFI 1 stops at the
  shortest; R7RS requires equal lengths), which is why the combined import
  renames them. `set-cdr!` works on `Pair` cells only — a proper list is a
  host `list`, so its tail cannot be changed in place. The export list is a
  documented subset of SRFI 1 (the audit checked what the DSL uses).
- **`(srfi 26)`** is syntax (`cut`/`cute`), not the `partial`/`curry`
  procedures.
- **`(srfi 88)`** has no `|...|` quoted keywords and no `#:foo` prefix
  spelling; the keyword syntax is the suffix colon (`host:`), and a lone `:`,
  `:host`, and `foo:bar` are symbols.
- **`(srfi 89)`** is `define*`/`lambda*` with named parameters spelled
  `(keyword v default)` per the grammar above; it is not Common Lisp `&key`
  or DSSSL `#!key`, and `case-lambda` is not extended to SRFI 89 formals.
- **`(srfi 197)`** is the `chain` family; `->`/`->>` are the project's own
  extensions and are not part of the SRFI claim. A quasiquote template in a
  `chain` is not ellipsis-aware.
- **`(srfi 241)`** is the global `match`; the project's tag-dispatch matcher
  is the separate `variant-match`. Two documented deviations: the
  catamorphism's recursion is a nested interpreter call, not a trampolined
  tail call (bounded by the data's depth); and a quasiquote template followed
  by *multiple* ellipses does not distribute. The auxiliary syntax (`guard`,
  `_`, `...`, `->`, `unquote`, `unquote-splicing`) is recognized structurally
  and is **not exported**, so exporting only `match` cannot collide with
  `(scheme base)`.
- The dotted list patterns of SRFI 241 match a proper list's tail; an
  improper `Pair` is not a sequence in this dialect, so `(1 . 2)` patterns
  match no value here.

## How to verify

From `python_tetris_lisp/`:

```bash
# the full suite (the count below is the recorded run)
../python_tetris/env/bin/python -m pytest -q

# the SRFI gate
../python_tetris/env/bin/python -m pytest tests/test_srfi.py -q

# the architecture fence (the SRFI layer never learns a game word)
../python_tetris/env/bin/python -m pytest tests/test_architecture.py -q

# the game, headless
../python_tetris/env/bin/python -m lisp play --validate
```

Last recorded run: **1057 passed**, plus `play --validate` → `ok`. If the
count drifts, update this section in the same change.

## The profiles

- **`profile="dsl"` (the default)** — `make_env()`, the REPL, `run`, the game,
  and embedded hosts: the SRFI layer is pre-imported with the collision
  resolutions above. The profile is *additive*: it binds no name the core
  already binds, so no existing meaning changes. `(features)` reports
  `dsl-profile` and the `srfi-*` identifiers.
- **`profile="r7rs"`** — the strict subset: the core and the prelude only.
  This is the conformance target; the conformance tests run on it, and it is
  the profile to use when you want to know whether a program is portable.
- **`profile=None`** — no profile at all, for tests that need the bare
  machinery.

`install_tetris` is orthogonal: no profile installs game bindings. The
profile lint (`lisp/profile.lint`) checks that every shipped `.scm` file
loads under the default profile; `tests/test_profile.py` runs it and proves
it goes red on a file that does not load.

The tables in `tests/test_srfi.py` (`MUST_IMPORT`, `MUST_BIND`, and the
per-library fixtures) are the source of truth for this page's matrix: if a
claim and a test disagree, the test wins, and the page is updated in the same
change.


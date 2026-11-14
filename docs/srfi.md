# SRFIs: the supported layer

> **The claim, in one paragraph.** The SRFI layer is a set of R7RS *libraries*
> on top of the library system (A13): `(srfi 1)`, `(srfi 26)`, `(srfi 88)`,
> `(srfi 89)`, `(srfi 197)`, and `(srfi 241)` — plus the trading layer landed
> as S10–S12: `(srfi 19)` (time and date), `(srfi 158)` (generators and
> accumulators), and `(srfi 160 base)` + `(srfi 160 f64)` (numeric vectors) —
> plus the standard-library wave landed as S14–S18: `(srfi 125)` (hash
> tables), `(srfi 132)` (sorting), `(srfi 64)` (a Scheme test API),
> `(srfi 180)` (JSON), `(srfi 28)` + `(srfi 152)` (formatting and
> strings) — plus the cooperative-concurrency wave: `(srfi 226)` (delimited
> continuations), `(srfi 190)` (coroutine generators), and `(srfi 18)`
> (cooperative threads, mutexes, and condition variables). A library either meets its
> SRFI's semantics — audited name by name, with the tests to show it — or it
> fails loudly as "not implemented yet". Nothing is aliased into pretending.
> The plan and the per-name audit live in
> [`docs/SRFI_TASKS.md`](SRFI_TASKS.md); the umbrella language
> contract is [`lisp-dsl.md`](lisp-dsl.md); the base-language matrix is
> [`r7rs.md`](r7rs.md).

## Status

| Library | Status | Where it lives | Tests |
| --- | --- | --- | --- |
| `(scheme base)` | supported | Python registry generated from the A0 manifest | `tests/test_library.py` |
| `(scheme write)` | supported | Python registry generated from the A0 manifest | `tests/test_library.py` |
| `(srfi 1)` | supported | `shslisp/srfi1.scm` (pure Lisp) | `tests/test_srfi.py` |
| `(srfi 26)` | supported | `shslisp/srfi26.scm` (pure Lisp, `defmacro`) | `tests/test_srfi.py` |
| `(srfi 88)` | supported | core: reader, evaluator, printer, `builtins.py` | `tests/test_srfi.py` |
| `(srfi 89)` | supported | `shslisp/srfi89.scm` (pure Lisp, `defmacro`) | `tests/test_srfi.py` |
| `(srfi 197)` | supported | `shslisp/srfi197.scm` (pure Lisp, `defmacro`) | `tests/test_srfi.py` |
| `(srfi 241)` | supported | core: `evaluator.py` (the global `match`) | `tests/test_srfi.py`, `tests/test_rop.py` |
| `(srfi 19)` | supported | core: `builtins.py` + `shslisp/srfi19.py` | `tests/test_srfi19.py` |
| `(srfi 158)` | supported | prelude: `shslisp/generators.scm` | `tests/test_generators.py` |
| `(srfi 160 base)` | supported | core: `builtins.py` + `shslisp/srfi160.py` | `tests/test_srfi160.py` |
| `(srfi 160 f64)` | supported | core: `builtins.py` + `shslisp/srfi160.py` | `tests/test_srfi160.py` |
| `(srfi 28)` | supported | core: `shslisp/srfi28.py` | `tests/test_s14_to_s18_srfis_tdd.py` |
| `(srfi 64)` | supported | `shslisp/srfi64.scm` (pure Lisp: assertion macros + runner) | `tests/test_s14_to_s18_srfis_tdd.py` |
| `(srfi 125)` | supported | core: `shslisp/srfi125.py` over the core's `HashTable` | `tests/test_s14_to_s18_srfis_tdd.py` |
| `(srfi 132)` | supported | core: `shslisp/srfi132.py` (Python Timsort) | `tests/test_s14_to_s18_srfis_tdd.py` |
| `(srfi 152)` | supported | core: `shslisp/srfi152.py` (seven names) | `tests/test_s14_to_s18_srfis_tdd.py` |
| `(srfi 180)` | supported | core: `shslisp/srfi180.py` (stdlib `json`) | `tests/test_s14_to_s18_srfis_tdd.py` |
| `(srfi 226)` | supported | core: `shslisp/srfi226.py` (baton-scheduled cooperative fibers) | `tests/test_c01_srfi226_tdd.py` |
| `(srfi 190)` | supported | `shslisp/srfi190.scm` (`coroutine-generator`, `yield`) | `tests/test_c02_srfi158_190_tdd.py` |
| `(srfi 18)` | supported | core: `shslisp/srfi18.py` (cooperative threads, mutexes, condvars) | `tests/test_c03_srfi18_tdd.py` |
| `(srfi 204)` | withdrawn | - | importing it fails, naming SRFI 241 |

## Layout and the "supported subset" rule

- **Libraries are the A13 registry.** Every library has an explicit export
  list; importing binds exactly those names, and an export that is not bound
  in the library is an error at import time. The export list is a checked
  constant next to the implementation (`_SRFI1_EXPORTS` in
  `shslisp/library.py`), and a test asserts every exported name is bound in the
  library's own environment.
- **Pure-Lisp libraries** (`srfi1.scm`, `srfi26.scm`) load into a private
  scope whose parent is the owning environment. The private scope is
  instantiated *before* its exports are read (a `define-library`'s export
  list only exists after its definitions run), and self-imports hit the
  circular-instantiation guard.
- **Core-backed libraries** (`(srfi 88)` and the S10–S18 wave) install their
  Python primitives into one private scope the first time an import needs
  them — never into the core floor. A name the base environment already binds
  with exactly the SRFI's meaning (`(srfi 88)`'s predicates, `(srfi 125)`'s ten
  hash-table names) resolves to that *same binding object*; a name whose SRFI
  spelling has a wider arity or a different meaning (`(srfi 152)`'s
  `string-split`) is defined by the library, and the import is the consent.
- **A declared but unimplemented library** fails `(import ...)` with
  "not implemented yet", and `(srfi 204)` fails naming SRFI 241 (204 is
  withdrawn; 241 is the target).

## `(srfi 1)` — the list library

Implemented in `shslisp/srfi1.scm`; a pure-Lisp audit-and-complete of the SRFI 1
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

Implemented in `shslisp/srfi26.scm` as `defmacro`s (the raw tool): the macro
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

Implemented in `shslisp/srfi89.scm` as `defmacro`s, following SRFI 89's
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

Implemented in `shslisp/srfi197.scm` as `defmacro`s. Every macro does its work
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

Implemented as a Python pattern compiler in `shslisp/evaluator.py` — `match` is a
global special form (like SRFI 88's core-backed primitives, the `(srfi 241)`
Library entry only scopes the name for the import/collision rules). The
project's tag-dispatch matcher is renamed **`variant-match`** and keeps its
exact semantics for host scripts.

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
- **`(srfi 19)`** is the workhorse subset the ledger scoped (S10), audited
  against the final specification. The constants `time-tai` and `time-thread`
  exist, but `current-time` **refuses them loudly** — there is no
  leap-second table here and no thread clocks in this interpreter, and
  pretending UTC seconds are TAI seconds would be a silent lie. No leap
  seconds: `date-second` is 0..59. No `time-monotonic`↔UTC conversions: the
  monotonic clock is a stopwatch with an arbitrary origin — differences
  only. Zone offsets are SRFI 19's integer seconds east of UTC; there is no
  zone-name vocabulary and no `date-zone-name`/`date-dst?` (the reference
  surface does not require them). `date->string` supports `~~ ~a ~A ~b ~B
  ~c ~d ~D ~e ~h ~H ~I ~j ~k ~l ~m ~M ~n ~N ~p ~r ~S ~T ~U ~w ~W ~x ~X ~y
  ~Y ~z ~1 ~2 ~3 ~4 ~5` with C-locale English names; with no format
  argument it defaults to `~c`, as the reference does, and `~z` prints `Z`
  for a zero offset (the reference's spelling) and `+HHMM`/`-HHMM`
  otherwise. `string->date` implements Table 2's required converters
  (`~~ ~a ~A ~b ~B ~d ~e ~h ~H ~k ~m ~M ~S ~y ~Y ~z`), with unset fields
  defaulting to 1900-01-01 UTC and `~y` pivoting within 50 years of the
  current year. `~a`/`~A` and `~b`/`~h`/`~B` distinguish abbreviated from
  long names (matched exactly, case-insensitively, not by prefix), and `~z`
  reads exactly `HHMM` or `HH:MM` after the sign — also `Z`/`z`, and, as an
  extension, `UTC`/`GMT`/`UT`. The readers are width-capped like the
  reference's (`~d`/`~H`/`~M`/`~S` read at most two digits, `~Y` four), the
  time-of-day fields are range-checked like `make-date`, and the whole
  input must match the template — trailing garbage fails. Unknown
  directives fail loudly.
- **`(srfi 158)`** is the final export list, audited name by name. Its two
  coroutine constructors — `make-coroutine-generator` and
  `make-for-each-generator` — are powered by `shslisp`'s baton-scheduled
  `CooperativeFiber` runtime (`tests/test_c02_srfi158_190_tdd.py`). The S9
  `generator-end` sentinel is still defined and every library consumer still
  accepts it, so pre-S12 code keeps running; new code uses the eof-object.
  The final SRFI has no `max`/`min` accumulators, and none are claimed.
- **`(srfi 160)`** ships `(srfi 160 base)` (all twelve types) and
  `(srfi 160 f64)` (the full SRFI-133-shaped set, plus
  `make-f64vector-generator` and `write-f64vector`); the other eleven per-type
  full libraries do not exist yet, and importing one — `(srfi 160 u8)` —
  fails loudly. `@vector-comparator` is **omitted**: it requires SRFI 128,
  which is not scheduled; the omission is documented, not shimmed. Element
  domains are the spec's, enforced loudly: exact integers in range for the
  integer vectors, an *inexact* real for `f32`/`f64`, an inexact complex for
  `c64`/`c128` — an exact `1` is not an `f64` element. The reader tags
  cover eleven types; `#u8(` stays the R7RS bytevector. `fold`'s `kons`
  receives the state first, exactly as SRFIs 43/133 spell it.
- **`(srfi 125)`** re-exports ten core bindings and adds three SRFI spellings.
  `make-hash-table`'s optional comparator is accepted and **ignored**: the one
  storage is `equal?`-keyed, and SRFI 128 comparators are not scheduled, so
  there is no second equivalence to honour (the SRFI's default comparator is
  exactly `equal?`). `hash-table-ref`'s optional third argument is a thunk or
  a value, the core's shape. `hash-table->alist` answers two-element
  `(key value)` lists, and `alist->hash-table` accepts those *and* dotted
  pairs.
- **`(srfi 132)`** ships the six non-destructive sort/`sorted?` names. The
  mutation operators (`list-sort!`, `vector-sort!`, ...) and the
  merge/median/selection families are **not claimed** — importing looks for
  the six exported names only. `list-sort` and `list-stable-sort` share one
  stable implementation: stability is a stronger guarantee than SRFI 132
  requires of `list-sort`, never a different answer.
- **`(srfi 64)`**'s `test-error` optional error-type is a **predicate** over
  the caught condition (this dialect's conditions are `ErrorObject`s, not
  SRFI 64's type objects): `(test-error error-object? (car 1))`. The only
  runner is the simple one, and `test-end` prints one summary line
  (`;; name: P passed, F failed, T total`) and returns the runner vector.
  The full SRFI 64 runner/specifier protocol is not claimed.
- **`(srfi 152)` — `string-trim` trims BOTH ends here.** SRFI 152 gives that
  name the left-only job and reserves both-ends for `string-trim-both`. This
  dialect's core has always spelled the both-ends operation `string-trim`
  (`shslisp/builtins.py`), and the locked S18 test pins that meaning
  (`(string-trim "  hi  ")` ⇒ `"hi"`), so the library exports the established
  meaning: `string-trim` and `string-trim-both` are the same both-ends
  procedure, and the right-only spelling is not claimed. Making the name
  left-only would silently change existing programs on import — a subset is
  honest, a silent meaning change is not. A portable SRFI 152 program can see
  this difference. The trim predicate may be a char predicate, a character,
  or a string of characters to strip. `string-split`/`string-join` accept
  SRFI 152's optional arguments and supersede the core's simpler spellings
  inside an importing scope; `string-contains` (index or `#f`) is a different
  name from the core's `string-contains?` predicate.
- **`(srfi 28)`** adds `~%` and `~~` (SRFI 48's directives; SRFI 28 specifies
  only `~a`/`~s`). Both are additive. A missing argument, an unknown
  directive, or a leftover argument is a loud error.
- **`(srfi 180)`** is the two procedures `json-read`/`json-write`, and both
  speak **text**: `json-read` takes the JSON string and `json-write` answers
  it. SRFI 180's port-oriented spellings (`json-read-file`, the optional port,
  `json-lines-*`) are not claimed — `(write-string (json-write x) port)` is
  the port path. A JSON object with duplicate keys keeps the last value
  (unspecified in the SRFI), `'()` encodes as `[]` (write `'null` for JSON
  null), a bare symbol encodes as its JSON string, and a dotted pair that is
  not an object entry is refused loudly.

## The generator library: prelude, not an SRFI (S9)

Landing alongside the SRFI layer is **`shslisp/generators.scm`** (task S9 in
[`SRFI_TASKS.md`](SRFI_TASKS.md)): lazy sequences as ordinary closures. A
generator is a procedure of zero arguments answering the next value, and the
unique `generator-end` object at exhaustion — no evaluator change, no
continuations, shipped in both profiles as part of the prelude.

- **Constructors:** `generator`, `list->generator`, `vector->generator`,
  `make-range-generator` (one argument is infinite), `make-cycle-generator`.
- **Lazy combinators:** `gmap` (variadic, stops at the shortest, the SRFI 1
  `map` rule made lazy), `gfilter`, `gtake`/`gdrop` (both answer generators).
- **Drains:** `generator->list` (optional `k`), `generator->vector`,
  `generator-fold`, `generator-for-each`.

It is claimed as **`(srfi 158)`** since S12: the import binds the audited
surface — the eof-object protocol, the full combinator set, and the
accumulators — over these same prelude bindings. The tests are
[`tests/test_generators.py`](../tests/test_generators.py) and
[`tests/test_c02_srfi158_190_tdd.py`](../tests/test_c02_srfi158_190_tdd.py); the
S9 `generator-end` sentinel note is under [Deviations](#deviations).

## The trading layer: S10–S12

Three libraries landed (2026-11-05; ledger entries S10–S12 in
[`SRFI_TASKS.md`](SRFI_TASKS.md)) for the DSL's systematic-trading use —
Quant Data Manager 1-minute bars through pandas/numpy, live strategies on
MetaTrader 5. Each passed the same gate as the SRFIs above: audited name by
name against the final specification, with the tests to show it.

- **`(srfi 19)` — time and date (S10).** Core-backed Python primitives over
  `datetime`/the proleptic Gregorian calendar: `time-utc`/`time-monotonic`/
  `time-process`/`time-duration`, the immutable `date`, the comparison and
  duration arithmetic, `time-utc->date`/`date->time-utc`, the Julian Day
  family, and `date->string`/`string->date`. The deviations are listed under
  [Deviations](#deviations) — no TAI, no leap seconds, integer offsets.
- **`(srfi 160)` — numeric vectors (S11).** `(srfi 160 base)` covers all
  twelve types with the SRFI-4 eight and the `@?` predicates;
  `(srfi 160 f64)` is the full SRFI-133-shaped operation set. The payload is
  a Python `array.array` — the buffer protocol is the numpy bridge, and the
  reader/printer round-trip `#f64(...)`-style literals.
- **`(srfi 158)` — generators and accumulators (S12).** The S9 prelude,
  audited against the final SRFI 158 surface: the eof-object exhaustion
  protocol, the full combinator set, the multi-generator drains, the
  searching half, and the accumulators.

The default DSL profile pre-imports all of them (plus the feature identifiers
`srfi-19`, `srfi-158`, `srfi-160`); the strict `r7rs` profile leaves `(srfi 19)`
and `(srfi 160)` import-only — their primitives install into the libraries'
own scopes on first import, never the core floor — while `(srfi 158)` rides
the prelude in both profiles, as [the generator section](#the-generator-library-prelude-not-an-srfi-s9)
records.

## The standard-library wave: S14–S18

Five libraries landed (2026-11-14; ledger entries S14–S18 in
[`SRFI_TASKS.md`](SRFI_TASKS.md)) for the jobs a host script reaches for
between strategies: a dictionary that is not a list scan, a sort that is not
a Scheme merge loop, a test suite, JSON telemetry, and text assembly.

- **`(srfi 125)` — hash tables (S14).** Core-backed on the existing
  `equal?`-keyed `HashTable` (`shslisp/types.py`): `make-hash-table`,
  `hash-table-ref`/`-ref/default`/`-set!`/`-delete!`, `hash-table-contains?`,
  `hash-table-size`, the keys/values/`->alist` views, and `alist->hash-table`.
  Every operation is `O(1)` on average — a list or a vector works as a key,
  because `hash_key` canonicalises it. A missing key without a default is a
  loud condition.
- **`(srfi 132)` — sort libraries (S15).** Python Timsort behind the caller's
  Scheme comparator: `list-sorted?`, `list-sort`, `list-stable-sort`,
  `vector-sorted?`, `vector-sort`, `vector-stable-sort`, with the vector
  variants' optional `[start end]` subrange. Both sorts are stable here.
- **`(srfi 64)` — a Scheme API for test suites (S16).** `shslisp/srfi64.scm`:
  `test-begin`/`test-end`/`test-group`, the `test-assert`/`-equal`/`-eqv`/`-eq`
  assertion macros, `test-error`, and the simple runner
  (`test-runner-current`, `test-runner-simple`). The assertions are **syntax**:
  `(test-error (car 1))` must receive the expression unevaluated, and every
  assertion catches a raising expression as a test *error* instead of letting
  it escape.
- **`(srfi 152)` — string utilities (S18).** Seven names:
  `string-split`, `string-join`, `string-contains`, `string-trim`,
  `string-trim-both`, `string-prefix?`, `string-suffix?` — with SRFI 152's
  grammars (`infix`, `strict-infix`, `suffix`, `prefix`) and split `limit`.
- **`(srfi 28)` — basic format strings (S18).** `format` with `~a` (display),
  `~s` (write), `~%` (newline), `~~` (tilde); `#f` answers the string, `#t`
  and a port write through `(current-output-port)`.
- **`(srfi 180)` — JSON (S17).** `json-read`/`json-write` over the stdlib
  `json`: objects are alists with string keys, arrays are vectors, `null` is
  the symbol `null`, booleans and numbers are preserved, and malformed JSON
  or an unencodable value is a loud error.

**Neither profile pre-imports these.** The DSL profile's identifier list is
part of the published surface (`tests/test_profile.py` pins it), and these
libraries are the ones a script opts into: `(import (srfi 125))` in either
profile, with the primitives installing into the library's own scope on first
import. `(srfi 64)` is pure Lisp and scopes the same way.

## How to verify

From a checkout of this project:

```bash
# the full suite
python -m pytest -q

# the SRFI gate (plus the docs drift guard)
python -m pytest tests/test_srfi.py tests/test_generators.py tests/test_docs.py -q

# the trading-layer libraries' own suites (S10-S12)
python -m pytest tests/test_srfi19.py tests/test_srfi160.py tests/test_generators.py -q

# the standard-library wave's audited surface (S14-S18)
python -m pytest tests/test_s14_to_s18_srfis_tdd.py -q
```

Last recorded run (2026-11-14, a Windows checkout, after S14–S18 landed): the
extended SRFI gate — `tests/test_srfi.py`, `tests/test_generators.py`,
`tests/test_srfi19.py`, `tests/test_srfi160.py`,
`tests/test_s14_to_s18_srfis_tdd.py`, plus the docs drift guard — is
**271 passed**. The full suite is **1,204 passed** on Windows: the
pre-R-04 path failures (raw `tmp_path` backslashes inside Scheme string
literals) are gone. If the count drifts, update this section in the same
change.

## The profiles

- **`profile="dsl"` (the default)** — `make_env()`, the `shs` CLI, and
  embedded hosts: the SRFI layer is pre-imported with the collision
  resolutions above. The profile is *additive*: it binds no name the core
  already binds, so no existing meaning changes. `(features)` reports
  `dsl-profile` and the `srfi-*` identifiers.
- **`profile="r7rs"`** — the strict subset: the core and the prelude only.
  This is the conformance target; the conformance tests run on it, and it is
  the profile to use when you want to know whether a program is portable.
- **`profile=None`** — no profile at all, for tests that need the bare
  machinery.

Host editions are orthogonal: no profile installs host bindings. The
profile lint (`shslisp/profile.lint`) checks that every shipped `.scm` file
loads under the default profile; `tests/test_profile.py` runs it and proves
it goes red on a file that does not load.

The S14–S18 libraries are deliberately **not** pre-imported in either
profile. The DSL profile's identifier list is pinned by
`tests/test_profile.py` and part of the published surface; the wave's
libraries are the opt-in half of the layer — `(import (srfi 125))` where a
script wants a dictionary. Their primitives install into the library's own
scope on first import, exactly like `(srfi 19)`'s.

The tables in `tests/test_srfi.py` (`MUST_IMPORT`, `MUST_BIND`, and the
per-library fixtures) are the source of truth for this page's matrix: if a
claim and a test disagree, the test wins, and the page is updated in the same
change.


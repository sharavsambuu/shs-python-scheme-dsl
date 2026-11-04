# The Lisp DSL — R7RS-small, SRFIs, and the Python seam

This is the umbrella specification for the Lisp that `shs` runs. It answers
four questions in one place:

1. **What is this language for?** Domain-driven design (DDD), railway-oriented
   programming (ROP), monadic pipelines, and typed control flow.
2. **How standard is it?** It is an honest **R7RS-small subset** (the “Option A”
   decision), not a claim of full conformance.
3. **What is on top of R7RS?** A mandatory SRFI layer, enabled by default.
4. **How does Python fit?** The Python seam is a first-class feature, not an
   escape hatch.

The per-name truth lives in `docs/r7rs.md` (R7RS) and `docs/srfi.md` (SRFIs).
This page is the contract those matrices implement. The work is tracked in
[`docs/R7RS_TASKS.md`](R7RS_TASKS.md) and
[`docs/SRFI_TASKS.md`](SRFI_TASKS.md).

> **Status.** The interpreter is mid-migration. The R7RS tasks (A0–A15) and the
> SRFI tasks (S0–S8) are the plan; until they land, a name described here may
> still be missing. Do not read this page as “all of this already runs”. The
> matrices are the checkable truth, and the tests are the final word.

## The one-paragraph version

The DSL is a Scheme-flavoured Lisp with a small, readable Python runtime. It
uses R7RS-small as its base language, adds the standard SRFIs that make
functional pipelines and typed domain code pleasant (`(srfi 1)`, `(srfi 26)`,
`(srfi 88)`, `(srfi 89)`, `(srfi 197)`, `(srfi 241)`), and keeps a declared
Python bridge so a host project can publish its own functions as primitives.
The Python seam is a peer of the R7RS and SRFI layers, not an escape hatch. The
Tetris game is the worked example, not the definition of the language.

## The four pillars

### 1. Domain-driven design

The repository separates **rules** from **adapters**:

- *rules* are pure, hook-free functions: the domain's calculations, validation,
  planning, scoring;
- *adapters* translate between the host's platform and Lisp: input mapping,
  view formatting, file formats.
- The rule is **adapters may load rules; rules may not load adapters** — pin
  it as a test in the host's own suite.

The DSL supports this with ordinary values and functions, plus the SRFI layer:
SRFI 1 for list-shaped domain data, SRFI 89 for optional/named parameters on
domain APIs, SRFI 88 keywords for those parameters, and SRFI 241 for
destructuring domain events.

### 2. Railway-oriented programming (ROP)

`shslisp/rope.scm` defines a closed `Result` variant:

```scheme
(define-variant result
  (ok value)
  (err reason))
```

and builds the functor, monad, and Kleisli composition on one primitive,
`result-bind`:

```scheme
(result-map (ok 21) (lambda (x) (* x 2)))       ;=> (ok 42)
(result-bind (ok 41) (lambda (x) (ok (+ x 1)))) ;=> (ok 42)
(result-bind (err "halt") (lambda (x) (ok (+ x 1)))) ;=> (err "halt")
```

The rest of the library (`result-map-err`, `result-bimap`, `result-fold`,
`result-unwrap`, `result-unwrap-or`, `result-expect`, `result->list`,
`sequence-results`, `traverse-results`) is built from the same two ideas. The
laws are pinned by `tests/test_rop.py`.

### 3. Monadic pipelines

Kleisli arrows are functions `A -> Result`. `>=>` composes two of them;
`pipe-results` threads a value through any number of them:

```scheme
(define (>=> f g)
  (lambda (x) (result-bind (f x) g)))

(pipe-results 1
  (lambda (x) (ok (+ x 1)))
  (lambda (x) (ok (* x 10)))
  (lambda (x) (ok (- x 3))))
;=> (ok 17)
```

`result-do` is the do-notation form; `attempt` lifts a thunk that may raise onto
the rails. The SRFI layer is what makes these pipelines readable: SRFI 1
`fold`/`fold-right` for collections, SRFI 26 `cut`/`cute` for point-free steps,
and SRFI 197 `chain`/`nest` for the data-flow shape.

### 4. Typed control flow

Two matchers, two jobs:

- **`variant-match`** is the project’s exhaustive dispatcher. It is tied to
  `define-variant`, uses bare-symbol binders and tag patterns, and refuses to
  guess when a case is missing:
  ```scheme
  (define-variant outcome
    (win  score)
    (lose reason))

  (variant-match (win 42)
    ((win s)  (string-append "win " (number->string s)))
    ((lose r) (string-append "lose " r)))
  ```
  A non-exhaustive match names the value, the tag, and the declared cases.
- **`match`** is SRFI 241. It is the standard matcher: comma-prefixed pattern
  variables (`(a ,x ,y)`), `,_`, guards, ellipsis, vector patterns, dotted
  patterns, and catamorphism. Use it for data, not for the project’s closed
  variants.

`define-variant` stays a project extension. The SRFI 241 `match` is the global
`match`; the project matcher is `variant-match`. This is the collision policy,
not an accident.

### Pillars and the SRFIs that carry them

| Pillar | Primary SRFIs | Project extensions |
| --- | --- | --- |
| DDD | 1 (lists), 88 (keywords), 89 (named parameters), 241 (destructuring) | host conventions: rules vs adapters, pinned as fences |
| ROP | 1 (folds), 26 (`cut`), 197 (`chain`) | `Result`, `result-*`, `>=>`, `pipe-results`, `result-do`, `attempt` |
| Monadic pipeline | 1, 26, 197 | `result-bind`, `sequence-results`, `traverse-results` |
| Typed control flow | 241 (`match`, guards, catamorphism) | `define-variant`, `variant-match`, exhaustiveness errors |

## The three layers

| Layer | What it gives | Where it is specified |
| --- | --- | --- |
| **R7RS-small subset** | Reader, evaluator, tail calls, closures, the base procedures, `(scheme base)`, `(scheme write)` | `docs/r7rs.md`, [`docs/R7RS_TASKS.md`](R7RS_TASKS.md) |
| **SRFI layer** | SRFI 1, 26, 88, 89, 197, 241 | `docs/srfi.md`, [`docs/SRFI_TASKS.md`](SRFI_TASKS.md) |
| **Python seam** | `install_primitives`, `install_extension`, `make_env`, `run`, `load_lisp` | `shslisp/embed.py`, chapter [28](lisp_tutorial/28-embedding-in-python.md) |

### R7RS-small: the honest claim

The DSL is a **documented subset**, not a full R7RS implementation. The claim is:

> Every form and procedure the matrices mark as supported behaves as R7RS-small
> specifies. Every form or procedure marked as unsupported fails clearly. There
> is no silent third behaviour.

That is what “mostly R7RS-small compliant” means here. It does **not** mean
every R7RS library, every numeric tower, or re-entrant continuations.

Known deviations and boundaries:

- **Truthiness.** R7RS semantics: only `#f` is false. `0`, `""`, and `()` are
  true values; ask `null?` when you mean "empty". (`NIL` keeps a false Python
  `__bool__` for the host's convenience; Lisp control flow uses `is_true`.)
- **Numbers.** Exact integers, exact rationals (R1: `fractions.Fraction`,
  whole values normalized to integers), exact complex pairs (C1–C2: the
  rectangular and polar halves, exact arithmetic, inexact contagion), and
  inexact reals. `(scheme inexact)` and `(scheme complex)` are supported.
- **Continuations.** `call/cc` is escape-only. Option A does not rewrite the
  evaluator for re-entrant continuations.
- **Strings.** Literals are immutable Python `str`; `make-string` and
  `string-copy` return a mutable string that `string-set!`, `string-fill!`,
  and `string-copy!` can modify. Mutating a literal is a clear error.
- **Libraries.** `(load ...)` and textual `include` are the module mechanisms;
  `define-library`/`import`/`export` arrive with A13. `cond-expand`,
  `(features)`, and `(environment ...)` exist, but an environment is a child
  of the interaction scope rather than a restricted import.
- **Records and bytevectors.** `define-record-type`, records, and `#u8(...)`
  bytevectors are implemented; records compare by identity, as R7RS allows.
- **External representation.** `write` round-trips the forms the reader
  accepts, including radix/exactness prefixes, `+inf.0`/`+nan.0`, bar-quoted
  symbols, bytevectors, and the documented string/char escapes. Datum labels
  (`#1=`, `#1#`) and cyclic data are not supported (A14); rational literals
  read as the exact rationals they spell (`1/3`, R2 — `1/0` is a read error,
  `1/x` stays a symbol), and complex literals read and round-trip (`1+2i`,
  `+i`, the polar `2@1`; `#e`/`#i` govern the whole — C3).

The strict profile (`make_env(profile="r7rs")`) is what the conformance harness
measures. The default profile adds the SRFI layer and the project extensions on
top; that is a DSL feature, not an R7RS claim.

### The SRFI layer

These imports are **mandatory ingredients of the target language**:

| Import | What it gives the DSL | Why it is here | Task |
| --- | --- | --- | --- |
| `(scheme base)` | The R7RS base language | The foundation; not an SRFI, but the first import | S0 |
| `(scheme write)` | `display`, `write`, `newline`, `write-char`, `write-string` | Human and machine output | S0 |
| `(srfi 1)` | Lists: `fold`, `fold-right`, `filter`, `iota`, `zip`, `reduce`, `partition`, `span`, `any`, `every`, `list=`, `lset-*`, … | The FP collection layer | S1 |
| `(srfi 26)` | `cut`, `cute` | Partial application without currying; placeholders in the middle | S2 |
| `(srfi 88)` | Keyword objects (`host:`, `port:`), `keyword?`, `keyword->string`, `string->keyword` | Named parameters and readable APIs | S3 |
| `(srfi 89)` | `define*`, `lambda*` | Optional positional and named parameters | S4 |
| `(srfi 197)` | `chain`, `chain-and`, `chain-when`, `chain-lambda`, `nest`, `nest-reverse` | Pipelines with `_` placeholders and multiple values | S5 |
| `(srfi 241)` | `match` | The standard pattern matcher, including guards and catamorphism | S6, S6b |
| `(srfi 204)` | **Not implemented** | Withdrawn Wright–Cartwright–Shinn matcher; use SRFI 241 | none |

The detailed status of each name is in `docs/srfi.md`. The important
distinctions:

- **SRFI 26 is syntax, not `partial`/`curry`.** `partial` and `curry` remain
  extensions.
- **SRFI 197 is not `->`/`->>`.** The SRFI defines `chain`/`nest`; the
  Clojure-style threading macros remain extensions.
- **SRFI 241 is not the project `match`.** The project matcher is
  `variant-match`.
- **SRFI 88 keywords end in a colon.** `host:` is a keyword; `:host` is not.
- **SRFI 89 is `define*`/`lambda*`,** not Common Lisp `&key` or DSSSL `#!key`.

## The default profile

The DSL does **not** require an `(import ...)` preamble. `make_env()` installs
the **DSL profile**, so the `shs` CLI and embedded hosts see the
same language. This is a deliberate extension: it makes the SRFI layer the
language people actually use, instead of a library they forget to import.

The collision policy is explicit:

| Name family | Default binding | Collision resolution |
| --- | --- | --- |
| `map`, `for-each` | R7RS semantics (equal-length lists) | SRFI 1 versions are `srfi-1:map`, `srfi-1:for-each` |
| `member`, `assoc` | one binding with the optional comparator | re-exported from both, not aliased |
| `match` | SRFI 241 | project matcher is `variant-match` |
| `chain`, `nest`, … | SRFI 197 | `->`/`->>` stay as extensions |
| `cut`, `cute` | SRFI 26 | `partial`/`curry` stay as extensions |
| `define*`, `lambda*` | SRFI 89 | none |
| keywords | SRFI 88 | none |
| `fold`, `filter`, `iota`, `zip`, `reduce`, `partition`, `span`, `any`, `every` | SRFI 1 semantics | shared base names are the same binding; `map`/`for-each` are the exception |

**Why `map`/`for-each` keep R7RS semantics.** The DSL claims “mostly
R7RS-small”; the base names should behave like the base names. Code that wants
the SRFI 1 shortest-list behaviour says `srfi-1:map` explicitly.

**Why `match` is SRFI 241 and `variant-match` is the extension.** The standard
matcher should have the standard name. The project matcher’s bare-symbol
binders and tag patterns are not SRFI 241 syntax, so it gets a name that says
what it does.

**Why `reduce` changes.** The old global `reduce` was an alias for `foldl`.
SRFI 1 `reduce` is a different procedure: it uses `ridentity` only for the empty
list, then folds from the first element. The default profile uses the SRFI
semantics; S8 audits and migrates call sites.

**Strict mode.** `make_env(profile="r7rs")` builds the subset with no SRFI or
project extensions. That is the environment the conformance harness uses, and
the one to use when you want to know whether a program is portable.

## Python interop is a first-class feature

The DSL is designed to be embedded. The Python seam is a peer of the R7RS and
SRFI layers, not a workaround. The whole host surface is
[`shslisp/embed.py`](../shslisp/embed.py):

```python
from shslisp import install_primitives, make_env, run

def stock_total(rows):
    return sum(row["qty"] for row in rows)

env = make_env()                       # the DSL profile, no game needed
install_primitives(
    env,
    [("stock-total", stock_total)],    # the whole crossing, in one list
    source="inventory.py",
)
run('(stock-total (list (list "sku" "w") (list "qty" 3)))', env)   # -> 3
```

The contract has three rules:

1. **Declared, not discovered.** `install_primitives` takes an explicit list or
   mapping. Nothing is found by `getattr` or `type(x).__name__` at call time.
2. **Total and loud.** A duplicate name, a non-callable, or a malformed entry
   raises at install time, naming the `source`.
3. **Composable.** An extension is any callable `env -> env`, or an object with
   `install(env)`. A host ships its vocabulary as a value.

Value mapping is the obvious one, and it is documented where it is
implemented:

- Python lists are proper Lisp lists; Python callables are procedures.
- Python `str` is the Lisp string type until A8b.
- Python exceptions cross as Lisp conditions through the existing error
  classes.
- A host edition is installed only when present: `make_env()` is *auto* — the
  host joins the environment only if its package is importable — and
  `make_env(install_tetris=False)` is a plain DSL environment under every
  profile.

The seam is tested by `tests/test_embed.py`. The discipline that keeps
`shslisp/` free of host imports is what makes every Python project a valid host.
Chapter [28](lisp_tutorial/28-embedding-in-python.md) is the long version.

## Migration policy

Legacy Lisp code is not a museum piece. **Every shipped `.scm` file must load
under the default profile and use the SRFI names where they exist.** The
profile lint (`tests/test_profile.py`) keeps the rule mandatory: every `.scm`
file in `examples/` and the tutorial's exercises loads under the default
profile, and a file that does not turns the lint red.

The migration map:

| Old shape | New shape | Why |
| --- | --- | --- |
| `(match x ((tag field) ...))` for a `define-variant` value | `(variant-match x ((tag field) ...))` | `match` is now SRFI 241 |
| `(foldl f init xs)` | `(fold f init xs)` | SRFI 1 name; `foldl` stays an alias only if audited |
| `(foldr f init xs)` | `(fold-right f init xs)` | SRFI 1 name |
| `(reduce f init xs)` assuming the `foldl` alias | SRFI 1 `reduce`, or `fold` if a seed is intended | The semantics differ |
| `(partial f a b)` | `(cut f a b <>)` or `(cute f a b <>)` | SRFI 26 placeholders |
| `(-> x (f 1) g)` | `(chain x (f 1 _) (g _))` where the SRFI form is clearer | SRFI 197 pipeline |
| `(map f xs ys)` on unequal lists | `(srfi-1:map f xs ys)` if shortest is intended | R7RS `map` requires equal lengths |
| `(partition pred xs)` as a list of two lists | `(call-with-values (lambda () (partition pred xs)) list)` | SRFI 1 returns two values |
| `(any pred xs)` compared to `#t` | use the true value directly | SRFI 1 returns the predicate’s value |
| optional positional/named arguments by hand | `define*` / `lambda*` | SRFI 89 |

Extensions that stay:

- `define-variant`, `variant-match` — typed control flow.
- `result-*`, `>=>`, `pipe-results`, `result-do`, `attempt` — ROP.
- `->`, `->>` — a useful shorthand; not SRFI 197.
- `partial`, `curry` — procedures; not SRFI 26.
- `range`, `sort`, `alist-*`, `hash-table-*`.

The migration is complete when:

- every `.scm` file in `examples/` and the tutorial exercises loads under
  `make_env()`;
- the profile lint rejects a deliberately legacy file (the red run is recorded);
- the full suite is green.

## How to verify

From a checkout of this project:

```bash
# the full suite
python -m pytest -q

# focused gates
python -m pytest tests/test_r7rs.py -q
python -m pytest tests/test_srfi.py -q
python -m pytest tests/test_profile.py -q
```

The matrices and the tests are the source of truth. If this page and a matrix
disagree, the matrix wins; if the matrix and a test disagree, the test wins.
Update the page in the same change.

## Non-goals

- Full R7RS-small conformance. The target is a documented subset.
- Re-entrant `call/cc` or an evaluator rewrite.
- SRFI 204. It is withdrawn; use SRFI 241.
- Implementing every SRFI in the catalog.
- Removing the project extensions. They are the DSL’s vocabulary, not a
  compatibility shim.

## See also

- [The tutorial](lisp_tutorial/README.md) — the long-form teaching text.
- [The language guide](language.md) — the one-stop guide, with verified
  examples.
- [The capability assessment](capabilities.md) — where the DSL stands against
  the modern-language checklist, and what is cheap to close.
- [Chapter 09 — typed control flow](lisp_tutorial/21-typed-control-flow.md)
- [Chapter 10 — railway-oriented programming](lisp_tutorial/22-railway-oriented.md)
- [Chapter 21 — embedding in Python](lisp_tutorial/28-embedding-in-python.md)
- [Appendix A — reference](lisp_tutorial/appendix-a-reference.md)
- [`docs/R7RS_TASKS.md`](R7RS_TASKS.md)
- [`docs/SRFI_TASKS.md`](SRFI_TASKS.md)

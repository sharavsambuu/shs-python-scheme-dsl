# Appendix A — Reference

> A lookup sheet. Everything here is verified against the code; where a name is
> defined is in the heading. For the language contract — the R7RS-small subset,
> the SRFI layer, the default profile, and the Python seam — see the
> [DSL specification](../lisp-dsl.md).

## Run it

```sh
shs                                  # the REPL (default)
shs -e "(+ 1 2)"                     # evaluate an expression
shs run FILE                         # run a Lisp file
shs run FILE arg1 arg2               # args become *command-line-args*
shs --profile r7rs                   # strict R7RS-small, no SRFIs preloaded
shs --version
```

The examples quote `-e` expressions with **double quotes** on purpose: on
Windows, cmd and PowerShell treat single quotes as ordinary characters, so
`shs -e '(+ 1 2)'` would reach the interpreter as several arguments — the
space-split pieces of the form — and fail with an argparse `invalid choice`.
Double quotes work in cmd, PowerShell, and every Unix shell. The same rule
covers every other argument: a script path or a `*command-line-args*` value
that contains spaces or parentheses needs double quotes too. Inside the REPL
no shell is involved — `,load` takes the path raw, spaces included.

## Special forms (`lisp/evaluator.py`)

```
quote  quasiquote  if  define  set!  lambda  let  let*  letrec  letrec*
case-lambda  begin  cond  when  unless  and  or  defmacro  case  guard
let-values  let*-values  define-values  define-syntax  let-syntax  letrec-syntax
match  define-variant  define-record-type
```

Sugar the reader applies first (`lisp/reader.py`): `'x` → `(quote x)`, `` `x `` →
`(quasiquote x)`, `,x` → `(unquote x)`, `,@x` → `(unquote-splicing x)`, `#(…)` a
vector, `#u8(…)` a bytevector, `#\a` a char, `(a . b)` a dotted pair, `#;form`
a discarded datum, `#| … |#` a block comment.

The reader also accepts numeric prefixes (`#b #o #d #x #e #i`, in either
order: `#e#x10`), the inexact specials `+inf.0 -inf.0 +nan.0`, `|quoted
symbols|` (case and spaces preserved), the string escapes `\" \\ \a \b \t \n
\r \| \x…;` plus line continuations, and the `#!fold-case` / `#!no-fold-case`
directives (off by default). `write` emits forms the reader accepts; a symbol
that is not a plain identifier prints between bars (`|1+|`).

## Core primitives (`lisp/builtins.py`)

- **Numbers** `+ - * /` `modulo quotient remainder` `abs min max expt sqrt`
  `square floor ceiling truncate round` `gcd lcm` `floor/ floor-quotient
  floor-remainder truncate/ truncate-quotient truncate-remainder`
  `exact-integer-sqrt` `= < > <= >=` `number? integer? exact-integer?`
- **Exactness** `exact inexact exact? inexact? rational? real? complex?`
  `numerator denominator rationalize` — the tower is exact integers, exact
  rationals, exact complex pairs (C1–C2: `make-rectangular`/`real-part`/
  `imag-part` and the polar half), and inexact reals; the predicates say
  exactly that, and `(/ 3 4)` is `3/4`. Complex literals read and round-trip
  (C3: `1+2i`, `+i`, the polar `2@1`)
- **Inexact math** `finite? infinite? nan? exp log sin cos tan asin acos
  atan` — `(log x base)` and `(atan y x)` take their optional second
  argument; the complex tower's polar half (`magnitude`, `angle`,
  `make-polar`) landed in C2, and the transcendentals take complex
  arguments (`(asin 2)` answers the complex arc-function)
- **Equality / logic** `equal? eq? eqv? not boolean? boolean=? void`
- **Pairs / lists** `cons car cdr` and every `cxr` composition through four
  levels (`caar cadr cdar cddr caaar … cddddr`), `list length append reverse
  list-ref list-tail list? null? pair? list-copy make-list list-set! member
  member? memq memv assoc assq assv map filter foldl foldr for-each range sort`
- **Chars** `char? char->integer integer->char` `char=?`-family,
  `char-ci=?`-family, classifiers, `char-upcase char-downcase char-foldcase`,
  `digit-value`
- **Symbols / strings** `symbol? string? procedure? procedure-arity
  symbol->string string->symbol symbol=? string string-append string-length
  `string=?`-family `string-ci=?`-family string-foldcase
  `string-ref string-copy string-set! string-fill! string-copy! make-string
  substring string->number number->string
  to-string write-to-string string->list list->string string->vector
  vector->string string-map string-for-each string-upcase
  string-downcase string-trim string-split string-join string-contains?`
- **Vectors** `vector make-vector vector? vector-length vector-ref vector-set!
  vector-fill! vector-copy vector-copy! vector-append vector->list list->vector
  vector-map vector-for-each`
- **Bytevectors** `#u8(1 2 3)`, `bytevector bytevector? make-bytevector
  bytevector-length bytevector-u8-ref bytevector-u8-set! bytevector-copy
  bytevector-copy! bytevector-append utf8->string string->utf8`
- **Hash tables** `make-hash-table hash-table? hash-table-set! hash-table-ref
  hash-table-ref/default hash-table-has-key? hash-table-delete! hash-table-count
  hash-table-keys hash-table-values hash-table-clear! hash-table->alist
  hash-table-update!`
- **Tagged** `tag tagged? tag-of tag-fields variant-tags variant-of`
- **Conditions / values** `raise error-object? error-object-message
  error-object-irritants with-exception-handler dynamic-wind values
  call-with-values`
- **Continuations** `call/cc` (+ two aliases; escape continuations only)
- **Ports / I/O** `port? input-port? output-port? textual-port? binary-port?
  input-port-open? output-port-open? close-port close-input-port
  close-output-port call-with-port flush-output-port`
  `open-input-string open-output-string get-output-string`
  `open-input-file open-output-file read`
  `read-char peek-char read-line char-ready?` `write-char write-string`
  `write-shared write-simple` `eof-object eof-object?`
- **Binary ports** `open-input-bytevector open-output-bytevector
  get-output-bytevector open-binary-input-file open-binary-output-file
  read-u8 peek-u8 u8-ready? write-u8 read-bytevector read-bytevector!
  write-bytevector`; `file-exists? delete-file file-error? read-error?`
  complete the file predicates
- The standard ports are `standard-input-port standard-output-port
  standard-error-port`. `display write print newline` all take an optional
  trailing port, and default to `(current-output-port)`
- **Host environment** `exit emergency-exit command-line
  get-environment-variable get-environment-variables current-second
  current-jiffy jiffies-per-second features`
- **Programs and environments** `cond-expand include include-ci eval
  environment interaction-environment` — `cond-expand` understands
  `and`/`or`/`not`/`library`/`else`; `include` is textual and resolved like
  `load`; `(eval form env)` takes an environment object
- **Host holes** `apply eval read-string error assert gensym`
- **Macros, from the outside** `macroexpand-1 macroexpand` — hand back the
  *form* a macro would expand to (one step / all steps), so it prints as code
  and can be fed to `eval`. Free identifiers in the result appear as their
  hygiene aliases (`list#hN`); that is hygiene made visible, not a bug.

## Standard library (`lisp/prelude.scm`)

- **Combinators** `identity inc dec const compose pipe flip complement partial
  curry`
- **List access** `first rest second caar cadr caddr cadddr last last-pair
  list-head`
- **Alists** `alist-ref alist-has? alist-set`
- **Repetition** `repeat times`
- **Macros** `while ++ --` (defmacro); `push! pop! do dotimes -> ->>`
  (syntax-rules)
- **Predicates** `even? odd? zero? positive? negative?`
- **List algorithms** `take drop take-while drop-while span partition any every
  count find find-index delete remove zip append-map sum product iota iterate
  distinct map-index enumerate filter-map flat-map flatten`; the prelude's
  `foldl`/`foldr` take `(f elt acc)`. Under the default profile, SRFI 1's
  `fold`/`fold-right`/`reduce` replace the prelude's `fold`/`reduce` aliases
  (same fold argument order; SRFI 1 `reduce` semantics).
- **By key** `sort-by max-by min-by group-by`
- **Strings / tables** `string-prefix? string-suffix? string-index
  hash-table-for-each`
- **Delayed evaluation** `delay delay-force make-promise promise? force` — a
  promise is forced at most once, and `force` passes a non-promise through
- **Parameters** `make-parameter parameterize` — dynamically scoped cells;
  `parameterize` restores in a `dynamic-wind` *after* thunk, so a `raise` or a
  continuation exit restores too
- **The current ports** `current-input-port current-output-port
  current-error-port` are parameters; `with-output-to-file
  call-with-output-file with-input-from-file call-with-input-file` rebind them
  for the extent of a thunk/procedure, then close the file
- **Performance** `memoize` (structural-key cache)

Note `take`/`drop` take the list first: `(take xs n)`.

## SRFI libraries (`(import (srfi N))`)

The language ingests six SRFIs; the default DSL profile pre-imports them
(with the SRFI 1 `map`/`for-each` renamed), so programs need no preamble —
strict (`profile="r7rs"`) programs say `(import (srfi N))`:

- `(srfi 1)` — lists: `filter`, `member`, `assoc`, `fold-right`, `zip`,
  `iota`, `delete`, `set-car!`/`set-cdr!`, and the rest of the audited set.
- `(srfi 26)` — `cut` / `cute` (syntax, not the `partial`/`curry`
  procedures in the prelude).
- `(srfi 88)` — keyword objects: `host:` literals,
  `keyword?`/`keyword->string`/`string->keyword`.
- `(srfi 89)` — `define*` / `lambda*`: optional positional and named
  `(keyword v default)` parameters.
- `(srfi 197)` — pipelines: `chain`, `chain-and`, `chain-when`,
  `chain-lambda`, `nest`, `nest-reverse`. The prelude's `->`/`->>` are the
  project's own extensions, not this SRFI.
- `(srfi 241)` — the standard `match` (comma-prefixed pattern variables,
  guards, ellipsis, vector patterns, catamorphism). The project's tag
  dispatch is the separate `variant-match`.

The matrix and every deviation live in
[docs/srfi.md](../srfi.md).

### Signatures that bite

Argument order is the most common source of a confusing error in this
language, because there is no type checker to point at the wrong slot. These
are the ones readers actually get wrong:

| Call | Signature | The trap |
| --- | --- | --- |
| `(take xs n)` | list, then count | not `(take 3 xs)` |
| `(drop xs n)` | list, then count | same order as `take` |
| `(times f n)` | **function, then count** | `(times 3 f)` is an arity error |
| `(repeat n thunk)` | **count, then function** | the opposite of `times` |
| `(sort-by key less xs)` | key fn, comparator, list | three arguments, not two |
| `(group-by key xs)` | key fn, then list | the key is a function |
| `(alist-ref alist key)` | alist first | `#f` when absent, no raise |
| `(alist-set alist key value)` | alist first | returns a **new** alist |
| `(string-index s ch)` | string, then char | not a substring |
| `(substring s start end)` | half-open | `end` is exclusive |
| `(list-ref xs n)` | list, then index | 0-based |
| `(member? x xs)` | element, then list | returns `#t`/`#f` (not the tail) |
| `(foldl f init xs)` | function, seed, list | `foldr` mirrors it |
| `(range n)` / `(range start end)` | not step-aware | use `map` for steps |
| `(hash-table-ref h k)` | table, then key | a missing key raises |
| `(result-bind r f)` | result, then arrow | `(r >>= f)` in other syntax |
| `(pipe-results x f g)` | value, then arrows | left-to-right |
| `(>=> f g)` | arrow, then arrow | runs `f` then `g` (reads left-to-right) |
| `(attempt thunk)` | a **zero-argument** function | `(attempt (car '()))` runs too early |
| `(write-string s [port])` | string first, port optional | the port trails; `(display x p)` is the same shape |
| `(read-line [port])` | port optional | `#<eof>` at the end, never `#f` |
| `(with-output-to-file path thunk)` | a **thunk** | `(call-with-output-file path proc)` hands the proc the port |
| `(parameterize ((param v)) …)` | bindings, then body | a parameter is a *procedure*: `(param)` reads, `(param v)` sets |

The rule of thumb: a *predicate or key* comes before the collection
(`filter`, `take-while`, `group-by`, `sort-by`); a *seed* sits in the middle
(`foldl`); and the collection comes first only for the structural accessors
(`take`, `drop`, `list-ref`). When in doubt, the definition is three lines in
`lisp/prelude.scm`.

## ROP (`lisp/rope.scm`)

- **Type** `(define-variant result (ok value) (err reason))` → `ok err ok-value
  err-reason result?`
- **Functor / monad** `result-map result-map-err result-map2 result-bind
  result-bimap result-fold result-pure`
- **Leaving the rails** `result-unwrap result-unwrap-or result-unwrap-or-else
  result-expect result->list result-tags`
- **Kleisli** `>=> pipe-results-list pipe-results`
- **Collections** `sequence-results traverse-results ok-values err-reasons
  first-err count-errs`
- **Bridge** `attempt` (raising → rail)
- **Syntax** `result-do` (do-notation over `result-bind`)
- **Predicates** `result-ok? result-err?`

## Host editions (optional)

The language is one package; a *host edition* is a separate Python project
that installs its own vocabulary into an environment:

- `install_primitives(env, table)` binds a declared list of
  `name -> callable`, refusing a duplicate at install time;
- an **extension** — any object with `install(env)` — can bring its own Lisp
  prelude, loaded through the same loader as `lisp/prelude.scm`.

The Tetris edition (a separate project) is the worked example: its crossing
primitives, its Lisp vocabulary, and its design protocol are documented in
that project. Everything else in this appendix is the language itself, and
holds with no host installed at all.

## Common mistakes

**Truthiness.** Only `#f` and `'()` are false. `0` and `""` are true.

```scheme
(if 0 'yes 'no)     ;=> yes
(if '() 'yes 'no)   ;=> no
```

**A string is not a symbol.** `(equal? 'down "down")` is `#f`. Key names from
the edge are **strings**; commands are **symbols**. Compare names with
`string=?` and commands with `eq?`.

**`display` is not `write`.** `display` prints a string unquoted; `write` prints
its reader form. The tutorial's `text` blocks show `display` output. Both take an
optional trailing **port**; with no port they use `(current-output-port)`, so
`(parameterize ((current-output-port p)) (display x))` redirects them.

**Strings are immutable here.** There is no `string-set!`/`string-fill!`; a
"change" is a new string from `string-append`, `substring`, or `string-map`.
Vectors (`vector-set!`) and lists (`list-set!`) are the mutable sequences — and
that is why `make-parameter`, promises, and the ports are built on a vector, not
a string.

**A promise is forced once.** `(force p)` returns the same value on every call
and runs the thunk only the first time; `force` on a non-promise returns it
unchanged, so a lazy stage can be forced without a guard.

**The body is the return.** `lambda` and `define` return the last form's value;
use `begin` to sequence side effects.

**`let` is parallel, `let*` is sequential.**

```scheme
(let* ((x 1) (y (+ x 1))) y)          ;=> 2
(let  ((x 1) (y (+ x 1))) y)          ; raises: x is unbound in its own let
```

**A named `let` is a loop.** `(let loop ((i 0)) … (loop (+ i 1)))` — the name is
the function, and the bindings are its arguments.

**`cond` without `else` returns `()`; `variant-match` without `else` raises.**
One is a missed branch, the other is a refusal. Pick on purpose.

**`case` compares literals; `variant-match` binds.** `(case x ((a b) …))`
matches the symbols `a` and `b`; `(variant-match x ((circle r) …))` binds `r`.
(The standard `match` is SRFI 241; see `docs/srfi.md`.)

**Quote the data, not the call.** `(map square '(1 2 3))`, never
`(map square (1 2 3))` — the second tries to call `1`.

**`cons` prepends; `append` joins.**

```scheme
(cons 1 '(2 3))       ;=> (1 2 3)
(append '(1) '(2))    ;=> (1 2)
```

**A macro is not a value.** It only heads a form, so `(map m '(1 2))` and a bare
`m` are both type errors ("a macro is not a value"). Ask `(macroexpand '(m 1))`
what it became — that is the whole debugging loop for macros.

**`let-syntax` is local; `define-syntax` is not.** A local macro is gone when its
body ends, so it is the tool for a name you do not want to publish (and for
shadowing a function or macro of the same name inside one expression).

**A dotted tail is *forms*, not *data*.** For `((_ a . rest) …)`, write `'rest`
to get the tail as a list, and `rest ...` to splice it back into code. Written
bare, `(f rest)` puts the whole tail in one form and the evaluator tries to call
it.

## Closed sets (and what publishes them)

The language itself publishes the closed sets it refuses on — an unknown
keyword parameter name, an unknown case label, a `match` tag outside
`define-variant`'s registered set — always **by naming the set**, never by
defaulting. A host edition publishes its own sets the same way (a `clock`
argument in `install_primitives` can return the host's `(mode-names)`).

## Environment assembly (`lisp/runtime.py`)

1. **core** — `lisp/builtins.py`
2. **prelude** — `lisp/prelude.scm`, `lisp/rope.scm`
3. **the profile** — the pre-imported SRFI layer (`--profile dsl`, the
   default), or none (`--profile r7rs` / `--profile none`)
4. **extensions** — anything passed in `extensions=[…]`, plus a host edition
   when one is installed (`make_env()` is *auto*: the host is included only
   when its package is importable)

## Embedding in your own Python (`lisp/embed.py`)

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
- The package installs with `pip install git+https://github.com/sharavsambuu/shs-python-scheme-dsl.git`
  (see `docs/INSTALL.md`); the import name is `lisp`. See
  chapter [27](27-embedding-in-python.md).

## Budgets and limits

- `DEPTH_LIMIT = 1_000_000` (nested evaluation) → `LispRecursionError`
- `STEPS_BUDGET = 5_000_000` (trampoline steps) → `LispBudgetError`
- `MACROEXPAND_LIMIT = 1_000` (steps `macroexpand` will take before it calls a
  macro divergent) → `LispBudgetError`

## Where to look next

- The tutorial's map: [`README.md`](README.md), and the worked answers in
  [`exercises/`](exercises/).
- The language contract: `docs/srfi.md` (the SRFI layer) and
  `docs/language.md` (the one-stop reference).
- The language's own voice: the docstring at the top of every module in
  `lisp/`, and the comment at the top of every `.scm` beside them.
- The tests are documentation with teeth: `tests/test_tutorial.py` (this
  tutorial's examples), `tests/test_exercises.py` (the answer keys), and the
  per-module suites beside them.

Next: [B Glossary](appendix-b-glossary.md).

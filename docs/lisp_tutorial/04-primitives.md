# 04 — Primitives: the Python floor

> **What this chapter teaches.** What `shslisp/builtins.py` provides, why it is
> split into pure functions and a handful of named host holes, and the one rule
> that keeps it small: if Lisp can define it, it does not belong here.
>
> **Before this:** 03. · **Time:** ~12 min.
> **After this you can:** tell a pure primitive from a host hole, and add a
> function on the right side of that line.

`builtins.py` opens with the argument for its own size:

> *Nothing here is a special form; every name in this module is a first-class
> value. `(define + 3)` would even work — shadowing a builtin is allowed, because
> a lexical scope that can be shadowed is a lexical scope you can reason about.*

Primitives are installed by one function, `install_core(env, out=None)`, and it
reads as a flat list of `define(name, fn)` calls grouped by topic. `out` is the
stream `display`/`write`/`print` write to — captured at install time, which is why
a script's `display` goes to the runner's stdout and a test's goes to a buffer.

## The categories

**Numbers** — `+ - * /`, `modulo quotient remainder abs min max expt sqrt`, and
the comparisons `= < > <= >=` (which are *chained*, so `(< 1 2 3)` is true).
`number?` and `integer?` are here; booleans are deliberately not numbers.

**Equality and logic** — `equal?` (structural), `eq?` (identity), `not`,
`boolean?`, `boolean=?`, `void`.

**Pairs and lists** — `cons car cdr caar cadr cddr list length append reverse
list-ref list-tail list? null? pair? list-copy make-list member member? memq memv
assoc assq assv`, and the higher-order `map filter foldl foldr for-each range
sort`. The prelude also aliases `foldl` to `fold`, and the default DSL profile
pre-imports SRFI 1's `fold`/`fold-right`/`reduce` on top — same `(f elt acc)`
argument order — so `fold` is the name you will see in shipped code (chapter
[05](05-standard-library.md)).

**Characters** — `char? char->integer integer->char`, the `char=?` family, and
the classifiers `char-alphabetic? char-numeric? char-whitespace?
char-upper-case? char-lower-case? char-upcase char-downcase`.

**Symbols and strings** — `symbol? string? procedure? procedure-arity
symbol->string string->symbol string-append string-length` and the `string=?`
family, `string-ref string-copy make-string substring string->number
number->string to-string write-to-string string->list list->string string-upcase
string-downcase string-trim string-split string-join string-contains?`.

**Vectors** — `vector make-vector vector? vector-length vector-ref vector-set!
vector-fill! vector-copy vector-append vector->list list->vector vector-map
vector-for-each`. Note the mutators: a vector is the language's growable,
*in-place* array, and a search that rebuilds candidate states leans on
`vector-copy` + `vector-set!` being single interpreter steps.

**Hash tables** — `make-hash-table hash-table? hash-table-set! hash-table-ref
hash-table-ref/default hash-table-has-key? hash-table-delete! hash-table-count
hash-table-keys hash-table-values hash-table-clear! hash-table->alist
hash-table-update!`. Keys are compared with `equal?`, so two equal lists are the
same key.

**Tagged values** — `tag tagged? tag-of tag-fields variant-tags variant-of`. These
are the raw material `define-variant` and `variant-match` are built on.

**Conditions and multiple values** — `raise error-object? error-object-message
error-object-irritants with-exception-handler dynamic-wind values
call-with-values`.

**Continuations** — `call/cc` and its two aliases. Escape continuations only.

**Control over the host** — `apply eval read-string display write print newline
error assert gensym`.

## The split that matters: pure vs holes

The module docstring names the design:

> *Pure functions (`+`, `car`, `map` …) are the language's algebra. A few host
> hooks (`display`, `error`, `eval` — and `load`, which lives next door in
> `shslisp.loader` because resolution is a policy) are the deliberate holes where a
> program touches the outside world. Keeping the holes few and named is what
> lets the rest of a program be reasoned about as pure.*

Everything that *reads or writes the world outside the language* is one of a
short, named list:

| Hole | Where | What it touches |
| --- | --- | --- |
| `display` `write` `print` `newline` | `builtins.py` | the output stream |
| `error` `assert` `raise` | `builtins.py` | the condition system |
| `eval` | `builtins.py` | the evaluator itself |
| `read-string` | `builtins.py` | the reader |
| `load` | `loader.py` | the filesystem |

Everything else is a pure function of its arguments. That is the claim a host's
architecture can rest on: a program's *decisions* are pure Lisp over the host's
facts, and the only impure calls are named doors — the ones above, plus any
your host declares (chapter [28](28-embedding-in-python.md)).

Two subtleties worth filing away:

- **`eval` goes to the top level.** It is installed as
  `lambda form: evaluate(form, env)` where `env` is the environment the core was
  installed into — so `(eval '(+ 1 2))` uses the *global* environment, not the
  caller's lexical scope. It is a deliberate hole, not a scope escape hatch.
- **A host error becomes a Lisp error.** `apply_procedure` catches `TypeError`,
  `ValueError`, `IndexError` and `KeyError` from a primitive and re-raises
  `LispTypeError`, so a Python-level mistake surfaces as a program error your
  `guard` can catch, never a host traceback.

## Why so few primitives?

Because the standard library (chapter [05](05-standard-library.md)) is written in
Lisp. If you can express it with `lambda`, `let`, `define`, and macros, it does
not belong in Python. `map` is a primitive because it is a tight loop over a
Python list; `alist-ref`, `take`, `last`, `compose`, `memoize` are in
`prelude.scm` because they are three lines of Lisp. The rule keeps the Python
floor small enough to hold in your head and the library open enough to grow from
inside the language.

## Try it

```scheme
(display (< 1 2 3)) (newline)
(display (equal? '(1 2) '(1 2))) (newline)
(display (eq? 'x 'x)) (newline)
(display (vector-copy (vector 1 2 3) 1)) (newline)
(define h (make-hash-table))
(hash-table-set! h '(1 2) "pair key")
(display (hash-table-ref h '(1 2))) (newline)
(display (procedure-arity (lambda (a b) a))) (newline)
```

```text
#t
#t
#t
#(2 3)
pair key
2
```

(A string prints unquoted under `display`; `write` is the form that quotes it.
See chapter [02](02-values-and-reading.md) on the `write`/`display` split.)

## Exercises

1. **Sort the floor.** Classify each of `car`, `display`, `read-string`, `eval`,
   `map`, and `error` as *pure* or *host hole*, using the table above. Then check
   your answers against the module docstring in `shslisp/builtins.py`.
2. **Chained comparison.** Run `(< 1 2 3)` and `(< 1 3 2)`. The first is `#t` and
   the second is `#f`; a chain is not `(< (< 1 2) 3)`. Why would the second
   spelling be wrong in a language where booleans are not numbers?
3. **Resist the floor.** Implement `second` in Lisp as `(car (cdr xs))`. Then
   grep `shslisp/prelude.scm` for a function that already does it. The point of
   the chapter is that the second version belongs in the library, not in
   `builtins.py`.

## The shape you copy

> Keep the primitive floor small and *pure*, and make every outside-world
> contact a named hole. Then "the rest of the program is pure" is a checkable
> statement about a short list, not a hopeful one about a large file.

Next: [05 The standard library](05-standard-library.md).

# 02 — Values and reading

> **What this chapter teaches.** What a Lisp value *is* in this runtime (and how
> each one is an ordinary Python object), and how the reader turns text into
> those values. Nothing here is about meaning yet — that is chapter 03.
>
> **Before this:** 01. · **Time:** ~15 min.
> **After this you can:** look at any value here and say which Python object it
> is, and read quote sugar as data rather than as syntax.

## The value universe

Chapter 01 said a Lisp has almost no syntax. It also has almost no types. The
table below is the whole language; `lisp/types.py` opens with this mapping
(plus one extra row for opaque host values), and it is worth knowing by heart
because *everything* you read in the code is one of these.

| Lisp | Python | Reads / prints as |
| --- | --- | --- |
| number | `int` / `float` (one numeric tower) | `42`, `3.5` |
| boolean | `True` / `False` | `#t` / `#f` |
| string | `str` | `"hi"` |
| symbol | `Symbol` (a `str` subclass) | `square` |
| keyword | `Keyword` (a `str` subclass) | `host:` |
| character | `Char` | `#\a` |
| empty list / nil | the singleton `NIL` | `()` |
| proper list | a non-empty Python `list` | `(1 2 3)` |
| improper pair | `Pair` | `(1 . 2)` |
| vector | `Vector` | `#(1 2 3)` |
| hash table | `HashTable` (keys by `equal?`) | |
| tagged value | `Tagged` | `(ok 3)` |
| closure | `Closure` | `#<closure square>` |
| primitive | `Primitive` | `#<primitive car>` |
| macro | `Macro` / `SyntaxRules` | |

Two design choices in that table are load-bearing, so notice them now.

### 1. Truthiness: only `#f` is false

```lisp
(if '() "truthy" "falsy")   ;=> "truthy"
(if 'x  "truthy" "falsy")   ;=> "truthy"
(if 0   "truthy" "falsy")   ;=> "truthy"
(if #f  "truthy" "falsy")   ;=> "falsy"
```

This is R7RS truthiness, and it is stricter than the Lisp folklore: there is
no truthiness coercion of `0`, `""`, *or the empty list*. The primitive `not`
is defined as `not is_true(x)`, and `is_true` is only false for `False`.

The consequence is a discipline, not a nuisance: **a "missing" answer must be
`#f`, never `'()`** — a lookup that misses returns `#f` (see `alist-ref`
below), and a host seam that has no record to give returns `#f` too. A hook
that returns `'()` when it means "nothing" would be read as *a value*, because
`'()` is true.

### 2. Symbols are strings, but strings are not symbols

`Symbol` subclasses `str`, so the *name* of a symbol and the symbol share their
bytes — `(symbol->string 'square)` is `"square"`. But `string?` excludes symbols
(`isinstance(x, str) and not isinstance(x, Symbol)`), so `(string? 'square)` is
`#f`. This distinction is used everywhere: a name *reported by a platform* is
a **string** (`"left"`), while a command *you write* is a **symbol**
(`'move-left`). A host's keymap is the table that maps one to the other.

### 3. Keywords are their own type (SRFI 88)

The reader turns a symbol-shaped token with a **trailing colon** into a
*keyword object* — `host:` is the keyword named `host`, self-evaluating and
distinct from symbols:

```lisp
(keyword? host:)            ;=> #t
(keyword? ':host)           ;=> #f — a leading colon is just a symbol
(symbol? ':host)            ;=> #t
(keyword->string host:)     ;=> host
(eq? host: host:)           ;=> #t — keywords are interned
```

There is no `#:foo` prefix spelling in this dialect. Keywords exist so a call
can *name* an argument without evaluating it: `define*`/`lambda*` (SRFI 89)
use them for optional and named parameters — `(greet "ada" greeting: "hi")`.
`types.py` says the design in one line:

> *A keyword records its name without the trailing colon (which is what
> `keyword_to_string` answers), but it prints with the colon so it reads back.*

## Lists: proper, improper, and the empty one

A Lisp list is a linked chain. Three things model it here:

- `NIL` — the empty list. It is a **singleton** and, under R7RS truthiness, a
  *true* value (only `#f` is false). `(null? x)` is `is_nil(x)`; `(list? x)` is
  true for `NIL` or a proper list. Ask `null?`, not truthiness, when you mean
  "empty".
- a non-empty Python **`list`** — a proper list. The host can iterate it
  directly, which is why `map` and `filter` are cheap.
- a `Pair` — an improper chain, e.g. from `(cons 1 2)`.

```lisp
(display '(1 2 3))     ;=> (1 2 3)
(display (cons 1 2))   ;=> (1 . 2)
(display (list 1 2 3)) ;=> (1 2 3)
(display '())          ;=> ()
```

The helpers `to_cells` / `from_cells` in `types.py` convert between the host's
Python view and the Lisp view; a dotted parameter list like `(define (f a . rest) …)`
is a `Pair`, and the evaluator's `_parse_params` splits it into fixed parameters
plus a rest binder (chapter [03](03-evaluating.md)).

> **A gotcha worth remembering now.** `cdr` on a Python `list` *copies* the tail
> (`list[1:]`), while `car`/`cdr` on a `Pair` share structure. This is why a
> hot, ten-column profile is carried as a **vector** rather than a list:
> rebuilding it as a list would build a new ten-list per cell, while a vector
> is patched in place with `vector-set!`.

## Tagged values: `(tag . fields)`

A `Tagged` is a *tag* plus fields, and it prints like a one-element-headed list:

```lisp
(display (tag 'ok 3))         ;=> (ok 3)
(display (tag-of (tag 'ok 3))) ;=> ok
(display (tag-fields (tag 'ok 3))) ;=> (3)
```

`define-variant` (chapter [09](09-typed-control-flow.md)) builds tagged
constructors for you, and `match` knows how to read the fields back out. For now
just note that a tagged value is *list-shaped*, and that `match` accepts either
the declared-tag spelling `(ok v)` or the explicit-quote spelling `('ok v)`.

## The reader: how text becomes a form

`lisp/reader.py` is small because the syntax *is* the data. `tokenize` splits
text into tokens (parentheses and the delimiters `()'`,",; \t\r\n` are special);
`Reader` assembles tokens into forms. It understands this sugar, and nothing
else:

| Text | Becomes |
| --- | --- |
| `'x` | `(quote x)` |
| `` `x `` | `(quasiquote x)` |
| `,x` | `(unquote x)` |
| `,@x` | `(unquote-splicing x)` |
| `#(1 2)` | a vector literal |
| `#\a` | a character literal (`#\space`, `#\newline` too) |
| `(a b . rest)` | a dotted pair chain |
| `#;form` | the form is read and **thrown away** |
| `#\| … \|#` | a block comment |

The first four rows are the whole reason macros work. The reader expands `'x`
into `(quote x)` *before* evaluation, so quoting is not special syntax the
evaluator has to know — it is an ordinary special form that returns its argument
unevaluated. By the time a program runs, code and data are the same substance,
and a macro can be a plain procedure over lists.

Strings are read with the usual escapes (`\"`, `\\`, `\n`, `\t`, `\r`, plus
`\a` and `\0`), and `\xNN;` — a hex escape, terminated by `;`. `#;` is a *datum
comment*: the next form is read (so it must be
syntactically complete) and discarded — handy for commenting out one argument in
the middle of a form.

## Printing: `write` vs `display`

`lisp/printer.py` has one formatter, `to_string(value, write=False)`. The two
modes are the Scheme split:

```lisp
(display "hi")   ;=> hi      (for a human)
(write "hi")     ;=> "hi"    (so it can be read back)
```

`display`, `write`, `print` and `newline` are primitives that write to the
environment's output stream; `to-string` and `write-to-string` are the pure
functions that return the text instead. The REPL echoes in **display** form (so a
string comes back unquoted, and `hello` is what a string looks like).

> **Reading the examples in this tutorial.** A `;=>` comment shows a value in
> **reader** form — quoted, the way `write` would print it — because that is the
> unambiguous way to write a value down. A REPL transcript shows what the REPL
> actually echoes, which is display form. So `(string-append "a" "b")` has the
> value `"ab"` written as `;=> "ab"`, but you will see it echoed as `ab`.

## Try it

```sh
shs run /dev/stdin <<'EOF'
(display (read-string "(+ 1 2)"))          (newline)
(display (read-string "'(a b)"))           (newline)
(display (read-string "(a b . c)"))        (newline)
(display (read-string "#(1 2 3)"))         (newline)
(display (string? 'square))                (newline)
(display (symbol? 'square))                (newline)
(display (list? '()))                      (newline)
(display (if '() "truthy" "falsy"))        (newline)
EOF
```

```text
(+ 1 2)
(quote (a b))
(a b . c)
#(1 2 3)
#f
#t
#t
truthy
```

You should see `(+ 1 2)`, then `(quote (a b))` — the reader has already applied
the quote sugar — then `(a b . c)`, `#(1 2 3)`, `#f`, `#t`, `#t`, `truthy`:
under R7RS, only `#f` is false, so the empty list takes the true branch.

## Exercises

1. **Three questions about the empty list.** At the REPL, ask `(list? '())`,
   `(pair? '())`, and `(null? '())`. The answers are `#t`, `#f`, `#t`: the empty
   list is a list and is null, but it is not a pair — which is why `car` of it
   is an error rather than a silent `()`.
2. **Keep the shape you wrote.** Compare `(read-string "(1 . (2 3))")` with
   `(cons 1 '(2 3))`. Both print as `(1 2 3)`, but they are **not** `equal?`:
   the reader preserves a dotted pair as a dotted value. That is a useful
   reminder that the reader's output is data with a shape, not a normalised
   syntax tree.
3. **Truthiness.** Run `(if 0 "truthy" "falsy")` and
   `(if '() "truthy" "falsy")`. Only `#f` is false — `0` and the empty list
   are both true. Write down the rule before you look at the evaluator, and
   then say why a "missing" answer must be `#f` and never `'()`.

## The shape you copy

> A language needs very few *kinds of thing*. The reader's only cleverness is
> expanding quote sugar into ordinary forms, and that one decision is what makes
> "code is data" true rather than a slogan.

Next: [03 Evaluating](03-evaluating.md).

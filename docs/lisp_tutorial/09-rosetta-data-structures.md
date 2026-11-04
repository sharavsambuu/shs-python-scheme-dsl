# 09 — Rosetta: Python's data structures in this Lisp

> **What this chapter teaches.** The map from the structures you already know —
> `list`, `tuple`, `dict`, `set`, `class` — to the ones this language ships, and
> the two small surprises (truthiness and equality) that catch every Python
> programmer exactly once.
>
> **Before this:** 08. · **Time:** ~12 min.
> **After this you can:** pick the right structure for a job, convert between
> them, and predict what `#t`/`#f` and `equal?`/`eq?` will say before you run.

The rest of this series (chapters [10](10-lists-and-vectors.md)–[13](13-records-variants-and-objects.md))
is the structures themselves. This one is the *map*: which structure is which,
and how to move data between them.

## The mapping

| Python | Here | The one-line difference |
| --- | --- | --- |
| `list` | the proper list `(1 2 3)` | mutation goes through `set!` on a variable, not `xs[0] = ...` |
| `tuple` | the vector `#(1 2 3)` | *worse* than a tuple in one way: it is mutable (`vector-set!`) |
| `dict` | hash table (mutable) or alist (persistent) | chapter [12](12-dictionaries-alists-and-hash-tables.md) is all about this choice |
| `set` | a list + the `lset` family | sets are not a type; they are operations on lists |
| `dataclass` / `namedtuple` | `define-record-type` | chapter [13](13-records-variants-and-objects.md) |
| `Enum` / sum type | `define-variant` | a *closed* set of tagged cases; the interpreter names the ones you forget |
| `bytes` | bytevector `#u8(1 2 3)` | with the UTF-8 bridge `string->utf8` / `utf8->string` |
| `range`, `itertools` | the generator library | chapter [18](18-generators.md); `iota` for the common case |
| `str` | string | immutable like Python's; `string-split`, `string-join`, `string-append` |

Two structural notes the table hides:

- **A proper list is the host's list.** `lisp/types.py` says it plainly:
  proper lists are Python lists, so `length`, `list-ref`, and the primitive
  traversals are host-speed — but `cdr` *copies the tail* (it must, to stay
  immutable). `lisp/prelude.scm`'s traversal comment is the rule to copy:
  walk with `map`/`filter`/`fold`, not hand-rolled `(cdr xs)` recursion.
- **Dotted pairs are the exception, not the building block.** `(cons 1 2)` makes
  an improper `Pair` `(1 . 2)`, but the structures you will use daily — lists,
  alists, variants — are all built on *proper* lists. Chapter 12 shows why an
  alist is `((a 1) (b 2))`, not the classic `((a . 1) (b . 2))`.

## Truthiness: only `#f` is false

Python falsifies `0`, `""`, `[]`, and `None`. This language falsifies exactly
one value: `#f`. Everything else — zero, the empty string, the empty list —
is true:

```scheme
(if 0 'zero-is-true 'zero-is-false)     ;=> zero-is-true
(if '() 'empty-is-true 'empty-is-false) ;=> empty-is-true
```

The discipline that follows: a "missing" answer is `#f`, and a predicate that
means "no" must say `#f`, never `()` or `0`. That is why the library's searches
return `#f` on a miss (chapter [02](02-values-and-reading.md)).

## Equality: the three-question ladder

Python has `==` and `is`; here the ladder has three rungs, and you pick the
question you mean:

- `equal?` — *structural*: do these have the same contents? This is Python's
  `==` for containers, and it is the default for `assoc`, `member`, and hash
  table keys.
- `eqv?` — same as `equal?` for numbers and characters, identity for the rest.
- `eq?` — *identity*: is this the very same object? This is `is`, and it is
  what `assq`, `memq`, and the `lset` family's comparator examples use.

```scheme
(equal? '(1 2) (list 1 2)) ;=> #t
(eq?    '(1 2) (list 1 2)) ;=> #f — two different objects
(define xs (list 1 2))
(eq? xs xs)                ;=> #t — the same object
```

The working rule: reach for `equal?` unless you have a reason not to. Reach for
`eq?` only when comparing symbols, or when identity *is* the question (records —
chapter [13](13-records-variants-and-objects.md)).

## Converting between structures

The conversions are all two-way pairs, and they compose:

```scheme
(vector->list #(1 2 3))       ;=> (1 2 3)
(list->vector '(1 2 3))       ;=> #(1 2 3)
(hash-table->alist h)         ;=> ((k v) ...) — a snapshot of the table
(string->list "ab")           ;=> (#\a #\b)
(list->string (list #\a #\b)) ;=> "ab"
```

The one direction with no primitive is alist → hash table, and it is a `fold`
away (chapter [12](12-dictionaries-alists-and-hash-tables.md) builds it).

## The type Python has and you forget you need: bytevectors

`bytes` maps to the bytevector, and it round-trips through UTF-8 in one pair
of calls — the bridge you will use whenever a host hands you raw bytes:

```scheme
(define bv #u8(104 105))        ; a literal, like #(…) with a u8
(bytevector-length bv)          ;=> 2
(bytevector-u8-ref bv 0)        ;=> 104
(utf8->string bv)               ;=> "hi"
(string->utf8 "hi")             ;=> #u8(104 105)
```

Bytevectors are mutable in place (`bytevector-u8-set!`), copy with
`bytevector-copy`, and concatenate with `bytevector-append` — the vector API
over bytes. Equality is structural under `equal?`, so two bytevectors with
the same contents are `equal?` — one more place the ladder's default rung
does what Python's `==` does.

## The middle rung: `eqv?`

`eqv?` earned its place on the ladder with one rule: for numbers and
characters it asks the `equal?` question, for everything else it asks the
`eq?` question:

```scheme
(eqv? 1 1)     ;=> #t
(eqv? 1.0 1)   ;=> #f — same value, different exactness: not the same number
(eqv? #\a #\a) ;=> #t
(equal? #\a #\a) ;=> #t
```

That `1.0` vs `1` refusal is the exact/inexact boundary doing its job —
chapter [08](08-lisp-by-example.md)'s numeric tower keeps exact and inexact
numbers distinct, and `eqv?` is the rung that respects it. The working rule
expands to: `equal?` by default; `eqv?` when comparing numbers or characters
in a set-like context (it is what `case` and `memq`'s sibling `memv` use);
`eq?` for symbols and identity.

## Parsing back: strings into values

The conversion section's other direction — strings *into* structured values —
is how host input enters the world of chapter 09's types:

```scheme
(string->number "42")    ;=> 42
(string->number "1/2")   ;=> 1/2 — the reader's exact rationals, by string
(string->number "nope")  ;=> #f — a miss is #f, never an error
(char->integer #\A)      ;=> 65
(integer->char 66)       ;=> #\B
(string-split "a,b,c" ",") ;=> (a b c)
(string-join (list "a" "b") "-") ;=> "a-b"
```

`string->number` answering `#f` (not raising) is the house rule from chapter
[02](02-values-and-reading.md) — a miss is a value you can branch on, which
makes "parse or refuse" a one-line `if`.

## Try it

```scheme
;; truthiness: only #f is false
(display (if 0 'zero-is-true 'zero-is-false)) (newline)
(display (if '() 'empty-is-true 'empty-is-false)) (newline)
;; the equality ladder
(display (equal? '(1 2) (list 1 2))) (newline)
(display (eq? '(1 2) (list 1 2))) (newline)
(define xs (list 1 2))
(display (eq? xs xs)) (newline)
;; conversion round trips
(define t (vector 1 2 3))
(display t) (newline)
(display (vector->list t)) (newline)
(define d (make-hash-table))
(hash-table-set! d "alice" 30)
(display (hash-table-ref d "alice")) (newline)
(display (hash-table->alist d)) (newline)
;; a record is the dataclass
(define-record-type user (make-user name age) user? (name user-name) (age user-age))
(define u (make-user "alice" 30))
(display (user-name u)) (newline)
(display (user? u)) (newline)
(display (user? "alice")) (newline)
;; sets are lists with the lset family
(display (delete-duplicates '(1 2 1 3))) (newline)
(display (lset-union eq? '(1 2) '(2 3))) (newline)
(display (lset-difference eq? '(1 2 3) '(2))) (newline)
;; bytevectors round-trip through UTF-8
(define bv #u8(104 105))
(display bv) (newline)
(display (utf8->string bv)) (newline)
(display (string->utf8 "hi")) (newline)
;; the middle rung: eqv?
(display (eqv? 1 1)) (newline)
(display (eqv? 1.0 1)) (newline)
(display (eqv? #\a #\a)) (newline)
;; parsing strings into values
(display (string->number "1/2")) (newline)
(display (string->number "nope")) (newline)
(display (char->integer #\A)) (newline)
(display (string-split "a,b,c" ",")) (newline)
```

```text
zero-is-true
empty-is-true
#t
#f
#t
#(1 2 3)
(1 2 3)
30
((alice 30))
alice
#t
#f
(1 2 3)
(1 2 3)
(1 3)
#u8(104 105)
hi
#u8(104 105)
#t
#f
#t
1/2
#f
65
(a b c)
```

(The hash table prints only through its alist view `((alice 30))` — a table has
no reader syntax of its own; chapter [12](12-dictionaries-alists-and-hash-tables.md)
is about the two dictionary shapes that view connects.)

## Exercises

1. **The ladder, felt.** Predict, then run: `(equal? "a" "a")`,
   `(eq? "a" "a")`, `(equal? #(1 2) #(1 2))`. Two of the three are `#t` — which
   one is not, and what does that tell you about vector identity?
2. **Set vocabulary.** Using the `lset` family, write `(symmetric-difference a b)`
   as a `lset-union` of two `lset-difference` calls. Check it on `'(1 2 3)` and
   `'(2 3 4)` — the answer is `(1 4)`.
3. **Truthiness audit.** Python's `if users:` tests "non-empty". Write the Lisp
   equivalent for a list and for a hash table (hint: the list needs nothing;
   the table needs `hash-table-count`). Why does the list not need anything?

## The shape you copy

> Pick the structure by the operations you need — order and slicing say *list*,
> in-place indexing and mutation say *vector*, key lookup says *alist or hash
> table*, a closed set of cases says *variant*, a named shape says
> `define-record-type` — and let `equal?` be your default equality.

Next: [10 Lists and vectors in depth](10-lists-and-vectors.md).


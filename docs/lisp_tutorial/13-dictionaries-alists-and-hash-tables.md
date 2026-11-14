# 13 — Dictionaries: alists and hash tables

> **What this chapter teaches.** The two dictionary shapes this language ships —
> the persistent alist and the mutable hash table — the recipes that cover most
> of what Python dicts do daily (counting, grouping, inverting, indexing), and
> the two argument-order gotchas that are documented right here in the code.
>
> **Before this:** 11. · **Time:** ~15 min.
> **After this you can:** choose between the two dictionaries deliberately, and
> write the frequency-count / group-by / invert trio from memory.

## The alist: a dictionary that is just a list

An alist is a list of two-element lists — `((host "localhost") (port 8080))`.
That is the whole representation, which is why the prelude can define its
helpers in three lines of Lisp (`shslisp/prelude.scm`):

```scheme
(define settings '((host "localhost") (port 8080)))
(alist-ref settings 'port)       ;=> 8080        — d['port']
(alist-has? settings 'user)      ;=> #f          — 'user' in d
```

The classic Scheme spelling of a "record" is a dotted alist — `((a . 1))` —
and `assoc` itself is happy with it. But the prelude's `alist-ref` and this
dialect's whole sequence layer are built on *proper* lists (chapter 09), so the
house style is the two-element list: `((a 1) (b 2))`. `assoc` reads both:

```scheme
(assoc 'b '((a 1) (b 2)))  ;=> (b 2)
(assoc 'b '((a . 1) (b . 2)))  ;=> (b . 2)
```

Updating is *functional* — `alist-set` returns a new alist and the original is
untouched:

```scheme
(alist-set settings 'port 9090)  ;=> ((port 9090) (host "localhost"))
settings                          ;=> ((host "localhost") (port 8080)) — unchanged
```

Note the updated entry moves to the front: `alist-set` conses the new pair and
filters out the old, because prepending is the cheap end of a list.

**Reach for an alist when** the data is small, you want value semantics
(pass it around, derive new versions, never mutate), or you need it to print
and read back — an alist is just data.

## The hash table: the mutable dictionary

`make-hash-table` gives the Python-dict experience: in-place, O(1),
insertion-ordered. Keys are compared with `equal?` — structural comparison —
so *any* value can be a key, including lists and tagged values:

```scheme
(define board (make-hash-table))
(hash-table-set! board '(0 0) 'rook)   ; a list as a key
(hash-table-ref board '(0 0))          ;=> rook
```

The surface, mapped to Python:

| Here | Python |
| --- | --- |
| `hash-table-set! h k v` | `d[k] = v` |
| `hash-table-ref h k` / `hash-table-ref/default h k d` | `d[k]` / `d.get(k, d)` |
| `hash-table-has-key? h k` | `k in d` |
| `hash-table-delete! h k` | `del d[k]` |
| `hash-table-count h` | `len(d)` |
| `hash-table-keys h` / `hash-table-values h` | `d.keys()` / `d.values()` |
| `hash-table->alist h` | `list(d.items())` |

## SRFI 125: the standard spellings

The table above is the dialect's *core* vocabulary. `(import (srfi 125))` gives
the same storage under the standard names, plus the three procedures the core
does not carry:

```scheme
(import (srfi 125))

(define prices (alist->hash-table '((spy . 512) (qqq . 430))))
(hash-table-size prices)                 ;=> 2
(hash-table-contains? prices 'spy)       ;=> #t
(hash-table-ref/default prices 'iwm 0)   ;=> 0
```

| SRFI 125 | Core spelling | Note |
| --- | --- | --- |
| `hash-table-contains?` | `hash-table-has-key?` | the same predicate; the SRFI name is the portable one |
| `hash-table-size` | `hash-table-count` | the same answer |
| `alist->hash-table` | a fold over `hash-table-set!` | accepts dotted `(k . v)` pairs *and* two-element `(k v)` lists |
| `make-hash-table`, `hash-table-ref`, `hash-table-set!`, the rest | unchanged | the import binds the *same* objects the core has |

Two reasons to import it: your program reads the way the SRFI text reads (so
the code is portable and reviewable against a standard), and
`alist->hash-table` saves the fold — `(alist->hash-table settings)` is the
one-liner the exercise at the bottom of this chapter asks you to write by
hand. What the import does *not* add is a second table type: `hash-table?`
answers `#t` for the same objects, and a table built either way works with
every procedure above.

A missing key still raises, and that is the point of the pair
`hash-table-ref` / `hash-table-ref/default`: reach for the defaulting one when
absence is ordinary, and let the raising one catch a typo.

## The counting idiom: `hash-table-update!`

The most common dict loop in Python — `counts[w] = counts.get(w, 0) + 1` — is
one procedure here, because "read, transform, write back" is one operation:

```scheme
(for-each
  (lambda (word)
    (hash-table-update! counts word (lambda (n) (+ n 1)) 0))
  '("the" "cat" "the" "hat" "the"))
```

Two documented gotchas, both visible in the code (`shslisp/builtins.py`,
`shslisp/prelude.scm`):

- **The default is a value, not a thunk.** SRFI 69 spells this call with a
  lambda for the default; here the default is the value itself —
  `(hash-table-update! counts word f 0)`, never `(lambda () 0)`. Get it wrong
  and the error is loud: `+: expected a number, got Closure`.
- **`hash-table-for-each` takes the procedure first** —
  `(hash-table-for-each (lambda (k v) ...) h)` — because it is a prelude
  function built on `for-each`, not a table primitive. It is the one
  table function that breaks the table-first rhythm.

## The recipes

Most of what a Python dict does daily is these four shapes. Grouping the
prelude already ships as `group-by` (chapter 10); the other three are folds
away, and each is three lines:

**Frequency count** — `update!` with a default (above).

**Invert a mapping** — a fold that flips each entry:

```scheme
(fold (lambda (kv acc) (cons (list (cadr kv) (car kv)) acc))
      '()
      '((a 1) (b 2)))                    ;=> ((2 b) (1 a))
```

**Index a list by key** — `group-by` with a key function:

```scheme
(group-by car '((a 1) (b 2) (a 3)))    ;=> ((a ((a 1) (a 3))) (b ((b 2))))

```

**Memoise a function** — the prelude's `memoize` (chapter
[05](05-standard-library.md)) is exactly this: a hash table keyed
*structurally* on the whole argument list, so a function of lists is
memoised by value.

And the bridge back to the persistent world: `hash-table->alist` snapshots a
table into plain data — printable, comparable, safe to keep — which is how a
mutable accumulator reports its final state.

**Reach for a hash table when** the data is a running accumulator, the key
space is open, or lookups are hot. When a function returns a table to its
caller, consider returning `hash-table->alist` instead: data is a value, a
table is a machine.

## The comparator is the search

The three `ass*` searches differ in exactly one thing — the rung of the
equality ladder (chapter [10](10-rosetta-data-structures.md)) they use:

```scheme
(define alist '((b 2) ("a" 1)))
(assoc "a" alist)  ;=> ("a" 1) — equal?: structural, works on strings
(assq 'b alist)    ;=> (b 2)   — eq?: identity, for symbols
(assq 'z alist)    ;=> #f      — a miss is #f, like every search here
```

`assoc` is the default because `equal?` is; `assq` is the fast one for
symbol-keyed tables, where identity and equality agree anyway. `assv` sits
between them for numbers and characters. The same triangle organizes `member`
/`memq`/`memv` — one rule, two families.

## Keywords are their own keys

SRFI 88 keywords (chapter [17](17-srfi-88-keywords.md)) hash *separately*
from symbols, so the same name spelled two ways is two dictionary entries:

```scheme
(hash-table-set! kh 'host 1)   ; the symbol host
(hash-table-set! kh host: 2)   ; the keyword host:
(hash-table-ref kh 'host)      ;=> 1
(hash-table-ref kh host:)      ;=> 2
```

This is deliberate: a keyword is a self-quoting *name you say*, a symbol is a
name the program binds — and a table keyed by one should not silently answer
the other. Pick one spelling per table and be consistent.

## The counting recipe, finished

Chapter 13's counting loop plus chapter [11](11-lists-and-vectors.md)'s
`sort-by` is the whole word-frequency program:

```scheme
(for-each (lambda (w) (hash-table-update! counts w (lambda (n) (+ n 1)) 0))
          '(a b a c a b))
(sort-by cadr > (hash-table->alist counts))
;=> ((a 3) (b 2) (c 1))
```

`hash-table->alist` snapshots, `sort-by` orders by the count slot (`cadr`),
`>` descending. The table never leaves the function; the caller gets plain
data in a deliberate order.

## Tables compose — and remember their order

Two facts about the table itself worth knowing before you build on it.
First, iteration is in *insertion* order — `(hash-table-keys h)` answers in
the order you `set!` — which is Python-dict behavior, and it makes
`hash-table->alist` snapshots readable. Second, any value is a value, so a
table can hold tables:

```scheme
(hash-table-set! grid 'row1 (make-hash-table))
(hash-table-set! (hash-table-ref grid 'row1) 'col1 'x)
(hash-table-ref (hash-table-ref grid 'row1) 'col1)   ;=> x
```

That is a two-level index in four lines — but note what the pattern costs:
the inner table is *shared state* through the outer's slot, and chapter
[26](26-functional-core-imperative-shell.md)'s discipline says that kind of
mutation belongs in the shell, not in a decision.

## Try it

```scheme
;; the alist: a persistent dictionary
(define settings '((host "localhost") (port 8080)))
(display (alist-ref settings 'port)) (newline)
(display (alist-has? settings 'user)) (newline)
(define settings2 (alist-set settings 'port 9090))
(display settings2) (newline)
(display settings) (newline)
;; the hash table: a mutable dictionary
(define counts (make-hash-table))
(for-each
  (lambda (word)
    (hash-table-update! counts word (lambda (n) (+ n 1)) 0))
  '("the" "cat" "the" "hat" "the"))
(display (hash-table->alist counts)) (newline)
(display (hash-table-count counts)) (newline)
(display (hash-table-keys counts)) (newline)
(display (hash-table-ref/default counts "dog" 0)) (newline)
(display (hash-table-has-key? counts "cat")) (newline)
(hash-table-delete! counts "hat")
(display (hash-table-count counts)) (newline)
;; keys are compared with equal?, so a structure can be a key
(define board (make-hash-table))
(hash-table-set! board '(0 0) 'rook)
(display (hash-table-ref board '(0 0))) (newline)
;; the comparator is the search
(define alist '((b 2) ("a" 1)))
(display (assoc "a" alist)) (newline)
(display (assq 'z alist)) (newline)
;; keywords are their own keys
(define kh (make-hash-table))
(hash-table-set! kh 'host 1)
(hash-table-set! kh host: 2)
(display (list (hash-table-ref kh 'host) (hash-table-ref kh host:))) (newline)
;; insertion order survives deletes
(display (hash-table-keys counts)) (newline)
;; sort the snapshot by count
(display (sort-by cadr > (hash-table->alist counts))) (newline)
```

```text
8080
#f
((port 9090) (host localhost))
((host localhost) (port 8080))
((the 3) (cat 1) (hat 1))
3
(the cat hat)
0
#t
2
rook
(a 1)
#f
(1 2)
(the cat)
((the 3) (cat 1))
```

## Exercises

1. **Alist → table.** Write `(my-alist->hash-table alist)` yourself as a fold
   over the entries calling `hash-table-set!`, then `(import (srfi 125))` and
   compare it with the library's `(alist->hash-table alist)` — same table, one
   fewer fold to trust. Round-trip it: `(hash-table->alist
   (alist->hash-table settings))` — what changed about the order, and why is
   the answer "nothing, for a fresh table"?
2. **The thunk trap.** Call `(hash-table-update! counts "x" (lambda (n) (+ n 1))
   (lambda () 0))` and read the error. Then fix it. Which of the two spellings
   does SRFI 69 use, and where does this dialect document its difference?
3. **Word frequencies, finished.** Take the counting loop from the chapter and
   make it a function `(frequencies words)` that returns an *alist*, sorted by
   count descending — `sort-by` on `cadr`, with a `>` — and returns plain data,
   not the table.

## The shape you copy

> Small, shared, and derived — alist. Accumulated and hot — hash table. When a
> mutable accumulator must speak, it speaks through `hash-table->alist`: return
> data, not machinery. And reach for `hash-table-update!` before writing the
> read-check-write dance by hand.

Next: [14 Modeling data: records, variants, and closures](14-records-variants-and-objects.md).

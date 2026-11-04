# 10 — Lists and vectors in depth

> **What this chapter teaches.** The two sequence types, side by side: the
> manipulations you would reach for with Python list comprehensions and slices,
> the prelude's sorting and grouping, and the honest rule for when a vector
> earns its keep.
>
> **Before this:** 09, and chapter [11](11-srfi-1-the-list-library.md) is a
> friend, not a prerequisite. · **Time:** ~15 min.
> **After this you can:** transform, sort, group, and flatten sequences by
> name — and know when to reach for `#(...)` instead of `(...)`.

## Reading and building

The constructors and accessors, with their Python neighbours:

```scheme
(append '(1 2) '(3) '(4 5))  ;=> (1 2 3 4 5)   — [1, 2] + [3] + [4, 5]
(reverse '(1 2 3))           ;=> (3 2 1)
(take '(1 2 3 4) 2)          ;=> (1 2)          — xs[:2]
(drop '(1 2 3 4) 2)          ;=> (3 4)          — xs[2:]
(list-ref '(a b c) 1)        ;=> b              — xs[1]
(last '(a b c))              ;=> c              — xs[-1]
```

`cons` extends at the front — `(cons 1 '(2 3))` is `(1 2 3)` — and it is also
how a fold builds a list, which is why chapter 11's fold examples all end in a
`reverse`. The dotted pair `(cons 1 2)` is `(1 . 2)`, the *improper* pair: it
exists (`pair?` says `#t`), but the sequence operations refuse it, so keep it
out of your data unless a structure you chose calls for it.

## The comprehension moves

A Python comprehension is `map` + `filter` in one shape; the library splits
them back apart, and adds the two that comprehensions are bad at — counting
and folding:

```scheme
(filter odd? '(1 2 3 4 5))          ;=> (1 3 5)
(map * '(1 2 3) '(10 20 30))        ;=> (10 40 90) — zip + multiply
(append-map (lambda (x) (list x x)) '(1 2))  ;=> (1 1 2 2)
(fold (lambda (x acc) (+ acc (* x x))) 0 '(1 2 3))  ;=> 14 — sum of squares
(count even? '(1 2 3 4))            ;=> 2
```

Three prelude helpers close the remaining everyday gaps:

```scheme
(filter-map (lambda (x) (and (even? x) (* x x))) '(1 2 3 4))  ;=> (4 16)
(flatten '(1 (2 (3 4)) 5))          ;=> (1 2 3 4 5)
(enumerate '(a b))                  ;=> ((0 a) (1 b))
```

`filter-map` is the "map but keep only what worked" move — the `and` returns
`#f` for the odds and `filter-map` drops them. `enumerate` pairs each element
with its index, first-seen order preserved.

## Sorting and grouping

The prelude's sorting section is three names:

```scheme
(sort '(3 1 2) <)                       ;=> (1 2 3)
(sort-by car < '((3 c) (1 a) (2 b)))    ;=> ((1 a) (2 b) (3 c))
(group-by (lambda (x) (modulo x 2)) '(1 2 3 4 5))
;=> ((1 (1 3 5)) (0 (2 4)))
```

`sort` takes the less-than on elements; `sort-by` lifts it onto a key — the
`key=` of Python's `sorted`. `group-by` answers the `itertools.groupby`
question the way you actually wanted it: an alist of `(key elements)` in
first-seen order, readable straight back with `alist-ref` — no re-grouping
ritual, because the input did not have to be pre-sorted. Its companion
searches are `max-by` and `min-by`:

```scheme
(max-by car < '((3 c) (1 a) (2 b)))     ;=> (3 c)
```

## The performance model, honestly

This is the one place the language is *not* Python, and it is worth 60 seconds:

> *A proper list is a host list, and `cdr` copies the tail — so a traversal
> written as structural recursion (`(loop (cdr xs))`) costs O(n²) on a long
> list: fine for a board, wrong for a log. The helpers below walk with the
> primitive traversals (`map`, `filter`, `foldl`, `for-each`), which loop in
> the host without copying, and so stay linear.*
> — `shslisp/prelude.scm`, the traversal section header

So the rule is not "lists are slow"; it is *walk with the primitives*. In
exchange, `length`, `list-ref`, and `take`/`drop` are host indexing — O(1) —
which classic linked-list Schemes cannot say. Python intuition transfers here,
not there.

## Vectors: the mutable sequence

A vector is the tuple-shaped thing that can actually change:

```scheme
(define v (make-vector 3 0))   ;=> #(0 0 0) — [0, 0, 0]
(vector-set! v 1 'x)           ; v is now #(0 x 0) — xs[1] = 'x'
(vector-ref v 1)               ;=> x
(vector-append v #(9))         ;=> #(0 x 0 9) — a new vector, v unchanged
(vector-map + #(1 2) #(10 20)) ;=> #(11 22)
(list->vector '(1 2))          ;=> #(1 2)
(vector->list #(1 2))          ;=> (1 2)
```

Read the mutators carefully: `vector-set!` changes *the vector*, in place —
the same in-place mutation Python lists do. `vector-append` and `vector-copy`
are the non-mutating operations, and they return new vectors the way `cons`
returns a new list. When you want Python's `xs[1] = x` semantics, you want a
vector, not a list.

Which one, then? The decision is about *how the data changes*:

- Grows and shrinks element by element, or is built by transformation —
  **list**, with the fold family.
- Fixed length, written in place, indexed hot (game boards, buffers, the
  promise implementation itself — `shslisp/prelude.scm` builds promises on a
  two-slot vector) — **vector**.

## Deletion has two spellings — and lists can mutate after all

`delete` removes elements equal to a *value*; `remove` removes everything
satisfying a *predicate*. One takes the culprit, one takes the crime:

```scheme
(delete 2 '(1 2 3 2))    ;=> (1 3)
(remove odd? '(1 2 3 4)) ;=> (2 4)
```

And the mutable option exists for lists too, with the same naming discipline
as vectors: `list-set!` writes an index in place, `list-copy` gives you a
fresh list so the write hits only your copy:

```scheme
(define l (list 1 2 3))
(list-set! l 1 'x)
l        ;=> (1 x 3)
```

The discipline from chapter 22 still applies — mutation inside a function
boundary, value-style code outside — but when an algorithm genuinely owns a
scratch list, `list-set!` is there and it is host-speed.

**Prefix scans** round out the slicing family: `take-while`/`drop-while`
split at the first element that fails a predicate (their two-value cousins
`span`/`break` from SRFI 1 answer both halves at once — chapter
[11](11-srfi-1-the-list-library.md)):

```scheme
(take-while odd? '(1 3 2 4))  ;=> (1 3)
(drop-while odd? '(1 3 2 4))  ;=> (2 4)
```

## Strings and bytevectors are sequences too

The list operations have string twins, and the bridge between the two worlds
is `string->list`/`list->string` — so any list trick becomes a string trick
in two calls:

```scheme
(string->list "abc")  ;=> (#\a #\b #\c)
(list->string (map char-upcase (string->list "hi")))  ;=> "HI"
(string-upcase "hi")  ;=> HI — the direct route
(string-contains? "hello" "ell")  ;=> #t
```

(The map-over-chars route prints characters as `#\a` under `display` — the
`write`/`display` split from chapter [02](02-values-and-reading.md). Convert
back with `list->string` when you want a string again.)

Vectors complete the set: `vector-fill!` writes every slot, and
`vector-copy` takes optional start/end — slices, exactly:

```scheme
(define v (make-vector 4 0))
(vector-fill! v 9)
v                  ;=> #(9 9 9 9)
(vector-copy v 1 3) ;=> #(9 9) — slots 1 and 2
```

## Try it

```scheme
;; building and reading
(display (append '(1 2) '(3) '(4 5))) (newline)
(display (reverse '(1 2 3))) (newline)
(display (take '(1 2 3 4) 2)) (newline)
(display (drop '(1 2 3 4) 2)) (newline)
(display (list-ref '(a b c) 1)) (newline)
(display (last '(a b c))) (newline)
;; the comprehension moves
(display (filter odd? '(1 2 3 4 5))) (newline)
(display (map * '(1 2 3) '(10 20 30))) (newline)
(display (append-map (lambda (x) (list x x)) '(1 2))) (newline)
(display (fold (lambda (x acc) (+ acc (* x x))) 0 '(1 2 3))) (newline)
(display (count even? '(1 2 3 4))) (newline)
(display (filter-map (lambda (x) (and (even? x) (* x x))) '(1 2 3 4))) (newline)
(display (flatten '(1 (2 (3 4)) 5))) (newline)
(display (enumerate '(a b))) (newline)
;; sorting and grouping
(display (sort '(3 1 2) <)) (newline)
(display (sort-by car < '((3 c) (1 a) (2 b)))) (newline)
(display (group-by (lambda (x) (modulo x 2)) '(1 2 3 4 5))) (newline)
;; vectors: the mutable sequence
(define v (make-vector 3 0))
(vector-set! v 1 'x)
(display v) (newline)
(display (vector-map + #(1 2) #(10 20))) (newline)
(display (vector-append v #(9))) (newline)
(display (list->vector '(1 2))) (newline)
(display (vector->list #(1 2))) (newline)
;; deletion, mutation, and scans
(display (remove odd? '(1 2 3 4))) (newline)
(define l (list 1 2 3))
(list-set! l 1 'x)
(display l) (newline)
(display (take-while odd? '(1 3 2 4))) (newline)
(display (drop-while odd? '(1 3 2 4))) (newline)
;; strings are sequences too
(display (string->list "abc")) (newline)
(display (list->string (map char-upcase (string->list "hi")))) (newline)
(display (string-contains? "hello" "ell")) (newline)
;; vector fill and ranged copy
(define v (make-vector 4 0))
(vector-fill! v 9)
(display v) (newline)
(display (vector-copy v 1 3)) (newline)
```

```text
(1 2 3 4 5)
(3 2 1)
(1 2)
(3 4)
b
c
(1 3 5)
(10 40 90)
(1 1 2 2)
14
2
(4 16)
(1 2 3 4 5)
((0 a) (1 b))
(1 2 3)
((1 a) (2 b) (3 c))
((1 (1 3 5)) (0 (2 4)))
#(0 x 0)
#(11 22)
#(0 x 0 9)
#(1 2)
(1 2)
(2 4)
(1 x 3)
(1 3)
(2 4)
(#\a #\b #\c)
HI
#t
#(9 9 9 9)
#(9 9)
```

## Exercises

1. **Sum of squares, three ways.** Write `sum-of-squares` with `fold`, with
   `map` + `fold +`, and with `append-map`. All three are one line. Which one
   would you keep, and why?
2. **Word length groups.** `(group-by string-length '("a" "bb" "cc" "ddd"))`
   — predict the alist before running. Then read the `"ddd"` group back out
   with `alist-ref`.
3. **The in-place game.** Implement a 3×3 tic-tac-toe board as a 9-slot vector
   (`(make-vector 9 '-)`), write `board-ref`/`board-set!` in terms of
   `vector-ref`/`vector-set!` with `(quotient i 3)` and `(modulo i 3)`, and
   explain why the same program over a list would either copy on every move
   or need `set-car!` gymnastics.

## The shape you copy

> Transform sequences with `map`/`filter`/`fold` and the prelude's named
> helpers before writing a loop; sort with `sort`/`sort-by`; group with
> `group-by`. Reserve vectors for data that is written in place — and when a
> traversal is hot, walk it with a primitive, never hand-rolled `cdr`.

Next: [11 SRFI 1 — the list library](11-srfi-1-the-list-library.md).
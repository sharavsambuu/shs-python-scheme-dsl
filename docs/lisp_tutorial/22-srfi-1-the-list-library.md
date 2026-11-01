# 22 — SRFI 1: the list library

> **What this chapter teaches.** `(srfi 1)`, the list library that ships
> pre-imported: the fold family, list constructors and slicers, searching,
> set operations on lists — and the one import collision the language
> resolves for you.
>
> **Before this:** 08 (you are comfortable with `map`/`filter` and named
> `let`). · **Time:** ~15 min.
> **After this you can:** reach for the right list operation by name, and
> know when a result is *two values* rather than one.

## The layer is already there

Start a REPL — any of them — and the SRFI layer is loaded:

```sh
shs repl --no-tetris
```

This is the **default DSL profile** at work: `make_env()` pre-imports every
mandatory SRFI, so programs need no preamble. The profile is *additive* — it
binds no name the core already binds — and `cond-expand` reports it:

```lisp
(cond-expand (dsl-profile 'dsl) (else 'strict))            ;=> dsl
(cond-expand ((library (srfi 1)) 'there) (else 'absent))   ;=> there
```

Under the strict `profile="r7rs"` (the conformance target), none of this is
pre-imported; a program there says `(import (srfi 1))` itself. That split is
the point: the default profile is for *writing*, the strict one is for
*asking what is portable*.

## Fold, and its direction

SRFI 1's fold family is the workhorse. The function takes `(elt acc)` —
element first, accumulator second — and `fold` walks left to right:

```lisp
(fold + 0 '(1 2 3 4))                          ;=> 10
(fold (lambda (x acc) (cons (* x x) acc)) '() '(1 2 3))  ;=> (9 4 1)
(fold-right cons '() '(1 2 3))                 ;=> (1 2 3)
```

`reduce` folds with the first element as the seed (an empty list answers the
init): `(reduce + 0 '(1 2 3))` is `6`. The prelude's `foldl`/`foldr` remain
with the same argument order — `fold` is the name shipped code uses.

## Constructing and slicing

```lisp
(iota 5)                       ;=> (0 1 2 3 4)
(iota 5 10)                    ;=> (10 11 12 13 14)
(list-tabulate 3 (lambda (i) (* i i)))   ;=> (0 1 4)
(zip '(1 2 3) '(a b c))        ;=> ((1 a) (2 b) (3 c))
(take '(1 2 3 4) 2)            ;=> (1 2)
(drop-right '(1 2 3 4) 2)      ;=> (1 2)
(append-map (lambda (x) (list x x)) '(1 2))   ;=> (1 1 2 2)
```

`iota` is the counting list, `zip` interleaves, and the `take`/`drop` family
slices. Deletion comes in two shapes: `delete` removes equal elements,
`delete-duplicates` keeps the first of each:

```lisp
(delete 2 '(1 2 3 2))          ;=> (1 3)
(delete-duplicates '(1 2 1 3 2))   ;=> (1 2 3)
```

## Searching, with an optional comparator

The searching predicates return *useful* values, not just booleans: `find`
returns the element, `any` returns the predicate's true value, and
`member`/`assoc` return the tail/entry from the match onward. All of them
accept an optional comparator — which is how you search by content instead
of identity:

```lisp
(find even? '(1 3 4 5))        ;=> 4
(count odd? '(1 2 3 4 5))      ;=> 3
(any even? '(1 3 4))           ;=> #t
(member "b" '("a" "b" "c") string=?)   ;=> (b c)
(assoc 'b '((a 1) (b 2)))      ;=> (b 2)
```

## Two values, not one

`partition` and `span` answer *two* questions at once — what passes and what
fails — and they return **two values**, the way `values` does. This is the
single most surprising thing in the library, so meet it deliberately:

```lisp
(call-with-values (lambda () (partition odd? '(1 2 3 4))) list)
;=> ((1 3) (2 4))
(call-with-values (lambda () (span odd? '(1 3 2 4))) list)
;=> ((1 3) (2 4))
```

If you `display` the call directly you see the values printed as a group —
the form to remember is the `call-with-values` (or `let-values`) one.

## Lists as sets

The `lset` family treats lists as sets, taking the comparator first:

```lisp
(lset-union eq? '(1 2 3) '(3 4 5))         ;=> (1 2 3 4 5)
(lset-intersection eq? '(1 2 3) '(2 3 4))  ;=> (2 3)
(lset-difference eq? '(1 2 3) '(2 3 4))    ;=> (1)
```

## The one collision: `map` and `for-each`

SRFI 1's `map`/`for-each` **stop at the shortest list**; the `(scheme base)`
ones require equal lengths and raise. Because both readings are correct, the
default profile imports SRFI 1 with those two names **renamed**:

```lisp
(map + '(1 2 3) '(10 20))        ;=> error: map: lists must be the same length
(srfi-1:map + '(1 2 3) '(10 20)) ;=> (11 22)
```

So the base `map` keeps its report-mandated strictness, the SRFI 1 behaviour
is one explicit name away, and nothing silently changes meaning. The renames
are the only two in the whole layer.

## Try it

```sh
shs run /dev/stdin <<'EOF'
(display (cond-expand (srfi-1 'yes) (else 'no))) (newline)
(display (iota 5)) (newline)
(display (fold + 0 (iota 5))) (newline)
(display (fold-right cons '() '(1 2 3))) (newline)
(display (zip '(1 2 3) '(a b c))) (newline)
(display (delete 2 '(1 2 3 2))) (newline)
(display (delete-duplicates '(1 2 1 3 2))) (newline)
(display (member "b" '("a" "b" "c") string=?)) (newline)
(display (count odd? '(1 2 3 4 5))) (newline)
(display (find even? '(1 3 4 5))) (newline)
(display (any even? '(1 3 4))) (newline)
(display (call-with-values (lambda () (partition odd? '(1 2 3 4))) list)) (newline)
(display (lset-union eq? '(1 2 3) '(3 4 5))) (newline)
(display (srfi-1:map + '(1 2 3) '(10 20))) (newline)
EOF
```

```text
yes
(0 1 2 3 4)
10
(1 2 3)
((1 a) (2 b) (3 c))
(1 3)
(1 2 3)
(b c)
3
4
#t
((1 3) (2 4))
(1 2 3 4 5)
(11 22)
```

## Exercises

1. **Direction matters.** Write `(rev xs)` as `(fold (lambda (x acc) (cons x
   acc)) '() xs)` and check it against `reverse`. Then explain why
   `fold-right cons '() xs` is the identity on lists.
2. **Two values.** Write `(split nums)` that returns the even and odd
   elements as two values using `partition`, and read them back with
   `let-values`. What happens if you bind the result with a plain `let`?
3. **The comparator.** `(assoc "b" alist)` matches a `"b"` key — `assoc`
   compares with `equal?` by default. What extra argument makes
   `(assoc "B" alist)` find that same entry regardless of case? Try it with
   `string-ci=?`.

## The shape you copy

> The library answers the questions you were about to write a named `let`
> for. Before hand-rolling a loop, ask: is this `fold`, a search, a slice, or
> a set operation? And when a function answers two questions, expect two
> values.

Next: [23 SRFI 26 — cut and cute](23-srfi-26-cut-and-cute.md).


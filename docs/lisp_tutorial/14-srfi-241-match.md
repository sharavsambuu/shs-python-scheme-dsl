# 14 — SRFI 241: `match`

> **What this chapter teaches.** The standard pattern matcher: quasiquote
> patterns, guards, ellipsis, vector and dotted patterns, the catamorphism —
> and the deliberate split between this `match` and the project's
> `variant-match`.
>
> **Before this:** 13 (records and variants), 08. · **Time:** ~15 min.
> **After this you can:** destructure any value by shape, and know which
> matcher a case calls for.

## Two matchers, on purpose

This dialect has two matchers, and the split is deliberate:

- **`variant-match`** (chapter [20](20-typed-control-flow.md)) dispatches on
  a `define-variant` value's *tag*: bare-symbol patterns bind, the tag names
  the case, and a forgotten case is refused because the set is closed.
- **`match`** (this chapter, SRFI 241) is the general pattern matcher:
  patterns are **quasiquote-shaped** — a literal matches itself, and `,x`
  binds.

The two never collide: `variant-match` is the project's name, and `match` is
the SRFI's. Use `variant-match` for tagged domain values; use `match` when
the shape is a list's structure rather than a tag.

## Patterns are quasiquote-shaped

The pattern grammar reads like `quasiquote`:

- a **literal** (number, string, character, `#t`/`#f`, `()`) matches by
  `equal?`;
- a **bare symbol** is a constant — it matches the same symbol;
- `,_` matches anything and binds nothing (the wildcard);
- `,x` matches anything and binds it;
- a **list pattern** matches a list of the same length, element by element.

```scheme
(match 42 [,x x])                        ;=> 42
(match '(1 2 3) [(,a ,b ,c) (+ a b c)])  ;=> 6
(match '(ok 5) [(ok ,v) v])              ;=> 5
(match 'sym [sym 'same] [,other 'other]) ;=> same
```

Note the discipline: `(ok ,v)` matches the *symbol* `ok` as a constant and
binds the second element — the same shape a variant views as, written in
SRFI 241's grammar.

## Guards

A clause may carry a **guard** — a third element that must be true for the
clause to match; a failed guard moves on to the next clause, and its
bindings do not leak:

```scheme
(match 5
  [,i (guard (integer? i)) i]
  [,x 'no])                            ;=> 5

(match 5
  [,x (guard (> x 10)) 'big]
  [,y y])                              ;=> 5
```

A guard that fails with no later clause raises — `match` never silently
falls through, the same discipline as `variant-match`.

## Ellipsis: the rest of the list

`,x* ...` binds the remaining elements as a list:

```scheme
(match '(a 17 37)
  [(a ,x* ...) x*])                    ;=> (17 37)
```

Ellipses nest, which is how you flatten two levels at once:

```scheme
(match '(begin (1 5) (2 6))
  [(begin (,x* ,y*) ...) (append x* y*)])   ;=> (1 2 5 6)
```

## Vectors and dotted tails

Vector patterns match vectors with `#(...)`:

```scheme
(match (vector 1 2 3) [#(1 ,a ,b) (+ a b)])       ;=> 5
(match (vector 1 2 3 4) [#(1 ,a* ...) a*])        ;=> (2 3 4)
```

And a dotted pattern matches a list's tail:

```scheme
(match '(1 2 3) [(,a . ,rest) (list a rest)])     ;=> (1 (2 3))
(match '() [() 'empty])                           ;=> empty
```

A repeated variable is an equality *constraint*: `(match '(1 1) [(,a ,a)
'same])` matches, and `(match '(1 2) [(,a ,a) 'same])` raises.

## The catamorphism: recursing into the same match

`,[expr -> y]` (or `,[y]` for short) applies the *same `match`* to a
sub-pattern's match — the idiom that writes a recursive walk in one clause
list:

```scheme
(define (len lst)
  (match lst
    [() 0]
    [(,x . ,[y]) (+ 1 y)]))

(len '(a b c d))                         ;=> 4
```

The `,[y]` in the second clause is itself a match against the tail, so the
recursion is the pattern. Two documented deviations: the catamorphism's
recursion is a nested interpreter call (bounded by the data's depth, not a
trampolined tail call), and a quasiquote template followed by *multiple*
ellipses does not distribute.

## The no-clause error

No matching clause and no matching guard is an error that names the value:

```scheme
(match '(1 2 3) [(,a ,b) 1])     ;=> error: match: no clause matched (1 2 3)
```

That is the exhaustiveness discipline from chapter [20](20-typed-control-flow.md),
carried over to general patterns: `match` refuses to guess.

## Try it

```scheme
(define (area s)
  (match s
    [(circle ,r) (* 3.14 r r)]
    [(rect ,w ,h) (* w h)]))
(display (area '(circle 2))) (newline)
(display (area '(rect 3 4))) (newline)
(display (match '(1 2 3 4) [(1 ,_ ,b . ,r) (list b r)])) (newline)
(display (match 5 [,i (guard (integer? i)) i] [,x 'no])) (newline)
(display (match '(a 17 37) [(a ,x* ...) x*])) (newline)
(display (match '(begin (1 5) (2 6)) [(begin (,x* ,y*) ...) (append x* y*)])) (newline)
(display (match (vector 1 2 3) [#(1 ,a ,b) (+ a b)])) (newline)
(display (match '(1 1) [(,a ,a) 'same])) (newline)
```

```text
12.56
12
(3 (4))
5
(17 37)
(1 2 5 6)
5
same
```

## Exercises

1. **Tag vs shape.** Rewrite chapter [20](20-typed-control-flow.md)'s `area`
   with `variant-match` and with `match`. Which one refuses a case you
   forgot, and why does the SRFI's version need the `else`-style refusal
   written differently?
2. **A tree walk.** Write `(depth t)` for nested lists with the catamorphism:
   a leaf is `0`, a list is one more than its deepest child. Test it on
   `(1 (2 (3)))`.
3. **Guards vs `cond`.** Rewrite the guarded `match` above as `cond` with
   `let` bindings. Which version keeps the binding and the test in one
   place, and what does that buy?

## The shape you copy

> A pattern is the shape of the data, written where the data arrives. Reach
> for `variant-match` when the shape is a declared tag; reach for `match`
> when it is a list's structure. Either way, the matcher names the value that
> fits nothing — a silent default is the bug.

Next: [15 SRFI 26 — cut and cute](15-srfi-26-cut-and-cute.md).

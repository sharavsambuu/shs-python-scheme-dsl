# 23 — Functional programming: foundations

> **What this chapter teaches.** The paradigm the whole language is shaped
> around, named at last: pure functions and referential transparency, mutation
> quarantined instead of sprinkled, the fold family as *recursion schemes*,
> point-free style, and the real difference between currying and partial
> application.
>
> **Before this:** 11–14 (the data-structures track). · **Time:** ~15 min.
> **After this you can:** decide for any loop whether it is a `map`, a `fold`,
> or a named `let` — and keep every decision you make replaceable.

Nothing in this chapter is new machinery. That is the point: functional
programming in this language is not a feature you import, it is the grammar you
have been speaking since chapter [09](09-lisp-by-example.md) — `lambda`, `let`,
`define`, and the discipline of what you allow them to touch.

## Purity, and the substitution test

A pure function is one where the call can be replaced by its value. Not
"morally" — literally:

```scheme
(define (total prices) (fold + 0 prices))
(total '(100 250 50))                 ;=> 400
(equal? (total '(100 250 50)) 400)    ;=> #t
```

Two properties make `total` pure: *same inputs, same answer* (no hidden state),
and *no witness* (nothing outside the call changed — no `set!`, no table
mutated, no output). The second is the one Python code quietly fails, and the
reason this language's architecture is an FP claim: chapter
[04](04-primitives.md) keeps the primitive floor pure and names the impure
doors — `display`, `error`, `eval`, `read-string`, `load`. A program that
touches the world only through that short list has purity you can *check*
instead of hope for.

The test to run on your own code: **could you replace the call with its
printed value and nothing downstream could tell?** If yes, it composes, it
caches, it reorders, it tests. If no, you have found the one place the
mutation belongs — see next section.

## Quarantining mutation, not abolishing it

The FP move is not "never mutate" — the prelude itself mutates (`push!` into a
local, `hash-table-set!` in `group-by`). The move is *quarantine*: mutation
lives inside a function, behind a parameter, or inside a closure (chapter
[24](24-fp-design-patterns.md)), and the function still answers by value.

The workhorse replacement for "mutate as I go" is the **accumulator**: carry
the result forward as a parameter instead of writing it into a variable:

```scheme
(define (normalize xs)
  (reverse (fold (lambda (x acc) (cons (* 2 x) acc)) '() xs)))
```

`fold` *is* the accumulator pattern, packaged: the `acc` parameter, threaded
for you, with the reverse folded in. When you find yourself writing `(set! acc
...)` inside a loop, you are one step from a fold.

## Folds as recursion schemes

Here is the FP insight that turns the library into a vocabulary. Almost every
list recursion you will ever write is one of four shapes — and each shape has
a name:

| Shape | Name | Example |
| --- | --- | --- |
| transform each element | `map` | `(map (cut * 10 <>) xs)` |
| keep some elements | `filter` | `(filter odd? xs)` |
| collapse to one value | `fold` | `(fold + 0 xs)` |
| build a list back up | `fold-right` | `(fold-right cons '() xs)` |

The two folds differ in *direction*, and the difference is visible in one
line: `fold` processes left to right and prepends, so building with it
reverses; `fold-right` processes right to left, so building with it preserves:

```scheme
(fold cons '() '(1 2 3))      ;=> (3 2 1)
(fold-right cons '() '(1 2 3)) ;=> (1 2 3)
```

`fold` is also n-ary — two lists walk together, one step of the accumulator
each:

```scheme
(fold (lambda (a b acc) (+ acc (* a b))) 0 '(1 2 3) '(10 20 30))  ;=> 140
```

And "collapse to one value" is more general than summing — a maximum is a
fold, because the accumulator can be any value seen so far:

```scheme
(fold (lambda (x acc) (if (> x acc) x acc)) 0 '(3 9 4))  ;=> 9
```

**When a named `let` still wins.** Two cases, and they are the same two cases
every time: you need *more than one accumulator*, or you need to *stop early*:

```scheme
(let loop ((xs '(7 2 9 4)) (sum 0) (count 0))
  (cond ((null? xs) (/ sum count))
        ((> (car xs) 8) (loop (cdr xs) sum count))   ; early exit for one arm
        (else (loop (cdr xs) (+ sum (car xs)) (+ count 1)))))
;=> 13/3
```

Two accumulators, a skip rule, an exact rational out the other side. This is
the division of labour: `fold` for the shape the library owns, named `let` for
the shape *you* own — and both are tail calls the trampoline honours
(chapter [03](03-evaluating.md)).

## Point-free style: bind now, describe later

"Point-free" (tacit) style defines a function *without naming its argument* —
by composing functions instead. All the ingredients are in the prelude and
SRFI 26:

```scheme
(define (double n) (* n 2))
(map double '(1 2 3))        ;=> (2 4 6)
((compose double double) 3)  ;=> 12  — f∘g, right to left
(map (cut * 10 <>) '(1 2 3)) ;=> (10 20 30) — the argument goes in the <>
((partial + 10) 5)           ;=> 15 — bind the leading arguments now
```

The style earns its keep when the *pipeline is the idea*: `sort-by` is
point-free at its core (`(sort xs (lambda (a b) (less (key a) (key b))))`),
and chapter [20](20-srfi-197-chain-and-nest.md)'s `chain` is the same idea
read left to right. It loses when the composition is the only thing on the
line and the reader has to simulate it — a two-line `lambda` named after what
it computes beats a four-stage `compose` named after nothing. The rule of
thumb: *name the transformation, not the plumbing*; if you cannot say the
name, keep the `lambda`.

## Currying vs partial application

They look interchangeable and are not. **Partial application** binds *some*
arguments now, all the rest later, in one call:

```scheme
((partial + 10) 5)     ;=> 15 — one call supplies the rest
```

**Currying** turns a two-argument function into a chain of one-argument
functions — each call takes *exactly one* argument. The prelude's `curry`
needs the arity (a Lisp closure knows its own; a host primitive does not):

```scheme
(define (add a b) (+ a b))
(((curry add) 1) 2)    ;=> 3 — one argument per call
```

When does the difference matter? Currying shines when you will specialize
*one argument at a time* over time (configurers, builders); `partial` shines
when you know the leading arguments *now*. And SRFI 26's `cut` is the syntax
for the common case of both: `(cut f x <>)` is "f with x in front, argument
in the hole" — chapter [16](16-srfi-26-cut-and-cute.md) is its full grammar.

## Recursion on more than lists

The fold section's shapes cover lists; the same two recursion shapes cover
*numbers*, and it is worth seeing them side by side because the tail-call
rule is the same:

```scheme
(define (fact n) (if (= n 0) 1 (* n (fact (- n 1)))))   ; non-tail: the multiply waits
(define (sum-to n)
  (let loop ((i 0) (s 0))                               ; tail: the add happens now
    (if (> i n) s (loop (+ i 1) (+ s i)))))
```

`fact 20` is `2432902008176640000` — an exact integer, no overflow — and
`sum-to 100000` finishes without a whisper, because every `loop` call is in
tail position and the trampoline (chapter [03](03-evaluating.md)) reuses the
frame. Swap the two styles on the same input and you feel the difference the
budgets name (`LispRecursionError`, appendix [A](appendix-a-reference.md)):
deep *non-tail* recursion is the one that hits the depth limit.

**Mutual recursion** — two functions calling each other — is the other shape
the named `let` cannot spell, and `letrec` is its home:

```scheme
(letrec ((ev? (lambda (n) (if (= n 0) #t (od? (- n 1)))))
         (od? (lambda (n) (if (= n 0) #f (ev? (- n 1))))))
  (ev? 10))
;=> #t
```

So the complete recursion vocabulary is four entries: structural recursion
over lists (folds, usually), structural recursion over numbers (`fact`),
tail accumulation (`sum-to` and every named `let`), and mutual (`letrec`).

## The rest of the combinator shelf

Chapter 05 introduced the shelf; here is what the rest of it is *for*, with
each combinator pulling real weight:

```scheme
(reduce + 0 '(1 2 3))        ;=> 6 — fold without naming the seed
((complement even?) 3)       ;=> #t — a predicate negated into a predicate
((flip -) 1 10)              ;=> 9 — arguments reversed: (- 10 1)
((compose inc inc inc) 0)    ;=> 3 — arity survives composition
(iterate inc 0 5)            ;=> (0 1 2 3 4) — the first n of a sequence
```

`reduce` is the fold for "sum/max/any fold-with-first-element" where the seed
would be fake. `complement` is how a predicate stays a predicate —
`(filter (complement odd?) xs)` reads better than a `lambda` that inverts.
`flip` is the tool for a function whose arguments arrive in the wrong order
(most often: fixing a two-argument function for `partial`). And `iterate`
generates a sequence from a step function — the seed of chapter
[19](19-generators.md)'s infinite generators, eager here, lazy there.

## Try it

```scheme
;; purity: same inputs, same answer, nothing else changes
(define (total prices) (fold + 0 prices))
(display (total '(100 250 50))) (newline)
(display (equal? (total '(100 250 50)) 400)) (newline)
;; accumulator style replaces mutation
(define (normalize xs)
  (reverse (fold (lambda (x acc) (cons (* 2 x) acc)) '() xs)))
(display (normalize '(1 2 3))) (newline)
;; folds as recursion schemes
(display (fold (lambda (x acc) (if (> x acc) x acc)) 0 '(3 9 4))) (newline)
(display (fold cons '() '(1 2 3))) (newline)
(display (fold-right cons '() '(1 2 3))) (newline)
(display (fold (lambda (a b acc) (+ acc (* a b))) 0 '(1 2 3) '(10 20 30))) (newline)
;; named let: many accumulators, early exit
(display
  (let loop ((xs '(7 2 9 4)) (sum 0) (count 0))
    (cond ((null? xs) (/ sum count))
          ((> (car xs) 8) (loop (cdr xs) sum count))
          (else (loop (cdr xs) (+ sum (car xs)) (+ count 1))))))
(newline)
;; point-free style: bind now, describe later
(define (double n) (* n 2))
(display (map double '(1 2 3))) (newline)
(display ((compose double double) 3)) (newline)
(display (map (cut * 10 <>) '(1 2 3))) (newline)
(display ((partial + 10) 5)) (newline)
(define (add a b) (+ a b))
(display (((curry add) 1) 2)) (newline)
;; recursion on numbers, and the combinator shelf
(define (fact n) (if (= n 0) 1 (* n (fact (- n 1)))))
(display (fact 20)) (newline)
(define (sum-to n) (let loop ((i 0) (s 0)) (if (> i n) s (loop (+ i 1) (+ s i)))))
(display (sum-to 100000)) (newline)
(display (reduce + 0 '(1 2 3))) (newline)
(display ((complement even?) 3)) (newline)
(display ((flip -) 1 10)) (newline)
(display (iterate inc 0 5)) (newline)
```

```text
400
#t
(2 4 6)
9
(3 2 1)
(1 2 3)
140
13/3
(2 4 6)
12
(10 20 30)
15
3
2432902008176640000
5000050000
6
#t
9
(0 1 2 3 4)
```

## Exercises

1. **The substitution test, run for real.** Write `(bad-total! prices)` that
   sums by mutating a `total` variable with `set!` inside a `for-each`. It
   gives the right answer — so *what exactly* disqualifies it? Name the two
   purity properties and say which one it keeps and which it loses.
2. **Fold or named let?** For each, decide and justify in one sentence:
   (a) sum of squares, (b) running average that also reports how many values
   were skipped, (c) the last element satisfying a predicate, scanning from
   the left but stopping at the first match.
3. **The curried builder.** Write `(make-scaler k)` as `((curry *) k)`'s
   cousin — a function that answers functions multiplying by `k` — and check
   `(map (make-scaler 3) '(1 2 3))`. Then write the same with `partial` and
   explain which spelling a reader parses faster.

## The shape you copy

> Keep every function passing the substitution test; quarantine what must
> mutate inside a parameter, a fold accumulator, or a closure; reach for
> `map`/`filter`/`fold` before writing a loop, and a named `let` when you own
> extra accumulators or an early exit; compose when the pipeline is the idea,
> and keep the `lambda` when only the name would save it.

Next: [24 FP design patterns](24-fp-design-patterns.md).
# 23 — FP design patterns

> **What this chapter teaches.** The patterns that fall out of chapter 22's
> foundations once you build with them: behavior passed as data (the strategy),
> closures as modules with private state, memoisation as a pure wrapper, lazy
> composition over generators, and one shape — bind — that generalizes chapter
> [21](21-railway-oriented.md)'s Result railway to any container.
>
> **Before this:** 22; chapter [21](21-railway-oriented.md) for the Result
> vocabulary. · **Time:** ~15 min.
> **After this you can:** reach for the FP answer to the classic OO pattern
> book — and know which of the four patterns a given problem is.

None of these patterns is a class hierarchy. Each one is a function shape the
language already has, applied where an OO design would have reached for an
interface. That is the FP pattern book in one sentence: **the pattern is the
argument.**

## Behavior as data: the strategy

A strategy is a choice of behavior made at runtime. OO gives it an interface,
two implementations, and a factory; FP gives it a parameter:

```scheme
(define (total-with discount prices)
  (fold (lambda (p acc) (+ acc (discount p))) 0 prices))
(total-with (lambda (p) p) '(100 200))         ;=> 300 — no discount
(total-with (lambda (p) (* 9/10 p)) '(100 200)) ;=> 270 — ten percent off
```

The strategy is data: you can store it in an alist (chapter
[12](12-dictionaries-alists-and-hash-tables.md)), swap it per call, test it in
isolation, and compose it with `cut`/`compose`. The library is already built
this way — every higher-order function you have met (`sort-by`, `group-by`,
`filter-map`) takes its behavior as an argument. When you find yourself
writing a "manager" whose subclasses differ in one method, this is the shape
you wanted.

## Closures as modules: state behind a wall of behavior

Chapter [13](13-records-variants-and-objects.md) built a counter with a
closure. The pattern generalizes: a closure over a `let` is a module whose
state *cannot be reached* except through the behavior it exports — chapter
15's quarantine, taken seriously:

```scheme
(define (make-stack)
  (let ((items '()))
    (lambda (msg . args)
      (case msg
        ((push) (set! items (cons (car args) items)))
        ((pop) (let ((top (car items)))
                 (set! items (cdr items))
                 top))
        ((size) (length items))))))
```

The `set!` is real mutation — and nobody can touch it, because `items` is
visible only inside the closure. Every caller sees pure behavior: push, pop,
size. This is where mutation *belongs* in a functional program: at a boundary,
with a small message protocol, never smeared through the code that uses it.

## Memoisation: a pure wrapper over a private cache

The prelude's `memoize` (chapter [05](05-standard-library.md)) is the same
closure pattern aimed at performance: a private hash table, keyed
structurally, wrapped so the *caller* sees an ordinary pure function:

```scheme
(define (fib n) (if (< n 2) n (+ (fib (- n 1)) (fib (- n 2)))))
(define fib-fast
  (memoize (lambda (n)
             (if (< n 2) n (+ (fib-fast (- n 1)) (fib-fast (- n 2))))))))
(equal? (fib 20) (fib-fast 20))   ;=> #t
(fib-fast 60)                     ;=> 1548008755920 — instantly
```

The self-reference is the whole trick, and the classic gotcha: wrapping the
*named* `(fib ...)` does nothing for the recursion, because `fib` calls `fib`,
not the wrapper. Bind the memoised lambda to the name the recursion uses
(`fib-fast` calls `fib-fast`), and the cache pays off at every level. Note
also what did *not* change: the definition of the sequence. Purity is what
makes the cache legal at all — a memoised impure function is a bug factory.

## Lazy composition: pipelines that do no work until drained

Chapter [18](18-generators.md)'s generators are chapter 15's composition,
applied to *infinite* data: `gmap` and `gfilter` chain the way functions do,
but nothing evaluates until a drain asks for values:

```scheme
(generator->list
  (gtake (gmap (lambda (x) (* x x)) (make-range-generator 1)) 5))
;=> (1 4 9 16 25)
```

That pipeline describes the square of every natural number — and computes
exactly five of them. The pattern: describe the transformation, defer the
work, drain when you must. It is the point-free style of chapter 22 with time
added.

## One shape, two containers: bind

Chapter [21](21-railway-oriented.md) built error handling on one operation:
`result-bind` runs the continuation only on the success rail. The pattern is
not about errors — it is about *any* container where "continue in the same
shape" makes sense. The list is the second instance you already know:

```scheme
;; Result's bind: continue only on the ok rail
(pipe-results 40 halve halve)     ;=> (ok 10)
(pipe-results 41 halve halve)     ;=> (err odd: 41) — the rail refused
;; List's bind: continue into every element — it is append-map
(append-map (lambda (n) (list (* n 10))) '(1 2 3))   ;=> (10 20 30)
```

(`halve` returns `(ok (/ n 2))` for evens and `(err ...)` for odds; chapter
10 defines the variant and the vocabulary.) Same pipeline shape, same
"thread and short-circuit" idea, different container: Result short-circuits
at the first refusal, list fans out at every element. When you meet a third
container — a generator, a promise — you now know what to look for: its bind.
That is the design-pattern content of every monad tutorial, and this language
already ships you two of them.

## The strategy table: behaviors in a dictionary

The strategy pattern's second half is *choosing* at runtime, and chapter
[12](12-dictionaries-alists-and-hash-tables.md)'s alist is the chooser —
a dictionary whose values are functions:

```scheme
(define (double n) (* n 2))
(define (square n) (* n n))
(define strategies (list (list 'square square) (list 'double double)))

((alist-ref strategies 'square) 5)   ;=> 25
```

The name of the behavior is data; the behavior is data; the lookup composes
with `fold`/`map` like any other read. This is the shape behind every
"configurable pipeline": a config file's words become alist keys, and the
behavior table is the only place that knows what the words mean. Note the
proper two-element lists — chapter 12's house style is what makes
`alist-ref` work here.

## Memoisation with more arguments

Chapter 23's `fib-fast` memoised one argument; `memoize` keys on the *whole
argument list*, so arity is free:

```scheme
(define mulm (memoize (lambda (a b) (* a b))))
(mulm 6 7)   ;=> 42  — computed
(mulm 6 7)   ;=> 42  — the cache answers, keyed structurally on (6 7)
```

The structural key is the quiet superpower: a memoised function of *lists*,
or of records compared by their fields — anything `equal?` can see — caches
by value, exactly the behavior chapter 05's `hash_key` buys.

## A state machine: closure + variant + case

The three modeling tools of chapters [13](13-records-variants-and-objects.md)
and [23](23-fp-design-patterns.md) compose into the smallest honest state
machine — states as variants, transitions as `variant-match`, the machine
itself as a closure with a message protocol:

```scheme
(define-variant light (red) (green) (yellow))

(define (make-traffic-light)
  (let ((state (red)))
    (lambda (msg)
      (case msg
        ((next) (set! state
                  (variant-match state
                    ((red) (green))
                    ((green) (yellow))
                    ((yellow) (red)))))
        ((show) (tag-of state))))))
```

Two `next` messages move it `red → green → yellow`, and `show` reads the tag
back: `yellow`. Every transition is one named arm, the closed variant makes
an unknown state unrepresentable, and the state is unreachable except through
the protocol — chapter 22's quarantine, chapter 13's closed set, working as
one machine.

## The four, and when each is the answer

| The problem | The FP pattern |
| --- | --- |
| Behavior varies at runtime — discount rules, comparators, validators | a function parameter (the strategy) |
| State must exist but must not leak — stacks, counters, connections | a closure over a `let`, with a message protocol |
| The same pure function is called over and over with the same arguments | `memoize` over the self-referential binding |
| The data is big, infinite, or the work is conditional | a lazy generator pipeline |
| A step may fail, or may fan out | a container with a bind — `pipe-results` for Result, `append-map` for lists |

## Try it

```scheme
;; behavior as data: the strategy
(define (total-with discount prices)
  (fold (lambda (p acc) (+ acc (discount p))) 0 prices))
(display (total-with (lambda (p) p) '(100 200))) (newline)
(display (total-with (lambda (p) (* 9/10 p)) '(100 200))) (newline)
;; closures as modules: state behind a wall of behavior
(define (make-stack)
  (let ((items '()))
    (lambda (msg . args)
      (case msg
        ((push) (set! items (cons (car args) items)))
        ((pop) (let ((top (car items)))
                 (set! items (cdr items))
                 top))
        ((size) (length items))))))
(define s (make-stack))
(s 'push 'a)
(s 'push 'b)
(display (list (s 'pop) (s 'size))) (newline)
;; memoisation: a pure wrapper over a private cache
(define (fib n) (if (< n 2) n (+ (fib (- n 1)) (fib (- n 2)))))
(define fib-fast
  (memoize (lambda (n)
             (if (< n 2) n (+ (fib-fast (- n 1)) (fib-fast (- n 2)))))))
(display (equal? (fib 20) (fib-fast 20))) (newline)
(display (fib-fast 60)) (newline)
;; lazy composition: nothing runs until drained
(display (generator->list
           (gtake (gmap (lambda (x) (* x x)) (make-range-generator 1)) 5)))
(newline)
;; one shape, two containers: bind
(define (halve n)
  (if (even? n) (ok (/ n 2)) (err (string-append "odd: " (number->string n)))))
(display (pipe-results 40 halve halve)) (newline)
(display (pipe-results 41 halve halve)) (newline)
(display (append-map (lambda (n) (list (* n 10))) '(1 2 3))) (newline)
;; the strategy table
(define (double n) (* n 2))
(define (square n) (* n n))
(define strategies (list (list 'square square) (list 'double double)))
(display ((alist-ref strategies 'square) 5)) (newline)
;; two-argument memoisation
(define mulm (memoize (lambda (a b) (* a b))))
(display (mulm 6 7)) (newline)
;; a state machine
(define-variant light (red) (green) (yellow))
(define (make-traffic-light)
  (let ((state (red)))
    (lambda (msg)
      (case msg
        ((next) (set! state
                  (variant-match state
                    ((red) (green))
                    ((green) (yellow))
                    ((yellow) (red)))))
        ((show) (tag-of state))))))
(define t (make-traffic-light))
(t 'next)
(t 'next)
(display (t 'show)) (newline)
(t 'next)
(display (t 'show)) (newline)
```

```text
300
270
(b 1)
#t
1548008755920
(1 4 9 16 25)
(ok 10)
(err odd: 41)
(10 20 30)
25
42
yellow
red
```

## Exercises

1. **Swap the strategy.** Give `total-with` a strategy stored in an alist —
   `((none ...) (percent10 ...) (bogo ...))` — and write `(apply-discount
   name prices)` that looks the behavior up and applies it. What did you
   *not* have to change about `total-with`, and what would that have cost in
   the subclass version?
2. **The wrong memoise.** Define `(define fib-wrong (memoize fib))` and time
   `(fib-wrong 30)` against `(fib-fast 30)`. Explain the result using one
   sentence about which name the recursion calls. Then fix it the chapter's
   way.
3. **The third container.** Write `maybe` as a two-case variant (`(just v)`
   and `(nothing)`), write `maybe-bind`, and show that `pipe-results` and
   your `maybe-bind` pipeline have the same shape. You have written a monad —
   which of the two shipped ones is it closest to?

## The shape you copy

> When an OO design would declare an interface, pass a function; when it would
> hide a field, close over it; when it would cache, wrap the recursion in its
> own memoised name; when it would loop over data that may not exist, build a
> lazy pipeline; and when a step can fail or fan out, find the container's
> bind. Every one of these is behavior as an argument — which is why they all
> compose.

Next: [24 Bounded contexts: DDD in this Lisp](24-bounded-contexts.md).


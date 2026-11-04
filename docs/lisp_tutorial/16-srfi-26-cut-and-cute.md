# 16 — SRFI 26: `cut` and `cute`

> **What this chapter teaches.** Specializing a procedure without naming a
> lambda: `cut` and `cute`, their two placeholder kinds, the difference
> between them, and when the prelude's `partial`/`curry` are the better tool.
>
> **Before this:** 09. · **Time:** ~10 min.
> **After this you can:** write `(cut * 2 <>)` where a lambda would be noise,
> and say exactly when it is evaluated.

## The problem: a lambda with one line in it

Feeding `map` a partially applied function is everyday Lisp:

```scheme
(map (lambda (x) (* x 2)) '(1 2 3))    ;=> (2 4 6)
```

That `lambda` is boilerplate: it names a variable only to fill one slot of a
call. SRFI 26's `cut` writes the call directly, with `<>` marking the hole:

```scheme
(map (cut * 2 <>) '(1 2 3))            ;=> (2 4 6)
```

`(cut f a <> b)` is exactly `(lambda (g1) (f a g1 b))` — the `<>` becomes a
generated parameter, and everything else is captured. Several holes are
allowed; they become the parameters in order:

```scheme
((cut + 1 <> 10) 5)                    ;=> 16
((cut cons <> <>) 1 2)                 ;=> (1 . 2)
```

## The rest slot

`<...>` collects *all remaining* arguments into an `apply` — it must come
last, immediately after a `<>`:

```scheme
((cut list <> <...>) 1 2 3 4)          ;=> (1 2 3 4)
```

That is the "specialize the leading arguments, forward the rest" shape, and
it is why `cut` can wrap variadic procedures.

## `cut` vs `cute`: when the other arguments run

`cut` re-evaluates its non-slot expressions **on every call**; `cute`
evaluates them **once, at construction** (`cute` = "composable, uniformly
nestable, tail-oriented expression" — the `e` is *evaluated now*):

```scheme
(define n 0)
(define (tick) (set! n (+ n 1)) n)
(define f (cut + (tick) 0))
(f) (f)
n                                      ;=> 2  — cut ran (tick) per call
(define g (cute + (tick) 0))
(g) (g)
n                                      ;=> 3  — cute ran (tick) once, up front
```

The rule of thumb: `cut` when the surrounding expressions should track the
environment; `cute` when they are pure setup (and for that reason `cute`
composes more safely inside other expressions).

## `cut` is syntax; `partial` and `curry` are procedures

The prelude keeps two related tools (chapter [05](05-standard-library.md)):

```scheme
((partial + 1 2) 3)     ;=> 6  — binds the *leading* arguments, variadic
((curry + 3) 4)         ;=> a closure — one argument per call, needs an arity
```

The distinction is stated in `srfi26.scm` itself:

> *`partial` and `curry` remain project extensions — they are procedures, not
> syntax, and cannot leave a hole in the middle.*

`cut` can put the hole **first** (`(cut <> 10)`) or in the middle; `partial`
cannot. `curry` builds a chain of one-argument calls; `cut` is one call. Use
`cut`/`cute` at call sites and in pipelines; use `partial` when you need a
*value* to pass around (it is a procedure, so it can be stored and applied
generically).

## Try it

```scheme
(display ((cut + 1 <> 10) 5)) (newline)
(display (map (cut * 2 <>) '(1 2 3))) (newline)
(display ((cut cons <> <>) 1 2)) (newline)
(display ((cut list <> <...>) 1 2 3 4)) (newline)
(define n 0)
(define (tick) (set! n (+ n 1)) n)
(define f (cut + (tick) 0))
(f) (f)
(display n) (newline)
(define g (cute + (tick) 0))
(g) (g)
(display n) (newline)
```

```text
16
(2 4 6)
(1 . 2)
(1 2 3 4)
2
3
```

## Exercises

1. **Rewrite the lambda.** Take three `map` calls you wrote in chapter
   [09](09-lisp-by-example.md) and rewrite each with `cut`. Which ones got
   clearer, and which one was better as an explicit `lambda`?
2. **The rest slot.** Predict `((cut list <> <...>) 1)` and
   `((cut list <> <...>))`, then run them. The second is an arity error —
   why does the rest slot not save it? (Hint: the `<>` is still a required
   parameter.)
3. **Middle hole.** Write `((cut <> 10) inc)` — the hole in *operator*
   position — and explain what it does. Could `partial` express this?

## The shape you copy

> When a lambda exists only to fill a slot, delete it: write the call with
> `<>` where the argument goes. Reach for `cute` when the other arguments are
> pure, and for `partial`/`curry` when you need a procedure value rather than
> a specialised call.

Next: [17 SRFI 88 — keywords](17-srfi-88-keywords.md).

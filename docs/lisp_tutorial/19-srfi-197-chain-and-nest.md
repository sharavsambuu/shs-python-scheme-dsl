# 19 — SRFI 197: chain and nest

> **What this chapter teaches.** The pipeline operators: `chain` and its
> short-circuiting siblings, `chain-lambda`, and the lexically-substituting
> `nest`/`nest-reverse` — plus where the project's own `->`/`->>` fit.
>
> **Before this:** 08, 11. · **Time:** ~12 min.
> **After this you can:** write a data flow left to right, with early exit
> where it needs one.

## The pipeline shape

Data in this language is transformed in steps: filter, then map, then fold.
Written inside-out, the steps read backwards; `chain` writes them in the
order they run, with `_` naming the hole the previous step's value goes
into:

```scheme
(chain '(1 2 3)
  (map (lambda (x) (* x x)) _)
  (fold + 0 _))                    ;=> 14
```

Read it as: square everything, then sum. The `_` may appear anywhere in a
step — including operator position, so `(chain + (_ 1 2))` is `3` — and a
step with no `_` simply ignores the value and evaluates itself.

## Strings through a chain

The classic string-pipeline example, threading a growing value:

```scheme
(chain "" (string-append "foo" _) (string-append "bar" _))   ;=> barfoo
```

`chain` is built on `call-with-values`, so a step may return **multiple
values** and the next step's placeholders collect them in order — and a
trailing `_ ...` forwards all remaining values as an `apply`.

## Early exit: `chain-and` and `chain-when`

Two siblings add control flow to the pipeline:

- **`chain-and`** — if any step returns `#f`, the whole chain answers `#f`
  and the later steps never run. A truthy result is passed onward:

  ```scheme
  (chain-and 5 (* _ 2) (< _ 20))     ;=> #t   (5 → 10 → #t)
  (chain-and 15 (* _ 2) (< _ 20))    ;=> #f   (15 → 30 → #f, chain stops)
  ```

- **`chain-when`** — each step is `(guard expr)`: the step runs only when
  its guard is true, and the value flows through skipped steps untouched:

  ```scheme
  (chain-when 5
    (#t (* _ 10))          ; 5 → 50
    (#f (+ _ 1))           ; skipped
    ((= 1 1) (+ _ 1)))     ; 50 → 51
  ```

Note the guard is a plain expression — it does not see `_`; only the step
body does.

## `chain-lambda`: a pipeline as a procedure

`chain-lambda` is `chain` as a definition: the arguments arrive at the first
`_`, and the result is the last step's:

```scheme
((chain-lambda (* _ 2) (+ _ 1)) 5)     ;=> 11
```

## `nest` and `nest-reverse`: substitution, not evaluation

`chain` evaluates every step as it goes. `nest` is the other thing entirely:
it substitutes **lexically** — the placeholder in each step is replaced by
the accumulated *form* — and evaluates the final form once, at the end.
Steps are unquoted lists, the last argument is the innermost value, and the
first step is usually `(quote _)` so the finished form comes back as data:

```scheme
(nest (quote _) (1 2 _ 4) 3)           ;=> (1 2 3 4)
```

`nest-reverse` is the same walk in the other direction — the first value
goes into the first step, then forward:

```scheme
(nest-reverse 3 (1 2 _ 4) (quote _))   ;=> (1 2 3 4)
```

Because substitution happens before evaluation, `nest` can build *quoted
data* and can contain special forms — the two things `chain` cannot do.

## And the project's `->` / `->>`

The prelude's `->`/`->>` (chapter [08](08-lisp-by-example.md)) remain — they
are the project's own extensions with Clojure-style semantics:

```scheme
(-> 5 inc inc (* 2))                   ;=> 14
(->> (range 5) (map inc) (filter even?))   ;=> (2 4)
```

`->` inserts the value as the *first* argument, `->>` as the *last*; `chain`
marks the position explicitly with `_` and adds the short-circuiting
siblings. Use `chain` for anything with a conditional step; the threading
macros are fine for the simple cases.

## Try it

```scheme
(display (chain '(1 2 3)
           (map (lambda (x) (* x x)) _)
           (fold + 0 _))) (newline)
(display (chain "" (string-append "foo" _) (string-append "bar" _))) (newline)
(display (chain-and 5 (* _ 2) (< _ 20))) (newline)
(display (chain-and 15 (* _ 2) (< _ 20))) (newline)
(display (chain-when 5
           (#t (* _ 10))
           (#f (+ _ 1))
           ((= 1 1) (+ _ 1)))) (newline)
(display (nest (quote _) (1 2 _ 4) 3)) (newline)
(display (nest-reverse 3 (1 2 _ 4) (quote _))) (newline)
```

```text
14
barfoo
#t
#f
51
(1 2 3 4)
(1 2 3 4)
```

## Exercises

1. **First argument, last argument.** Rewrite both `->` examples above with
   `chain`, putting `_` where the value belongs. Which spelling says more?
2. **Guard the guard.** Put `_` in a `chain-when` guard and read the error.
   Then fix the step so the *body* does the comparison the guard was meant
   to do.
3. **A validator.** Write `(valid-password s)` as a `chain-and`: non-empty,
   at least 8 characters, contains a digit. Test it on three strings and say
   which step refused each.

## The shape you copy

> A pipeline is a list of steps in run order, and `_` is the pipe between
> them. When a step must be skipped or must stop the train, that is
> `chain-when` and `chain-and` — the same railway idea as chapter
> [21](21-railway-oriented.md), written as syntax.

Next: [20 Typed control flow](20-typed-control-flow.md).

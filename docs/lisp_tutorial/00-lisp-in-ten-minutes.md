# 00 — Lisp in ten minutes

> **What this chapter teaches.** The smallest useful subset of this dialect:
> forms, names, functions, local bindings, conditionals, and lists. Everything
> later in the tutorial is built from these, and nothing here needs the
> interpreter's source.
>
> **Before this:** you can program in some language. · **Time:** ~12 min.
> **After this you can:** read and write a Lisp form, and recognise the four
> constructs every design in this repository is made of.

## A program is a list of forms

Lisp has almost no syntax. A program is text; the **reader** turns it into
values; the **evaluator** turns those values into behaviour. A *form* is one
value the evaluator knows how to run. There are only three shapes:

```scheme
42              ; a literal — evaluates to itself
name            ; a symbol — evaluates to what `name` is bound to
(+ 1 2)         ; a list — call the first thing with the rest
```

That is the whole grammar. `define`, `if`, `let`, and `lambda` are not syntax
you memorise; they are *special forms* the evaluator recognises by name, and
chapter [03](03-evaluating.md) shows you the code that recognises them.

## Name a value, make a function

`define` binds a name. `lambda` makes a function. The `(define (f x) …)`
spelling is sugar for `(define f (lambda (x) …))`:

```scheme
(define answer 42)
(define (square x) (* x x))
(define add (lambda (a b) (+ a b)))

answer          ;=> 42
(square 5)      ;=> 25
(add 2 3)       ;=> 5
```

A function's body is the last form in it; there is no `return`. Calling a
function is just another list, so `(square 5)` reads the same way as `(+ 1 2)`.

## Name a local, and loop

`let` binds names for the extent of one body. A **named** `let` is also the
language's loop — it is a function that calls itself with new arguments:

```scheme
(let ((x 2) (y 3))
  (* x y))                     ;=> 6

(let loop ((i 0) (acc '()))
  (if (= i 3)
      (reverse acc)
      (loop (+ i 1) (cons i acc))))   ;=> (0 1 2)
```

The named `let` is the idiom to learn first. Recursion whose call is in tail
position costs no stack (chapter [03](03-evaluating.md)), so this loop can run
for millions of steps.

## Choose

`if` takes two or three forms. `cond` takes clauses. Only `#f` is false;
`0`, `""`, and even the empty list `'()` are true — R7RS truthiness:

```scheme
(if (> 3 2) 'yes 'no)                 ;=> yes
(cond ((= 1 2) 'one)
      (else 'other))                  ;=> other
```

## Hold many values

A list is either `'()` or a pair. `quote` stops evaluation, so `'(a b c)` is a
list of three symbols rather than a call to `a`:

```scheme
'(a b c)                  ;=> (a b c)
(car '(a b c))            ;=> a
(cdr '(a b c))            ;=> (b c)
(cons 0 '(1 2))           ;=> (0 1 2)
(map square '(1 2 3))     ;=> (1 4 9)
```

Records in this repo are **alists** — lists of two-element lists — because they
are just lists: `'((id "demo") (mode "marathon"))`. Chapter
[09](09-lisp-by-example.md) is the longer guided session on all of this.

## Why this is enough

Four constructs carry almost everything: `define` (name a value), `lambda`
(make a function), `let` (name a local, and loop), and the list (hold many
values). Add `if`/`cond` to choose and `quote` to write data, and you can read
every example in `examples/`. The rest of the language — variants and
`variant-match`, `Result`, macros, the SRFI layer the REPL pre-imports for you
— is built from these, in Lisp, in files you can open.

## Try it

```scheme
(display (+ 1 (* 2 3))) (newline)

(define (square x) (* x x))
(display (square 5)) (newline)

(define add (lambda (a b) (+ a b)))
(display (add 2 3)) (newline)

(display (let ((x 2) (y 3)) (* x y))) (newline)
(display (if (> 3 2) 'yes 'no)) (newline)
(display (cond ((= 1 2) 'one) (else 'other))) (newline)

(display '(a b c)) (newline)
(display (map square '(1 2 3))) (newline)
(display (let loop ((i 0) (acc '()))
  (if (= i 3) (reverse acc) (loop (+ i 1) (cons i acc))))) (newline)
```

```text
7
25
5
6
yes
other
(a b c)
(1 4 9)
(0 1 2)
```

## Exercises

1. **Write the sugar out.** Rewrite `(define (cube x) (* x x x))` in the
   `(define cube (lambda …))` form. They are the same definition; the reader
   does the rewrite, not the evaluator.
2. **Loop by hand.** Write `(sum-to n)` with a named `let` that adds the
   numbers from 1 to `n` in an accumulator. `(sum-to 10)` is `55`.
3. **Truthiness.** Predict and then run `(if 0 'zero 'other)`,
   `(if "" 'empty 'other)`, and `(if '() 'nil 'other)`. All three are truthy
   — only `#f` is false, which is why a "missing" answer must be `#f` and
   never `'()`. The rule is in the evaluator, and it is not Python's.

## The shape you copy

> A Lisp is a tiny evaluator over a tiny grammar — lists, symbols, literals —
> plus a large library written in the language. Learn four constructs and you
> can read the library; learn the evaluator (chapter [03](03-evaluating.md)) and
> you can change the language.

Next: [01 The pipeline](01-the-pipeline.md).

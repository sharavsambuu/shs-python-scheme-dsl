# 10 — Railway-oriented programming

> **What this chapter teaches.** `lisp/rope.scm`: writing a fallible computation
> as a *chain* instead of a nest of checks, using the `Result` variant from
> chapter [09](09-typed-control-flow.md).
>
> **Before this:** 09. · **Time:** ~20 min.
> **After this you can:** write a fallible step as a Kleisli arrow and compose a
> pipeline that short-circuits in exactly one place.
>
> **Target note.** `Result`, `>=>`, `pipe-results`, and `result-do` stay project
> extensions. The SRFI layer adds `cut`/`cute` for steps and `chain`/`nest` for
> data flow; it does not replace the ROP vocabulary. See
> [the DSL specification](../lisp-dsl.md).

## The picture

ROP ("railway oriented programming") is a metaphor with a precise meaning:

```
   ok ──▶ [step] ──▶ ok ──▶ [step] ──▶ ok ──▶ result
             │                 │
             ▼ err             ▼ err
   err ─────────────────────────────▶ err      (short-circuited)
```

Every step returns a value that says *which rail it is on*. The chain
short-circuits: the first refusal stops the train, and every later step is simply
not run. There is no orchestrating `if`/`else` — the pipeline **is** the control
flow.

`rope.scm` opens with exactly that, and it names its two ingredients: a closed
`Result` variant, and Kleisli composition built on the single operation
`result-bind`. It also points at its twin:

> *The names line up with the classic Haskell names (`result`, `kleisli`), so
> this file reads side by side with any monad tutorial. The laws the textbooks
> pin — left identity, right identity, associativity — are pinned for this one
> too (`tests/test_rop.py`).*

## The type

```lisp
(define-variant result
  (ok value)
  (err reason))
```

`define-variant` gives `ok`, `err`, `ok-value`, `err-reason`, and `result?` for
free. The library then spells its predicates `result-ok?`/`result-err?` — while
the *game* installs its own rail tests, `success?`/`failure?`, over the domain's
`Success`/`Failure`. The two vocabularies never collide: `success?` is named for
the domain's `Success`, not for this library's `ok`.

## The functor and the monad

```lisp
;; map touches the success rail and leaves a refusal alone
(define (result-map r f)
  (if (result-ok? r) (ok (f (ok-value r))) r))

;; bind is the one primitive: run *f* only on the success rail
(define (result-bind r f)
  (if (result-ok? r) (f (ok-value r)) r))
```

`result-bind` is the whole monad. Every other operation in the file is built from
it, which means there is exactly **one place** a short-circuit can be implemented
(or got wrong).

The full set: `result-map`, `result-map-err`, `result-map2`, `result-bind`,
`result-bimap` (both rails), `result-fold` (collapse to a plain value, naming both
rails), `result-pure` (lift a plain value).

```lisp
(result-map (ok 21) (lambda (x) (* x 2)))      ;=> (ok 42)
(result-map (err "nope") (lambda (x) (* x 2))) ;=> (err "nope")
(result-bind (ok 41) (lambda (x) (ok (+ x 1)))) ;=> (ok 42)
(result-bind (err "halt") (lambda (x) (ok (+ x 1)))) ;=> (err "halt")
```

## Leaving the rails

Sometimes you must read the value back out. The library gives you a ladder of
ways, each naming what happens on a refusal:

```lisp
(result-unwrap        (ok 1))          ;=> 1
(result-unwrap        (err "e"))       ;=> error
(result-unwrap-or     (err "e") 0)     ;=> 0
(result-unwrap-or-else (err "e") (lambda (r) r))  ;=> "e"
(result-expect        (err "e") "boom");=> error "boom"
(result->list         (ok 1))          ;=> (1)
(result->list         (err "e"))       ;=> ()
```

`result-tags` returns the declared, closed tag set as data — the same
`variant-tags` you met in chapter [09](09-typed-control-flow.md).

## Kleisli composition

A *Kleisli arrow* is a function `A -> Result`. Two arrows compose left to right,
short-circuiting in between:

```lisp
(define (>=> f g)
  (lambda (x) (result-bind (f x) g)))

(define (pipe-results-list x steps)
  (foldl (lambda (step acc) (result-bind acc step)) (ok x) steps))

(define (pipe-results x . steps) (pipe-results-list x steps))
```

`pipe-results` threads a starting value through any number of arrows. The value is
lifted with `ok` first, so the first arrow sees a plain value and every later one
sees the previous success — or nobody sees anything after the first refusal:

```lisp
(pipe-results 1
  (lambda (x) (ok (+ x 1)))
  (lambda (x) (ok (* x 10)))
  (lambda (x) (ok (- x 3))))
;=> (ok 17)

((>=> parse-int with-tax) "")   ; the first arrow refuses → (err "empty")
```

## Collections of results

`sequence-results` turns a list of Results into a Result of a list — all-ok gives
every value, the *first* refusal is the whole answer. `traverse-results` maps a
fallible function and collects. And when short-circuiting is *not* what you want,
`ok-values`, `err-reasons`, `first-err`, `count-errs` read the list directly.

## `attempt`: a raising computation joins the rails

```lisp
(define (attempt thunk)
  (guard (e (#t (err e)))
    (ok (thunk))))
```

A procedure, not a macro, so it cannot capture a name in the caller's expression.
It turns any `error`/`raise` into a value on the failure rail:

```lisp
(attempt (lambda () (+ 1 1)))       ;=> (ok 2)
(attempt (lambda () (car '())))     ;=> (err #<error "car: expected a non-empty list">)
```

## Do-notation

The largest macro in the library reads like imperative code but is `result-bind`
all the way down:

```lisp
(define-syntax result-do
  (syntax-rules (<-)
    ((_ (name <- expr) rest ...)
     (result-bind expr (lambda (name) (result-do rest ...))))
    ((_ expr) expr)
    ((_) (ok (void)))))
```

```lisp
(result-do
  (a <- (ok 2))
  (b <- (ok 3))
  (_ <- (ok 'ignored))          ; _ discards a step's value
  (ok (+ a b)))
;=> (ok 5)
```

Because it is `syntax-rules`, the `name`s are the caller's and the internal
bindings are the template's, and neither can capture the other (chapter
[06](06-macros.md)).

## A host's rails

A host edition can lift its own success/failure values onto these rails, so a
*sequence of commands* can be one pipeline. That lift is a few lines of Lisp,
and it is exactly the shape you will write for your own domain:

```lisp
(define (as-result result)
  (if (host-ok? result) (ok (host-value result)) (err (host-error result))))

(define (command-arrow action)
  (lambda (state) (as-result (host-step state action))))

(define (run-commands state commands)
  (pipe-results-list state (map command-arrow commands)))
```

It is just as easy to keep a variant that reports *how far* the train got:

```lisp
(define (advance state commands)
  (let loop ((cs commands) (st state) (landed '()))
    (if (null? cs)
        (list (ok st) (reverse landed))
        (let ((r ((command-arrow (car cs)) st)))
          (if (result-err? r)
              (list r (reverse landed))
              (loop (cdr cs) (ok-value r) (cons (car cs) landed)))))))
```

You will see `(ok 17)`, `(err empty)`, and the do-notation's `(ok 5)` in the
Try-it below — the same rails doing the work a custom exception hierarchy
would, without unwinding the stack.

## Why a *library* and not built-in syntax

`Result` and `>=>` are written in Lisp, on top of `define-variant`, `match`,
`guard`, and `define-syntax`. Nothing in the interpreter knows what a monad is.
That is the test of the embedding from chapter [01](01-the-pipeline.md): the
language is generic enough that a whole error-handling idiom is a 160-line
file you can read and change.

## Try it

```sh
shs run /dev/stdin <<'EOF'
(define parse-int
  (lambda (s) (if (string=? s "") (err "empty") (ok (string-length s)))))
(define with-tax (lambda (n) (ok (+ n 10))))

(display ((>=> parse-int with-tax) "hello"))  (newline)
(display ((>=> parse-int with-tax) ""))       (newline)
(display (result-do (a <- (ok 2)) (b <- (ok 3)) (ok (* a b))))  (newline)
(display (attempt (lambda () (car '()))))     (newline)
(display (result-map-err (attempt (lambda () (car '())))
                         (lambda (e) "car of () refused")))  (newline)
EOF
```

```text
(ok 15)
(err empty)
(ok 6)
(err #<error "car: expected a non-empty list">)
(err car of () refused)
```

Display form, so the strings are unquoted. The last two lines are the same
failure — a caught `car` of `()` — once raw, once with its message rewritten by
`result-map-err`.

## Exercises

1. **The answer key.** Write three Kleisli arrows that parse, validate, and
   rename a string, and confirm an early `(err …)` skips the rest, and that
   `(result-bind (ok x) f)` equals `(f x)`. A worked file ships at
   `exercises/rename-pipeline.scm`.
2. **One short-circuit.** Grep `lisp/rope.scm` for where the pipeline stops.
   Count the places that decide "this is a failure, stop". The chapter's claim
   is that there is exactly one.
3. **Lift a domain.** Write `as-result` (the lift from the "host's rails"
   section) for a domain of your choosing — say, a Python function that
   returns a `(value, error)` pair — and explain why an error becomes an
   `(err …)` value on a rail rather than a raised condition. (Note that the
   language's own rail predicate is `result-ok?`; a host's may be anything,
   which is exactly why the lift is a *host* decision.)

## The shape you copy

> Model "it failed" as a *value on a rail*, compose your steps as arrows, and
> implement short-circuiting exactly once. The control flow disappears into the
> pipeline, and a refusal is data you can inspect instead of an exception you must
> remember to catch.

Next: [21 Embedding in Python](21-embedding-in-python.md).

# 26 — Functional core, imperative shell

> **What this chapter teaches.** The architecture pattern this whole project
> embodies: a pure decision-making core that answers with *data*, wrapped in a
> thin imperative shell that owns every effect — and how to build one
> deliberately, so the impurity is countable.
>
> **Before this:** 23–25 (purity, closures as modules, aggregates over events).
> · **Time:** ~15 min.
> **After this you can:** name which half of your program is the core and which
> is the shell, and prove the split by counting the shell's impure arms.

The pattern has a name — Gary Bernhardt's — and a one-line contract:

> **Decisions without effects; effects without decisions.** The core answers
> *what should happen* as plain data; the shell is the only code that makes
> anything actually happen.

Everything before this chapter was building to this. Chapter
[23](23-functional-foundations.md) named purity and quarantine; chapter
[24](24-fp-design-patterns.md) put mutation behind closure walls; chapter
[25](25-bounded-contexts.md) reduced aggregate state to a fold over events.
Functional core, imperative shell is the *architectural name* for what all
three were doing: the core is the pure part, the shell is the quarantine
boundary, and the wall between them is made of data.

## The language already is one

You have been reading this pattern since chapter [01](01-the-pipeline.md)
without the label:

- **The core:** the reader, the trampoline evaluator, the primitive floor —
  all pure functions of their arguments. `shslisp/builtins.py` states the claim
  as an architecture (chapter [04](04-primitives.md)): everything is pure
  *except a short, named list of host holes* — `display`, `error`, `eval`,
  `read-from-string`, `load`.
- **The shell:** the REPL and the file runner. They are the only code that
  prints, reads files, and catches conditions — and they are *thin*: chapter
  [01](01-the-pipeline.md) puts the whole machine at about five thousand
  lines, and the shell part of it is a fraction.

Chapter [28](28-embedding-in-python.md) adds the third piece, the host seam:
`install_primitives` is the door where *your* project's effects enter, as a
declared list. A host edition of this language is a functional core (the Lisp
program) inside an imperative shell (the Python host), and the seam is the
wall.

The rest of this chapter builds the same shape *in Lisp*, for a domain — so
you can see both halves in one file.

## The core: decisions that answer with data

A small checkout. The core owns the *rules* — what may be added, what a
checkout owes — and owns nothing else. Two disciplines make it a core:

**Facts enter as arguments.** The price list is not fetched from a database
mid-decision; it is a value the core can see, passed in or bound beside it.
A core that *fetches* is a core with a hidden shell.

```scheme
(define prices '((w-42 199) (k-9 599)))
(define (total cart)
  (fold (lambda (line acc)
          (+ acc (* (cadr line) (alist-ref prices (car line)))))
        0
        cart))
```

**Effects are described, not performed.** The commands and the effects are
variants — chapter [25](25-bounded-contexts.md)'s events, pointed the other
way: events record what *did* happen, effects describe what *should*:

```scheme
(define-variant command (add-item sku qty) (checkout))
(define-variant effect (charge cents) (log entry))
```

And the decision function is pure in the strict chapter-15 sense —
substitution test passing, refusals as `Result` values (chapter
[22](22-railway-oriented.md)), new state returned instead of mutated:

```scheme
(define (decide cart command)
  (variant-match command
    ((add-item sku qty)
     (if (or (<= qty 0) (not (alist-has? prices sku)))
         (err "unknown sku or bad quantity")
         (ok (list (cons (list sku qty) cart)
                   (list (log (list 'added sku qty)))))))
    ((checkout)
     (if (null? cart)
         (err "nothing to check out")
         (ok (list '()
                   (list (charge (total cart)) (log 'sold))))))))
```

Read what `decide` answers: `(ok (new-cart effects))` — the new state *and*
the list of things that should happen, as data. A refusal is data too. This
is the whole trick of the pattern: **the decision is inspectable.** You can
`display` it, diff it, test it with `equal?`, replay it — before anyone has
charged anything:

```scheme
(decide '() (add-item 'w-42 2))
;=> (ok (((w-42 2)) ((log (added w-42 2)))))
(decide '() (checkout))
;=> (err nothing to check out)
```

## The shell: every effect has exactly one door

The shell is two small functions. First, the interpreter for effect data —
the *only* place in the program that touches the world:

```scheme
(define (perform! effect)
  (variant-match effect
    ((charge cents) (display "charging ") (display cents) (newline))
    ((log entry)    (display "logging ") (display entry) (newline))))
```

Second, the driver: decide, then perform, then hand the new state back. Note
what it does *not* do — it makes no decisions. A refused command performs
nothing and leaves the cart alone; the shell's refusals are the core's
refusals, printed:

```scheme
(define (run! command cart)
  (variant-match (decide cart command)
    ((err reason) (begin (display "refused: ") (display reason) (newline) cart))
    ((ok (new-cart effects))
     (begin (for-each perform! effects) new-cart))))
```

The session loop is the shell's last privilege, and the only `set!` in the
program lives here — at the top, holding the state between commands, exactly
where chapter 22 said mutation belongs:

```scheme
(define cart '())
(set! cart (run! (add-item 'w-42 2) cart))
(set! cart (run! (add-item 'k-9 1) cart))
(set! cart (run! (add-item 'ghost 1) cart))   ; refused: unknown sku...
(set! cart (run! (add-item 'w-42 0) cart))    ; refused: unknown sku...
(set! cart (run! (checkout) cart))            ; charging 997, logging sold
```

The audit of impurity is the pattern's proof, and here it is short: two
`display` arms in `perform!`, one in `run!`'s refusal branch, one session
`set!`. Four places, all in two shell functions, all reachable by eye. A
program whose effects you cannot count is a program whose effects you cannot
trust.

## What the split buys

**The core is testable with no mocks.** A mock exists to fake the world a
test cannot reach; the core never reaches the world, so its tests are
`equal?` over returned data — the fastest, most honest tests there are. The
two `decide` lines above *are* the test suite.

**The shell is replaceable.** Swap `perform!`'s arms for chapter
[25](25-bounded-contexts.md)'s repository and the effect log is persisted;
swap them for a Python seam call (chapter [28](28-embedding-in-python.md))
and the effects cross the host boundary. Neither change touches a line of
`decide` — which is the point.

**The shape generalizes.** Chapter [24](24-fp-design-patterns.md)'s bind
showed `pipe-results` and `append-map` as the same "continue in the shape"
idea. Effects-as-data is the same family: a list of effect descriptions is a
container, `for-each perform!` is its interpreter, and if you squint you can
see why the theory calls this shape a *free monad* — you do not need the
theory, you need the one `variant-match` that performs.

## Plan the whole session, then perform it

Because `decide` is pure, the shell does not have to interleave deciding and
performing at all. It can *plan the entire session first* — one fold, no
effects — and then perform the resulting log. The planning fold threads
`(cart effects)` as its accumulator and appends a plain `(refused reason)`
entry for every refusal, so the plan records failures too:

```scheme
(define (session commands cart)
  (fold (lambda (cmd st)
          (let ((c (car st)) (fx (cadr st)))
            (variant-match (decide c cmd)
              ((err reason) (list c (append fx (list (list 'refused reason)))))
              ((ok (new-cart e2)) (list new-cart (append fx e2))))))
        (list cart '())
        commands))
```

Run it over the same session and inspect the outcome *before anything
happens*: the final cart is `()`, and the effect log is a complete,
ordered record of what the session will do —

```scheme
((log (added w-42 2))
 (refused unknown sku or bad quantity)
 (log (added k-9 1))
 (charge 997)
 (log sold))
```

The shell's whole job shrinks to interpreting one list — with `tagged?`
(chapter [21](21-typed-control-flow.md)) telling the two entry kinds apart:

```scheme
(for-each (lambda (e)
            (if (tagged? e)
                (perform! e)
                (begin (display "refused: ") (display (cadr e)) (newline))))
          (cadr outcome))
```

This is the pattern's endgame, and it is worth pausing on. *Planning* is
pure, replayable, testable with `equal?` — and it is where every interesting
decision lives. *Performing* is a fixed interpreter over a value that already
exists, which makes it auditable after the fact: the log you executed is the
log you can print. Chapter [25](25-bounded-contexts.md)'s event sourcing and
this chapter's effect log are the same list seen from two sides — one records
what the domain decided, the other what the shell will do about it.

## Try it

```scheme
;; --- the core: decisions only, facts enter as arguments --------------------
(define prices '((w-42 199) (k-9 599)))
(define (total cart)
  (fold (lambda (line acc)
          (+ acc (* (cadr line) (alist-ref prices (car line)))))
        0
        cart))
(define-variant command (add-item sku qty) (checkout))
(define-variant effect (charge cents) (log entry))
(define (decide cart command)
  (variant-match command
    ((add-item sku qty)
     (if (or (<= qty 0) (not (alist-has? prices sku)))
         (err "unknown sku or bad quantity")
         (ok (list (cons (list sku qty) cart)
                   (list (log (list 'added sku qty)))))))
    ((checkout)
     (if (null? cart)
         (err "nothing to check out")
         (ok (list '()
                   (list (charge (total cart)) (log 'sold))))))))
;; the core answers with data — a decision you can read, not a side effect
(display (decide '() (add-item 'w-42 2))) (newline)
(display (decide '() (checkout))) (newline)
;; --- the shell: the only impurity, and it is countable ---------------------
(define (perform! effect)
  (variant-match effect
    ((charge cents) (display "charging ") (display cents) (newline))
    ((log entry)    (display "logging ") (display entry) (newline))))
(define (run! command cart)
  (variant-match (decide cart command)
    ((err reason) (begin (display "refused: ") (display reason) (newline) cart))
    ((ok (new-cart effects))
     (begin (for-each perform! effects) new-cart))))
(define cart '())
(set! cart (run! (add-item 'w-42 2) cart))
(set! cart (run! (add-item 'k-9 1) cart))
(set! cart (run! (add-item 'ghost 1) cart))
(set! cart (run! (add-item 'w-42 0) cart))
(set! cart (run! (checkout) cart))
(display cart) (newline)
;; plan the whole session purely, then perform the log
(define (session commands cart)
  (fold (lambda (cmd st)
          (let ((c (car st)) (fx (cadr st)))
            (variant-match (decide c cmd)
              ((err reason) (list c (append fx (list (list 'refused reason)))))
              ((ok (new-cart e2)) (list new-cart (append fx e2))))))
        (list cart '())
        commands))
(define outcome
  (session (list (add-item 'w-42 2) (add-item 'ghost 1) (add-item 'k-9 1) (checkout)) '()))
(display (car outcome)) (newline)
(display (cadr outcome)) (newline)
(for-each (lambda (e)
            (if (tagged? e)
                (perform! e)
                (begin (display "refused: ") (display (cadr e)) (newline))))
          (cadr outcome))
```

```text
(ok (((w-42 2)) ((log (added w-42 2)))))
(err nothing to check out)
logging (added w-42 2)
logging (added k-9 1)
refused: unknown sku or bad quantity
refused: unknown sku or bad quantity
charging 997
logging sold
()
()
((log (added w-42 2)) (refused unknown sku or bad quantity) (log (added k-9 1)) (charge 997) (log sold))
logging (added w-42 2)
refused: unknown sku or bad quantity
logging (added k-9 1)
charging 997
logging sold
```

(Notice the order of the transcript: the two core decisions print first —
*before* any effect runs, because deciding and performing are separate
activities. The final cart is `()` because checkout consumed it; the session
kept the state the core handed back.)

## Exercises

1. **New command, zero shell changes.** Add `(remove-item sku)` to the
   `command` variant and handle it in `decide` — including a refusal when the
   sku is not in the cart. Count the lines of `perform!` and `run!` you
   changed. That number is the test of whether the boundary is in the right
   place.
2. **A second shell.** Write `perform-quietly!` that appends effects to a
   list instead of displaying, run the same session with it, and `display`
   the collected effect log. Same core, different shell — confirm no
   decision moved.
3. **The audit.** List every impure call in the whole program (`display`,
   `newline`, the session `set!`) with the function it lives in. Then move
   one decision — say, "free shipping over 500" — into `decide` as a
   `(notify ...)` effect and check the audit count did not grow outside the
   shell.

## The shape you copy

> The core answers *what should happen* as data — new state plus described
> effects, refusals included — and never fetches, prints, or mutates. The
> shell decides nothing and owns every effect behind one interpreter, with
> the session's `set!` at the top. If you can count the shell's impure arms
> on one hand, the core is testable without mocks and the shell is
> replaceable without fear.

Next: [27 The gala: one checkout, eight ideas](27-the-gala-checkout.md).

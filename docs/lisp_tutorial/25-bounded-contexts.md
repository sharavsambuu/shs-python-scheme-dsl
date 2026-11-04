# 25 — Bounded contexts: DDD in this Lisp

> **What this chapter teaches.** Domain-driven design, mapped onto the
> structures you already own: the ubiquitous language as `define-variant`,
> value objects and entities as the two equalities from chapter
> [14](14-records-variants-and-objects.md), aggregates as folds over events,
> the context map as one named translation, and the repository as chapter
> [24](24-fp-design-patterns.md)'s closure-with-a-protocol.
>
> **Before this:** 14 and 23; chapter [08](08-modules.md) for modules and
> [21](21-typed-control-flow.md) for `variant-match`. · **Time:** ~15 min.
> **After this you can:** draw a context map over a real domain and implement
> every arrow in it with something this language already has.

Domain-driven design sounds like an enterprise-Java subject, but its core
claims are oddly at home in a small Lisp. The two that matter here:

1. **The model and the code are the same thing.** A language where the domain's
   words can be *defined* — not just named in comments — makes the ubiquitous
   language literal.
2. **A context owns its vocabulary.** Two parts of a system may both say
   "order" and mean different things; the design's job is to make the boundary
   and the translation explicit.

This codebase has been doing the second all along: the Tetris edition's
`success?`/`failure?` are named for the *domain's* `Success`/`Failure` and
never collide with the library's `ok`/`err` (chapter
[22](22-railway-oriented.md)). That naming discipline is a context map in
miniature. This chapter builds the full pattern.

## Value objects and entities: the two equalities

The DDD distinction is exactly chapter [14](14-records-variants-and-objects.md)'s
distinction, so the language makes it a *choice you make*, not an accident:

- A **value object** — money, an address, a date range — is defined by its
  contents. Two ten-dollar amounts are the same amount. Build it as plain
  data, and `equal?` does the domain's job for free.
- An **entity** — an order, a user, a game piece — is defined by its identity.
  Two orders with the same lines are still two orders. Build it as a record,
  which compares by identity, and carry the id as the field that *means*
  identity.

```scheme
(define (money amount currency) (list 'money amount currency))
(equal? (money 10 'usd) (money 10 'usd))    ;=> #t — value object
(define-record-type order (make-order id lines) order?
  (id order-id)
  (lines order-lines))
(eq? (make-order 1 '()) (make-order 1 '())) ;=> #f — entities by identity
```

The test is the DDD question asked directly: *if every field matched, would
these be the same thing?* Data answers yes, records answer no, and both are
one line apart.

## Events: the ubiquitous language, declared

A bounded context's vocabulary is most visible in what *happened* there. Each
context declares its own events — its own words — with `define-variant`
(chapter [21](21-typed-control-flow.md)):

```scheme
;; the catalog context
(define-variant catalog-event (price-set sku cents) (sku-renamed sku name))
;; the ordering context — a different word for the same money
(define-variant order-event (order-placed id lines) (order-cancelled id why))
```

Note the deliberate mismatch: the catalog counts **cents**, ordering speaks of
**lines**. That is not sloppiness; that is two contexts. A tagged event prints
and reads as plain data — `((order-placed 1 ((w-42 2))) ...)` is a *history*
you can display, diff, and store, because events are values.

## The context map: one named translation

Where two vocabularies meet, DDD asks for the meeting to be *one place*. Here
that place is a function — and because the events are variants, `variant-match`
is the translation table:

```scheme
(define (catalog->ordering ev)
  (variant-match ev
    ((price-set sku cents) (list 'line sku cents))
    (else #f)))                        ; this context does not care about renames
```

`catalog->ordering` is the context map in code: catalog events enter the
ordering world *only* through it, reshaped into ordering's words
(`(line w-42 199)`), and anything the ordering context does not consume is
answered `#f` — explicitly, at the boundary, not by silent drift. When the
foreign vocabulary is a *host's* — Python objects crossing into the domain —
the same discipline scales up to the seam itself: chapter
[28](28-embedding-in-python.md)'s `install_primitives` is the anti-corruption
layer, the one door where outside facts are translated into domain words
before anything downstream can see them.

## The aggregate: state is a fold over events

An aggregate is a consistency boundary: a rule-enforcing lump of state. The FP
answer (chapters [23](23-functional-foundations.md)–[24](24-fp-design-patterns.md))
is that state is not a thing you mutate — it is the *reduction of history*:

```scheme
(define (apply-order-event ev state)
  (variant-match ev
    ((order-placed id lines)
     (if (null? lines)
         (error "an order needs at least one line")
         (cons (list id lines) state)))
    ((order-cancelled id why)
     (filter (lambda (o) (not (equal? (car o) id))) state))))
```

Read the signature against `fold`'s contract from chapter 22: `(f elt acc)` —
this function *is* a fold reducer, which makes the aggregate one line:

```scheme
(define orders (fold apply-order-event '() events))
```

The invariant lives at the transition, and it refuses in domain words —
`an order needs at least one line` — which is the ubiquitous language doing
double duty as the error message. A cancellation is not a mutation either; it
is a *transition* that filters the state, so cancelling never forgets why
(`why` is on the event, and the event is in the log).

And event sourcing — usually a framework — is here just the observation that
rebuilding is the same fold:

```scheme
(equal? orders (fold apply-order-event '() events))   ;=> #t
```

Same history, same state, always — because state *is* the history reduced.

## The repository: a closure with a protocol

The repository's DDD job is to make "where the aggregate lives" someone else's
problem. Chapter [24](24-fp-design-patterns.md)'s module pattern does it
exactly — private state, a small message protocol, behavior at the wall:

```scheme
(define (make-repo)
  (let ((state '()))
    (lambda (msg . args)
      (case msg
        ((handle) (set! state (apply-order-event (car args) state)))
        ((find)   (find (lambda (o) (equal? (car o) (car args))) state))
        ((count)  (length state))))))
```

The mutation is real and it is *quarantined*: callers say `handle`, `find`,
`count` — domain verbs — and cannot touch `state` from outside. Swap the
`let` binding for a host-backed table (a Python seam primitive, chapter
[28](28-embedding-in-python.md)) and no caller changes. That swap-ability is
the entire promise of a repository, and here it is one `let` wide.

## Contexts as files

In a script the two contexts above are sections; in a program they are
*modules*. Chapter [08](08-modules.md)'s file model is the boundary: the
catalog context is a file that defines `catalog-event` and its reducer and
nothing of ordering's; the ordering file defines its own; the translation
lives in a third, or in whichever file loads last. The load order then forces
the design conversation DDD wants you to have — a context that needs another
context's words has to *say so* by loading it, and the dependency arrow
becomes visible in the load list. `SHS_PATH` (chapter [28](28-embedding-in-python.md))
is how contexts in different projects find each other.

## Projections: questions answered without state

The event log is not just for rebuilding — it is queryable *directly*, with
chapter 22's tools. A count by tag, a fold that reads the fields:

```scheme
(count (lambda (ev) (eq? (tag-of ev) 'order-placed)) events)   ;=> 2
(fold (lambda (ev acc)
        (variant-match ev
          ((order-placed id lines) (+ acc (length lines)))
          (_ acc)))
      0
      events)                                                   ;=> 2
```

`tag-of` (chapter [21](21-typed-control-flow.md)'s raw layer) classifies an
event without knowing its variant; the fold's `_` arm makes "everything else
contributes nothing" explicit. These are *read models* in DDD's vocabulary —
answers shaped for a caller, derived from the one history, never stored as a
second truth to drift out of sync.

## Policies: the cross-context rules

Some rules touch two contexts — "place an order only for skus the catalog
knows." That rule belongs to *neither* aggregate; it is a **policy**: a pure
function that reads one context and produces another's command, with
`Result` (chapter [22](22-railway-oriented.md)) carrying the refusal:

```scheme
(define catalog '((w-42 199) (k-9 599)))
(define (place-order lines)
  (if (every (lambda (l) (alist-has? catalog (car l))) lines)
      (ok (order-placed 9 lines))
      (err "unknown sku")))

(place-order '((w-42 1)))   ;=> (ok (order-placed 9 ((w-42 1))))
(place-order '((nope 1)))   ;=> (err unknown sku)
```

Because the policy is pure, testing it is `equal?` on the two answers — no
mocked repository, no test double. And because the policy *returns* the
event rather than applying it, the decision stays inspectable: the fold that
owns the aggregate decides whether to accept it.

## A third context, and the shape holds

The translation table generalizes without strain — ordering's events become
billing's invoices through one more function, and events the new context
ignores are answered `#f` at the boundary:

```scheme
(define (order->billing ev)
  (variant-match ev
    ((order-placed id lines) (list 'invoice id (length lines)))
    (_ #f)))

(order->billing (order-placed 2 '((k-9 1))))    ;=> (invoice 2 1)
(order->billing (order-cancelled 1 "x"))        ;=> #f
```

Three contexts now share one history: catalog emits, ordering aggregates,
billing projects. No context imports another's internals — only the
translation functions know two vocabularies, and they are the only places a
change must be checked when one context renames a word.

## Try it

```scheme
;; value objects compare by value; entities by identity
(define (money amount currency) (list 'money amount currency))
(display (equal? (money 10 'usd) (money 10 'usd))) (newline)
(define-record-type order (make-order id lines) order?
  (id order-id)
  (lines order-lines))
(display (eq? (make-order 1 '()) (make-order 1 '()))) (newline)
(display (order-id (make-order 7 '()))) (newline)
;; the catalog context: its own vocabulary of events
(define-variant catalog-event (price-set sku cents) (sku-renamed sku name))
;; the ordering context: a different word for the same money
(define-variant order-event (order-placed id lines) (order-cancelled id why))
;; the context map: the one place the two vocabularies meet
(define (catalog->ordering ev)
  (variant-match ev
    ((price-set sku cents) (list 'line sku cents))
    (else #f)))
(display (catalog->ordering (price-set 'w-42 199))) (newline)
;; the aggregate: fold events into state, invariants enforced at the fold
(define (apply-order-event ev state)
  (variant-match ev
    ((order-placed id lines)
     (if (null? lines)
         (error "an order needs at least one line")
         (cons (list id lines) state)))
    ((order-cancelled id why)
     (filter (lambda (o) (not (equal? (car o) id))) state))))
(define events
  (list (order-placed 1 '((w-42 2)))
        (order-placed 2 '((k-9 1)))
        (order-cancelled 1 "duplicate")))
(display events) (newline)
(define orders (fold apply-order-event '() events))
(display orders) (newline)
;; same history, same state — event sourcing is the same fold again
(display (equal? orders (fold apply-order-event '() events))) (newline)
;; the invariant refuses, loudly, in domain words
(display (guard (e (#t 'refused))
           (fold apply-order-event '() (list (order-placed 3 '())))))
(newline)
;; the repository: a closure with a message protocol
(define (make-repo)
  (let ((state '()))
    (lambda (msg . args)
      (case msg
        ((handle) (set! state (apply-order-event (car args) state)))
        ((find) (find (lambda (o) (equal? (car o) (car args))) state))
        ((count) (length state))))))
(define repo (make-repo))
(for-each (lambda (ev) (repo 'handle ev)) events)
(display (repo 'count)) (newline)
(display (repo 'find 2)) (newline)
;; projections and policies
(display (count (lambda (ev) (eq? (tag-of ev) 'order-placed)) events)) (newline)
(define catalog '((w-42 199) (k-9 599)))
(define (place-order lines)
  (if (every (lambda (l) (alist-has? catalog (car l))) lines)
      (ok (order-placed 9 lines))
      (err "unknown sku")))
(display (place-order '((nope 1)))) (newline)
(define (order->billing ev)
  (variant-match ev
    ((order-placed id lines) (list 'invoice id (length lines)))
    (_ #f)))
(display (order->billing (order-placed 2 '((k-9 1))))) (newline)
```

```text
#t
#f
7
(line w-42 199)
((order-placed 1 ((w-42 2))) (order-placed 2 ((k-9 1))) (order-cancelled 1 duplicate))
((2 ((k-9 1))))
#t
refused
1
(2 ((k-9 1)))
2
(err unknown sku)
(invoice 2 1)
```

## Exercises

1. **A third word.** Add `(line-removed id sku)` to `order-event` and a new
   invariant — a line's quantity must be positive — then watch the refusal
   name the rule. Where did you have to put the check, and why is "at the
   transition" the only place it cannot be bypassed?
2. **Two files, one map.** Split the script into `catalog.scm`,
   `ordering.scm`, and a loader that translates and folds. What does the load
   list now say about your dependencies that the single script hid?
3. **The cross-context policy.** "Place an order only for skus the catalog
   knows" touches two contexts. Write it as a function that translates, asks,
   and returns a `Result` (chapter [22](22-railway-oriented.md)) — and
   explain why this is a *policy* (a pure function over both contexts) rather
   than a constraint buried in one aggregate.

## The shape you copy

> A bounded context is a file that owns its words; the ubiquitous language is
> `define-variant` plus the names of its refusals; entities carry identity,
> value objects carry contents, and the equality you chose is the design
> decision; an aggregate is a fold over its events with the invariants at the
> transitions; every crossing between contexts is one named translation; and
> the repository is the only place that knows where the state sleeps.

Next: [26 Functional core, imperative shell](26-functional-core-imperative-shell.md).


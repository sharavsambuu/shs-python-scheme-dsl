# 26 — The gala: one checkout, eight ideas

> **What this chapter teaches.** Everything from chapters
> [20](20-typed-control-flow.md)–[25](25-functional-core-imperative-shell.md)
> in one program: typed control flow, pattern matching, contracts, functional
> programming, monadic pipelines, railway-oriented programming, bounded
> contexts, and the functional core / imperative shell split — arranged
> around a single case study, the checkout pipeline.
>
> **Before this:** 21 and 22–25 (the ideas arrive pre-loaded; this chapter is
> where they meet). · **Time:** ~20 min.
> **After this you can:** read an architecture from its shape, and build one
> of your own by placing each idea where it belongs.

## The case study

A checkout. Raw cart lines go in; a receipt — or a precise, structured
refusal — comes out:

```text
raw lines
  ──> [line contracts]      ──> UnvalidatedOrder survives
  ──> [stock check]         ──> ValidatedOrder
  ──> [coupon applied]      ──> ValidatedOrder (with a discount)
  ──> [priced + postcondition] ──> PricedOrder
  ──> [payment verdict]     ──> PaidOrder + receipt
```

Each stage is fallible, each failure has a *name* the domain owns, and the
happy path never mentions failure at all. The chapter is built in two halves:
the **before** — the same checkout written the way a tired controller method
writes it — and the **after** — the architecture, in seven stations.

## The before: five sins in twenty lines

```scheme
(define (checkout-bad lines coupon)
  (let ((total 0)
        (rate (if (assoc coupon coupon-table) (cadr (assoc coupon coupon-table)) 0)))
    (for-each
      (lambda (l)
        (let ((price (alist-ref catalog (car l))))
          (if price
              (set! total (+ total (* (cadr l) price))))))   ; sin 3: a miss is silently skipped
      lines)
    (set! total (- total (quotient (* total rate) 100)))     ; sin 4: mutation mid-calculation
    (if (>= total 0) (list 'receipt total) #f)))             ; sin 5: failure as #f
```

Count the sins: (1) **a silent default** — an unknown coupon becomes a 0%
discount, and the customer never learns their code was bad; (2) **zero
quantities accepted** — nothing refuses `(w-42 0)`; (3) **unknown skus
silently skipped** — the order succeeds *without* the item; (4) **mutation
mid-calculation** — `total` is a moving target no test can pin; (5)
**failure as `#f`** — indistinguishable, to the caller, from any receipt.
The smoking gun, verified:

```scheme
(checkout-bad '((ghost 1)) "nope")   ;=> (receipt 0)
```

The store just sold a product it does not carry, for zero cents, and called
it a receipt. Every sin below has a named cure.

## Station 1 — typed control flow: illegal states unrepresentable

The lifecycle is a closed variant (chapter
[20](20-typed-control-flow.md)) where *each stage is its own tag* — and the
later stages carry the data only that stage has earned:

```scheme
(define-variant order-state
  (unvalidated id lines)
  (validated id lines discount)
  (priced id lines total)
  (paid id lines total receipt))
```

A `priced` order cannot exist without a total, and a `paid` order cannot
exist without a receipt — not because a comment says so, but because there is
no way to construct one. This is DDD's "make illegal states unrepresentable"
(chapter [24](24-bounded-contexts.md)), and the state machine *is* the type:
you cannot ask for the total of an unvalidated order, because unvalidated
orders do not have that slot.

## Station 2 — contracts: named invariants at the boundaries

A **contract** is a predicate with a name and a verdict on the rails
(chapter [21](21-railway-oriented.md)):

```scheme
(define (contract name pred)
  (lambda (v) (if (pred v) (ok v) (err (list 'contract-violated name v)))))

((contract "quantity-positive" (lambda (n) (> n 0))) 5)   ;=> (ok 5)
((contract "quantity-positive" (lambda (n) (> n 0))) -1)
;=> (err (contract-violated quantity-positive -1))
```

Contracts compose through `check-all` — a fold that runs each and keeps the
first violation:

```scheme
(define (check-all cs v)
  (fold (lambda (c r) (if (result-ok? r) (c (ok-value r)) r)) (ok v) cs))

(define line-contracts
  (list (contract "lines-not-empty" (lambda (ls) (not (null? ls))))
        (contract "quantities-positive" (lambda (ls) (every (lambda (l) (> (cadr l) 0)) ls)))))
```

Two vocabularies matter here. **Preconditions** run at a boundary's entrance
(the line contracts above). **Postconditions** run at its exit, and the
pricing stage checks one — the total may never go negative, whatever the
discount:

```scheme
(define (postcondition total)
  ((contract "total-non-negative" (lambda (n) (>= n 0))) total))
```

> **A dialect note.** Some Schemes allow curried definitions —
> `(define ((contract name pred) value) …)`. This dialect does not: write the
> plain two-step `define` and `lambda` above, or you will meet an
> `unexpected )` from the reader.

Where do contracts end and types begin? The variant *shapes* the data (a
priced order has a total slot); the contract *constrains* its values (the
total is non-negative). Shape is the definer's job, constraint is the
boundary's — and neither needs a type system to enforce.

## Station 3 — the pipeline: the type progression *is* the flow

The stage arrows are pure functions between the stage types — each arrow's
input tag and output tag are different, so the pipeline's shape *is* the
lifecycle diagram (chapters [22](22-functional-foundations.md) and
[21](21-railway-oriented.md)):

```scheme
(define (checkout coupon verdict order)
  (pipe-results order
                validate-lines      ; unvalidated  -> validated (contracts ran)
                check-stock         ; validated    -> validated (or refused)
                (apply-coupon coupon) ; validated  -> validated + discount
                price               ; validated    -> priced (postcondition ran)
                (pay verdict)))     ; priced       -> paid (or declined)
```

`pipe-results` (chapter [21](21-railway-oriented.md)) is the monadic
pipeline: green track advances stage by stage; the first refusal bypasses
everything and comes back tagged. Note where `coupon` and `verdict` enter —
as *arguments* to arrow builders, not as globals the core reads. That is
chapter [25](25-functional-core-imperative-shell.md)'s rule: facts enter as
arguments, and the payment gateway's verdict is a fact the shell supplies.

## Station 4 — pattern matching: failures are data with names

The failure side of the rails is *typed* too — a closed variant of named
refusals, so an error can carry its own evidence (chapter
[20](20-typed-control-flow.md)):

```scheme
(define-variant failure
  (bad-lines id) (out-of-stock sku) (bad-coupon code) (payment-declined code))
```

And the shell's whole job is one exhaustive match from domain outcomes to
the outside world's shapes — HTTP-style envelopes, since this shell fronts a
service:

```scheme
(define (respond result)
  (variant-match result
    ((ok o) (variant-match o
              ((paid id lines total receipt) (list 200 receipt))
              (else (list 500 'impossible))))
    ((err f) (variant-match f
               ((bad-lines id)          (list 400 (list 'bad-lines id)))
               ((out-of-stock sku)      (list 409 (list 'out-of-stock sku)))
               ((bad-coupon code)       (list 400 (list 'bad-coupon code)))
               ((payment-declined code) (list 402 (list 'payment-declined code)))))
    (else (list 500 'no-clause))))
```

Read the two `else`s — they are documentation. The inner one means "the
pipeline promised only `paid` orders succeed; if that ever changes, this
arm is where you find out." The outer one means "the failure vocabulary is
closed; a new refusal must be matched here *on the day it is declared*, or
the shell answers 500 loudly." The before-version's silent `(receipt 0)`
has become a structured, testable `(409 (out-of-stock ghost))`.

## Station 5 — bounded contexts: billing sees only invoices

The ordering context's `paid` order is *its* word. Billing receives its own
shape through one translation (chapter [24](24-bounded-contexts.md)) — and
notice billing never learns about lines, discounts, or the coupon system:

```scheme
(define (order->billing result)
  (variant-match result
    ((ok o) (variant-match o
              ((paid id lines total receipt) (ok (list 'invoice id total)))
              (else (err 'no-invoice))))
    ((err f) (err f))))

(order->billing (checkout "SAVE10" #t (unvalidated 1 '((w-42 2) (k-9 1)))))
;=> (ok (invoice 1 898))
```

Three vocabularies now cooperate — catalog (skus and cents), ordering (the
lifecycle), billing (invoices) — and only the translation knows two of them.

## Station 6 — the functional core, tested by property

Everything from station 1 to 5 is pure: same inputs, same answer, no
witness. Which makes the interesting test a *property*, not an example —
"whatever the quantity, a paid order's total is never negative" — swept over
many inputs with `every` (chapter [22](22-functional-foundations.md)):

```scheme
(define (all-paid? quantities)
  (every (lambda (qty)
           (variant-match (checkout "SAVE10" #t (unvalidated 9 (list (list 'w-42 qty))))
             ((ok o) (variant-match o ((paid id lines total receipt) (>= total 0)) (else #f)))
             ((err f) #f)))
         quantities))

(all-paid? '(1 2 3 4 5))   ;=> #t
(all-paid? '(0 1))         ;=> #f — the quantity contract refused, correctly
```

No mocks: the pipeline never touches the world, so the test is `equal?`-and-
predicates over returned data. And notice what the second sweep *proves*: a
quantity of zero does not slip through to the property — the contract
catches it at the boundary, exactly where chapter 24 placed invariants.

## Station 7 — the audit

The imperative shell is: `respond`, one `display` per envelope line if this
fronted a real service, and the session machinery from chapter
[25](25-functional-core-imperative-shell.md) (plan the whole checkout with
the `session` fold, then perform the effect log). Count the impure arms:
they fit on one hand, they are all in shell functions, and none of them is
inside a decision. The proof the boundary is in the right place is the
same one as chapter 25's: add a stage — say, gift-wrap, one more arrow —
and count the shell lines you changed. Zero.

And the test that keeps the contracts honest: delete one from
`line-contracts`, run the property sweep, and watch `(all-paid? '(0 1))`
flip from `#f` to... whatever the unguarded pipeline does. A contract you
cannot feel removing was never load-bearing.

## Try it

```scheme
;; ============================================================ the shared facts
(define catalog '((w-42 199) (k-9 599)))
(define coupon-table '(("SAVE10" 10) ("HALF" 50)))
;; ============================================================ THE BEFORE
(define (checkout-bad lines coupon)
  (let ((total 0)
        (rate (if (assoc coupon coupon-table) (cadr (assoc coupon coupon-table)) 0)))
    (for-each
      (lambda (l)
        (let ((price (alist-ref catalog (car l))))
          (if price
              (set! total (+ total (* (cadr l) price))))))   ; a miss is silently skipped
      lines)
    (set! total (- total (quotient (* total rate) 100)))     ; a bad coupon was silently 0
    (if (>= total 0) (list 'receipt total) #f)))             ; and zero-quantity is fine?!
(display (checkout-bad '((w-42 2) (k-9 1)) "SAVE10")) (newline)
(display (checkout-bad '((ghost 1)) "nope")) (newline)
(display (checkout-bad '((w-42 0)) "SAVE10")) (newline)
;; ============================================================ THE AFTER
;; ---- the typed lifecycle: each stage is its own tag ----
(define-variant order-state
  (unvalidated id lines)
  (validated id lines discount)
  (priced id lines total)
  (paid id lines total receipt))
;; ---- the failure vocabulary: tagged data, not strings ----
(define-variant failure
  (bad-lines id) (out-of-stock sku) (bad-coupon code) (payment-declined code))
;; ---- contracts: named predicates at the boundaries ----
(define (contract name pred)
  (lambda (v) (if (pred v) (ok v) (err (list 'contract-violated name v)))))
(define (check-all cs v)
  (fold (lambda (c r) (if (result-ok? r) (c (ok-value r)) r)) (ok v) cs))
(define line-contracts
  (list (contract "lines-not-empty" (lambda (ls) (not (null? ls))))
        (contract "quantities-positive" (lambda (ls) (every (lambda (l) (> (cadr l) 0)) ls)))))
(define (postcondition total)
  ((contract "total-non-negative" (lambda (n) (>= n 0))) total))
;; ---- the stage arrows: the type progression IS the pipeline ----
(define (validate-lines ord)
  (variant-match ord
    ((unvalidated id lines)
     (variant-match (check-all line-contracts lines)
       ((ok _) (ok (validated id lines 0)))
       ((err e) (err (bad-lines id)))))))
(define (check-stock ord)
  (variant-match ord
    ((validated id lines discount)
     (let ((unknown (find (lambda (l) (not (alist-has? catalog (car l)))) lines)))
       (if unknown (err (out-of-stock (car unknown))) (ok ord))))))
(define (apply-coupon code)
  (lambda (ord)
    (variant-match ord
      ((validated id lines discount)
       (let ((rate (alist-ref coupon-table code)))
         (if rate (ok (validated id lines rate)) (err (bad-coupon code))))))))
(define (price ord)
  (variant-match ord
    ((validated id lines discount)
     (let* ((subtotal (fold (lambda (l acc) (+ acc (* (cadr l) (alist-ref catalog (car l)))))
                            0 lines))
            (total (- subtotal (quotient (* subtotal discount) 100))))
       (variant-match (postcondition total)
         ((ok _) (ok (priced id lines total)))
         ((err e) (err e)))))))
(define (pay verdict)
  (lambda (ord)
    (variant-match ord
      ((priced id lines total)
       (if verdict
           (ok (paid id lines total (list 'receipt id total)))
           (err (payment-declined 'card-declined)))))))
;; ---- the pipeline ----
(define (checkout coupon verdict order)
  (pipe-results order validate-lines check-stock (apply-coupon coupon) price (pay verdict)))
;; ---- the shell: match the outcome to an HTTP-style envelope ----
(define (respond result)
  (variant-match result
    ((ok o) (variant-match o
              ((paid id lines total receipt) (list 200 receipt))
              (else (list 500 'impossible))))
    ((err f) (variant-match f
               ((bad-lines id)          (list 400 (list 'bad-lines id)))
               ((out-of-stock sku)      (list 409 (list 'out-of-stock sku)))
               ((bad-coupon code)       (list 400 (list 'bad-coupon code)))
               ((payment-declined code) (list 402 (list 'payment-declined code)))))
    (else (list 500 'no-clause))))
;; ---- the gala runs ----
(display (checkout "SAVE10" #t (unvalidated 1 '((w-42 2) (k-9 1))))) (newline)
(display (checkout "nope"  #t (unvalidated 2 '((w-42 1))))) (newline)
(display (checkout "SAVE10" #t (unvalidated 3 '((ghost 1))))) (newline)
(display (checkout "SAVE10" #f (unvalidated 4 '((w-42 2))))) (newline)
(display (respond (checkout "SAVE10" #t (unvalidated 1 '((w-42 2) (k-9 1)))))) (newline)
(display (respond (checkout "SAVE10" #t (unvalidated 3 '((ghost 1)))))) (newline)
(display (respond (checkout "SAVE10" #f (unvalidated 4 '((w-42 2)))))) (newline)
;; ---- the billing context: one translation, no shared words ----
(define (order->billing result)
  (variant-match result
    ((ok o) (variant-match o
              ((paid id lines total receipt) (ok (list 'invoice id total)))
              (else (err 'no-invoice))))
    ((err f) (err f))))
(display (order->billing (checkout "SAVE10" #t (unvalidated 1 '((w-42 2) (k-9 1)))))) (newline)
;; ---- the property sweep: postconditions over many inputs ----
(define (all-paid? quantities)
  (every (lambda (qty)
           (variant-match (checkout "SAVE10" #t (unvalidated 9 (list (list 'w-42 qty))))
             ((ok o) (variant-match o ((paid id lines total receipt) (>= total 0)) (else #f)))
             ((err f) #f)))
         quantities))
(display (all-paid? '(1 2 3 4 5))) (newline)
(display (all-paid? '(0 1))) (newline)
```

```text
(receipt 898)
(receipt 0)
(receipt 0)
(ok (paid 1 ((w-42 2) (k-9 1)) 898 (receipt 1 898)))
(err (bad-coupon nope))
(err (out-of-stock ghost))
(err (payment-declined card-declined))
(200 (receipt 1 898))
(409 (out-of-stock ghost))
(402 (payment-declined card-declined))
(ok (invoice 1 898))
#t
#f
```

Read the transcript against the before: the same three orders that produced
`(receipt 898)` twice and a phantom `(receipt 0)` now produce a paid order,
a *named* bad-coupon refusal, a *named* out-of-stock refusal, and a
*declined* payment — every one carrying its evidence.

## Exercises

1. **Gift-wrap.** Add a `(wrap-gift note)` stage between `price` and `pay`:
   a contract on the note's length plus a flat 500-cent surcharge on the
   total. Count the shell lines you changed, and re-run the property sweep —
   the postcondition should still hold for every quantity.
2. **The sixth sin.** The before-version also prints nothing: it *returns*.
   Write `respond-bad` that maps `checkout-bad`'s outcomes to envelopes and
   show that it cannot — `#f` and `(receipt 0)` are indistinguishable
   evidence. Then state in one sentence which station cures this and how.
3. **Coupon stacking.** Let `apply-coupon` compose two coupons by taking a
   list of codes and folding the rates — refusing on the first unknown code.
   The postcondition must still hold; find the coupon combination that comes
   closest to breaking it.
4. **A fourth context.** Shipping needs `(shipment id address)` for every
   *paid* order. Write `order->shipping`, and explain why it is allowed to
   ignore every failure arm.

## The shape you copy

> Declare the stages as types, so an illegal state has no constructor; hang
> named contracts on every boundary's entrance and exit; make the pipeline
> the type progression, with facts entering as arguments; give failures a
> closed, evidence-carrying vocabulary; translate between contexts at one
> named place; keep every effect in a shell you can count; and test the core
> by property, not by example. Eight ideas, one program — each doing the one
> job it is best at.

Next: [27 Embedding in Python](27-embedding-in-python.md).

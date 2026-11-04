# 13 — Modeling data: records, variants, and closures

> **What this chapter teaches.** The three ways to be a "custom class" here:
> `define-record-type` for named shapes, `define-variant` for closed sets of
> cases, and a closure over private state when the object is *behaviour*. Each
> is a different answer to "what does this value know?"
>
> **Before this:** 12; chapter [20](20-typed-control-flow.md) for `variant-match`.
> · **Time:** ~15 min.
> **After this you can:** model a domain object the way the shipped libraries
> do — and defend the choice between record, variant, and closure.

## Records: the dataclass

`define-record-type` is R7RS's `@dataclass`: one form declares the constructor,
the predicate, and every field's accessor — and every constructor field must
have its clause (omit one and the definer refuses: `constructor names
undeclared field y`):

```scheme
(define-record-type point (make-point x y) point?
  (x p-x set-p-x!)        ; the third name, when present, is the setter
  (y p-y))
```

That one line defines `make-point`, `point?`, `p-x`, `set-p-x!`, and `p-y`:

```scheme
(define p (make-point 1 2))
(list (p-x p) (p-y p))   ;=> (1 2)
(set-p-x! p 9)           ; fields with a setter mutate in place
(p-x p)                  ;=> 9
(point? "alice")         ;=> #f
```

Two Python differences to internalise:

- **Accessors refuse the wrong type** — `(p-x 5)` is an error, not `None` and
  not a crash one stack deeper. The refusal is the dataclass-with-types
  promise, enforced.
- **Records compare by identity.** Two points made equal are not `equal?`:
  R7RS allows this, and the interpreter takes the allowance (`shslisp/types.py`
  documents it). Structural equality is yours to define — usually by
  converting to data: `(equal? (list (p-x a) (p-y a)) (list (p-x b) (p-y b)))`,
  or by keeping the fields in an alist/hash table instead when equality is the
  point (chapter [12](12-dictionaries-alists-and-hash-tables.md)).

A record prints as its contents — `#<record:point 1 2>` — so it is inspectable,
but it has no reader syntax: you cannot `read` one back.

## Variants: the closed set of cases

Where Python reaches for a class hierarchy — `Circle` and `Rect`, both
subclasses of `Shape` — this language declares the *whole set* in one form:

```scheme
(define-variant shape (circle r) (rect w h))
```

`circle` and `rect` are constructors; `shape?` is the predicate;
`variant-tags` reports the closed set:

```scheme
(circle 3)               ;=> (circle 3) — prints as its tagged data
(variant-tags 'shape)    ;=> (circle rect)
```

Dispatch is `variant-match` — chapter [20](20-typed-control-flow.md) teaches
the full pattern grammar, and its central promise is worth repeating: with no
matching clause and no `else`, the error *names the cases you forgot*. That is
the thing a class hierarchy with a base-class default cannot do for you.

A tagged value keys a hash table like any other value (chapter 12), and it
prints and reads as plain data — `(circle 3)` round-trips through `write` and
`read` in a way a record cannot.

## Closures: behaviour with private state

The third "class" is not a type at all. A closure over a `let` is an object
whose fields nobody can touch except through its methods — Python's name-
mangling ambition, achieved by scope:

```scheme
(define (make-counter)
  (let ((n 0))
    (lambda (msg)
      (case msg
        ((inc) (set! n (+ n 1)) n)
        ((get) n)
        (else (error "unknown message" msg))))))
```

`n` is the private field; `inc` and `get` are the methods; the `else` refuses
unknown messages loudly instead of returning `None`. Every call of
`(make-counter)` is a new object with its own `n`.

## Choosing between the three

| You are modeling | Reach for |
| --- | --- |
| A named shape with fixed fields — a row, a config, a point | `define-record-type` |
| A closed set of alternatives, dispatched by case — AST nodes, results, game events | `define-variant` (+ `variant-match`) |
| A thing that *does* something over time — counters, connections, state machines | a closure |
| Open-ended keyed data, or data that must compare by value | alist / hash table (chapter [12](12-dictionaries-alists-and-hash-tables.md)) |

The shipped code follows this table: `shslisp/rope.scm` declares `Result` as a
variant (chapter [21](21-railway-oriented.md)), the prelude builds promises on
vectors (data that mutates in exactly one slot), and the memoiser is a closure
over a hash table — all three, each where it fits.

## Defaults over the constructor

Records take every field, every time — and that is *right* for a data
carrier, but callers should not pay for it. SRFI 89's `define*` (chapter
[17](17-srfi-89-optional-and-named-parameters.md)) wraps the constructor with
defaults, and the pattern is one line:

```scheme
(define-record-type user (make-user name age admin?) user?
  (name user-name) (age user-age) (admin? user-admin?))
(define* (new-user name (age: a 0) (admin: admin #f))
  (make-user name a admin))

(user-age (new-user "ada"))                  ;=> 0
(user-admin? (new-user "bob" age: 41 admin: #t))  ;=> #t
```

Callers now say what they mean — `(new-user "ada")` for the common case,
keyword arguments for the rest — while the record itself stays a plain,
total constructor. The keyword in the *definition* (`admin:`) must match the
keyword at the *call site* exactly; SRFI 89 refuses a near-miss loudly.

## Records are ordinary procedures

`make-user`, `user-name`, `user-admin?` — every name the definer created is
a first-class procedure, so the list tools work on records the way they work
on anything:

```scheme
(map user-name (list (new-user "a") (new-user "b")))  ;=> (a b)
```

That is the quiet payoff of chapter 13's model: there is no method table, no
`__dict__` — a record is its accessors, and its accessors are values.

## Identity bites in hash tables too

Chapter [12](12-dictionaries-alists-and-hash-tables.md) taught that table
keys compare structurally. Records are the exception that proves the rule —
they compare by identity, so two same-content records are *different keys*:

```scheme
(hash-table-set! h (make-user "ada" 0 #f) 'first)
(hash-table-has-key? h (make-user "ada" 0 #f))          ;=> #f
(hash-table-ref/default h (make-user "ada" 0 #f) 'missing)  ;=> missing
```

Not a bug — the DDD entity rule (chapter [24](24-bounded-contexts.md)) doing
its job. The fix when you want lookup-by-value is the same one the domain
uses: key by the *id field*, not the record —
`(hash-table-set! h (user-name u) u)` — and let the name be the identity.

## Nesting composes

Records hold variants, variants hold records, and one `variant-match` takes
the whole tower apart in a single pattern:

```scheme
(define-variant maybe-user (found u) (absent))

(variant-match (found (new-user "ada" age: 30))
  ((found u) (user-name u))
  ((absent) "nobody"))
;=> ada
```

The pattern binds `u` straight into a record, and the accessor reads it —
no intermediate unpacking. This is the normal shape of a modeled domain:
chapter [24](24-bounded-contexts.md)'s aggregates are exactly this, one level
deeper.

## Try it

```scheme
;; a record: the dataclass
(define-record-type point (make-point x y) point?
  (x p-x set-p-x!)
  (y p-y))
(define p (make-point 1 2))
(display (list (p-x p) (p-y p))) (newline)
(set-p-x! p 9)
(display (list (p-x p) (p-y p))) (newline)
;; records compare by identity, not field by field
(define q (make-point 1 2))
(display (eq? p q)) (newline)
(display (equal? p q)) (newline)
;; an accessor refuses the wrong type
(display (guard (e (#t 'refused)) (p-x 5))) (newline)
;; a variant: the closed set of cases
(define-variant shape (circle r) (rect w h))
(define h2 (make-hash-table))
(hash-table-set! h2 (circle 3) 'round)
(display (hash-table-ref h2 (circle 3))) (newline)
(display (variant-tags 'shape)) (newline)
;; a closure: behavior with private state
(define (make-counter)
  (let ((n 0))
    (lambda (msg)
      (case msg
        ((inc) (set! n (+ n 1)) n)
        ((get) n)
        (else (error "unknown message" msg))))))
(define c (make-counter))
(c 'inc) (c 'inc) (c 'inc)
(display (c 'get)) (newline)
(display (guard (e (#t 'badmsg)) (c 'boom))) (newline)
;; defaults over the constructor
(define-record-type user (make-user name age admin?) user?
  (name user-name) (age user-age) (admin? user-admin?))
(define* (new-user name (age: a 0) (admin: admin #f)) (make-user name a admin))
(display (user-age (new-user "ada"))) (newline)
(display (user-admin? (new-user "bob" age: 41 admin: #t))) (newline)
(display (map user-name (list (new-user "a") (new-user "b")))) (newline)
;; identity bites in hash tables too
(define h3 (make-hash-table))
(hash-table-set! h3 (make-user "ada" 0 #f) 'first)
(display (hash-table-has-key? h3 (make-user "ada" 0 #f))) (newline)
(display (hash-table-ref/default h3 (make-user "ada" 0 #f) 'missing)) (newline)
;; nesting composes
(define-variant maybe-user (found u) (absent))
(display (variant-match (found (new-user "ada" age: 30))
          ((found u) (user-name u))
          ((absent) "nobody")))
(newline)
```

```text
(1 2)
(9 2)
#f
#f
refused
round
(circle rect)
3
badmsg
0
#t
(a b)
#f
missing
ada
```

## Exercises

1. **Structural equality, by hand.** Write `(point-equal? a b)` for the
   `point` record. Then make the point's *fields* live in a single alist and
   observe that `equal?` starts working for free. Which modelling would you
   keep for a config object? For a game piece?
2. **Two objects, one closure.** Make two counters with `make-counter`,
   increment one twice and the other once, and confirm their states are
   independent. Then explain in one sentence why `(make-counter)` returning
   `n` directly would break the whole point of the pattern.
3. **The refusal ladder.** Add a `rect` arm to the `shape` variant, write
   `(area s)` with `variant-match`, and call it on `(circle 3)`. Now call
   `area` on `5` and read the error — it names the declared cases. Compare
   with what Python's `isinstance` chain does when you forget a branch.

## The shape you copy

> Data that *is* a shape gets a record; data that is *one of a closed set* gets
> a variant; a thing whose essence is *doing* gets a closure; and anything that
> must compare by value stays plain — alist, hash table, list. Model with all
> four, refuse none of them, and let the accessor's refusal do the type
> checking you would have written tests for.

Next: [14 SRFI 241 — match](14-srfi-241-match.md).

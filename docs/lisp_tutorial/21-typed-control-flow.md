# 21 — Typed control flow: `define-variant` and `match`

> **What this chapter teaches.** How to declare a *closed set* and dispatch on it
> so the compiler (well, the interpreter) refuses to guess when you have forgotten
> a case. This is one of the four pillars the whole project is built on.
>
> **Before this:** 09. · **Time:** ~15 min.
> **After this you can:** declare a closed set and write a `match` that refuses
> to guess.
>
> **Target note.** SRFI 241 is the standard `match` now (S6), and this
> chapter's tag-dispatch matcher is spelled `variant-match` — which is what the
> code below uses. See [the DSL specification](../lisp-dsl.md).

## The problem with `cond`

A `cond` that falls through returns `()`. That is a *silent* default: if the
value is a shape you did not anticipate, you get "nothing" and no hint that you
missed something. For a program — especially a game where a refusal is a real
outcome — that silence is the bug.

The fix is to make the set of possibilities a *declared, closed thing*, and to
make the dispatcher **name the cases you forgot**.

## Declaring a variant

`define-variant` declares a closed union of tagged cases in one form:

```scheme
(define-variant outcome
  (win  score)
  (lose reason))
```

From that single declaration it defines:

- the **constructors** `win` and `lose` (a procedure of exactly the named fields);
- the **accessors** `win-score` and `lose-reason`, each of which *refuses a value
  on the wrong tag*;
- the **predicate** `outcome?`.

It also records the tags so `match` can report them. `evaluator.py` says why the
registry is global:

> *The registry is global (like the edge's closed screen set) because a tag's
> meaning is not lexical: `result?` must answer the same way in any scope.*

```scheme
(display (win 42))                 ;=> (win 42)
(display (win-score (win 42)))     ;=> 42
(display (outcome? (win 1)))       ;=> #t
(display (variant-tags 'outcome))  ;=> (win lose)
```

A tagged value views as `(tag . fields)` — see the `tag-of`/`tag-fields`
primitives, and note that a *list* of the same shape matches the same patterns.

## Matching, and refusing to guess

`match` tries each clause in order; the first whose pattern matches wins:

```scheme
(define (describe o)
  (variant-match o
    ((win s)  (string-append "you win, score " (number->string s)))
    ((lose r) (string-append "you lose: " r))
    (else     "not an outcome")))

(describe (win 42))        ;=> "you win, score 42"
(describe (lose "busted")) ;=> "you lose: busted"
(describe 5)               ;=> "not an outcome"
```

`_step_match`'s docstring lists the pattern kinds precisely:

> * `_` — matches anything, binds nothing;
> * a bare symbol — matches anything, binds it;
> * a literal (number, string, character, `#t`/`#f`/`()`) or a quoted datum `'x`
>   — matches by `equal?`;
> * `(tag p ...)` — a **tag pattern** when `tag` is a symbol the program declared
>   with `define-variant`: the head is read as the tag (not a binder) and the
>   fields are matched by the sub-patterns, so `(ok v)` reads the tag `ok` and
>   binds its field. `('ok v)` spells the same thing with an explicit quote,
>   which also works for an undeclared tag;
> * `(p1 ... pn)` or `(p1 ... . rest)` — any other list pattern. It reads a
>   value's *cells*: a `Tagged` views as `(tag . fields)`, so a list of the same
>   shape matches the same pattern.

And the crucial part — **no matching clause and no `else` is an error that names
the possibilities**:

```scheme
> (variant-match (win 1) (('lose r) r))
error: match: no clause matched (win 1); this outcome is one of win lose
```

(The REPL echoes a failure as `error: …`; the file runner prints the same
message as `shs: …`.)

That message is the whole point. Compare it to a `cond` that returns `()`: here
you are told the value, that nothing matched, and exactly which cases exist. `else`
is the *explicit* catch-all — when you write it, you have made a decision; when
you omit it, you have made the interpreter check for you.

## Why `else` must be last

`_step_match` enforces it:

```python
if clause[0] is ELSE:
    if index != len(clauses) - 1:
        raise LispSyntaxError("match: else must be the last clause")
    return _match_body(clause[1:], None)
```

An `else` in the middle would silently swallow the clauses after it; refusing is
the same discipline as refusing a fall-through.

## `case` vs `match`

`case` is the older, simpler dispatcher: it compares a value against literal
datum lists with `eqv?`-style equality and does not destructure.

```scheme
(case 2
  ((1) (display "one"))
  ((2) (display "two"))
  (else (display "other")))      ;=> two
```

Reach for `case` when you are dispatching on a symbol or small integer and want
no binding; reach for `match` when there is a *shape* to take apart (a tag with
fields, a list of fixed length, a refusal record).

## Where you meet this in the language

- `shslisp/rope.scm` declares the `Result` variant: `(define-variant result (ok value) (err reason))`
  (chapter [22](22-railway-oriented.md)) — two rails, and no arm that swallows a
  third kind of value by accident.
- A host edition declares its own variants the same way, and matches *by name*
  with no wildcard, so "a new rail would fall off the end rather than be silently
  floored to `()`".

The *discipline* is the one to copy: closed set, named arms, no silent default.

## The pattern grammar, exercised

The docstring above lists the pattern kinds; here is each one doing real work,
because reading them in a list and choosing them under pressure are different
skills.

**Literal patterns** pin an exact value — the arm fires only for that one
datum. This is how you give a common case its own fast arm before the general
one:

```scheme
(define-variant drawing (poly points) (circle r))

(variant-match (circle 2)
  ((circle 2) 'unit)          ; the literal radius 2, not a binder
  ((circle r) (list 'r r)))   ; every other circle
;=> unit
```

The order matters, and the order *means* something: a literal arm before a
binding arm is a special case, the same move a Python `match` makes with
`case 2:` before `case x:`. With the value `(circle 3)` the first arm does not
match, and the second binds `r` to `3`.

**Fall-through binding arms** — the same shape, more general — are how one
`variant-match` reports "and everything else of this tag":

```scheme
(variant-match (step 'west 2)
  ((step 'north d) (list 'due-north d))
  ((step dir d)    (list 'other dir d))
  ((turn dir)      dir))
;=> (other west 2)
```

**Nested list patterns** destructure a field *inside* the tag in one shot —
no intermediate `let`:

```scheme
(variant-match (poly (list 1 2 3))
  ((poly (a b c)) (list 'triangle a b c))
  ((poly pts)     (list 'many (length pts))))
;=> (triangle 1 2 3)
```

A field that holds exactly three points takes the first arm and binds all
three; any other count falls to `pts`. The nest can go as deep as the data.

**Plain lists match the same list patterns.** A tagged value views as
`(tag . fields)`, so a bare list is just a tag with no name — and the same
grammar takes it apart:

```scheme
(variant-match (list 1 2 3) ((a b c) (+ a b c)))   ;=> 6
```

That is why chapter [22](22-railway-oriented.md) can pattern-match `Result`
values and chapter [25](25-bounded-contexts.md) can match event variants with
the same syntax — one matcher, one grammar, any tagged shape.

## The raw layer under the sugar

`define-variant` is sugar over three primitives you can use directly —
useful for probing, logging, and writing generic code that does not know
which variant it holds:

```scheme
(tag-of (circle 1))        ;=> circle — the tag as a symbol
(tag-fields (rect 3 4))    ;=> (3 4)  — the fields as a list
(tagged? 'nope)            ;=> #f
(tag 'mystery 1 2)         ;=> (mystery 1 2) — a tag no variant declared
(variant-of 'circle)       ;=> shape — which variant declared this tag
```

`tag` builds a tagged value with *no* declaration — handy for ad-hoc marks
in tests, and worth using sparingly in a domain, precisely because
`variant-tags` will not know it. The generic-code idiom is `(tag-of ev)`:
chapter [25](25-bounded-contexts.md) uses it to sort a mixed event log by
which context produced it.

## Try it

```scheme
(define-variant shape
  (circle radius)
  (rect   w h))

(define (area s)
  (variant-match s
    ((circle r) (* 3.14 r r))
    ((rect w h) (* w h))
    (else (error "not a shape" s))))

(display (area (circle 2)))  (newline)
(display (area (rect 3 4)))  (newline)
(display (variant-tags 'shape))  (newline)

;; and the refusal, caught so we can print it:
(display (guard (e (#t (error-object-message e)))
           (variant-match (circle 1) (('rect w h) w))))
(newline)
;; literals, fall-through arms, plain lists, and the raw layer
(display (variant-match (circle 2) ((circle 2) 'unit) ((circle r) (list 'r r)) (else 'other))) (newline)
(display (variant-match (rect 3 4) ((rect w h) (* w h)) (else 'other))) (newline)
(display (variant-match (list 1 2 3) ((a b c) (+ a b c)))) (newline)
(display (tag-of (circle 1))) (newline)
(display (tag-fields (rect 3 4))) (newline)
(display (tagged? 'nope)) (newline)
(display (variant-of 'circle)) (newline)
```

```text
12.56
12
(circle rect)
match: no clause matched (circle 1); this shape is one of circle rect
unit
12
6
circle
(3 4)
#f
shape
```

## Exercises

1. **The answer key.** Add a `triangle base height` case to the variant and to
   `area`, then delete the `else` and read the error the interpreter gives you
   for a shape you did not handle. A worked file ships at
   `exercises/shapes.scm`.
2. **Count the arms.** `match` checks that a pattern list is *closed* only when
   you write a binding pattern; `(circle 1)` refused above because neither arm
   matched. Which arm would you add to make the refusal impossible, and what
   does adding it cost you in the exhaustiveness guarantee?
3. **Against the Python side.** Python has its own structural `match`
   (chapter [28](28-embedding-in-python.md) crosses the languages). Write one
   Python `match` for the same shapes chapter 20's Lisp examples use, and
   compare what each refuses.

## The shape you copy

> Declare the set, dispatch on the set, and *fail loudly* on the value that is
> not in it. A closed set plus a named refusal is how you get exhaustiveness
> without a compiler to enforce it.

Next: [22 Railway-oriented programming](22-railway-oriented.md).

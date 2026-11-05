# 19 — Generators: lazy sequences

> **What this chapter teaches.** The prelude's generator library: a generator
> is an ordinary procedure of zero arguments that answers the next value, and
> the eof-object when the values run out. Constructors over
> lists, vectors, and ranges — including *infinite* ones; the lazy
> combinators `gmap`, `gfilter`, `gtake`, `gdrop`; and the drains
> `generator->list`, `generator-fold`, `generator-for-each`.
>
> **Before this:** 05 (the standard library), 08. · **Time:** ~20 min.
> **After this you can:** walk data you never want to hold all at once, and
> say precisely why the library needed no interpreter change.

## The protocol: a procedure and the eof-object

A **generator** is any procedure of zero arguments that follows one convention:

- each call answers the **next value** of a sequence;
- when the values are gone, it answers **the eof-object** — the same object
  `(eof-object)` builds and `read` answers at an empty input, checked with
  **`eof-object?`**.

That is the whole protocol. A generator is not a type — `(procedure? (generator
1))` is `#t`, and there is nothing else to it. Exhaustion is idempotent: call
an exhausted generator again and it answers the eof-object again, so a
consumer cannot fall off the end by over-reading.

> **History, for the record.** S9 originally used a custom `generator-end`
> pair as the sentinel; S12 — the SRFI 158 audit — aligned the protocol on
> the eof-object, the standard's spelling. The old object still exists and
> every library procedure still accepts it, so pre-S12 code keeps running;
> new code should check `eof-object?`.

## Constructors

```scheme
(generator 1 2 3)                       ; the values themselves
(list->generator '(a b c))              ; a list, left to right
(vector->generator (vector 7 8))        ; a vector, left to right
(make-range-generator 0 5)              ; 0 1 2 3 4
(make-range-generator 0 10 3)           ; 0 3 6 9
(make-range-generator 5)                ; 0 1 2 3 ... — infinite
(make-cycle-generator '(hit miss))      ; hit miss hit miss ... — infinite
```

The two infinite generators are the point of the whole design: an unbounded
sequence costs nothing until someone pulls from it, and pulling is an ordinary
function call. The empty list cycles to *nothing* — it ends immediately rather
than looping forever.

## Combinators are lazy

`gmap`, `gfilter`, `gtake`, and `gdrop` all answer **generators**, so they
compose into pipelines that do no work until drained:

```scheme
(define odds (gfilter odd? (make-range-generator 0)))   ; no work yet
(generator->list (gtake odds 5))                        ;=> (1 3 5 7 9)
```

`gmap` over several generators pulls one value from each and stops at the
first exhaustion — the same rule SRFI 1's `map` follows, made lazy.
`gdrop` skips its `k` values once, on the first pull, then passes everything
through unchanged.

## Draining

Three procedures consume a generator for real:

- `(generator->list gen)` — all the values; with a `k`, at most `k` of them;
- `(generator-fold f acc gen)` — a left fold, like `fold` over the values;
- `(generator-for-each proc gen ...)` — run `proc` on each value, stop at the
  first exhaustion.

The idiomatic shape for unbounded data is a drain of a *slice*:
`(generator-fold + 0 (gtake (make-range-generator 1) 5))` is `15`, and the
other infinitely many values were never computed.

## The SRFI 158 claim

Since S12 this library **is** `(srfi 158)`: the export list was audited name
by name against the final specification (the combinators, the multi-generator
drains, the searching half, and the accumulators — `sum-accumulator` and
friends). Two coroutine-shaped constructors, `make-coroutine-generator` and
`make-for-each-generator`, fail loudly: suspending a body mid-computation
needs re-entrant continuations, which this dialect deliberately does not have
(chapter [07](07-code-is-data.md) and `docs/r7rs.md` record the
limit). The deviations are in `docs/srfi.md`; the ledger entry is S12 in
`docs/SRFI_TASKS.md`.

## Try it

```scheme
(display (generator->list (generator 1 2 3))) (newline)
(display (generator->list (gtake (gfilter odd? (make-range-generator 0)) 5))) (newline)
(display (generator->list (gtake (make-cycle-generator '(hit miss)) 6))) (newline)
(display (generator->list (gtake (gdrop (make-range-generator 0) 3) 4))) (newline)
(display (generator->list (gmap + (generator 1 2) (generator 10 20 30)))) (newline)
(display (generator-fold + 0 (gtake (make-range-generator 1) 5))) (newline)
(define g (generator 'a 'b))
(g) (g)
(display (eof-object? (g))) (newline)
```

```text
(1 2 3)
(1 3 5 7 9)
(hit miss hit miss hit miss)
(3 4 5 6)
(11 22)
15
#t
```

## Exercises

1. **Squares, lazily.** Define `squares` as a generator over the infinite
   squares 1, 4, 9, ... using `gmap` and `make-range-generator`, and drain its
   first six values. Then do it again with `gtake ... 3` composed on the front
   — what does `gdrop` over *that* answer first?
2. **A finite window.** Write `(window gen i k)` that answers the list of
   `k` values starting at index `i` of `gen` — with `gdrop` and `gtake`, in
   one line, and without draining the whole generator.
3. **Protocol honesty.** `(define (my-gen) 42)` answers 42 forever. Is it a
   generator? Which library procedure hangs on it, and which finishes? (The
   step budget is the backstop either way — chapter [03](03-evaluating.md).)

## The shape you copy

> A generator is a closure holding "what is left", and every combinator is
> another closure over that. Laziness is not a language feature here — it is
> what first-class procedures were always for.

Next: [20 SRFI 197 — chain and nest](20-srfi-197-chain-and-nest.md).
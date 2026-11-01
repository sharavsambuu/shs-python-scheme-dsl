# 05 — The standard library, in Lisp

> **What this chapter teaches.** `lisp/prelude.scm`: what "adding a feature to
> the language" looks like when the language can define its own features. Every
> name here is ordinary Lisp you could have typed at the REPL.
>
> **Before this:** 04. · **Time:** ~15 min.
> **After this you can:** read the prelude as ordinary Lisp, and add a library
> function without touching Python.

> **Target note.** The DSL specification moves several of these names onto the
> SRFI layer: `reduce` gets SRFI 1 semantics, `partition`/`span` return
> multiple values, and `->`/`->>` remain extensions alongside SRFI 197
> `chain`/`nest`. S8 has landed: the default DSL profile pre-imports the SRFI
> libraries (with `map`/`for-each` renamed), so the prelude's `fold = foldl`
> and `reduce = foldl` aliases below are *replaced* in the default
> environment by SRFI 1's `fold` and `reduce` — `fold` keeps the same
> `(f elt acc)` argument order, `reduce` gets SRFI 1's semantics. This
> chapter teaches the prelude itself, which both profiles share. See
> [the DSL specification](../lisp-dsl.md).

`prelude.scm` says why it exists:

> *Everything here is ordinary Lisp you could have typed at the REPL — no Python,
> no host hooks. That is the point: once a language has `lambda`, `let`,
> `define`, and macros, this file is what "adding features" looks like. Read it
> as the first worked example of the language, and as the place to experiment:
> change a definition here and it is reloaded with every environment.*

Crucially, it is loaded by `runtime.make_env`, so if you edit this file, every
REPL session and every `shs run` picks it up. It is the cheapest place to experiment with
the language.

## The tour

**Small combinators.** `identity`, `inc`, `dec`, `const`, then the four
higher-order workhorses:

```lisp
(define (compose . fs)                       ; right-to-left; (compose f g) = f∘g
  (cond ((null? fs) identity)
        ((null? (cdr fs)) (car fs))
        (else (let ((outer (car fs))
                    (inner (apply compose (cdr fs))))
                (lambda args (outer (apply inner args)))))))
```

`pipe` is the same pipeline read left-to-right (`(pipe f g h)` is `(compose h g f)`).
`flip` reverses a procedure's arguments, `complement` negates a predicate,
`partial` binds leading arguments, and `curry` binds one argument per call (it
needs an arity; pass it for a host primitive, e.g. `(curry + 3)`).

**List access sugar.** `first rest second caar cadr caddr cadddr last last-pair
list-head`. These exist so a line reads like the shape it manipulates.

**Association lists — the record shape.** An alist is a list of `(key value)`
pairs, and it is *the* record in this language. `assoc` (a primitive) finds an
entry; the prelude's readers are the friendly spelling:

```lisp
(define (alist-ref alist key)
  (let ((entry (assoc key alist)))
    (if entry (cadr entry) #f)))             ; a miss is #f, which is false
```

`alist-has?` and `alist-set` round it out. You met alists already — `design-meta`,
`mode-options`, `active-piece`, a turn's events, and a refusal are all alists.
`alist-ref` returning `#f` on a miss is why Lisp's "no" and "false"
unify, and why an absent field reads as a decision.

**Repetition.** `repeat`/`times` are named-let loops. There is no `for`; a named
`let` *is* the loop:

```lisp
(define (repeat n thunk)
  (let loop ((i 0))
    (if (>= i n) '() (begin (thunk) (loop (+ i 1))))))
```

**Macros.** `while`, `++`, `--` are `defmacro` (the raw kind); `push!`, `pop!`,
`do`, `dotimes`, `->`, `->>` are `define-syntax`/`syntax-rules` (the hygienic
kind). Chapter [06](06-macros.md) takes these apart; for now notice that the
threading macros are *only* a way to write nested calls in the order the data
flows, and cost nothing at run time:

```lisp
(define-syntax ->
  (syntax-rules ()
    ((_ x) x)
    ((_ x (f arg ...) more ...) (-> (f x arg ...) more ...))
    ((_ x f more ...) (-> (f x) more ...))))
```

**List algorithms.** `take drop take-while drop-while span partition any every
count find find-index delete remove zip append-map sum product iota iterate
distinct map-index enumerate filter-map flat-map flatten`, plus predicates
`even? odd? zero? positive? negative?`. The prelude also defines `fold = foldl`
and `reduce = foldl` — but under the default profile SRFI 1's `fold` and
`reduce` are pre-imported in their place (same fold argument order, SRFI 1
`reduce` semantics), so prefer the SRFI 1 names in new code.

**By a key.** `sort-by max-by min-by group-by`:

```lisp
(define (sort-by key less xs)
  (sort xs (lambda (a b) (less (key a) (key b)))))
```

`group-by` returns an alist of `(key (elements …))` — each entry's value is
*the list of elements* with that key — in first-seen order, so `alist-ref` reads
it (returning that list) and the order is the input's, not a hash table's.

**Strings.** `string-prefix? string-suffix? string-index`, on top of the
primitives. And `hash-table-for-each`.

**Memoisation.** The one piece of performance machinery in the library:

```lisp
(define (memoize f)
  (let ((cache (make-hash-table)))
    (lambda args
      (if (hash-table-has-key? cache args)
          (hash-table-ref cache args)
          (let ((value (apply f args)))
            (hash-table-set! cache args value)
            value)))))
```

Hashing is structural (`hash_key` in `types.py`), so a procedure of several
arguments — or of lists — is memoised by *value*, and a closure with a private
cache is a one-liner.

## Why these and not others

The split between `builtins.py` and `prelude.scm` is a discipline, not a
convenience: primitives are the tight loops over host data; everything
expressible in a few lines of Lisp lives here. That is why `map` is Python and
`alist-ref` is Lisp, and why adding `take-while` to the language was a four-line
diff to this file rather than a change to the interpreter.

## Try it

```sh
shs run /dev/stdin <<'EOF'
(display ((compose inc inc) 5)) (newline)
(display ((pipe inc inc inc) 5)) (newline)
(display (alist-ref '((a 1) (b 2)) 'b)) (newline)
(display (alist-ref '((a 1)) 'c)) (newline)
(display (take-while (lambda (n) (< n 4)) (range 10))) (newline)
(display (group-by even? (range 6))) (newline)
(display (-> 5 inc inc (* 2))) (newline)
(display (->> (range 5) (map inc) (filter even?))) (newline)
(do ((i 0 (+ i 1))) ((= i 3) (display "done")) (display i))
(newline)
EOF
```

```text
7
8
2
#f
(0 1 2 3)
((#t (0 2 4)) (#f (1 3 5)))
14
(2 4)
012done
```

## Exercises

1. **Read one function.** Open `lisp/prelude.scm` and find `take-while`. It is
   four lines. Which primitive does the recursion bottom out in, and what does
   it return when the predicate is false on the very first element?
2. **Add a function.** Write `count-where` — `(count-where pred xs)` returns how
   many elements satisfy `pred` — and try to write it with `fold` alone. Then
   decide whether it belongs in `prelude.scm` or in your own file, and why.
3. **Short-circuit the pipeline.** Compare `(pipe inc inc inc)` with `(compose
   inc inc inc)`. They compute the same thing; the difference is which one
   reads left-to-right. Rewrite one with the other and check your answer with
   `(equal? ((pipe inc inc) 5) ((compose inc inc) 5))`.

## The shape you copy

> The standard library is where a language proves it can grow itself. Keep the
> host floor to the things only the host can do; write everything else *in the
> language*, where the users can read it, change it, and copy it.

Next: [06 Macros](06-macros.md).

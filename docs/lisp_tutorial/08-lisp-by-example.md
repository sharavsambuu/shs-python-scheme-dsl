# 08 — Lisp by example

> **What this chapter teaches.** The language itself, at the REPL: functions,
> recursion, local bindings, lists, higher-order functions, records, mutation,
> and the small idioms that make Lisp feel like Lisp. Read it with the REPL open.
>
> **Before this:** 02–03 (skim Part I; you do not need the interpreter to write
> the language). · **Time:** ~30 min, at a REPL.
> **After this you can:** write functions, named-`let` loops, higher-order list
> code, and alist records — the four things every design in this repo uses.

Start it:

```sh
shs repl --no-tetris
```

You get a prompt. Type a form, press enter, see its value. The REPL reads lines
until the parentheses balance, so a `define` can span as many lines as it takes.

## Calling things

```lisp
> (+ 1 2 3)
6
> (< 1 2 3)
#t
> (string-append "hello, " "world")
hello, world
```

Everything is a call: the first element of a list is the procedure, the rest are
arguments. `+` and `append` are variadic primitives.

## Defining functions

```lisp
> (define (square x) (* x x))
square
> (square 5)
25
> (define (fact n) (if (= n 0) 1 (* n (fact (- n 1)))))
fact
> (fact 10)
3628800
```

`(define (name params…) body…)` is sugar for binding a `lambda`. The body is a
sequence of forms evaluated in order; the last value is the function's value.

`define*` (SRFI 89) extends `define` with optional and named parameters. A
positional optional is `(v default)`; a named one is `(keyword: v default)`,
supplied at the call site by keyword:

```lisp
> (define* (greet name (greeting: g "hello"))
    (string-append g ", " name))
> (greet "ada")
hello, ada
> (greet "ada" greeting: "hi")
hi, ada
```

Domain APIs like this read like named arguments in any language — and the
keyword `greeting:` is a value of its own (SRFI 88; chapter
[02](02-values-and-reading.md)).

## Conditionals

```lisp
> (if (> 3 2) "yes" "no")
yes
> (cond ((= 1 2) "one") ((= 2 2) "two") (else "other"))
two
> (when (> 2 1) (display "hi") (newline))   ; one-armed: when false, returns ()
> (and 1 2 3)      ; the last truthy value, or #f
3
> (or #f #f 7)
7
```

`cond` tries clauses in order; `when`/`unless` are one-armed; `and`/`or`
short-circuit and return a *value* (`(and 1 2 3)` is `3`, not `#t`). Every one of
these has a tail position the trampoline honours, so a recursive call in a `cond`
arm is a tail call.

## Local bindings

```lisp
> (let ((a 2) (b 3)) (+ a b))
5
> (let* ((a 2) (b (* a a))) b)     ; b sees a
4
> (letrec ((even2? (lambda (n) (if (= n 0) #t (odd2? (- n 1)))))
           (odd2?  (lambda (n) (if (= n 0) #f (even2? (- n 1))))))
    (even2? 10))
#t
```

`let` binds in parallel, `let*` sequentially, `letrec` lets the bindings refer to
one another (for mutual recursion). There is no `for`; a **named `let` is the
loop**:

```lisp
> (let loop ((i 0) (acc '()))
    (if (= i 3) (reverse acc) (loop (+ i 1) (cons i acc))))
(0 1 2)
```

Read it as: call `loop` with `i=0`, `acc=()`. The body either returns or calls
`loop` again with new values — in tail position, so it costs no host stack
(chapter [03](03-evaluating.md)). This named-let shape is *the* Lisp loop, and you
will see it in nearly every file in `scripts/`.

```lisp
> (define (sum-to n) (let loop ((i 0) (s 0)) (if (> i n) s (loop (+ i 1) (+ s i)))))
> (sum-to 10)
55
```

## Lists and higher-order functions

Lists are built recursively — `cons` puts an element on the front, `car`/`cdr`
take it apart, `()` ends it:

```lisp
> (cons 1 '(2 3))
(1 2 3)
> (car '(1 2 3))
1
> (cdr '(1 2 3))
(2 3)
> (map inc '(1 2 3))
(2 3 4)
> (filter even? (range 10))
(0 2 4 6 8)
> (fold + 0 '(1 2 3 4))
10
```

`map`, `filter` and `fold` are the three you will use most. `fold` is SRFI 1's,
pre-imported by the default profile: its function takes `(elt acc)`, and
`fold-right` mirrors it. The prelude's `foldl`/`foldr` remain with the same
argument order, so `(foldl + 0 xs)` and `(fold + 0 xs)` are the same call —
`fold` is the name shipped code uses. Note the prelude's
list functions take the list first and the count second — `(take xs n)`, not
`(take n xs)`:

```lisp
> (take (range 10) 3)
(0 1 2)
> (drop (range 10) 7)
(7 8 9)
> (take (iterate inc 0 10) 3)     ; iterate: x, f(x), f(f(x)), …
(0 1 2)
```

## Closures

A `lambda` captures the scope it was written in, which is how you carry private
state without objects:

```lisp
> (define (make-counter) (let ((n 0)) (lambda () (set! n (+ n 1)) n)))
> (define c (make-counter))
> (c)
1
> (c)
2
```

Each `make-counter` makes a fresh `n`; the returned closure is the only thing
that can see it. This is the pattern a host's hooks use for per-session state:
they put the state in top-level `define`s so the host can call each hook
independently.

## Symbols, strings, and records

Strings are for text from the outside world; symbols are for names you write.
Quoting a symbol yields the symbol itself:

```lisp
> 'square
square
> (symbol? 'square)
#t
> (string? "square")
#t
> (string? 'square)
#f
> (symbol->string 'square)
square
> (string->symbol "square")
square
```

An **alist** — a list of `(key value)` pairs — is the language's record shape:

```lisp
> (alist-ref '((a 1) (b 2)) 'b)
2
> (alist-ref '((a 1)) 'missing)
#f
> (alist-set '((a 1)) 'b 2)
((b 2) (a 1))
```

`alist-ref` returns `#f` on a miss, which is false — so "not found" and "false"
are the same answer, and a lookup can be used directly in a condition. Every
record in the game (a piece, a fact, a refusal, the design metadata, the view) is
an alist, and `alist-ref` is how you read a field.

## Mutation

`set!` mutates the nearest binding; vectors and hash tables are mutable in place:

```lisp
> (define i 0)
> (while (< i 3) (display i) (set! i (+ i 1)))
012
> (define v (make-vector 3 0))
> (vector-set! v 1 'x)
> v
#(0 x 0)
> (define h (make-hash-table))
> (hash-table-set! h '(1 2) "pair key")
> (hash-table-ref h '(1 2))
"pair key"
```

Vectors are the language's growable array and hash tables its map; both are
what a search over candidate states uses them for, for exactly the reason you
would expect — speed.

## Two small programs

**FizzBuzz**, with `cond`:

```lisp
> (define (fizzbuzz n)
    (cond ((= (modulo n 15) 0) "FizzBuzz")
          ((= (modulo n 3) 0)  "Fizz")
          ((= (modulo n 5) 0)  "Buzz")
          (else (number->string n))))
> (map fizzbuzz (range 1 16))
(1 2 Fizz 4 Buzz Fizz 7 8 Fizz Buzz 11 Fizz 13 14 FizzBuzz)
```

**A word count**, with `fold` and an alist accumulator:

```lisp
(define (word-count words)
  (fold (lambda (w acc)
           (let ((n (alist-ref acc w)))
             (alist-set acc w (+ (if n n 0) 1))))
         '() words))

(word-count '("a" "b" "a" "a"))   ;=> ((a 3) (b 1))
```

**A tiny evaluator**, with recursion and `case` (a preview of the pattern the
game itself is written in — data in, value out):

```lisp
(define (calc e)
  (cond ((number? e) e)
        ((list? e)
         (let ((op (car e)) (l (calc (cadr e))) (r (calc (caddr e))))
           (case op ((+) (+ l r)) ((-) (- l r)) ((*) (* l r))
                 (else (error "bad op" op)))))
        (else (error "bad expr" e))))

(calc '(* (+ 1 2) 3))   ;=> 9
```

## Threading

When a sequence of calls reads better in data-flow order, `->` and `->>` rewrite
it (they are macros; they cost nothing):

```lisp
> (-> 5 inc inc (* 2))                 ; (* (inc (inc 5)) 2)
14
> (->> (range 5) (map inc) (filter even?))
(2 4)
```

SRFI 197's `chain` is the pre-imported standard spelling of the same idea —
`_` names the hole, `chain-and`/`chain-when` add early exit:

```lisp
> (chain '(1 2 3) (map (lambda (x) (* x x)) _) (fold + 0 _))
14
```

The partial-application side of the same coin is SRFI 26's `cut`/`cute`:

```lisp
> ((cut + 1 <>) 41)
42
```

## Try it

```sh
shs run /dev/stdin <<'EOF'
(define (square x) (* x x))
(display (square 5)) (newline)

(define (fact n) (if (= n 0) 1 (* n (fact (- n 1)))))
(display (fact 10)) (newline)

(display (let loop ((i 0) (acc '()))
  (if (= i 3) (reverse acc) (loop (+ i 1) (cons i acc))))) (newline)

(display (fold + 0 '(1 2 3 4))) (newline)
(display (take (range 10) 3)) (newline)
(display (alist-ref '((a 1)) 'missing)) (newline)
(display (alist-set '((a 1)) 'b 2)) (newline)

(define v (make-vector 3 0))
(vector-set! v 1 'x)
(display v) (newline)
EOF
```

```text
25
3628800
(0 1 2)
10
(0 1 2)
#f
((b 2) (a 1))
#(0 x 0)
```

The named `let` is the loop; `fold` is the accumulation; the alist is the
record. Those three plus `define`/`lambda` are the whole language you write.

## Exercises

1. **FizzBuzz.** Write `(fizzbuzz n)` returning `"Fizz"`, `"Buzz"`, `"FizzBuzz"`,
   or the number as a string, and map it over `(range 1 16)`. The `cond` you
   need is the one from earlier in the chapter.
2. **A record, twice.** Represent a point as `'((x 1) (y 2))` and write
   `point-x`, `point-y`, and `point+`. Then do the same with `define-variant`
   (chapter [09](09-typed-control-flow.md)) and say which one the domain's shape
   types would use, and why.
3. **Recursion to a loop.** Take the recursive `fact` above and rewrite it with
   an accumulator in a named `let`. Confirm both give `3628800` for `10`, then
   explain which one survives `(fact 5000)`.

## The shape you copy

> Learn four things and you can write this language: `define`/`lambda` for
> functions, the named `let` for loops, `map`/`filter`/`fold` for lists, and the
> alist for records. Everything else is a variation, and everything the game does
> is built from these.

Next: [09 Typed control flow](09-typed-control-flow.md).

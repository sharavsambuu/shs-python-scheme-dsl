# 06 — Macros: the language rewriting itself

> **What this chapter teaches.** The two macro systems — the raw `defmacro` and
> the hygienic `define-syntax`/`syntax-rules` — how a macro is recognised and
> expanded, and why hygiene is not a nicety. Then the pieces real macro code
> needs: nested and stacked ellipses, vector patterns, local macros, and the
> `macroexpand` microscope.
>
> **Before this:** 05. · **Time:** ~20 min.
> **After this you can:** choose between `defmacro` and `syntax-rules`; say
> exactly what a hygienic macro renamed; and inspect any expansion with
> `macroexpand`.

Chapter [03](03-evaluating.md) showed that before the evaluator evaluates a form,
it checks whether the head names a macro; if it does, it expands the form and
loops. A macro is therefore a *procedure from forms to a form*, run at expansion
time. Because the reader already turned code into lists (chapter
[02](02-values-and-reading.md)), that procedure is just ordinary Lisp over lists.

## `defmacro`: the raw tool

```scheme
(defmacro (while test . body)
  `(let loop ()
     (when ,test
       ,@body
       (loop))))
```

The arguments arrive **unevaluated** — `test` and `body` are forms, not values.
The template builds the replacement with quasiquote. `while` *must* be a macro
rather than a function: `(while test body)` must not evaluate `body` before the
test passes, and a function call cannot promise that.

The same shape gives the tiny helpers:

```scheme
(defmacro (++ place) `(set! ,place (+ ,place 1)))
```

`(++ x)` rewrites to `(set! x (+ x 1))`, which is why it can appear on the left
of an assignment — something no function can do.

`defmacro`'s weakness is that its template is *unhygienic*: a name the template
introduces can collide with a name in the caller's expression. `while` binds
`loop` and gets away with it only because no caller is called `loop`.

## `define-syntax` / `syntax-rules`: the hygienic tool

```scheme
(define-syntax push!
  (syntax-rules ()
    ((_ place value) (set! place (cons value place)))))

(define-syntax pop!
  (syntax-rules ()
    ((_ place)
     (let ((v (car place)))     ; v is the template's own
       (set! place (cdr place))
       v))))
```

A `syntax-rules` macro is a list of `(pattern template)` clauses; the first whose
*pattern* matches the use wins, and its template is instantiated. `_` matches
anything and binds nothing; `...` repeats the subpattern before it (`(f x ...)`).
The first element of each pattern — `_` above — matches the macro's own name.

`syntax.py` handles the two directions of hygiene, and its docstring names them:

> * **Template binders are renamed.** `(let ((x ...)) ...)` inside a template
>   gets a fresh `x#hN`, and so do its references — a caller's `x` is safe.
> * **Free template identifiers are captured *by resolution*.** `list` in a
>   template becomes a private alias pinned to whatever `list` meant where the
>   macro was defined, so a caller's local `list` cannot shadow it.

Here is the difference in one session. Two macros compute "a or b", one raw and
one hygienic, both binding a temporary named `t`; the caller also has a `t`:

```scheme
(define-syntax hy-or
  (syntax-rules ()
    ((_ a b) (let ((t a)) (if t t b)))))   ; template's t is renamed

(defmacro (raw-or a b)
  `(let ((t ,a)) (if t t ,b)))              ; template's t is the caller's t

(define t 99)
(hy-or  #f t)   ;=> 99   — the caller's t, unharmed
(raw-or #f t)   ;=> #f   — the template's t captured the caller's t
```

That capture is exactly the class of bug hygiene removes. The hygienic macro's
`t` became `t#hN` — a fresh name with a hash and a counter — so it cannot be
the caller's `t`.

### Four deviations worth knowing

`syntax.py`'s docstring is honest about them:

- a template's `(define name …)` **keeps its written name** (so a macro that
  defines a helper leaves it visible);
- only the binding forms `lambda` / `let` / `let*` / `letrec` are scope-analysed;
- an identifier that was **unbound where the macro was defined** has no binding
  to pin, so it resolves at the use site. Define a helper before the macro that
  expands to it (or use `defmacro` with `gensym`) when use-site capture would
  matter;
- the transformer is **always `syntax-rules`** — there is no `syntax-case`, and
  no custom ellipsis identifier. What `syntax-rules` can express, this does.

A dotted tail is the fifth thing to know, because it is the variadic idiom and it
has two readings: `((_ a . rest) …)` binds `rest` to the *forms* after `a`, so
write `'rest` for the tail as data and `rest ...` to splice it back into code.

## Derived forms

The strongest macros *derive* what they offer from what the language already has,
so they cost nothing at run time. `do` is the classic:

```scheme
(define-syntax do
  (syntax-rules ()
    ((_ ((var init step) ...) (test result ...) body ...)
     (let loop ((var init) ...)
       (if test
           (begin result ...)
           (begin body ... (loop step ...)))))))
```

and `dotimes` is `do`:

```scheme
(define-syntax dotimes
  (syntax-rules ()
    ((_ (var n) body ...)
     (do ((var 0 (+ var 1))) ((= var n)) body ...))))
```

The threading macros `->` and `->>` (chapter [05](05-standard-library.md)) are the
same idea: ordinary calls, written in the order the data flows, expanded at
compile time.

You will meet one more, the largest, in chapter [22](22-railway-oriented.md):
`result-do`, a do-notation for the `Result` monad, built on `result-bind`.

## Two shapes of ellipsis

A pattern may nest, and a template may meet it nested or flat:

```scheme
(define-syntax grid                     ; (grid (1 2) (3 4)) => ((1 2) (3 4))
  (syntax-rules () ((_ (x ...) ...) (list (list x ...) ...))))

(define-syntax flat                     ; (flat (1 2) (3 4)) => (1 2 3 4)
  (syntax-rules () ((_ (x ...) ...) (list x ... ...))))
```

`x ... ...` descends one level per `...` — the flat spelling of a doubly-repeated
variable. A `...` that reaches past the binding's depth is a `LispSyntaxError`,
not a silent truncation.

A **vector** is a pattern and a template too, so a macro can destructure `#(1 2)`
as readily as `(1 2)`:

```scheme
(define-syntax vec-second
  (syntax-rules () ((_ #(a b)) b)))
(vec-second #(10 20))   ;=> 20
```

## Local macros: `let-syntax`

`define-syntax` publishes a macro for the rest of the program. When you want one
for a single expression — to shadow a function of the same name, or to keep a
helper out of the global namespace — use `let-syntax`:

```scheme
(define (twice x) (* x 10))
(let-syntax ((twice (syntax-rules () ((_ x) (* x 2)))))
  (twice 21))          ;=> 42  — the macro, for the body's extent
(twice 21)             ;=> 210 — the function again
```

`letrec-syntax` is the same, except that a template may name a *sibling* macro:
the macros are pinned in the local frame, so they can see one another.

## Seeing the expansion: `macroexpand`

A macro that "did nothing" is usually a template that did something else. The
microscope is `macroexpand-1` — one step — and `macroexpand`, which keeps going
while the head still names a macro:

```scheme
(define-syntax with-list (syntax-rules () ((_ x) (list x))))
(macroexpand-1 '(with-list 7))                 ;=> (list#hN 7)
(display (eval (macroexpand '(with-list 7))))  ;=> (7)
```

`list#hN` is hygiene showing its work: the template's `list` was pinned to
whatever `list` meant where the macro was defined, and that alias is what the
expansion really calls. It is a *real* binding, which is why the expansion can be
handed straight to `eval` — and why renaming the alias is never the fix when a
macro misbehaves. Change the template, or the pattern. (`N` counts fresh names
for the run, so it is not the same number twice; do not match on it.)

## When to reach for which

- **A function**, if the arguments should be *evaluated* before the call. Most
  things.
- **A `syntax-rules` macro**, if the arguments are *forms* to be rearranged,
  named, or repeated — and you want hygiene. This is the default for anything
  syntactic.
- **A `defmacro`**, only when you genuinely want to manipulate the caller's names
  (or want the clumsier-but-simpler raw template). The prelude's `while`/`++` are
  the examples; they are macros, but they are careful ones.

When a macro misbehaves, do not edit the use site — ask what it became. That is
what `macroexpand` is for, and it is cheaper than any amount of staring.

## Try it

```scheme
(define-syntax my-list
  (syntax-rules ()
    ((_ x ...) (list x ...))))
(display (my-list 1 2 3))                 (newline)

(define xs '(1 2))
(push! xs 0)  (display xs)  (newline)
(display (pop! xs)) (display " ") (display xs) (newline)

(define p 1) (define q 2)
(define-syntax swap
  (syntax-rules ()
    ((_ a b) (let ((tmp a)) (set! a b) (set! b tmp)))))
(swap p q) (display (list p q)) (newline)

;; A dotted tail: the forms after the fixed ones.
(define-syntax tag (syntax-rules () ((_ . rest) (list 'head rest ...))))
(display (tag 1 2 3))                     (newline)

;; Stacked ellipses flatten; a vector is a pattern too.
(define-syntax flat (syntax-rules () ((_ (x ...) ...) (list x ... ...))))
(display (flat (1 2) (3 4)))              (newline)
(define-syntax vec-second (syntax-rules () ((_ #(a b)) b)))
(display (vec-second #(10 20)))           (newline)

;; A local macro, gone when its body ends.
(display (let-syntax ((twice (syntax-rules () ((_ x) (* x 2)))))
           (twice 21)))
(newline)

;; The microscope: the expansion, handed to eval.
(define-syntax with-list (syntax-rules () ((_ x) (list x))))
(display (eval (macroexpand '(with-list 7))))  (newline)
```

```text
(1 2 3)
(0 1 2)
0 (1 2)
(2 1)
(head 1 2 3)
(1 2 3 4)
20
42
(7)
```

`my-list` and `swap` are `syntax-rules` macros, so pasting them into a REPL just
works, and `swap` looks like it introduces `tmp` yet cannot collide with a
caller's `tmp`. The rest of the block is the new ground: a dotted tail spliced
with `rest ...`, a stacked `x ... ...`, a vector pattern, a `let-syntax`, and one
`macroexpand` handed to `eval`.

## Exercises

1. **The answer key.** Write the hygienic `unless-not` macro the blockquote used
   to ask for: `(unless-not test body…)` expanding to `(when (not test) body…)`.
   A worked version ships at `exercises/unless-not.scm`, beside this tutorial.
   Then rewrite it with `defmacro` and try to capture a caller's variable, to
   see exactly what you lose.
2. **Prove hygiene.** Define `(define tmp 'mine)`, then `swap` two other
   variables, then print `tmp`. It is still `mine`. Now write the same swap with
   `defmacro` and watch it clobber `tmp`.
3. **Watch the rename.** Run the `hy-or` / `raw-or` session from above
   yourself: `(define t 99)`, then `(hy-or #f t)` and `(raw-or #f t)`. One
   prints `99` and the other `#f`. Name, in one sentence, the difference — and
   then find where `syntax.py` mints the `t#hN` name.
4. **A macro that takes anything, and one that flattens.** Write `my-begin` as a
   dotted-tail macro so `(my-begin a b c)` splices its body into a `begin`, and
   `flatten` so `(flatten (1 2) (3) (4 5))` yields `(1 2 3 4 5)` with stacked
   ellipses. Then prove the expansion is real code by running it through
   `macroexpand` and `eval`. A worked version ships at
   `exercises/expand-and-flatten.scm`, and the suite runs it.
5. **Local vs global.** Give `twice` a function definition, then shadow it with
   `let-syntax` for one expression and show the function is back afterwards.
   Then ask what `letrec-syntax` would change — and why a sibling macro is
   invisible to a `let-syntax` template.

## The shape you copy

> If two things must not collide, let the *language* rename one of them. Hygiene
> is what lets a library of macros feel like built-in syntax instead of a set of
> names you must avoid.

Next: [07 Code is data: homoiconicity](07-code-is-data.md).

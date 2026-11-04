# 07 — Code is data: homoiconicity

> **What this chapter teaches.** The property the Lisp family is named for. A
> program in this language *is* a data structure — the same lists, symbols, and
> literals chapter [02](02-values-and-reading.md) catalogued — so a program can
> take a program apart, build a new one from a template, and run the result.
> `quote` freezes code into data; `eval` thaws data back into behaviour;
> quasiquote is the template that builds code out of code. Then the part most
> tutorials skip: *why* this matters — macros, program generators, code as
> configuration, DSLs — and where the honest limits are.
>
> **Before this:** 06. · **Time:** ~25 min.
> **After this you can:** take any form apart with list operations, build a new
> form with a template, run a form you built at runtime, and say exactly what
> homoiconicity buys you — and what it does not.

In Python, a program is *text*. To reason about code you parse it — `ast.parse`
hands you a tree of node objects that are nothing like the values your program
normally handles, and `eval` takes a *string*, which is why "eval is dangerous"
is a proverb: a string has no structure to inspect before you run it.

In this Lisp there is no such split. The reader (chapter [01](01-the-pipeline.md))
turns text into ordinary values; the evaluator consumes those same values. A
program is a list. That is the whole trick, and it has a name:
**homoiconicity** — from the Greek *homoios* (same) and *eikon* (image): the
program's representation is the language's own data, the same "icon" all the
way down. Every technique in this chapter is a consequence of that one decision.

## The circle: text, data, behaviour

Chapter [03](03-evaluating.md) showed the evaluator as a loop over forms. Here
is the point that chapter made in passing: `eval` — the evaluator itself — is
just a procedure you can call. Data goes in, behaviour comes out:

```scheme
(display '(+ 1 2))          ; the form: a three-element list
(newline)
(display (eval '(+ 1 2)))   ; the same list, handed to the evaluator
(newline)
```

```text
(+ 1 2)
3
```

`'(+ 1 2)` is `(quote (+ 1 2))` — the reader's sugar (`shslisp/reader.py`,
expanded exactly as `test_quote_sugar_expands` in `tests/test_r7rs.py` checks).
`quote` means: *here is the data, do not run it*. `eval` is the mirror: *here
is the data, run it*. Together they close a circle with three stations:

```text
   text --(read/read-string)--> data --(eval)--> value
     ^                                            |
     +--------------(write/print)-----------------+
```

The REPL is that circle driven interactively (`shslisp/repl.py` is a few
hundred lines, most of them error handling); the loader is the same circle
driven over files (`shslisp/loader.py` reads a file, gets forms, evaluates
them). Neither is a special subsystem — they are `read` and `eval` in a loop.

## Taking a program apart

Because a form is a list, every list operation you learned in chapter
[11](11-lists-and-vectors.md) works on code:

```scheme
(display (car '(+ 1 2)))    ; the operator is data too
(newline)
(display (cdr '(+ 1 2)))    ; so are the operands
(newline)
(display (length '(+ 1 2))) ; three elements
(newline)
```

```text
+
(1 2)
3
```

Nothing about `+` is special here. `(car '(+ 1 2))` is the *symbol* `+`, which
is a value — hashable, comparable, convertible (`(eq? 'x
(string->symbol "x"))` is `#t`; symbols are interned strings,
`shslisp/types.py`). You can walk a whole program with ordinary recursion:

```scheme
(define (leaves form)
  (cond ((pair? form) (append (leaves (car form)) (leaves (cdr form))))
        ((null? form) '())
        (else (list form))))

(display (leaves '(define (square x) (* x x))))
(newline)
```

```text
(define square x * x x)
```

Nine lines — no parser, no visitor pattern, no node classes — and you have a
program that reads another program. Notice what the walker does *not* see:
comments and whitespace. The reader consumed them; code as data keeps
*structure*, not layout. That is a feature (you can rebuild pretty-printing
later) and a limit (you cannot recover the author's comments from a form).

### Quote of quote: a program whose value is a program

What happens if you quote a quote? This is the moment homoiconicity stops
being a slogan:

```scheme
(display ''x)        ; a program whose value is... a program
(newline)
(display (car ''x))  ; ...which you can take apart
(newline)
(display (eval ''x)) ; ...and run one more time
(newline)
```

```text
(quote x)
quote
x
```

Read the first line carefully. `''x` is `(quote (quote x))` as a datum;
evaluating it *once* yields the list `(quote x)` — a small program, printed as
data. Its `car` is the symbol `quote`. Evaluate it *again* and you finally get
`x`. Each `quote` strips one layer: data → code → value. Two layers of quoting
is how you talk *about* code while still holding it as data — and it is exactly
the shape of a macro's argument list, which is chapter [06](06-macros.md)'s
whole premise.

## Building code: the template

`cons` and `list` can build a form — `(list '+ 1 2)` is code — but nesting
quote inside quote gets unreadable fast. The template is quasiquote (chapter
[03](03-evaluating.md) introduced it): backquote the skeleton, comma the holes,
`,@` splice a list into a hole:

```scheme
(define op '+)
(define args '(20 22))

(display `(,op ,@args))          ; the form, as data
(newline)
(display (eval `(,op ,@args)))   ; the form, run
(newline)
```

```text
(+ 20 22)
42
```

The inversion inside the template is the whole idea. In `(+ 1 2)`, the `+` is
a *name* the evaluator will look up. In `` `(,op ,@args) ``, the operator
position holds a *value* — whatever `op` is bound to. Values can sit anywhere a
name could, including positions you think of as syntax:

```scheme
(write `(if ,(> 3 2) 'yes 'no))   ; a computed subform, in a test position
(newline)

(define table `((double ,(lambda (x) (* 2 x)))
                (square ,(lambda (x) (* x x)))))
(display ((cadr (assoc 'square table)) 9))   ; a function, stored in code
(newline)
```

```text
(if #t (quote yes) (quote no))
81
```

The second example is worth a second look: the *operator* of that call —
`(cadr (assoc 'square table))` — was computed at runtime. Code that computes
its own operator is not a party trick; it is how rule tables and dispatch
tables work (chapter [13](13-dictionaries-alists-and-hash-tables.md) rebuilds
Python's dict-of-lambdas this way).

## eval: the escape hatch

`(eval form)` evaluates in the interaction environment — the one the REPL
shares — and `(eval form (interaction-environment))` says so explicitly. The
form can be anything, including a definition:

```scheme
(eval '(define temp 41))
(display (eval '(+ temp 1)))
(newline)
```

```text
42
```

A program that defines its own next line. In this repository, `eval` is one of
the named "host holes" (chapter [04](04-primitives.md)) — the impure doors —
and the places it is actually used are instructive:

- `macroexpand` + `eval` — chapter [06](06-macros.md) ran a macro's expansion
  through both, proving the expansion is real code and not a printout;
- the loader — `(load "file.scm")` is `read` each form, `eval` each form;
- the REPL — every line you type.

**The warning that goes with the door.** `eval` on data that came from outside
your program is arbitrary code execution — a hostile string is a hostile
program. The homoiconic answer is not "never touch code as data", it is
*inspect before you run*: walking a form with `leaves` (above) or matching it
with `match` (chapter [15](15-srfi-241-match.md)) is safe, because nothing is
evaluated. Structure is exactly what a string does not have.

## Why this matters

Everything above is mechanics. Here is what the mechanics are *for*.

**Macros are homoiconicity applied.** A macro is a procedure from forms to a
form — and "forms are lists" is what makes that a *normal function* instead of
a compiler plugin. Chapter [06](06-macros.md) wrote `while` in eight lines:
quasiquote the skeleton, comma the holes. No parser to drive, no AST node zoo
to learn, and the language's own list library is your code-manipulation
library. `macroexpand-1` shows the rewrite for what it is:

```scheme
(display (macroexpand-1 '(while #f 'done)))
(newline)
```

```text
(let loop () (when #f (quote done) (loop)))
```

**Programs that write programs.** Any time you would copy-paste a near-identical
definition, a generator can build them from data instead:

```scheme
(define (make-check name ok?)
  `(lambda (value)
     (if (,ok? value)
         (list 'ok ',name value)
         (list 'no ',name value))))

(define check-age (eval (make-check 'age 'number?)))
(display (check-age 42))    (newline)
(display (check-age "old")) (newline)
```

```text
(ok age 42)
(no age old)
```

`make-check` is a template with two holes; each `eval` stamps out one checker.
The generated code is a *real* lambda — inspectable with `write`, walkable with
`leaves`, composable with the rest of the program. Compare the Python moves:
building a source string and `exec`ing it (no structure, injection-shaped), or
a metaclass (powerful, but the generated code is invisible and the mechanism is
a language of its own). The Lisp generator is middle-weight: it is just a
function returning a list.

**Code as configuration — and configuration as code.** Because code is data, a
rule can live in a variable, a file, or a host-side Python string, and your
program decides what to do with it:

```scheme
(define discount '(if (vip? customer) 20 0))

(display (car (cadr discount)))   ; the condition, as a symbol
(newline)
```

```text
vip?
```

You can `eval` it (run the rule), walk it (validate the rule), translate it
(show it to the user), or refuse it (a rule editor that only accepts forms it
recognises). The reader doubles as a *serializer for code*: `write` a form and
it prints back in a form the reader can read — the round trip is lossless for
structure. Chapter [28](28-embedding-in-python.md) is this idea at the seam:
a host publishes a vocabulary, and the "config file" is a Lisp program.

**DSLs are cheap because the syntax never changes.** In most languages, a DSL
means a parser. Here, new vocabulary is macros (same parentheses), and new
*nouns* are plain data — `'(circle 3)` reads as a shape, a point, or a command
depending on the program holding it. Chapter
[14](14-records-variants-and-objects.md) shows variants printing and reading as
plain data for exactly this reason.

**A Lisp can contain its own interpreter.** `eval` is a procedure, the
evaluator is one readable trampoline (chapter [03](03-evaluating.md)), and
McCarthy's original `eval` — written *in Lisp* — is short enough to fit on a
blackboard; Alan Kay called it "the Maxwell's equations of software". That is
the deep possibility: a language that can describe itself is a language you can
modify while it is running — new syntax (macros), new meaning (`eval`), even
new notation, all without forking a compiler.

**Fexprs: arguments that stay code.** Some procedures *need* their arguments
unevaluated — `while` must not run its body before the test passes. With code
as data, "take this argument as a form" is one `quote` away, and the prelude's
`while` (chapter [06](06-macros.md)) is the shipped example.

## The honest limits

Homoiconicity is not magic, and this dialect states its edges:

- **No `gensym`.** A raw `defmacro` template that binds a name can capture the
  caller's; the usual fix — generate a fresh name — has no primitive here.
  Chapter [06](06-macros.md)'s advice stands: prefer `syntax-rules`, whose
  hygiene renames template binders for you, or bind helpers before the macro.
- **`syntax-rules` is pattern-only.** There is no `syntax-case`: the hygienic
  tool matches shapes, it does not compute. Procedural code generation is
  `defmacro`/quasiquote territory, with hygiene as your responsibility.
- **Nested quasiquote counts depth.** R7RS semantics: `` `(a `(b ,(+ 1 2))) ``
  leaves the inner template intact — the inner `,` belongs to the inner
  quasiquote. Powerful, and one more thing to count when templates nest.
- **`eval` needs an environment.** Forms have no home until you give them one;
  `(eval form)` uses the interaction environment, and library code should be
  explicit about which environment it means.
- **Comments and layout are gone.** The reader's output is structure; a form
  cannot tell you what column it started in or what the author said about it.
- **`eval` is a door.** Treat code from outside as a program, because that is
  what it is — inspect it, match it, whitelist it, and only then run it.

## Try it

```scheme
;; 1. Quote freezes: the form, not the answer.
(display '(+ 1 2))                            (newline)
(display (eval '(+ 1 2)))                     (newline)

;; 2. A form is an ordinary list -- take it apart.
(display (car '(+ 1 2)))                      (newline)
(display (cdr '(+ 1 2)))                      (newline)

;; 3. Quote of quote: a program whose value is a program.
(display ''x)                                 (newline)
(display (car ''x))                           (newline)
(display (eval ''x))                          (newline)

;; 4. Build code with a template, then run it.
(define op '+)
(define args '(20 22))
(display `(,op ,@args))                       (newline)
(display (eval `(,op ,@args)))                (newline)

;; 5. The full circle: text -> data -> value.
(display (eval (read-string "(* 6 7)")))      (newline)

;; 6. A program that writes a program.
(define (make-check name ok?)
  `(lambda (value)
     (if (,ok? value)
         (list 'ok ',name value)
         (list 'no ',name value))))
(define check-age (eval (make-check 'age 'number?)))
(display (check-age 42))                      (newline)
(display (check-age "old"))                   (newline)
```

```text
(+ 1 2)
3
+
(1 2)
(quote x)
quote
x
(+ 20 22)
42
42
(ok age 42)
(no age old)
```

Station by station: quote hands back the form, `eval` runs it, `car`/`cdr`
treat code as the list it is, the double quote shows a program whose value is a
program, the template builds a form out of runtime values, `read-string` closes
the circle from text, and `make-check` stamps out a real procedure from a
template with two holes.

## Exercises

1. **Leaves, and a generator.** Write `leaves` (collect every atom of a form,
   in order), then extend `make-check` so `(make-check 'age 'number? 0)`
   returns a checker that *repairs* instead of refusing: a bad value becomes
   `0`. Inspect your generated lambda with `write` before you run it. A worked
   version of the chapter's pair — `leaves` plus `make-check` — ships at
   `exercises/code-is-data.scm`, and the suite runs it.
2. **A form classifier.** Write `(kind form)` that returns the symbol
   `'definition` for a form whose head is `define`, `'application` for any
   other pair, and `'atom` otherwise. Feed it
   `(list '(define x 1) '(+ 1 2) 7)` and check the three answers.
3. **Change the data, not the code.** Build `(if (< 3 1) 'yes 'no)` with a
   quasiquote template where the `3` and the `1` come from variables, eval it,
   then rebind the variables and eval again — same template, two answers.
4. **Symbols are not strings.** Prove `(eq? 'x (string->symbol "x"))` is `#t`
   while `(eq? 'x "x")` is `#f`, then explain in one sentence why the reader
   interns symbols (`shslisp/types.py`) — and what would break if it did not.
5. **The capture, once more.** Revisit chapter [06](06-macros.md)'s `raw-or`
   exercise, but this time name the mechanism: which piece of the template is
   data, which is code, and why hygiene has to *rename* rather than hide. No
   new machinery — just the words for what you already saw.

## The shape you copy

> When you reach for a string that contains code, stop and build the form
> instead. Structure survives, `car`/`cdr` and `match` can inspect it, and
> nothing is executed until you say `eval`. Homoiconicity is not a curiosity —
> it is the reason macros, generators, and code-as-configuration are ordinary
> programming here instead of metaprogramming.

Next: [08 Modules](08-modules.md).

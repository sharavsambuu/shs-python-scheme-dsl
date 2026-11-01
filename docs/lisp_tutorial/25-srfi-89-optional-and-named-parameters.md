# 25 — SRFI 89: optional and named parameters

> **What this chapter teaches.** `define*` and `lambda*`: a formals list with
> three sections — positional, named, rest — and the keyword-prefixed call
> syntax that fills the named ones.
>
> **Before this:** 24 (keywords), 08. · **Time:** ~12 min.
> **After this you can:** write a procedure whose callers name their
> arguments, and read its errors when a call is wrong.

## The formals grammar

An ordinary `define` formals list is one section: required positionals. A
`define*` formals list has **up to three sections, in any order**:

- positional: required `v`, then optional `(v default)`;
- named: required `(keyword: v)`, then optional `(keyword: v default)`;
- rest: `. r` last.

```lisp
(define* (greet name (greeting: g "hello"))
  (string-append g ", " name))
```

Here `name` is required positional; `greeting:` names an optional parameter
whose *variable* is `g` and whose default is `"hello"`. Note the shape — the
keyword, then the variable, then the default. The keyword is what the caller
writes; the variable is what the body reads.

## Calling: positionals by place, named by keyword

Positional arguments go by place, as always. Named arguments are written as
a keyword followed by its value, and may appear **in any order**:

```lisp
(greet "ada")                  ;=> hello, ada
(greet "ada" greeting: "hi")   ;=> hi, ada
```

A named parameter with no default is *required*: omitting it (or supplying a
keyword the formals never declared) is an error at call time, named as such:

- `unknown keyword, calling` — the keyword is not in the formals;
- `duplicate keyword, calling` — the same keyword twice;
- `missing required keyword` — a `(keyword: v)` with no default was omitted.

All three fail loudly, the way this library does everything.

## Optional positionals, too

The `(v default)` section gives positional arguments defaults, so a
small-arity call site stays short:

```lisp
(define* (point (x: x 0) (y: y 0))
  (list 'point x y))

(point)                        ;=> (point 0 0)
(point y: 7)                   ;=> (point 0 7)
```

Defaults are evaluated left to right, at most once, in the scope of the
parameters bound before them — so a later default can reference an earlier
parameter.

## Rest, mixed in

The rest section collects whatever is left — positionals beyond the required
ones, and any arguments that were not keyword-value pairs:

```lisp
(define* (at-least? floor . xs)
  (every (lambda (x) (>= x floor)) xs))

(at-least? 3 4 5)              ;=> #t
(at-least? 3 4 2)              ;=> #f
```

## `lambda*` and what it compiles to

`define*` is a thin rewrite onto `lambda*`, and `lambda*` expands to an
ordinary `lambda` over a single rest parameter plus a runtime binder — the
shape SRFI 89 recommends. `procedure-arity` and `apply` are untouched, so a
`define*` procedure is an ordinary closure everywhere else in the language:
it can be `map`ped, stored in an alist, and partially applied with `cut`
(chapter [23](23-srfi-26-cut-and-cute.md)).

## Try it

```sh
shs run /dev/stdin <<'EOF'
(define* (greet name (greeting: g "hello"))
  (string-append g ", " name))
(display (greet "ada")) (newline)
(display (greet "ada" greeting: "hi")) (newline)
(define* (point (x: x 0) (y: y 0))
  (list 'point x y))
(display (point)) (newline)
(display (point y: 7)) (newline)
(define* (at-least? floor . xs)
  (every (lambda (x) (>= x floor)) xs))
(display (at-least? 3 4 5)) (newline)
(display (at-least? 3 4 2)) (newline)
EOF
```

```text
hello, ada
hi, ada
(point 0 0)
(point 0 7)
#t
#f
```

## Exercises

1. **The three sections at once.** Write `(register title (admin: admin?
   #f) . tags)` and call it three ways: bare, with `admin:`, with tags.
   Which arguments go to `tags`?
2. **Read the errors.** Call your `register` with a keyword it does not
   declare, then twice with the same keyword. Read both errors — they name
   the call and the keyword.
3. **Order independence.** Give `point` four named parameters and call it
   with the keywords in a different order than the formals. Why does the
   runtime binder make this free, when positional arguments need places?

## The shape you copy

> When a procedure grows a fourth boolean or a mode flag, do not add another
> positional — name it. `define*` keeps short calls short and long calls
> self-documenting, and the keyword in the call site is the documentation.

Next: [26 SRFI 197 — chain and nest](26-srfi-197-chain-and-nest.md).

# 03 — Evaluating: the trampoline

> **What this chapter teaches.** How a form becomes a value: the single loop that
> is the evaluator, why it is a loop rather than a recursion, what a closure
> captures, and the two budgets that bound a runaway program.
>
> **Before this:** 02. · **Time:** ~25 min.
> **After this you can:** read the trampoline, explain why a tail call costs no
> stack, and predict which of two recursions will hit a budget.

## The loop

`shslisp/evaluator.py` has one function at its heart, `_run`. Everything else in
the file is a helper it calls. Here is its shape, trimmed to the load-bearing
lines:

```python
def _run(expr: Any, env: Environment) -> Any:
    """The trampoline: evaluate *expr*, looping in tail position."""
    while True:
        _charge()
        if isinstance(expr, Symbol):
            value = env.lookup(expr)
            ...
            return value

        if not isinstance(expr, list):
            return expr          # a number, string, boolean, or NIL literal

        if not expr:
            return NIL

        head = expr[0]
        # ... macro dispatch ...
        # ... special-form dispatch (if, define, lambda, let, match, ...) ...
        # An application.
        proc = evaluate(head, env)
        args = [evaluate(arg, env) for arg in expr[1:]]
        ...
        if isinstance(proc, Closure):
            env = _bind(proc, args)
            expr = _body_form(proc.body)
            continue             # <-- the tail call: no Python frame
        return apply_procedure(proc, args)
```

The key is the `while True` and the two `continue`s. Instead of *calling* for a
tail position, the evaluator **rebinds `expr` and `env` and loops**. When a
closure is applied in tail position, `env` becomes the closure's captured scope
extended with the arguments, `expr` becomes the body, and the loop runs the body
in place. No new Python frame. That is what lets this work:

```scheme
(define (count-up n)
  (let loop ((i 0) (s 0))
    (if (= i n) s (loop (+ i 1) (+ s 1)))))

(count-up 100000)   ;=> 100000, in constant host stack
```

A *non-tail* call — an argument, or the operand of `+`, or the recursive call in
`(define (non-tail n) (if (= n 0) 0 (+ 1 (non-tail (- n 1)))))` — does nest,
because the outer `+` must wait for the result. `apply_procedure` is that path:

```python
def apply_procedure(proc: Any, args: List[Any]) -> Any:
    """Apply *proc* to already-evaluated *args* (the non-tail path)."""
    if isinstance(proc, Primitive):
        ...
        return proc.fn(*args)
    if isinstance(proc, Closure):
        return _apply_closure(proc, args)
    raise LispTypeError(f"not a procedure: {type(proc).__name__}")
```

## The order of dispatch, and why it matters

Look again at the order in `_run`:

1. **symbol** — look up;
2. **literal** — return as-is;
3. **macro** — if the head names a macro, *expand it and loop* — the expanded
   form is then evaluated normally;
4. **special form** — `if`, `define`, `lambda`, `let`, `match`, … — matched
   **before the head is evaluated**, because `if` must not evaluate both
   branches, `define` must not evaluate its name, and `match` must not evaluate
   its patterns;
5. **application** — evaluate the head and arguments, then call.

Steps 3 and 4 in that order are the subtle part. A macro is recognised by looking
its head up *unevaluated*; if the head is a special form, the macro lookup is
skipped (`head not in _SPECIAL_FORMS`). This is why you cannot shadow `if` with a
macro, and why a macro can expand to a special form:

```python
if isinstance(head, Symbol) and head not in _SPECIAL_FORMS:
    macro = _find_macro(env, head)
    if macro is not None:
        expr = _expand_syntax(macro, expr) if isinstance(macro, SyntaxRules) else _expand_macro(macro, expr[1:])
        continue
```

## The special forms

`_SPECIAL_FORMS` is a literal frozenset — the complete list of forms the
evaluator knows by name. Everything else is a macro or a function:

```
quote quasiquote if define set! lambda let let* letrec begin cond when unless
and or defmacro case guard let-values let*-values define-values define-syntax
match define-variant
```

A few worth knowing before we meet them properly:

- **`define`** has two shapes: `(define name value)` binds a value, and
  `(define (name params…) body…)` is sugar for `(define name (lambda …))`. It
  returns the name.
- **`lambda`** builds a `Closure` that captures the current environment. A
  dotted parameter list (`(lambda (a . rest) …)`) collects the rest into a list.
- **`let` / `let*` / `letrec`** differ in *when* the bindings see each other:
  `let` binds in parallel (and is compiled to a direct application), `let*` sees
  earlier bindings, `letrec` lets bindings refer to each other (for mutual
  recursion).
- **`cond` / `when` / `unless` / `and` / `or` / `case`** are the conditional
  family; each has a tail position that the trampoline honours.
- **`guard`** is the condition system's catcher (below).
- **`match`** and **`define-variant`** are the typed control flow of chapter
  [21](21-typed-control-flow.md).

## Closures and lexical scope

`env.py` is 64 lines and holds the whole of scope: a dictionary plus a parent
pointer. A `Closure` stores the environment it was created in, so it keeps
seeing that scope's bindings *after* the `define` that made them returned:

```scheme
(define (make-counter)
  (let ((n 0))
    (lambda ()
      (set! n (+ n 1))
      n)))

(define c (make-counter))
(c)   ;=> 1
(c)   ;=> 2
```

Each call to `make-counter` makes a fresh `n`; the returned closure captures that
one. This is lexical scope (the closure sees where it was *written*), as opposed
to dynamic scope (where it was *called*) — and the fact that the closure still
works after `make-counter` returned is the classic test.

A nuance you will meet in a host: `define` at the top level and `set!` inside a
function both mutate the *nearest* binding found by walking the parent chain. A
host's hooks keep their per-session state in top-level `define`s and mutate it
with `set!`; that is the idiomatic way to write a stateful edge in a
lexically-scoped language.

## Quasiquote: templates

`` `x `` is `(quasiquote x)` and behaves like quote, except that `,x`
(unquote) evaluates the enclosed form, and `,@x` (unquote-splicing) splices a
list. It is how you build a list-shaped template:

```scheme
(display `(1 ,(+ 1 1) ,@(list 3 4)))   ;=> (1 2 3 4)
```

`quasiquote` is implemented in Python (`quasiquote(expr, env, depth)`) and tracks
nesting depth, so a quoted quasiquote inside a quasiquote behaves. Macros (chapter
[06](06-macros.md)) are almost always written with quasiquote.

## Conditions: `guard`, `raise`, `error`

`error` raises a `LispError`; `raise` raises any value; `guard` catches and binds
a condition:

```scheme
(guard (e (#t (error-object-message e)))
  (car '()))
;=> "car: expected a non-empty list"
```

`guard` evaluates the body; if it raises, it binds the condition to `e` and tries
the clauses. `with-exception-handler` and `dynamic-wind` are the lower-level
versions; `let-values` / `call-with-values` handle multiple values; `call/cc`
provides escape continuations. You will use `guard` in chapter
[22](22-railway-oriented.md) to fold a *raising* computation onto a result rail.

## The two budgets

`evaluate` bounds two different kinds of runaway cost, and it is worth knowing
both because the error messages name them:

- **`DEPTH_LIMIT = 1_000_000`** — *nested* evaluation (argument lists, non-tail
  recursion). Exceeding it raises `LispRecursionError`. `shslisp/stack.py` reserves
  a worker thread with a large stack so this ceiling holds; on CPython 3.11+
  Python-to-Python calls do not consume C stack, so the deep recursion works on
  any thread.
- **`STEPS_BUDGET = 5_000_000`** — *work*, counted once per trampoline step. A
  flat infinite tail loop has no depth but must still end, so only this budget
  can see it. Exceeding it raises `LispBudgetError`.

```python
budget = getattr(_local, "budget", None)
if budget is None or budget.depth == 0:
    budget = _Budget()    # a fresh root evaluation — its own budget
```

The budget is per thread (and per root call): nested evaluations share the walk's
budget, and a fresh root resets it, without two threads sharing a counter. So a
program that loops a million times *before* returning to the top will trip the
step budget even though it never nests:

```scheme
(define (count-up n) (let loop ((i 0) (s 0)) (if (= i n) s (loop (+ i 1) (+ s 1)))))
(count-up 100000)   ;=> 100000
(count-up 5000000)  ;=> LispBudgetError: one evaluation spent more than 5,000,000 steps
```

The message is written for you, the author: "an endless loop? (tail calls cost no
depth, so only this budget can see it)".

## Try it

```scheme
(define (fact n) (if (= n 0) 1 (* n (fact (- n 1)))))
(display (fact 10))                                   (newline)

(define (make-counter) (let ((n 0)) (lambda () (set! n (+ n 1)) n)))
(define c (make-counter))
(display (list (c) (c) (c)))                          (newline)

(define (f a . rest) (list a rest))
(display (f 1 2 3))                                   (newline)

(display `(1 ,(+ 1 1) ,@(list 3 4)))                  (newline)
```

```text
3628800
(1 2 3)
(1 (2 3))
(1 2 3 4)
```

The counter is the closure lesson: `(c)` mutates the `n` it captured, and no
other call to `make-counter` can see that `n`.

## Exercises

1. **Count the frames.** `fact` is not tail-recursive; `fact 1000` would hit the
   depth limit. Rewrite it as a named `let` with an accumulator, and check that
   it runs much deeper. Which function's stack does *not* grow, and why?
2. **Make the budget speak.** `(count-up 5000000)` raises
   `LispBudgetError: one evaluation spent more than 5,000,000 steps`. Write a
   tail-recursive loop that does *nothing* forever and confirm the message you
   get. The words "tail calls cost no depth" are the hint the message is giving
   you about where to look.
3. **Capture, deliberately.** Define `(make-adder n)` returning
   `(lambda (x) (+ x n))`, make two adders, and confirm each closed over its own
   `n`. Then shadow `n` afterwards and confirm the closures do not change.

## The shape you copy

> Make the *last* thing the fast path. A loop that rebinds its two variables
> gives you tail calls for free in a host that has none, and costs one Python
> function frame total. Then bound the two ways a program can run away — depth
> and steps — and name each in the message.

Next: [04 Primitives](04-primitives.md).

# 21 — Embedding this language in your own Python

> **What this chapter teaches.** The host-facing seam, `lisp/embed.py`: how a
> *different* Python project exposes its own functions to this language in one
> declared list, and how the language stays a language while it does. The Tetris
> edition is the worked example, not the special case.
>
> **Before this:** 04, 05. · **Time:** ~15 min.
> **After this you can:** point this interpreter at your own project, register
> your own primitives, and know exactly which names you have published.

Everything so far has lived inside this one repository. This chapter takes the
repository away.

The claim the tutorial has been making all along is that the language is the
first-class thing and the domain is a library. This is where that claim is cashed:
`lisp/embed.py` is the whole of the surface a host needs, and the Tetris edition
(a separate project) is just one caller of it.

## The seam is three functions

```python
from lisp import install_primitives, install_extension, load_lisp, make_env, run
```

- **`install_primitives(env, table, source=…)`** binds a *declared* list (or map)
  of `name → callable` pairs. The callables are ordinary Python functions; the
  language reaches them only by the names you wrote down.
- **`install_extension(env, extension)`** runs one extension — a callable
  `env -> env`, or any object with an `install(env)` method.
- **`make_env(extensions=[…])`** builds a ready environment: core primitives, the
  Lisp prelude, the SRFI layer (`profile="dsl"` by default — pass
  `profile="r7rs"` for the strict subset, or `None` for the bare core), then
  each extension in order. The default profile is what makes a foreign host a
  full DSL: `fold`, `cut`, `chain`, `match`, `define*`, and keywords all work
  before the host writes a line of its own.

Three properties make this safe to reason about, and they are the same three any
well-run crossing obeys:

1. **Declared, not discovered.** Nothing is looked up by
   `getattr(module, type(x).__name__)` at event rate. A reviewer reads one list
   and sees every name the host publishes.
2. **Total and loud.** A duplicate name, a non-callable, or a malformed entry
   raises *at install time*, naming the `source` you passed — never a silent
   shadow discovered later by a puzzled user.
3. **Composable.** A host ships its vocabulary as a *value* and hands it to
   `make_env`, so a project composes as data the same way a design does.

## A worked host

Imagine a small inventory project. Its Python functions are the "primitives"; the
DSL is how a shopkeeper writes rules about them:

```python
from lisp import install_primitives, make_env, run

def stock_total(rows):
    return sum(row["qty"] for row in rows)

def restock(rows, sku, qty):
    rows.append({"sku": sku, "qty": qty})
    return rows

env = make_env()                       # a general Scheme; no game needed
install_primitives(env, [
    ("stock-total", stock_total),
    ("restock!", restock),
], source="inventory.py")

run("(stock-total (restock! (list) \"widget\" 3))", env)   # -> 3
```

That is the entire integration. No subclassing, no registry decorator, no
`sys.modules` spelunking. The interpreter needed no change to "support"
inventory, which is the test of a good embedding.

## Try it

The standard library the host inherits is the point: because the language owns its
own features, a foreign project gets **parameters, promises, and ports** — written
in Lisp, no host required. This program uses all three, and never mentions the
game:

```sh
shs run /dev/stdin <<'EOF'
;; A parameter is a dynamic cell; `parameterize` is the only way to rebind it.
(define depth (make-parameter 0))
(define (label tag) (parameterize ((depth (+ (depth) 1))) (list tag (depth))))
(display (label 'a)) (newline)
(display (parameterize ((depth 9)) (label 'b))) (newline)
(display (depth)) (newline)

;; A promise forces at most once, however many times it is forced.
(define calls 0)
(define cache (delay (begin (set! calls (+ calls 1)) 'computed)))
(display (list (force cache) (force cache) calls)) (newline)

;; A string port collects output without touching the terminal.
(define sink (open-output-string))
(parameterize ((current-output-port sink))
  (display "into ")
  (write 42))
(display (get-output-string sink)) (newline)
EOF
```

```text
(a 1)
(b 10)
0
(computed computed 1)
into 42
```

`display` and `write` are host primitives, but they write to
`(current-output-port)` — a parameter — so rebinding it is all it takes to redirect
them. That is the split the whole chapter is about: the *mechanism* (a port
object, a `write`) is Python; the *policy* (which port is current) is Lisp.

## What is not here, on purpose

The language is deliberately small, and the gaps are declared rather than
discovered (chapter [04](04-primitives.md) argues why). A host should know them
before it plans around them:

- **No Python import from Lisp.** `(eval …)` evaluates Lisp; `(load …)` reads
  `.scm` only. A host function becomes a primitive only by being *declared* in
  `install_primitives`. There is no `(import "os")`.
- **Strings are immutable** (like Python's), so there is no `string-set!`; the
  mutable sequences are vectors and lists.
- **`call/cc` is escape-only** — one-shot exits, not re-entrant continuations.
- **The tower is int and float.** No rationals or complex numbers, and
  `exact?`/`inexact?` say so honestly.
- **Macros are a subset of `syntax-rules`.** Hygienic macros, local
  `let-syntax`/`letrec-syntax`, nested and stacked ellipses, and vector patterns
  all work; `syntax-case` and a custom ellipsis identifier do not. `macroexpand`
  shows what a template became.

Each of these is a fence a test can check, which is worth more than a feature
nobody trusts.

## Packaging

The language installs on its own:

```sh
pip install git+https://github.com/sharavsambuu/shs-python-scheme-dsl.git
# (once published, plain `pip install shs` will work too — see docs/INSTALL.md)
```

`pyproject.toml` publishes exactly the `lisp` package — pure standard library,
no runtime dependencies. A host edition is a separate project that depends on
this one and installs its own vocabulary through the seam above. When
`make_env()` is called somewhere no host is installed, it is simply a general
Scheme — the default is *auto*.

## Exercises

1. **Publish a function.** In a scratch file, `install_primitives` a function
   that reverses a string, then `run("(reverse \"abc\")")` — wait, is `reverse`
   already taken? Why does that matter, and what does `install_primitives` do
   about it?

2. **Write an extension.** Package two related primitives as a single callable
   `env -> env` and pass them with `make_env(extensions=[…])`. Then wrap the same
   pair in a class with an `install` method and pass the instance instead — the
   seam accepts both.

3. **Redirect your own host.** Give a primitive an optional output port and have
   it write through `(current-output-port)`, exactly as `display` does. Prove it
   with a string port and `parameterize`.

4. **Find the fence.** Search `lisp/` for any module other than `runtime.py`
   and `__main__.py` that names a host edition. Explain why `lisp/embed.py`
   must come up empty — and what a "convenient" `import yourhost` shortcut
   inside `embed.py` would cost the next embedder.

Next: [22 SRFI 1 — the list library](22-srfi-1-the-list-library.md). The
tutorial continues with a six-chapter tour of the SRFI layer.

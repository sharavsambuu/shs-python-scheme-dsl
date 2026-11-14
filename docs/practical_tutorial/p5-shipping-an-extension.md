# P5 — Shipping an extension

**Before this:** [P2](p2-programs-across-files.md) — you think in boundaries
now; chapter [28](../lisp_tutorial/28-embedding-in-python.md) of the main
tutorial is the big picture.
**Time:** 30 minutes.
**After this you can:** hand a Lisp program a table of Python functions it
calls like primitives, ship a vocabulary as a reusable extension, and know the
three rules the crossing enforces.

The embedding seam is `shslisp/embed.py` — three functions and a discipline. The
guest side needs no changes at all: a host-provided primitive is called exactly
like a builtin. The contract is pinned by `tests/test_embed.py`, which tests it
from the host's side on purpose — that file is this chapter's source of truth.

## `install_primitives`: the declared crossing

```python
from shslisp import install_primitives, make_env, run

env = make_env(install_tetris=False)
install_primitives(
    env,
    [
        ("host-double", lambda n: n * 2),
        ("host-greet", lambda name: f"Hello, {name}!"),
    ],
    source="myproject.py",
)
print(run("(host-double 21)", env))        # 42
print(run('(host-greet "Ada")', env))      # Hello, Ada!
```

Three rules, all enforced at install time (`tests/test_embed.py` pins each):

1. **A duplicate name is refused** — and the error names the *source file*
   (`myproject.py: duplicate primitive 'twice'`), so two modules shipping the
   same word is a diagnosis, not a mystery.
2. **A non-callable is refused** — `("oops", 42)` fails before it can fail at
   call time.
3. **A malformed entry is refused** — a pair that is not `(name, callable)` is
   rejected on sight.

The values crossing the boundary are the ordinary host types — numbers,
strings, lists — the same ones chapter [28](../lisp_tutorial/28-embedding-in-python.md)
catalogues. A primitive that raises a Python exception surfaces on the Lisp
side as an error a `guard` can catch ([P1](p1-when-things-go-wrong.md)).

## Extensions: a vocabulary you can ship

A list of primitives is a snapshot; an *extension* is something a host project
can reuse — a plain function taking `env`, or any object with an `install(env)`
method:

```python
from shslisp import install_extension, make_env, run

def clock_extension(env):
    from shslisp import install_primitives
    install_primitives(env, [("now", lambda: __import__("time").time())],
                       source="clock.py")

env = make_env(install_tetris=False, extensions=[clock_extension])
print(run("(now)", env) > 0)    # True — the guest called the host's clock
```

Extensions run *after* the prelude, so an extension's install may itself call
Lisp — `tests/test_embed.py::test_extensions_run_after_the_prelude_so_they_can_use_it`
proves the order. That is the seam the Tetris edition uses: the game is an
extension, nothing more.

## Ship it to the command: `--plugin` and `SHS_PLUGINS`

`make_env(extensions=[…])` is the *embedded* host's door. When the user runs the
command, the same extension shape can be loaded by `shs` itself: a **plugin** is
an importable module whose `install(env)` binds the vocabulary, and `--plugin`
installs it before any Lisp is read.

```python
# clock_plugin.py — the extension from above, as a module
from shslisp import install_primitives

def install(env):
    install_primitives(
        env, [("host-double", lambda n: n * 2)], source=__name__
    )
```

```sh
shs --plugin clock_plugin -e "(host-double 21)"     # -> 42
shs --plugin clock_plugin run policy.scm            # the script sees it too
SHS_PLUGINS=clock_plugin shs -e "(host-double 21)"  # every invocation
```

- `--plugin MOD[:ATTR]` is repeatable; `ATTR` defaults to `install`, so a module
  that names its installer differently is `--plugin clock_plugin:register`.
- `SHS_PLUGINS` is `os.pathsep`-separated (`:` on Unix, `;` on Windows) and is
  merged with the flags — one install per spec, in order. On PowerShell:
  `$env:SHS_PLUGINS = "clock_plugin"`; in cmd: `set SHS_PLUGINS=clock_plugin`.
- The same list reaches `run`, `-e`, and the REPL, so a REPL started with a
  plugin has the vocabulary at the prompt — exactly as if the program had called
  `make_env(extensions=[...])`.
- Failure is early and loud: `shs: plugin 'SPEC': …` on stderr with exit `1`,
  *before* any Lisp runs, so a typo in `SHS_PLUGINS` can never produce a
  half-configured session.

Which door to use: a host library imported by your Python program →
`extensions=`; a command a person runs from a shell → `--plugin` / `SHS_PLUGINS`.
The extension object is the same in both cases — that is what shipping a
*vocabulary* rather than a convenience import means.

## The guest side: a script that knows its arguments

The guest does not know or care whether it talks to builtins or host
primitives. It does know `*command-line-args*` — the list `shs run script.scm
a b c` binds:

```scheme
(define who
  (if (null? *command-line-args*)
      "world"
      (car *command-line-args*)))
(display "hello, ")
(display who)
(newline)
```

```text
hello, world
```

Run the same file with `shs run greet.scm gala` and it answers
`hello, gala` — one script, two invocations, no environment variable, no flag.

## The discipline

- **The table is the API.** Review `install_primitives`' list like a public
  interface — because it is one.
- **Convert at the door.** A primitive that takes a Lisp list and returns a
  Lisp list keeps the guest's vocabulary; a primitive that leaks a Python
  object into a variable hands the guest a value no Lisp form can take apart.
- **Name the source.** Every install carries `source=...`; the day two
  extensions collide, the error tells you where each one lives.

## Try it

The guest-side half of the contract — arguments arrive as a list, default
gracefully:

```scheme
(define (main args)
  (display "args: ")
  (display (length args))
  (newline))
(main *command-line-args*)
```

```text
args: 0
```

## Exercises

1. Install a `host-max` primitive over Python's `max` and call it with three
   Lisp numbers.
2. Write an extension that installs `(host-timestamp)` returning
   `current-second`'s host equivalent, and call it from the guest.
3. Install the same name twice from two different `source=` strings; read the
   error and say which source it blames.
4. Write a guest script that treats `*command-line-args*` as a shopping list
   and prints the count — run it with zero, one, and three arguments without
   changing the file.
5. **Ship the extension to the command.** Move `clock_extension` into a module
   with `install(env)`, run it with `--plugin`, then export `SHS_PLUGINS` and
   run a script with no flags. What does the guest program know about the
   difference? (Nothing — which is the point.)

## See also

- [28 Embedding in Python](../lisp_tutorial/28-embedding-in-python.md) — the
  full value-crossing table and the `--plugin` section
- [P6 — Testing Lisp from the host](p6-testing-lisp-from-the-host.md) — the
  same seam, from the test's side
- The seam itself: `shslisp/embed.py`; the CLI's plugin loader:
  `shslisp/__main__.py`; the contract: `tests/test_embed.py`

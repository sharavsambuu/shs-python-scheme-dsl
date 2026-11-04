# 07 — Modules: `(load …)`

> **What this chapter teaches.** `shslisp/loader.py`: how a program is split across
> files. Three rules, and they are the whole system — resolution, load-once,
> cycles.
>
> **Before this:** 05. · **Time:** ~12 min.
> **After this you can:** split a program across files and say why a second
> `(load …)` defines nothing.

`loader.py` opens:

> *A language that cannot read a file is a language where every program is one
> file. This module is the smallest thing that fixes that, and it is deliberately
> three rules:*

## Rule 1 — Resolution

A relative path is tried against **the loading file's own directory first**, then
each **search path**; the `.scm` suffix is optional; an absolute path is used as
given.

```python
def bases(self) -> List[Path]:
    """Where a relative spec is looked up: the caller's dir, then the path."""
    here = [self._stack[-1].parent] if self._stack else []
    return _unique([*here, *self.search_paths])
```

The "loading file's own directory" part is the one that makes the tree composable:
a library can say `(load "keymap")` next to itself, while a script can say
`(load "examples/announcement")` from anywhere because the working directory is
on the search path. The `.scm`-optional rule is why both
spellings below are the same file — the loader tries the name with `.scm` and
then without it.

```scheme
(load "domains/pacing/gravity")   ; root-relative, from any script
(load "profile")                  ; a neighbour of the loading file
```

`resolve` reports *everywhere it looked* when it fails, so a typo names the
search path rather than vanishing:

```python
raise LispError(f"load: no such module {spec!r}; searched {self._where()}")
```

## Rule 2 — Load once

A module is read and evaluated **at most once per environment**, however many
times it is loaded. The second `(load …)` returns the first result and defines
nothing again. The cache is keyed by the **resolved absolute path**, so
`domains/pacing/gravity.scm` and `./domains/pacing/gravity.scm` are one module,
not two.

```scheme
(load "domains/pacing/gravity")
(load "domains/pacing/gravity")   ; a no-op; returns the first load's value
```

This is what makes a library tree safe to compose: a program and the library it
is built from both loading `keymap` defines it once. Loading it twice is a
no-op, and the file joins the same cache the host uses.

## Rule 3 — Cycles are errors

`a → b → a` raises, naming the chain, instead of recursing until the interpreter's
stack dies:

```python
if path in self._stack:
    raise LispError(f"load: circular dependency: {self._chain(path)}")
```

`_chain` prints the cycle from its first repeat: `b -> c -> b`.

## How it is wired in

The loader belongs to **exactly one environment**, and the environment remembers
it (`env.loader`), which is why any scope can ask `(load …)` and get the same
cache. `Loader.install(env)` also defines the introspection primitives:

| Primitive | Answers |
| --- | --- |
| `(load "a" "b" …)` | evaluate each module; return the last value |
| `(loaded? "x")` | has this module already been evaluated? |
| `(loaded-modules)` | the resolved paths, in load order |
| `(search-path)` | the directories a bare spec is tried against |

`runtime.make_env` orders the search path as **the embedder's paths first, then
the working directory**:

```python
loader.add_search_paths([*search_paths, Path.cwd()])
```

Extra directories come from the caller: the CLI adds `SHS_PATH` entries, and a
host passes its own library directory through `make_env(search_paths=[…])` —
so `shs run` still loads plain-Lisp modules from any directory on the path:

```python
def _search_paths():
    return [
        Path(part)
        for part in os.environ.get("SHS_PATH", "").split(os.pathsep)
        if part
    ]   # os.pathsep: ":" on Unix, ";" on Windows
```

so an embedder can put its own library first, ahead of the working directory.

## The other mechanism: `define-library`

The loader answers "how does a *program* split across files?". The R7RS
library system — `define-library` / `import` / `export` — answers "how does a
*module* declare what it provides?". A library names its exports and imports
exactly those; the import sets `only`/`except`/`prefix`/`rename` are
supported, and the R7RS `(scheme …)` libraries and the SRFIs are entries in
the same registry:

```scheme
(define-library (demo math)
  (export double)
  (import (scheme base))
  (begin (define (double x) (* x 2))))

(import (demo math))
(double 21)                        ;=> 42
```

Unlike `(load …)`, a library does not leak names into the surrounding
environment — only `import` binds. The two mechanisms compose: the SRFI
libraries are files under `shslisp/` loaded by the registry, while a host's
scripts are loader modules. Use the loader for programs, `define-library` for
reusable vocabulary — and see chapter [05](05-standard-library.md) and
[Appendix A](appendix-a-reference.md) for the SRFI side of it.

## The entry file is module zero

When you run `shs run FILE`, the file is loaded *through the loader*,
so it joins the load-once cache and its own `(load …)` calls resolve relative to
*it*:

```python
def _run_script(path, out, tetris, profile, script_args):
    env = make_env(
        out=out, install_tetris=tetris,
        profile=_profile_value(profile), search_paths=_search_paths(),
    )
    if script_args is not None:
        env.define(intern("*command-line-args*"), make_list(list(script_args)))
    return load_file(env, path), env
```

`load_file` prefers the environment's loader, and a file with no forms evaluates
to `()` — the language's "nothing" — so a caller always sees a value.

This is exactly why an entry file can be one line:

```scheme
(load "examples/announcement.scm")   ; resolved via the search path
```

## Try it

```scheme
(write (loaded? "examples/announcement")) (newline)
(display (load "examples/announcement")) (newline)
(write (loaded? "examples/announcement")) (newline)
(display (length (loaded-modules))) (newline)
(display (length (search-path))) (newline)
```

```text
#f
announcement-loaded
#t
4
1
```

Three modules are loaded before the first form runs — `prelude.scm`,
`rope.scm`, and `generators.scm` — so the count starts at three and the
announcement makes four. The
search path here is just the working directory (`SHS_PATH` adds more). `(load …)`
returns the module's *last value*, which is why the second line is the string
the file ends with.

## Exercises

1. **The answer key.** Create a module defining `(hello name)`, put its
   directory on the search path, and load it by bare name *and* by full path.
   Confirm `(loaded-modules)` lists it once. A worked file ships at
   `exercises/greeting.scm`, beside this tutorial.
2. **Two spellings, one module.** Load `examples/announcement` and then
   `./examples/announcement`. The second load defines nothing, because the
   cache is keyed by the *resolved absolute path*. Prove it by checking the
   length of `(loaded-modules)` twice.
3. **Make a cycle.** Write a module `cycle-a` that loads `cycle-b`, and
   `cycle-b` that loads `cycle-a`, and run the first. The error names the chain
   that closed the loop. Delete both files when you are done.

## The shape you copy

> A module system is three rules people keep re-inventing: resolve relative to the
> *speaker*, evaluate each module once, and refuse a cycle by naming it. Everything
> else — package managers, manifests, versions — is a policy layer on top.

Next: [08 Lisp by example](08-lisp-by-example.md).

# P2 — Programs across files

**Before this:** [P0](p0-the-repl-as-a-workbench.md); the tutorial's
[chapter 07](../lisp_tutorial/08-modules.md) helps but is not required.
**Time:** 30 minutes.
**After this you can:** split a program into files twice over — `(load ...)`
for scripts that grow, `define-library`/`import` for code that must keep its
boundaries — and name exactly what each mechanism promises.

Chapter 07 taught `(load ...)`. This chapter teaches the *second* mechanism the
interpreter ships — the R7RS library system — and when to reach for each.

## `(load ...)`: the script's include

`(load "payments.scm")` evaluates a file into the current environment. Two
guarantees make it safe to build on:

- **Load-once.** A file loaded twice is a no-op — the loader remembers
  (`loaded?` answers the question directly).
- **Relative to the file.** A `(load ...)` inside a script in `src/` resolves
  against `src/`, not against wherever you ran the command from.

`SHS_PATH` (an `os.pathsep`-separated environment variable, like `PATH`) puts
your own library directory in front of the working directory — no code needed.

## `define-library`: the boundary

A library declares what it exports; everything else stays private. The whole
system, in one file:

```scheme
(define-library (shop money)
  (export cents->string)
  (import (scheme base))
  (begin
    (define (cents->string n)
      (string-append "$" (number->string (/ n 100))))
    (define (secret-margin n)   ; not exported — invisible outside
      (* n 47))))
(import (shop money))
(display (cents->string 1250))
(newline)
```

```text
$25/2
```

Wait — `1250 / 100` is the *exact rational* `25/2`; the numeric tower is
honest (chapter [02](../lisp_tutorial/02-values-and-reading.md)). Divide with
`quotient` when you want whole dollars:

```scheme
(define-library (shop money2)
  (export dollars)
  (import (scheme base))
  (begin (define (dollars cents) (quotient cents 100))))
(import (shop money2))
(display (dollars 1250))
(newline)
```

```text
12
```

Import sets shape what crosses the boundary — the four R7RS modifiers:

```scheme
(import (only (scheme base) car cdr))              ; just these
(import (except (scheme base) map))                ; everything but map
(import (prefix (only (scheme base) car) get-))    ; car becomes get-car
(import (rename (only (scheme base) car) (car first)))  ; car becomes first
```

Two libraries exporting the same name collide *loudly* — the import names the
clash instead of silently choosing (`tests/test_library.py` pins the message).
Resolve it yourself with `only`/`rename`, the way the DSL profile resolves
SRFI 1's `map` (`shslisp/profile.py`).

## `(environment ...)` and `eval`: the escape hatch

`eval` runs a form in a *restricted* environment you name — the guest-language
way to run a quoted expression with only the bindings you hand it:

```scheme
(display (eval '(+ 1 2) (environment '(scheme base))))
(newline)
```

```text
3
```

A second import of the same library is not a collision; the environment exists
so a meta-program (a config loader, a rule engine) can offer *exactly* its
vocabulary and nothing else.

## Which one, when

| Use `(load ...)` when | Use `define-library` when |
| --- | --- |
| a script grows past one file | the code outlives the script |
| you want the file's names *in* your environment | consumers should see only the exports |
| the boundary is "mine, mine, mine" | the boundary is the API |

They compose: a library's `(begin ...)` body may `(load ...)` its own helpers.

## Try it

A library with a private helper — the consumer calls the export and cannot see
the inside:

```scheme
(define-library (text wrap)
  (export around)
  (import (scheme base))
  (begin
    (define (pad s) (string-append "  " s "  "))
    (define (around s) (string-append "[" (pad s) "]"))))
(import (text wrap))
(display (around "core"))
(newline)
```

```text
[  core  ]
```

`only` narrows an import to the names you can defend:

```scheme
(import (only (scheme base) exact? floor))
(display (exact? (floor 5/2)))
(newline)
```

```text
#t
```

## Exercises

1. Write a library `(geom circle)` exporting `area`, with the radius formula's
   constant kept private. Call `area` on radius 1 and check the answer is
   `#e3.14`'s cousin — the exact rational `314/100` if you compute it as
   `(* 314 r r)` over `100`… or just print it and read the tower's answer.
2. Import `car` under the name `first` and prove the old name is gone.
3. Cause a collision on purpose: two libraries exporting `version`, then import
   both. Read the error — it names the name.
4. Put a directory on `SHS_PATH`, move your library there, and show the same
   program still runs.

## See also

- [08 Modules](../lisp_tutorial/08-modules.md) — the loader's story
- [P5 — Shipping an extension](p5-shipping-an-extension.md) — the same
  boundary discipline, from the host side
- The library system: `shslisp/library.py`, `shslisp/manifest.py`;
  the guarantees: `tests/test_library.py`

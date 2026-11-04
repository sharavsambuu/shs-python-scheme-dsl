# P3 — Files, ports, and the one door

**Before this:** [P1](p1-when-things-go-wrong.md) — you know what an error
object is; the tutorial's [chapter 25](../lisp_tutorial/26-functional-core-imperative-shell.md)
names the architecture.
**Time:** 25 minutes.
**After this you can:** read and write files from Lisp, guarantee cleanup with
`dynamic-wind`, and place every effect behind one door so the functional core
stays pure and testable.

The interpreter ships the R7RS port library — `call-with-output-file`,
`call-with-input-file`, `read-line`, `delete-file` and friends. This chapter is
half "here is the API" and half "here is where it belongs", because in an
embedded DSL the *placement* of I/O is the architecture.

## The API: round-tripping a file

```scheme
(call-with-output-file "guest.txt"
  (lambda (p)
    (display "line one" p) (newline p)
    (display "line two" p) (newline p)))
```

`call-with-*` opens the port, hands it to your procedure, and closes it on the
way out — normal return *or* error. Reading goes the same way:

```scheme
(display (call-with-input-file "guest.txt" read-line))
(newline)
```

```text
line one
```

`read-line` answers one line, newline stripped; the port's position carries on
to the next call. When you are done with a file outright:

```scheme
(delete-file "guest.txt")
(display (if (file-exists? "guest.txt") "still there" "gone"))
(newline)
```

```text
gone
```

Relative paths resolve against the *script's* directory — the same rule
`(load ...)` uses — so a program that reads its own data files works from any
working directory.

## `dynamic-wind`: cleanup you can promise

`call-with-*` covers the single-procedure case. When *you* manage a resource —
a temporary file, a global flag, a "currently open" marker — `dynamic-wind`
guarantees the after-thunk runs on every exit, including errors:

```scheme
(define trace '())
(define (note x) (set! trace (cons x trace)))

(define (with-log thunk)
  (dynamic-wind
    (lambda () (note 'open))
    thunk
    (lambda () (note 'close))))

(guard (e (else 'handled))
  (with-log (lambda () (error "boom"))))
(display (reverse trace))
(newline)
```

```text
(open close)
```

Wait — read that again: the body *raised*, the `guard` handled it, and the
after-thunk ran anyway: `(open close)`, with no `during`. That is the whole
promise. `parameterize` (chapter [04](../lisp_tutorial/04-primitives.md)) is
built on exactly this mechanism.

## The one door

Chapter 25's rule: the functional core takes values and returns values; the
imperative shell owns every effect. Concretely in Lisp:

```scheme
(define (total lines)          ; pure — testable without a filesystem
  (fold + 0 (map string-length lines)))

(define (total-of-file path)   ; the door — reads, delegates, closes
  (call-with-input-file path
    (lambda (p) (total (port->lines p)))))
```

The core (`total`) is a pure function you can test with two strings; the door
(`total-of-file`) is three lines whose only job is to fetch what the core
needs. Test the core as data; *count* the doors — chapter 25's audit — and keep
the count small.

## Try it

A self-contained round trip: write, read back the first line, clean up.

```scheme
(call-with-output-file "handbook.txt"
  (lambda (p)
    (display "first line" p) (newline p)
    (display "second line" p) (newline p)))
(display (call-with-input-file "handbook.txt" read-line))
(newline)
(delete-file "handbook.txt")
(display (file-exists? "handbook.txt"))
(newline)
```

```text
first line
#f
```

`dynamic-wind` under error pressure — the after-thunk is not optional:

```scheme
(define audit '())
(define (record x) (set! audit (cons x audit)))

(guard (e (else 'recovered))
  (dynamic-wind
    (lambda () (record 'acquire))
    (lambda () (record 'use) (error "fault"))
    (lambda () (record 'release))))
(display (reverse audit))
(newline)
```

```text
(acquire use release)
```

## Exercises

1. Write a file with three lines, then a program that prints the *second* one
   (two `read-line` calls — the first consumes, the second answers).
2. Wrap `(delete-file ...)` in `dynamic-wind` so a file your program creates is
   removed even when the body raises.
3. Split a "read config file and compute" program into a pure core and a
   one-line door; test the core with a literal list, no filesystem.
4. Count the effect doors in your last Lisp program. If the answer is more than
   three, name which one could become a parameter.

## See also

- [26 Functional core, imperative shell](../lisp_tutorial/26-functional-core-imperative-shell.md)
  — the audit this chapter obeys
- [P1 — When things go wrong](p1-when-things-go-wrong.md) — what the after-thunk
  survives
- The manifest of every port name: `shslisp/manifest.py`; the behaviour table:
  `tests/test_r7rs.py`

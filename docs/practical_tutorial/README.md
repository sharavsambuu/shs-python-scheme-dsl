# The practical handbook: working with the interpreter

> **The claim, in one paragraph.** [`docs/lisp_tutorial/`](../lisp_tutorial/README.md)
> teaches the language and the ideas: what the code means, and what programs
> should look like. This handbook teaches the workflow: how you actually live
> with the interpreter day to day — developing from the REPL, reading a failure,
> splitting a program across files, touching files and ports, measuring, shipping
> a host extension, and testing Lisp code from Python. Everything it will teach
> already exists in [`lisp/`](../../lisp/) and is already tested; the handbook's
> job is to turn those tools into a path a newcomer can walk.

> **Honesty note.** Every chapter below is *planned, not written*. The chapter
> table is the schedule, the ledger is the contract, and — following the rule
> this repository learned the hard way ([`SRFI_TASKS.md`](../SRFI_TASKS.md)) —
> a chapter enters this folder only when its examples ship machine-checked.
> Until then, this page claims nothing about the interpreter's behaviour; it
> points at the files and tests that do.

## The division of labour

The main tutorial answers *what does this mean?* (`docs/lisp_tutorial/`, 28
chapters). This handbook answers *how do I work with it?* The split follows the
same seam the language itself draws: the main tutorial's Part III is ideas, and
chapter 27 is the first taste of tooling — this handbook continues in that
direction and leaves the language alone.

Three language topics the main tutorial leaves untaught — `define-library`/
`import`, ports and files, and `dynamic-wind` — are deliberately absorbed here,
as chapters [P2](#the-ledger) and [P3](#the-ledger), where they have practical
jobs rather than abstract ones.

## The chapters

| Task | Chapter | What it will teach | Where the truth lives today |
| --- | --- | --- | --- |
| **P0** | The REPL as a workbench | The day-one loop: `,help`, `,load`, `-e`, `shs run`, iterate on a definition without leaving the prompt | [`lisp/repl.py`](../../lisp/repl.py), the CLI section of [`appendix-a-reference.md`](../lisp_tutorial/appendix-a-reference.md) |
| **P1** | When things go wrong | Reading a failure: the three kinds (read / evaluation / runtime), error objects, stack traces, `error-object-message` and irritants | [`lisp/errors.py`](../../lisp/errors.py), [`lisp/stack.py`](../../lisp/stack.py), [`tests/test_evaluator.py`](../../tests/test_evaluator.py) |
| **P2** | Programs across files | `(load ...)` and `loaded?` first, then the real library system: `define-library`, `import`, the generated export manifest, and `(environment ...)` | [`lisp/loader.py`](../../lisp/loader.py), [`lisp/library.py`](../../lisp/library.py), [`lisp/manifest.py`](../../lisp/manifest.py), [`tests/test_library.py`](../../tests/test_library.py) |
| **P3** | Files, ports, and the one door | The `(scheme file)` and `(scheme base)` port procedures, `dynamic-wind` for guaranteed cleanup, and the functional-core rule for where I/O belongs | the manifest in [`lisp/manifest.py`](../../lisp/manifest.py), chapter [25](../lisp_tutorial/25-functional-core-imperative-shell.md) |
| **P4** | Measuring | The profiler, `(scheme time)`, `procedure-arity`, and the defensive checks a DSL program can afford | [`lisp/profile.py`](../../lisp/profile.py), [`tests/test_profile.py`](../../tests/test_profile.py) |
| **P5** | Shipping an extension | A worked host primitive: `install_primitives`, packaging, and what the guest sees | [`lisp/embed.py`](../../lisp/embed.py), chapter [27](../lisp_tutorial/27-embedding-in-python.md) |
| **P6** | Testing Lisp from the host | The pattern this repository eats: `run_script` against `run_script` assertions — giving an embedded program the same safety net as the interpreter | [`tests/test_exercises.py`](../../tests/test_exercises.py), [`tests/test_tutorial.py`](../../tests/test_tutorial.py) |

## The ledger

*(All tasks open. Nothing has landed; there is no "Landed" table yet, and this
page will not pretend otherwise.)*

### The gates

A chapter lands when all of these hold — the same gates the SRFI ledger uses,
minus nothing:

1. **Its user value is stated in one sentence** a newcomer would recognise
   ("how do I read this error?" beats "covering error objects").
2. **Every `Try it` example is executable and machine-checked.** The harness in
   [`tests/test_tutorial.py`](../../tests/test_tutorial.py) guards
   `docs/lisp_tutorial/` only; landing P0 includes extending the guard to this
   folder (a `_pages()` addition or a sibling `tests/test_practical.py`) so the
   handbook can never drift the way the top-level docs once did.
3. **Every file and test it cites exists** — the same three checks
   [`tests/test_docs.py`](../../tests/test_docs.py) runs on the top-level pages.
4. **It leaves the language claims to the pages that own them.** Behaviour is
   cited (`lisp/…`, `tests/…`), not re-asserted; where a chapter and a test
   disagree, the test wins.

### Order

P0 → P1 first: the workbench and the failure-reading chapter are the two a
newcomer needs in their first hour. P2 follows because a growing program hits
the file boundary fast. P3–P6 are independent after that; P5 and P6 pair well
together (an extension wants a test).

## See also

- [`docs/lisp_tutorial/README.md`](../lisp_tutorial/README.md) — the language
  and ideas track this handbook assumes
- [`docs/SRFI_TASKS.md`](../SRFI_TASKS.md) — the ledger style this page follows
- [`docs/capabilities.md`](../capabilities.md) — what the interpreter is fit for,
  and the walls
- [`README.md`](../../README.md) — the map of all of it

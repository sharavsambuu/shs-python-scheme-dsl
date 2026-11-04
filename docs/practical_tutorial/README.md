# The practical handbook: working with the interpreter

> **The claim, in one paragraph.** [`docs/lisp_tutorial/`](../lisp_tutorial/README.md)
> teaches the language and the ideas: what the code means, and what programs
> should look like. This handbook teaches the workflow: how you actually live
> with the interpreter day to day — developing from the REPL, reading a failure,
> splitting a program across files, touching files and ports, measuring, shipping
> a host extension, and testing Lisp code from Python. Everything it will teach
> already exists in [`shslisp/`](../../shslisp/) and is already tested; the handbook's
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
as chapters [P2](p2-programs-across-files.md) and [P3](p3-files-ports-and-the-one-door.md),
where they have practical jobs rather than abstract ones.

## The chapters

| Task | Chapter | What it will teach | Where the truth lives |
| --- | --- | --- | --- |
| **P0** | [The REPL as a workbench](p0-the-repl-as-a-workbench.md) | The day-one loop: `,help`, `,load`, `,quit`, `-e`, `shs run`, iterate on a definition without leaving the prompt, and why a mistake is an error line, not a crash | [`shslisp/repl.py`](../../shslisp/repl.py), [`tests/test_repl.py`](../../tests/test_repl.py), the CLI section of [`appendix-a-reference.md`](../lisp_tutorial/appendix-a-reference.md) |
| **P1** | [When things go wrong](p1-when-things-go-wrong.md) | Reading a failure: the three kinds (read / name / runtime), error objects, `error-object-message` and irritants, what a `guard` can and cannot catch | [`shslisp/errors.py`](../../shslisp/errors.py), [`shslisp/stack.py`](../../shslisp/stack.py), [`tests/test_repl.py`](../../tests/test_repl.py) |
| **P2** | [Programs across files](p2-programs-across-files.md) | `(load ...)` and `loaded?` first, then the real library system: `define-library`, `import`, the four modifiers, collisions, and `(environment ...)` | [`shslisp/loader.py`](../../shslisp/loader.py), [`shslisp/library.py`](../../shslisp/library.py), [`shslisp/manifest.py`](../../shslisp/manifest.py), [`tests/test_library.py`](../../tests/test_library.py) |
| **P3** | [Files, ports, and the one door](p3-files-ports-and-the-one-door.md) | The `(scheme file)` and `(scheme base)` port procedures, `dynamic-wind` for guaranteed cleanup, and the functional-core rule for where I/O belongs | the manifest in [`shslisp/manifest.py`](../../shslisp/manifest.py), chapter [25](../lisp_tutorial/25-functional-core-imperative-shell.md) |
| **P4** | [Features and the walls](p4-features-and-the-walls.md) | `features` and `cond-expand` for one-script-many-runtimes, `procedure-arity`, and the two named ceilings — the depth limit and the step budget. There is no profiler; the chapter says so and points timing at `(scheme time)` and the host | [`shslisp/evaluator.py`](../../shslisp/evaluator.py) (`DEPTH_LIMIT`, `STEPS_BUDGET`), [`shslisp/profile.py`](../../shslisp/profile.py) (the feature list, not a profiler), [`tests/test_profile.py`](../../tests/test_profile.py) |
| **P5** | [Shipping an extension](p5-shipping-an-extension.md) | A worked host primitive: `install_primitives`, extensions as a shippable vocabulary, the three install-time refusals, and the guest side of `*command-line-args*` | [`shslisp/embed.py`](../../shslisp/embed.py), [`tests/test_embed.py`](../../tests/test_embed.py), chapter [27](../lisp_tutorial/27-embedding-in-python.md) |
| **P6** | [Testing Lisp from the host](p6-testing-lisp-from-the-host.md) | The pattern this repository runs on: `run_script` from pytest, guest-side `checked` self-checks, and the rule for which side a test belongs on | [`tests/test_exercises.py`](../../tests/test_exercises.py), [`tests/test_tutorial.py`](../../tests/test_tutorial.py), [`tests/test_embed.py`](../../tests/test_embed.py) |

## The ledger

*(All seven chapters have landed. Every gate below was checked the day it
landed; the machine-checked ones stay checked by `tests/test_practical.py`.)*

| Task | Landed | What the landing proves |
| --- | --- | --- |
| P0 | yes | the harness guard now covers this folder: [`tests/test_practical.py`](../../tests/test_practical.py) reuses the main tutorial's block contract — one definition of an executable example, two tracks |
| P1 | yes | the three failure kinds, error objects in action, the two catchable-by-nothing walls, and two honest warts (a Python signature leaking into a builtin's arity error; no line numbers on read errors) |
| P2 | yes | `define-library` + `import` in one verified file, all four modifiers, the loud collision, and `(environment ...)` |
| P3 | yes | a self-contained file round trip, `dynamic-wind`'s after-thunk under an error, and the one-door split |
| P4 | yes | `cond-expand` on the real feature list, `procedure-arity`'s honest `#f`, and the step-budget message quoted exactly as the CLI prints it. **Correction on landing:** the original plan called this chapter "Measuring" with `shslisp/profile.py` as a profiler — that file is the import-profile installer, not a profiler. The chapter is titled for what the runtime actually offers; the plan's claim is corrected here rather than quietly. |
| P5 | yes | the three install-time refusals as cited tests, extensions running after the prelude, and the guest side of `*command-line-args*` (machine-checked with `script_args=[]`) |
| P6 | yes | `run_script` from pytest, the `checked` helper, the `FAIL` shape, and the which-side rule |

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
   cited (`shslisp/…`, `tests/…`), not re-asserted; where a chapter and a test
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

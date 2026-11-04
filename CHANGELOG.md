# Changelog

## 0.2.0 — 2026-11-04

The name release. One name everywhere: the import package and the PyPI
distribution are both **`shslisp`**; the CLI stays `shs`.

- **Breaking:** the import package is `shslisp`, not `lisp` — update
  `from lisp import …` to `from shslisp import …`. The distribution on PyPI
  is `shslisp` (was `shs-scheme-dsl`). The rename is machine-checked: the
  packaging claims in `tests/test_embed.py` and the docs path-reference
  guards in `tests/test_docs.py` pin the new name.
- `shs --version` reads the `shslisp` distribution metadata again (the
  rename had left it asking for the old distribution names).
- Import-collision errors name both import sets and teach the three
  remedies — split into separate `(import ...)` forms, `(except ...)`,
  `(rename ...)` — with runnable fragments built from the actual sets.
- The numeric tower completes: exact rationals across the tower and the
  complex half of `(scheme complex)` (reader literals, the polar forms, the
  transcendentals; `string->number` as the reader's twin).
- Hygienic `case-lambda` and R7RS double-unquote quasiquote semantics; the
  Python floor is honestly 3.11.
- S9: a lazy-sequence generator library in the prelude; R5RS clause
  keywords are auxiliary syntax, not bindings.
- The REPL is hostile-input safe: a mistake is an error line, never a crash.
- The practical tutorial handbook (P0–P6) lands — REPL workbench, reading
  failures, programs across files, ports and `dynamic-wind`, features and
  the walls, shipping an extension, testing from the host — every `Try it`
  block executed by `tests/test_practical.py`.
- The full CLI surface is audited for Windows: every documented example
  quotes portably, and the appendix explains why single quotes are not
  shell quotes under MSVC argv rules.
- Eight runnable concurrency examples, from generator pipelines to
  supervised actors, with the multi-core pair measured (parallel-map 4.89×,
  core saturation 9.02× on 24 cores).

## 0.1.0 — initial tagged release

The language as a pure-standard-library package: reader, evaluator with
tail calls and a depth budget, the R7RS-small subset with documented
deviations, SRFIs 1/26/88/89/197/241, the `(define-library)` system, the
gosh-like `shs` CLI, and the tutorial series 00–27.

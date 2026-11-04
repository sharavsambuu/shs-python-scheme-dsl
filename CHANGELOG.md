# Changelog

## Unreleased

A conformance review of the R7RS-small surface, run from the CLI against the
0.2.0 build — fifteen tasks, all landed. The tests that pin them are in
`tests/test_review_fixes.py`.

- **Breaking:** `read-string` is now R7RS's character reader — `(read-string k
  [port])` returns up to *k* characters. The datum-from-text convenience kept
  its behaviour under a new name, `read-from-string`; update
  `(read-string "…")` to `(read-from-string "…")`. Tutorial chapters 01, 02 and
  07 and the reference appendix follow the rename.
- `read` on a port reads one datum without draining the stream, and a stream
  that begins with a dispatch form — `#;`, `#|`, `#(`, `#u8(`, `#\`, `#!` — or
  a quote prefix is read whole instead of stopping after `#`. A lone `#` is a
  syntax error, not the symbol `#`.
- Malformed forms fail loudly instead of leaking host exceptions: a binding
  list with a missing initializer, an extra form, or a non-symbol name; a
  `lambda` with no body; a dotted form in expression position. Each raises
  `LispSyntaxError`.
- Equality is one rule across the board: `equal?` compares numbers the way
  `eqv?` does, so exactness distinguishes (`(equal? 1 1.0)` is `#f`), and
  `case`, `memv`, `assv` and hash-table keys follow. Hash keys carry the
  numeric type.
- The printer round-trips what it writes: a symbol whose name ends in `:` is
  written `|a:|` (bare, it would read back as a keyword), and a keyword whose
  name cannot be a bare identifier is written `|a b|:`.
- A cached `syntax-rules` expansion is copied before it is handed out, so
  quoted data in a template is fresh per use — `set-car!` on one expansion no
  longer reaches the next identical use.
- **Hygiene resolves free template identifiers at the definition site.** An
  identifier that is unbound where the macro is defined no longer resolves in
  the caller's frame: it pins to the definition site's root scope, so a
  `let-syntax` sibling is invisible (R7RS's rule — `letrec-syntax` is the form
  that names siblings), a caller's local cannot capture it, and a helper
  defined later at top level still answers. Quoted data in a template is data:
  `'x` is the symbol `x`, never a hygiene alias. **Breaking** for code that
  relied on use-site capture; `(macroexpand '(m …))` still shows the aliases.
- Radix ratios read: `#x1/2` is the exact `1/2`, `#i#x1/2` is `0.5`, and
  `#x1/0` is a read error. A radix *decimal* (`#x1.8`) stays a bad literal,
  because the report's `<decimal 10>` fixes the radix at ten.
- One radix and one exactness prefix, in either order, are now enforced:
  `#e#x10` and `#x#e10` are numbers, `#i#e10` and `#x#x10` are errors instead
  of silently last-one-wins.
- A `#!fold-case` / `#!no-fold-case` directive read from a *port* now applies
  to the datum that follows it and to later `read`s on the same port, as it
  already did within a file.

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
- The guided tutorial gains a chapter on homoiconicity — `07 Code is data` —
  `quote`/`eval`/quasiquote templates, a program that writes a program, code as
  configuration, and the honest limits (no `gensym`, pattern-only
  `syntax-rules`, depth-counting nested quasiquote). Chapters 07–27 renumber to
  08–28 with every cross-link, metadata line, and worked exercise updated; the
  new chapter's `Try it` block and answer key (`exercises/code-is-data.scm`)
  are enforced by `tests/test_tutorial.py` and `tests/test_exercises.py`.
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

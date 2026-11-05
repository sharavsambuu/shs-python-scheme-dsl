# Changelog

## 0.2.1 — 2026-11-06

The trading layer. `(srfi 19)`, `(srfi 158)` and `(srfi 160)` land, so a
strategy's rules can stay in Scheme while the numeric work stays host-side
across a buffer seam; the R7RS conformance review closes fifteen findings; and
`docs/quant_stuffs/README.md` records what the seam costs, with
`tests/test_quant.py` keeping its measured outputs true. One breaking change:
`read-string` is R7RS's character reader; the datum reader is
`read-from-string`.

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
- The SRFI ledger schedules the trading layer — `(srfi 19)` time and date,
  `(srfi 160)` numeric vectors, and the `(srfi 158)` audit-and-complete of
  the generator prelude (S10–S12 in `docs/SRFI_TASKS.md`). Documentation
  only: importing any of them still fails loudly until a library lands.
- **The trading layer lands: S10, S11, S12.** `(srfi 19)` time and date —
  core-backed Python primitives with the documented deviations (no TAI, no
  leap seconds, integer zone offsets, a `date->string`/`string->date`
  directive subset). `(srfi 160 base)` for all twelve homogeneous numeric
  vector types and `(srfi 160 f64)` with the full SRFI-133-shaped operation
  set — the payload is an `array.array`, so `numpy.frombuffer` is the
  zero-copy bridge, and the reader/printer round-trip `#f64(...)`-style
  literals. `(srfi 158)` generators and accumulators: the generator prelude
  is audited against the final SRFI 158 export list — the eof-object
  exhaustion protocol (the S9 `generator-end` sentinel is still accepted),
  the full combinator set, the multi-generator drains, the searching half,
  and the accumulators; `make-coroutine-generator`/`make-for-each-generator`
  fail loudly (they need re-entrant continuations). All three ship in both
  profiles, pre-imported by the default DSL profile, with the `srfi-19`/
  `srfi-158`/`srfi-160` feature identifiers. Tests: `tests/test_srfi19.py`,
  `tests/test_srfi160.py`, and the grown `tests/test_generators.py`.
- **The trading-layer audit pass (S13): sixteen review findings fixed.**
  `(srfi 160)`: `make-@vector` validates its fill like every other insert
  (an exact `1`, `#t`, or an out-of-range integer now raises a Lisp type
  error instead of silently coercing — or leaking a host `OverflowError`);
  `f64vector-copy!`/`f64vector-reverse-copy!` handle self-overlap "as if the
  source is first copied into a temporary vector" (SRFI 133); the f64
  operations require f64vectors and `f64vector-map` answers an f64vector;
  `f64vector-any` on an empty vector returns `#t`, `f64vector=` with zero or
  one vector returns `#t`, `f64vector-concatenate` refuses a non-list,
  `list->f64vector` of the empty list is the empty vector,
  `f64vector-index-right`/`skip-right` require equal lengths, and
  `f64vector-partition` calls the predicate once per element. `(srfi 19)`:
  `string->date` range-checks hour/minute/second like `make-date`, caps the
  readers' widths like the reference's, and requires the whole input to
  match the template; `date-week-number` matches the SRFI 19 reference
  implementation and `~U`/`~W` are zero-padded with the partial-first-week
  rule; `time-resolution` validates its type argument and the Julian Day
  converters require a `time-utc`. `(srfi 158)`: `gmerge` is lazy — it
  consumes nothing from its sources until the merged generator is first
  called. **Profile:** the strict `r7rs` profile no longer carries the
  `(srfi 19)`/`(srfi 160)` names in its core floor — they are import-only
  there, exactly as `docs/srfi.md` has always claimed (the default DSL
  profile still pre-imports them). Doc drift: "the other ten per-type full
  libraries" is eleven. **The review-regression pass** adds two more loud
  fixes: `f64vector-copy!`/`f64vector-reverse-copy!` reject a negative or
  oversized target index before the first write (Python's negative indexing
  no longer leaks, and a failed copy leaves the target untouched), and
  `time-resolution` refuses `time-duration` — a duration is not a clock.
  **The final audit sweep** closes the remaining edges: every base
  `list-><type>vector` accepts `()`, and every `<type>vector->list` (and the
  f64 slices and reverse conversion) answers `()` as `NIL`, so `null?`,
  `list?` and `equal?` behave; the Julian Day and date converters reject
  non-finite or out-of-range values with a Lisp type error instead of
  leaking a host `OverflowError`; `date->string` defaults to `~c` and prints
  `Z` at a zero offset; `string->date` distinguishes abbreviated from long
  weekday/month names and requires `~z` to be exactly `HHMM` or `HH:MM`.
- **The quant playbook lands** — `docs/quant_stuffs/README.md`: where strategy
  rules stay in Scheme and numeric kernels stay in Python, and what the seam
  costs. The measured table (Python 3.14.7, Apple M1 / arm64): a 1M-element
  `f64vector-fold` with a primitive callback is ~1.1 s, with a Scheme lambda
  ~3.8 s; a pre-parsed per-bar decision is ~12–14 µs, so one rule over 1M bars
  is ~13 s. The step budget's real thresholds are recorded per rule shape — a
  branch per element raises at ~900k elements, two arithmetic branches at
  ~550k — next to the working patterns: the one-memcpy host→engine seam and
  the zero-copy `np.frombuffer` return, index-honest crossover predicates,
  hygienic rule macros, `(srfi 19)` session gates, `(srfi 158)` replay/live
  streams, typed decisions with `ok`/`err` risk gates, five execution patterns,
  the backtest-modelling checklist, and the S14 candidate list. The page's
  claim that every Scheme snippet was evaluated against this build is
  machine-kept by `tests/test_quant.py`: the fences run in document order and
  every `;; =>` value is diffed against the build's answer.

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

# Hardening tasks: the review ledger (2026-11 review)

> **The claim, in one paragraph.** This ledger tracks the findings from the
> 2026-11 code review of `shslisp` (Python-as-runtime Scheme DSL). Each
> finding either lands a fix + regression test in the same change, or stays
> honestly open here with its severity. The checkable truth is the test
> suite (`python -m pytest -q`) and the doc sections each task updates;
> where this ledger and a test disagree, the test wins. This is a personal-use
> hardening list, not an R7RS/SRFI conformance list — those live in
> [`R7RS_TASKS.md`](R7RS_TASKS.md) and [`SRFI_TASKS.md`](SRFI_TASKS.md).

> **Honesty note.** First entry 2026-11-10. Personal-use scope: Alpha, MIT,
> no promise of production support. Severity: P1 = real limitation the user
> must know for personal projects; P2 = tech-debt / polish; P3 = nice-to-have.

## Landed

| Task | Finding | Fix |
| --- | --- | --- |
| H0 | Baseline | `1159 passed` (Python 3.14), `py_compile` clean, manual smoke: `embed`, `tail-loop 100k`, `non-tail 200k`, hygiene `unless`, numeric tower `(/ 1 2)=1/2`, `(sqrt -1)=Complex(0,1)` |
| H1 | Sandbox undocumented | `README.md` Security section + `capabilities.md` wall 6 (3 sentences, no code) |
| H2 | Perf unmeasured | `tests/test_perf_smoke.py` bounded bounds (tail 10k <5s, fib20 <10s, map 1k <5s) |
| H4 | No tooling gate | `pyproject.toml` `[tool.mypy]`/`[tool.ruff]` + `.github/workflows/ci.yml` |
| H5 | REPL no history | `shslisp/repl.py` `~/.shs_history` + `readline`, `,load`/`run_repl(install_tetris=False)` |
| H6 | Tetris auto-discovery | `runtime.py:make_env(install_tetris: bool=False)`, `None`→`DeprecationWarning`; `__main__.py`/`repl.py` updated |
| H11 | Build hygiene | `.gitignore` already covers `build/`/`*.egg-info/`/`env/`; `git ls-files` empty (verified) |
| H3 | Host exception leakage | `evaluator.apply_procedure` wraps `ZeroDivision/Overflow/ArithmeticError` → `LispTypeError`; pinned in `test_hardening.py` (host `bad-div`, `boom`) |
| H12 | Exact vs inexact complex | `tests/test_complex_property.py` (exact stays exact, inexact contaminates, `eqv?` distinguishes, literal round-trip) |
| H9 | Source locations | `errors.SourceLocation`, `reader.tokenize_located`/`_locator`/`read_all_located`/`read_one_located`, `Result.source` on errors; `tests/test_locations.py` |
| H7 | Library `syntax-rules` hygiene | Decision (a): keep limitation, document with example + workaround in `docs/lisp_tutorial/06-macros.md`, pin in `tests/test_h7_library_macros.py` (top-level ok, library private-helper/import fail loudly, defmacro+export workaround) |
| H8 | Re-entrant `call/cc` | Decision: escape-only contract pinned in `tests/test_h8_continuations.py`; stays in `capabilities.md` Tier 1; `make-coroutine-generator` fail-loudly pinned. No evaluator change. |
| H10 | Formatter / LSP | Decision: tech-debt recorded, outline in H10 below; `capabilities.md` wall 7 names it. Located reader (H9) is step one. No code this round. |

## Open

*(Empty. All hardening findings are now either landed with tests or
recorded as deliberate non-goals above. The remaining documented gaps are
Tier-1 deliberate non-goals or Tier-3 library items in
`capabilities.md`.)*

## Open — details (retained for the audit trail)

### H1 — Sandbox / security boundary is undocumented (P1, effort: small)

**User value.** A personal DSL that loads files and runs Python primitives
must state that Lisp code is *trusted code* — there is no sandbox. Today a
script can `load`, `open-input-file`, `eval`, and call any
`install_primitives` primitive. This is by design (the host *is* the trust
boundary), but the README and `capabilities.md` never say it. A user embedding
`shslisp` for config / policy files needs that sentence before they paste a
file from the internet.

**Shape.** Docs-only: a "Security / trust model" subsection in
[`../README.md`](../README.md) and [`capabilities.md`](capabilities.md)
*The walls*. 3–4 sentences, no code.

**Gate.** The text names: (a) no sandbox — same privilege as host Python,
(b) only primitives explicitly installed via `install_primitives` are
reachable (declaration, not discovery — already in `embed.py`), (c) do not
`run`/`load` untrusted input.

### H2 — Performance wall is stated but not measured in-repo (P1, effort: small)

**User value.** Tree-walking interpreter timing affects whether a game frame,
a per-bar strategy rule, or a REPL script feels snappy. `capabilities.md`
says "10–100× slower" but no benchmark lives in `tests/`.

**Shape.** Add `tests/test_perf_smoke.py` with a bounded benchmark
(`fib 20`, `loop 10000`, `(map …)` over `iota 1000`) asserting a generous
upper bound, plus a one-row note in `capabilities.md`.

**Gate.** Test passes on CI-fast machine, is flaky-proof (10× headroom), and
`fib 20` / `loop 10k` numbers are printed in the decision record.

### H3 — Host exception leakage on malformed forms (P1, effort: medium)

**User value.** Malformed forms should raise `LispSyntaxError`, never a raw
Python `ZeroDivisionError` / `OverflowError` / `ValueError`. Phase R/C fixed
the numeric family; a few `builtins.py` conversions still let host errors
escape before wrapping.

**Shape.** Grep `builtins.py` for bare `float(...)`, `int(...)`,
`array.array(...)` conversions, wrap as `LispTypeError`, add pinning tests
mirroring `test_review_fixes.py`.

**Gate.** New tests in `test_hardening.py`, no Python traceback in `shs run`
output for the same inputs on main.

### H4 — Tooling: type checker / linter / formatter not enforced (P2, effort: small)

**User value.** Type hints are extensive (`from __future__ import annotations`
in all modules) but never checked. A `mypy`/`ruff` gate would catch the next
`bool`-as-`int` class bug at edit time.

**Shape.** `pyproject.toml`: `[tool.mypy]`, `[tool.ruff]` minimal; optional
`.github/workflows/ci.yml` running `mypy shslisp` + `ruff check shslisp` +
`pytest -q`. Keep dev deps out of runtime deps (`dev = ["pytest"]` stays).

**Gate.** `mypy` zero errors on `shslisp/` (or documented ignores), `ruff`
zero warnings.

### H5 — REPL UX: no history / completion (P2, effort: medium)

**User value.** `shslisp/repl.py` reads with paren-balance and survives
bad input, but has no history, no tab completion, no persistent line editing.
Personal use suffers.

**Shape.** Try `readline` (stdlib) history on `run_repl`, add `,history`
command, keep REPL host-agnostic (injectable `in_stream`/`out`).

**Gate.** Manual: type a define, `,quit`, re-open, `↑` recalls. Tests in
`test_repl.py` still pass.

### H6 — Tetris coupling: `make_env` auto-probes `tetris.env` (P2, effort: small)

**User value.** `runtime.py:73` probes `importlib.util.find_spec("tetris.env")`
in default auto mode. For a general-purpose library, host editions should be
*opt-in* via `extensions=[...]` (`embed.py`), not auto-discovered. Today a
foreign project that happens to have a `tetris` package is silently bound.

**Shape.** Default `install_tetris=False`, keep `True`/`None` as migration
path, or remove auto entirely. Deprecation warning if `None` is passed.
Update `__main__.py:_run_script`, `runtime.py:make_env` docstring, README.

**Gate.** `make_env()` in a tree without `tetris` is unchanged; `make_env(install_tetris=True)` without `tetris.env` raises the existing `LispError` (already present at runtime.py:162).

### H7 — Hygiene: `syntax-case` / custom ellipsis / library-macro scope (P2, effort: large)

**User value.** Documented limitation (`syntax.py:40`): exported
`syntax-rules` macros cannot reach library-private helpers. Host editions that
ship macros need `syntax-case` or a documented pattern ("export helpers, or
build with `defmacro`").

**Shape.** Decide: (a) keep limitation, document with example + workaround in
`docs/lisp_tutorial/06-macros.md`, or (b) implement `syntax-case`. (a) is
P2-small, (b) is a new language task.

**Gate.** Either tutorial example pinned by test, or `syntax-case` lands with
its own SRFI-style ledger entry.

### H8 — No re-entrant `call/cc` — generator/coroutine wall (P2, effort: large)

**User value.** `call/cc` is escape-only (`ContinuationJump`). `make-coroutine-generator`
fails loudly by design. This is intentional (Tier-1 deliberate gap in
`capabilities.md`) but should stay on the ledger so a future reader does not
re-discover it.

**Shape.** No code change now. Task remains *open* until a user value demands
re-entrant continuations and a per-thread / CPS redesign is approved.

**Gate.** Stays in `capabilities.md` Tier 1. No new test.

### H9 — No source locations (P2, effort: medium)

**User value.** Reader (`reader.py`) tracks no line/column, errors carry no
coordinates. Squiggles / go-to-definition / precise REPL errors need this.
`capabilities.md:275` names it as first IDE step.

**Shape.** Attach optional `(line . col)` to forms (or at least to `LispError`
at `read`/`evaluate` time), propagate through `printer` round-trip tests.

**Gate.** Single test: parse `"(\n  + 1)"` gets location, `(error "x")` on
line 2 reports line 2.

### H10 — Formatter / LSP go-to-definition (P3, effort: large)

**User value.** Writing `prelude.scm`, `generators.scm`, `srfi1.scm` (500+
lines) without a formatter is friction.

**Shape.** No code scheduled. Task is recorded so the tech-debt is visible.

### H11 — Build & env hygiene (P3, effort: small)

**User value.** `build/`, `*.egg-info/` are ignored but present on disk;
`env/` and `.venv` confuse new clones.

**Shape.** Verify `.gitignore` already covers `build/` (line 11) and
`*.egg-info/` (line 24) and `env/` (line 156) — it does. No repo change.
Document `pip install -e .` vs `pip install .` in `INSTALL.md`.

**Gate.** `git ls-files build/ *.egg-info/` is empty (verified 2026-11-10).

### H12 — Numeric: `Complex` (exact) vs `complex` (inexact) dual tower (P3, effort: medium)

**User value.** Two complex types coexist; `eqv?`/`equal?` semantics must stay
pinned. Current tests pin it, but the invariant deserves one more property
test (exactness preserved through `+ * / conjugate magnitude angle`).

**Shape.** Add property-style tests in `test_quant.py` / `test_r7rs.py`,
no code change if they pass.

**Gate.** Tests added, pass.

## Deliberately not scheduled

- **SRFI breadth.** `SRFI_TASKS.md` already defers 64/125/128/132/133/146/151/152/170/173/180/193. H-tasks do not reopen them without a user value.
- **Syntax-case / re-entrant continuations / concurrency / static types** — Tier-1 deliberate gaps in `capabilities.md`. Entering any of them is a new language task, not a hardening fix.
- **Annotation / ML typing** — research, not a hardening item.

## How to verify

```bash
./env/bin/python -m pytest tests/ -q
# H1/H2/H4 after landing:
./env/bin/python -m pytest tests/test_hardening.py tests/test_perf_smoke.py -q
./env/bin/python -m mypy shslisp --strict  # H4 gate
./env/bin/python -m ruff check shslisp    # H4 gate
```

## How this ledger relates to the others

| File | Scope |
| --- | --- |
| [`R7RS_TASKS.md`](R7RS_TASKS.md) | R7RS-small conformance (A0–A15, T01–T15, numeric R/C) |
| [`SRFI_TASKS.md`](SRFI_TASKS.md) | SRFI libraries (S0–S13) |
| [`HARDENING_TASKS.md`](HARDENING_TASKS.md) (this file) | Review findings → hardening, tooling, docs |

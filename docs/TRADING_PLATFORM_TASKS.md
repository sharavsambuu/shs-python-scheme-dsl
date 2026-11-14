# Runtime, CLI & Standard-Library Roadmap (Post-Trading-Lab Review)

> **Why this file exists.** These tasks were surfaced directly while building and
> modernizing `shs-scheme-trading-exps` (`T-110`–`T-141`: 29 `(define-strategy ...)`
> strategies, 19 standalone `.scm` curriculum experiments, typed wire events,
> Scheme-native `define-test-suite` specs, Durenard multi-symbol swarms, and
> 4-slice portfolio backtests under the `5,000,000`-step budget).

Every task below records **what motivated it**, **the exact gap observed**, and
**the target design** in `shslisp`.

---

## 1. Runtime, CLI & Evaluator Track (`R-01`–`R-04`)

| ID | Task | Priority | Status | Primary Files |
|---|---|---|---|---|
| `R-01` | Generic `--plugin <module[:attr]>` CLI flag & `SHS_PLUGINS` loader | P1 | DONE | `shslisp/__main__.py`, `shslisp/embed.py` |
| `R-02` | Multi-frame Scheme call-stack trace on `LispError` | P1 | DONE | `shslisp/evaluator.py`, `shslisp/errors.py` |
| `R-03` | Per-procedure step hotspot profiler (`measure_calls`) & `_run` macro/lookup fast-path | P1 | DONE | `shslisp/evaluator.py`, `shslisp/builtins.py` |
| `R-04` | Windows `tmp_path` backslash & CWD hygiene in `tests/` | P2 | DONE | `tests/test_ports.py`, `tests/test_library.py`, `tests/test_r7rs.py`, `tests/test_srfi.py` |

### `R-01` — Generic `--plugin` CLI & `SHS_PLUGINS`
* **Motivation & Origin:** `shslisp/embed.py` already provides `install_extension(env, extension)` and `make_env(..., extensions=[...])`, yet `shslisp/__main__.py` only exposes a hardcoded `tetris: bool = False` toggle. Because of this gap, `shs-scheme-trading-exps` had to maintain its own `python -m host.scm` launcher wrapper instead of running scripts directly with `shs`.
* **Target Design:** Add repeatable `--plugin module.path[:attr]` (default attribute `install`) and `SHS_PLUGINS` env var support in `shslisp/__main__.py` for `run`, `-e`, and `repl`, delegating to `install_extension`.
* **Shipped:** `--plugin` is a repeatable top-level flag; `SHS_PLUGINS` (`os.pathsep`-separated) is merged with it (one install per spec), resolved eagerly by `load_plugins` (`MOD[:ATTR]`, default `install`), and passed to `make_env(..., extensions=...)` for `run`, `-e` and `repl`. A bad spec exits `1` with `shs: plugin 'SPEC': ...` on stderr. The gosh-style scan also skips option values now, so a plugin flag may sit between `shs` and the script path without hiding the script. Pinned by `test_r01_plugin_cli_tdd.py`.

### `R-02` — Multi-Frame Scheme Call-Stack Trace on `LispError`
* **Motivation & Origin:** Combinator-heavy Scheme code (`define-strategy`, `wrap-pure-stake`, `step-bets`, `step-swarm`) nests multiple closures before hitting a runtime `LispTypeError` or `LispBudgetError`. `_Budget.sources` in `shslisp/evaluator.py` already tracks the active `SourceLocation` stack, but `_attach_eval_source` currently keeps only the single innermost location (`budget.sources[-1]`).
* **Target Design:** Capture a bounded call-frame snapshot (top $N$ frames / call sites) onto `LispError.traceback` when an error unwinds, and render a concise multi-line Scheme backtrace in `LispError.__str__()` (or `format_traceback()`) without breaking existing single-line substring assertions.
* **Shipped:** `LispError.traceback` (class default `()`, class-level annotation) is filled by `_attach_eval_source` from the first — deepest — handler that sees the escaping error: unique non-`None` spans from `budget.sources`, innermost first, capped at `TRACEBACK_FRAMES = 32`. `LispError.format_traceback()` renders `Scheme traceback (innermost first):` + one `at file:line:col` line per frame + the single-line message; `str(exc)` and `exc.source` are unchanged, so every historical substring assertion still holds. `evaluate_program` also accepts the `(form, SourceLocation)` pairs `read_all_located` returns, so a host can read with spans and run the result directly. Pinned by `test_r02_callstack_traceback_tdd.py`.

### `R-03` — Step Hotspot Profiler & `_run` Fast-Path / Macro Cache
* **Motivation & Origin:** After adding typed wire events and v2 sizing dispatch in `shs-scheme-trading-exps`, `test_portfolio_scales_chunk_for_the_step_budget` (1,200 bars × 4 slices) hit `LispBudgetError` (`5,000,000` steps) at `chunk_bars = 600` and `500`, forcing the trading host to shrink portfolio chunks (`2 * n_slices + 1`). Meanwhile, `measure_steps` only reports a single total integer, giving no visibility into *which* Scheme procedures spent the steps.
* **Target Design:**
  1. Add a lightweight `measure_calls` / `profile_calls` hook alongside `measure_steps` that aggregates step & call counts per procedure name.
  2. Optimize `_run` hot paths in `shslisp/evaluator.py` (skip `_find_macro` when `head` resolves to a cached non-macro binding or literal, and cache `SyntaxRules` macro expansions per call-site form where safe) to cut per-bar step counts and Python wall-clock time.
* **Shipped:**
  1. `measure_calls(thunk) -> (result, steps, counts)` — same private-budget swap as `measure_steps` (caller's steps untouched, `STEPS_BUDGET` still armed), tallying applications per name for tail-called closures (`_run`), non-tail closures and primitives (`apply_procedure`, so `map`/`apply` calls are included). `_Budget.calls` is `None` for ordinary evaluation, so profiling costs one `is not None` test on the hot path.
  2. `_run` fast paths, both semantics-preserving: the reader-span probe is inlined and skips atoms (no source-table hit for a literal), and the ~35-comparison special-form dispatch now runs only for heads in `_SPECIAL_FORMS` or `_DISPATCH_ONLY` — a plain application goes straight to evaluation, with `_find_macro` still probed first so a macro keeps shadowing `variant-match` / `%srfi241-quasiquote` exactly as before. Measured on a 200k-iteration tail loop and a 50k-iteration `syntax-rules` loop: ~17% and ~26% less wall-clock with **identical** step counts (170 steps for the ten-iteration macro loop), so no budget behaviour moved. Pinned by `test_r03_profiler_and_fastpath_tdd.py`.

### `R-04` — Windows Path & CWD Hygiene in `tests/`
* **Motivation & Origin:** Running the full `shslisp` test suite on Windows showed 11 failures out of 1,186 tests: `test_ports.py`, `test_library.py`, and `test_r7rs.py` interpolate raw `tmp_path` strings containing `\` into Scheme string literals (turning `\t` or `\b` into control characters), and `test_srfi.py` assumes CWD is the `shs-python-scheme-dsl` root.
* **Target Design:** Use `.as_posix()` or escaped paths in Scheme string templates and `Path(__file__).resolve().parents[1]` for repo-relative test fixtures.
* **Shipped:** every `tmp_path`/`Path` interpolated into a Scheme string literal in `test_ports.py`, `test_library.py` and `test_r7rs.py` goes through `.as_posix()` (a raw Windows path would feed `\t`, `\b`, ... to the reader as escapes); `test_srfi.py` resolves `shslisp/srfi1.scm` from `REPO_ROOT = Path(__file__).resolve().parents[1]`; `docs/HARDENING_TASKS.md` no longer cites an uncommitted CI workflow as if it existed. Full suite green on Windows (1,194 passed).

---

## 2. Standard-Library SRFI Track (`S14`–`S18`)

See [`SRFI_TASKS.md`](SRFI_TASKS.md) (`## Open`) for the full scope, user value, and deviation specs.

| ID | Task | Status | Shipped as |
|---|---|---|---|
| `S14` | `(srfi 125)` hash tables — `O(1)` tables replacing `O(N)` `assoc`/`assq` scans | DONE | `shslisp/srfi125.py` |
| `S15` | `(srfi 132)` sorting — Python Timsort behind the caller's comparator | DONE | `shslisp/srfi132.py` |
| `S16` | `(srfi 64)` testing — assertion macros, groups, and the simple runner | DONE | `shslisp/srfi64.scm` |
| `S17` | `(srfi 180)` JSON — `json-read` / `json-write` over the stdlib `json` | DONE | `shslisp/srfi180.py` |
| `S18` | `(srfi 28)` `format` + `(srfi 152)` string utilities | DONE | `shslisp/srfi28.py`, `shslisp/srfi152.py` |

Each library is import-only in **both** profiles — `(import (srfi 125))` opts
in, and the primitives install into the library's own scope on first import.
The DSL profile's feature list is pinned by `tests/test_profile.py`, so the
wave deliberately does not extend it. The audited export lists live in
`shslisp/library.py`; the locked surface test is
`tests/test_s14_to_s18_srfis_tdd.py`.

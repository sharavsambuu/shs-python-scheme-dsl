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
| `R-01` | Generic `--plugin <module[:attr]>` CLI flag & `SHS_PLUGINS` loader | P1 | OPEN | `shslisp/__main__.py`, `shslisp/embed.py` |
| `R-02` | Multi-frame Scheme call-stack trace on `LispError` | P1 | OPEN | `shslisp/evaluator.py`, `shslisp/errors.py` |
| `R-03` | Per-procedure step hotspot profiler (`measure_calls`) & `_run` macro/lookup fast-path | P1 | OPEN | `shslisp/evaluator.py`, `shslisp/builtins.py` |
| `R-04` | Windows `tmp_path` backslash & CWD hygiene in `tests/` | P2 | OPEN | `tests/test_ports.py`, `tests/test_library.py`, `tests/test_r7rs.py`, `tests/test_srfi.py` |

### `R-01` — Generic `--plugin` CLI & `SHS_PLUGINS`
* **Motivation & Origin:** `shslisp/embed.py` already provides `install_extension(env, extension)` and `make_env(..., extensions=[...])`, yet `shslisp/__main__.py` only exposes a hardcoded `tetris: bool = False` toggle. Because of this gap, `shs-scheme-trading-exps` had to maintain its own `python -m host.scm` launcher wrapper instead of running scripts directly with `shs`.
* **Target Design:** Add repeatable `--plugin module.path[:attr]` (default attribute `install`) and `SHS_PLUGINS` env var support in `shslisp/__main__.py` for `run`, `-e`, and `repl`, delegating to `install_extension`.

### `R-02` — Multi-Frame Scheme Call-Stack Trace on `LispError`
* **Motivation & Origin:** Combinator-heavy Scheme code (`define-strategy`, `wrap-pure-stake`, `step-bets`, `step-swarm`) nests multiple closures before hitting a runtime `LispTypeError` or `LispBudgetError`. `_Budget.sources` in `shslisp/evaluator.py` already tracks the active `SourceLocation` stack, but `_attach_eval_source` currently keeps only the single innermost location (`budget.sources[-1]`).
* **Target Design:** Capture a bounded call-frame snapshot (top $N$ frames / call sites) onto `LispError.traceback` when an error unwinds, and render a concise multi-line Scheme backtrace in `LispError.__str__()` (or `format_traceback()`) without breaking existing single-line substring assertions.

### `R-03` — Step Hotspot Profiler & `_run` Fast-Path / Macro Cache
* **Motivation & Origin:** After adding typed wire events and v2 sizing dispatch in `shs-scheme-trading-exps`, `test_portfolio_scales_chunk_for_the_step_budget` (1,200 bars × 4 slices) hit `LispBudgetError` (`5,000,000` steps) at `chunk_bars = 600` and `500`, forcing the trading host to shrink portfolio chunks (`2 * n_slices + 1`). Meanwhile, `measure_steps` only reports a single total integer, giving no visibility into *which* Scheme procedures spent the steps.
* **Target Design:**
  1. Add a lightweight `measure_calls` / `profile_calls` hook alongside `measure_steps` that aggregates step & call counts per procedure name.
  2. Optimize `_run` hot paths in `shslisp/evaluator.py` (skip `_find_macro` when `head` resolves to a cached non-macro binding or literal, and cache `SyntaxRules` macro expansions per call-site form where safe) to cut per-bar step counts and Python wall-clock time.

### `R-04` — Windows Path & CWD Hygiene in `tests/`
* **Motivation & Origin:** Running the full `shslisp` test suite on Windows showed 11 failures out of 1,186 tests: `test_ports.py`, `test_library.py`, and `test_r7rs.py` interpolate raw `tmp_path` strings containing `\` into Scheme string literals (turning `\t` or `\b` into control characters), and `test_srfi.py` assumes CWD is the `shs-python-scheme-dsl` root.
* **Target Design:** Use `.as_posix()` or escaped paths in Scheme string templates and `Path(__file__).resolve().parents[1]` for repo-relative test fixtures.

---

## 2. Standard-Library SRFI Track (`S14`–`S18`)

See [`SRFI_TASKS.md`](SRFI_TASKS.md) (`## Open`) for full scope, user value, and deviation specs:
* **`S14` — `(srfi 125)` Hash Tables:** `O(1)` Python `dict`-backed tables replacing `O(N)` `assoc`/`assq` scans in correlation matrices and symbol state maps.
* **`S15` — `(srfi 132)` Sorting:** Python Timsort-backed `list-sort` / `vector-sort`, replacing `O(N^2)` pure-Scheme sorting loops (e.g. `sort-agents-desc` in the swarm module).
* **`S16` — `(srfi 64)` Testing:** Upstreamed unit-test runner (`test-begin`, `test-end`, `test-equal`, `test-assert`, `test-error`) generalizing the trading repo's test suite DSL.
* **`S17` — `(srfi 180)` JSON:** `json-read` / `json-write` over stdlib `json`, eliminating manual JSON string formatting in CLI scripts.
* **`S18` — `(srfi 28)` + `(srfi 152)` Formatting & Strings:** `format` and essential string splitting/joining/trimming (`string-split`, `string-join`, `string-contains`, `string-trim`).

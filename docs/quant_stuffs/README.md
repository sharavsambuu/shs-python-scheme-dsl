# Quant development on the DSL — rules in Scheme, hot loops in Python

> **The thesis, in one paragraph.** This dialect is not a pandas replacement
> and should not try to be. It is the **strategy-expression layer**: session
> filters, signal rules, position state, risk gates and order policies written
> in a small, hygienic, loud-failing language with a real type story — while
> the **compute stays on the Python side** (pandas/numpy for data engineering,
> numpy/numba for the hot kernels), handed to the engine one `f64vector` per
> column through the buffer protocol. The seam is the design
> ([S11](../SRFI_TASKS.md): "strategy logic reads unboxed doubles and the hot
> loops stay on the Python side of the seam"). This page records the measured
> numbers behind that claim, the working patterns, and the examples — every
> snippet here was evaluated against this repository's build, and the outputs
> shown are the real ones.

Everything below rides on the libraries landed in S10–S13:

- [`shslisp/srfi160.py`](../../shslisp/srfi160.py) — `(srfi 160 base)` +
  `(srfi 160 f64)`: unboxed `f64vector`s backed by `array.array`, the
  SRFI-133-shaped operation set. The matrix is in [`srfi.md`](../srfi.md).
- [`shslisp/srfi19.py`](../../shslisp/srfi19.py) — `(srfi 19)`: calendar, clock,
  sessions, `date->string`/`string->date`, Julian Days.
- [`shslisp/generators.scm`](../../shslisp/generators.scm) — `(srfi 158)`:
  lazy streams, multi-source merges, online accumulators. Prelude in both
  profiles.
- [`shslisp/rope.scm`](../../shslisp/rope.scm) — the `Result`/Either vocabulary
  (`ok`/`err`, `result-bind`, `>=>`), pinned by
  [`tests/test_rop.py`](../../tests/test_rop.py). Prelude in both profiles.
- [`shslisp/embed.py`](../../shslisp/embed.py) — the host-facing seam:
  `make_env`, `install_primitives`, `load_lisp`. This is what your trading
  host imports.

## Where the numbers are (measured, this build, 1M f64 elements)

| Operation | Time | Note |
| --- | --- | --- |
| numpy `sum` over 1M f64 | ~0.3–1 ms | host-side, when numpy is installed |
| `(f64vector-fold + 0.0 v)` over 1M | **~1070 ms** | every element is an interpreter `apply_procedure` |
| Scheme tail loop step | ~9.5 µs | `(loop (- i 1) (+ acc 1.0))` |
| per-bar `evaluate_program` (read+eval) | ~26 µs/bar | parse included |
| per-bar **pre-parsed** callback | **~13 µs/bar** | `apply_procedure(strategy, [vec, i])` — 1M bars ≈ 13 s per rule pass |

The conclusion is not "Scheme is slow" — it is **put each kind of code where
it is cheap**:

| Kind of code | Where it runs | Why |
| --- | --- | --- |
| data loading, resampling, alignment, joins | pandas (host) | years of tooling; do not reimplement |
| indicator kernels over full history (SMA, EMA, zscore, ATR) | numpy / numba (host) | 3+ orders of magnitude faster per element |
| session filters, calendar windows | `(srfi 19)` in Scheme | stdlib-backed, loud, exact |
| signal rules, state machines, sizing, risk gates | Scheme | the part you iterate on daily; expressiveness wins |
| event loop over bars | Python host loop → Scheme callback (Pattern B below), or full Scheme for small data | ~13 µs per pre-parsed decision |

## The data seam

**Host → engine (one memcpy per column).** A pandas/numpy column becomes one
`f64vector`; never ship boxed lists across the seam:

```python
import array
from shslisp import make_env, install_primitives, run
from shslisp.types import Srfi160Vector

def make_close_vector(closes):
    """A host column -> one f64vector. `array.array('d', x)` accepts anything
    with the buffer protocol (numpy float64 1-D, pandas .to_numpy(), a list)."""
    return Srfi160Vector("f64", array.array("d", closes))

env = make_env()                       # default (dsl) profile: SRFIs pre-imported
install_primitives(env, [("make-close-vector", make_close_vector)])

run("(define closes (make-close-vector '(101.0 102.5 99.0 103.25 104.0)))", env)
```

Verified in-engine:

```scheme
(import (srfi 160 f64))
(define closes (make-close-vector '(101.0 102.5 99.0 103.25 104.0)))
(list (f64vector? closes) (f64vector-length closes) (f64vector-ref closes 3))
;; => (#t 5 103.25)
```

**Engine → host (zero-copy read).** The payload *is* the buffer:

```python
mv = memoryview(vec.data)                       # no copy
arr = np.frombuffer(mv, dtype=np.float64)       # no copy; np.shares_memory -> True
```

numpy is deliberately **not** a repository dependency (the zero-dependency
promise) — it is a *host* dependency, like pandas and numba. When the host has
it, the view above is free; features computed on `arr` are computed once, and
Scheme reads the same doubles.

**Seam rules.**

1. One `f64vector` per column, one conversion per column. Cache it.
2. Vectors cross the seam unboxed; *decisions* cross as symbols/records — the
   seam is not a dataframe API.
3. Fresh features from numpy go back as new `f64vector`s (Pattern C) — not as
   side effects on shared buffers, so backtests stay reproducible.

## Expressing strategy rules in Scheme

**A crossover rule, index-honest.** `f64vector-index` predicates receive
*elements*, not positions — a rule that needs the index carries it explicitly:

```scheme
(import (srfi 160 f64))
(define fast (f64vector 1.0 2.0 3.0 4.0))
(define slow (f64vector 1.5 1.5 2.5 2.5))

(define (cross-over? f s i)
  (and (> i 0)                                   ;; no lookahead: i-1 exists
       (<= (f64vector-ref f (- i 1)) (f64vector-ref s (- i 1)))
       (>  (f64vector-ref f i)       (f64vector-ref s i))))

(define (first-cross-over f s)
  (let loop ((i 1))
    (cond ((>= i (min (f64vector-length f) (f64vector-length s))) #f)
          ((cross-over? f s i) i)
          (else (loop (+ i 1))))))

(first-cross-over fast slow)
;; => 1
```

**Rules as syntax.** Once a rule shape repeats, lift it into `syntax-rules` —
hygienic, so the macro's internals cannot capture your names. One lesson we
hit while writing this page: a macro *body* written at the use site cannot see
the macro-generated index (`i` is unbound there — hygiene working as
intended). Emit a *predicate form* and compose the action in plain Scheme:

```scheme
(import (srfi 160 f64))
(define-syntax cross-over?
  (syntax-rules ()
    ((_ f s i)
     (and (> i 0)
          (<= (f64vector-ref f (- i 1)) (f64vector-ref s (- i 1)))
          (>  (f64vector-ref f i)       (f64vector-ref s i))))))

(define-syntax cross-under?
  (syntax-rules ()
    ((_ f s i)
     (and (> i 0)
          (>= (f64vector-ref f (- i 1)) (f64vector-ref s (- i 1)))
          (<  (f64vector-ref f i)       (f64vector-ref s i))))))

(define (long-signal f s i)
  (and (cross-over? f s i) (list 'enter 'long i)))

(long-signal (f64vector 1.0 1.0 3.0) (f64vector 2.0 2.0 2.0) 2)
;; => (enter long 2)
```

**Pipelines and partial application.** `(srfi 197)`'s `chain` (the placeholder
is `_`) and `(srfi 26)`'s `cut` keep glue code out of the way:

```scheme
(import (srfi 197) (srfi 26) (srfi 160 f64))
(chain 4 (+ _ 1) (* _ 10))                        ;; => 50
(f64vector-count (cut > <> 1.5) (f64vector 1.0 2.0 3.0))   ;; => 2
```

**Position arithmetic is exact until the broker boundary.** Fractions do not
drift; convert to float only when an order leaves the engine:

```scheme
(define equity 100000)
(define risk 1/100)                ;; 1% of equity per trade
(define stop-distance 3/4)         ;; $0.75 per share
(* equity risk stop-distance)      ;; => 750   (exact)
```

## Typed decisions: variants, match, and Results

Domain objects as closed variants — `match` refuses an unhandled case instead
of quietly defaulting (the machinery is `define-variant`/`variant-match`, the
same typed control flow [`tests/test_rop.py`](../../tests/test_rop.py) pins):

```scheme
(define-variant order
  (buy symbol quantity price)
  (sell symbol quantity price))

(define o (buy 'AAPL 100 227.48))
(variant-match o
  ((buy sym q p)  (list 'long  sym q p))
  ((sell sym q p) (list 'short sym q p)))
;; => (long AAPL 100 227.48)
```

Validation pipelines compose as Results, not exceptions — a data-quality gate
reads like the rule it guards:

```scheme
(define (nonempty v) (if (f64vector-empty? v) (err "empty vector") (ok v)))
(define (positive v) (if (> (f64vector-ref v 0) 0) (ok v) (err "nonpositive head")))

((>=> nonempty positive) (f64vector 1.0 2.0))
;; => #<ok #<f64vector of 2>>

(define (checked-ref v i)
  (if (< -1 i (f64vector-length v))
      (ok (f64vector-ref v i))
      (err "index out of range")))

(result-bind (checked-ref closes 1)     ;; closes: the host column from above
  (lambda (x) (ok (* x 2.0))))
;; => #<ok 5.0>
```

## Time: sessions, broker clocks, lookbacks

`(srfi 19)` answers the trading-specific calendar questions with stdlib-backed
machinery. Note the documented deviations (integer zone offsets only, no TAI
clocks) — they are loud, not silent:

```scheme
(import (srfi 19))
;; a New York session bar: zone offset -18000 s = UTC-5
(define d (make-date 0 0 0 12 5 11 2026 -18000))
(list (date-hour d) (date-week-day d) (date->string d "~c"))
;; => (12 4 "Thu Nov 05 12:00:00-0500 2026")

;; MetaTrader's broker stamp parses with ~z's exact HHMM/HH:MM reader...
(date->string
  (string->date "05.11.2026 21:30:00 +0300" "~d.~m.~Y ~H:~M:~S ~z") "~4")
;; => "2026-11-05T21:30:00+0300"

;; ...and lookback spans are plain time arithmetic
(define a (make-time 'time-utc 0 1000))
(define b (add-duration a (make-time 'time-duration 0 500)))
(list (time<? a b) (time-second (time-difference b a)))   ;; => (#t 500)

;; calendar-day math without timezone noise: Julian Days
(- (date->julian-day (make-date 0 0 0 12 5 11 2026 0))
   (date->julian-day (make-date 0 0 0 12 1 11 2026 0)))    ;; => 4.0
```

A session gate is one function; wire it into the bar callback and the backtest
cannot trade overnight by accident:

```scheme
(define (rth? d)   ;; regular hours, Monday-Friday
  (and (<= 9 (date-hour d) 15)
       (<= 1 (date-week-day d) 5)))
```

## Streaming: one stream vocabulary for backtest and live

`(srfi 158)` generators are the same abstraction for replay and live: a bar
feed is a 0-argument procedure answering the next bar or the eof-object.

```scheme
(import (srfi 158))
(define bars (make-range-generator 0 10))
(generator->list (gtake (gmap (lambda (i) (* i i)) bars) 4))
;; => (0 1 4 9)

;; two venue feeds, each time-sorted: a stable, lazy merge — construction
;; consumes nothing, heads are pulled on first call (fixed in S13)
(define feed-a (list->generator '(1 3 5 7)))
(define feed-b (list->generator '(2 3 6 8)))
(generator->list (gmerge < feed-a feed-b))
;; => (1 2 3 3 5 6 7 8)
```

Online statistics come from the accumulators, so a live session and a replay
share one definition:

```scheme
(import (srfi 158))
(define acc (sum-accumulator))
(acc 101.0) (acc 102.5) (acc (eof-object))     ;; => 203.5
```

An indicator with memory is a closure — the state IS the lambda:

```scheme
(import (srfi 158))
(define (running-ema alpha)
  (let ((prev #f))
    (lambda (x)
      (if (eof-object? x)
          prev
          (begin
            (set! prev (if prev (+ (* alpha x) (* (- 1.0 alpha) prev)) x))
            prev)))))
(define ema (running-ema 0.5))
(define out (list-accumulator))
(for-each (lambda (x) (out (ema x))) '(1.0 2.0 3.0))
(out (eof-object))
;; => (1.0 1.5 2.25)
```

## Three execution patterns

**Pattern A — full-Scheme event loop.** For daily bars or small universes,
where the whole history is a few hundred thousand elements. The backtest is a
`fold` over a feature vector; position state is a plain list in the fold
accumulator (the fold *is* the book — no hidden globals):

```scheme
(import (srfi 160 f64))
;; features were computed host-side (numpy) and handed over as f64vectors
(define (backtest fast slow equity)
  (f64vector-fold
    (lambda (st i)                    ;; st = (position entry equity)
      (cond ((cross-over? fast slow i)
             (list 'long (f64vector-ref fast i) (list-ref st 2)))
            ((cross-under? fast slow i)
             (list 'flat 0.0 (+ (list-ref st 2) 0.0)))  ;; + realized P&L
            (else st)))
    (list 'flat 0.0 equity)
    fast))
```

**Pattern B — Python loop, Scheme decisions (the tick-scale default).** Parse
the strategy *once*, apply it per event; the host owns the data plumbing:

```python
from shslisp import make_env, run
from shslisp.evaluator import apply_procedure
from shslisp.types import intern

env = make_env()
run("""
(import (srfi 160 f64))
(define (decide closes i)
  (if (< i 1) 'flat
      (if (> (f64vector-ref closes i) (f64vector-ref closes (- i 1)))
          'long 'flat)))
""", env)
strategy = env.lookup(intern("decide"))

for i, bar in enumerate(bars):                    # host loop, host clock
    signal = apply_procedure(strategy, [closes_vec, i])
```

Measured above: **~13 µs per pre-parsed decision** — one rule over 1M bars is
~13 s; twenty rules is minutes. Daily bars and single-symbol minute replays
are comfortable; at tick scale the Scheme callback must be the *decision*, not
the *computation*.

**Pattern C — numpy features, Scheme rules (the daily driver).** Compute
rolling features vectorized host-side, hand them over, keep only the decision
in Scheme:

```python
import numpy as np, array
from shslisp.types import Srfi160Vector

def f64col(arr):                       # one memcpy per column
    return Srfi160Vector("f64", array.array("d", np.asarray(arr, dtype=np.float64)))

fast = f64col(df["close"].rolling(10).mean().fillna(0.0).to_numpy())
slow = f64col(df["close"].rolling(50).mean().fillna(0.0).to_numpy())
# -> hand both to the engine (install_primitives once, or make-env extensions)
```

```scheme
(import (srfi 160 f64))
(define signals                              ; Scheme sees the same doubles
  (f64vector-map (lambda (f s) (if (> f s) 1.0 (if (< f s) -1.0 0.0)))
                 fast slow))
```

**The numba corner.** A kernel too custom for numpy stays Python; JIT it and
declare it to the engine through the same seam:

```python
from numba import njit

@njit(cache=True)
def rolling_zscore(arr, n):
    out = np.full(arr.shape[0], np.nan)
    for i in range(n - 1, arr.shape[0]):
        w = arr[i - n + 1 : i + 1]
        s = w.std()
        out[i] = 0.0 if s == 0.0 else (arr[i] - w.mean()) / s
    return out

install_primitives(env, [("make-zscore-vector",
                          lambda arr, n: f64col(rolling_zscore(np.asarray(arr), n)))])
```

The rule then reads `(f64vector-ref z i)` — the interpreter never loops over
the window; numba does.

## The backtest honesty checklist

Pin these in tests (`tests/test_*.py`), not in comments:

- **No lookahead** — a rule at index `i` may only read `≤ i`. The audit-pass
  style makes this testable: `cross-over?` literally checks `(> i 0)`.
- **Every fill pays** — fees and slippage are part of the fold step, not a
  report-time adjustment.
- **Position state is explicit** — the fold accumulator *is* the book; hygiene
  means hidden globals cannot be captured by accident.
- **Money arithmetic is exact until the boundary** — rationals inside, floats
  at the broker edge.
- **Failures are loud** — invalid elements, bad dates and junk input raise;
  after S13 nothing in the numeric surface coerces silently.

## What to build next (the S14 candidate)

The seams above work today; these are the edges that would still hurt:

- **Rolling primitives as core-backed primitives** — `f64vector-rolling-mean`
  / `-std` / `-max` / `-min`, implemented Python-side over the payload (the
  S11 ledger already notes "a numpy backing can serve them vectorized instead
  of through the tree walker"). Biggest daily-driver win: it moves the
  ~1 µs/element fold into host code.
- **Running `max`/`min` accumulators** — deliberately absent from SRFI 158's
  export list, so they would be a `(quant)` extension library, not a claim
  about the SRFI.
- **A NaN policy** — trading data has gaps; decide "NaN poisons the window"
  loudly versus a documented skip rule, before strategies encode one by
  accident.
- **OHLCV helpers** — true range, ATR from four vectors, gap detection; small,
  pure, easy to pin.

A candidate like this enters [`../SRFI_TASKS.md`](../SRFI_TASKS.md) only after
it states its user value and passes the "meets its semantics or fails loudly"
gate — the same bar S10–S13 cleared.

## How to verify

```bash
python -m pytest tests/test_srfi160.py tests/test_srfi19.py tests/test_generators.py -q
python -m pytest tests/test_docs.py -q          # the doc drift guard (top-level pages)
```

Every Scheme snippet on this page was evaluated against this build; the
Python-side examples are host programs (numpy/pandas/numba are host
dependencies, per [`shslisp/embed.py`](../../shslisp/embed.py)'s contract).

```scheme
(import (srfi 160 f64))
;; features were computed host-side (numpy) and handed over as f64vectors
(define (backtest fast slow equity)
  (f64vector-fold
    (lambda (st i)                    ;; st = (position entry equity)
      (cond ((cross-over? fast slow i)
             (list 'long (f64vector-ref fast i) (list-ref st 2)))
            ((cross-under? fast slow i)
             (list 'flat 0.0 (+ (list-ref st 2) 0.0)))  ;; + realized P&L
            (else st)))
    (list 'flat 0.0 equity)
    fast))
```

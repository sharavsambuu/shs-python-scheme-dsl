# Quant development on the DSL — rules in Scheme, hot loops in Python

> **The thesis, in one paragraph.** This dialect is not a pandas replacement
> and should not try to be. It is the **strategy-expression and decision
> layer**: session filters, signal rules, position state, risk gates and
> order policies written in a small, hygienic, loud-failing language with a
> real type story — while the **compute stays on the Python side**
> (pandas/numpy for data engineering, numpy/numba for the hot kernels), handed
> to the engine one `f64vector` per column through the buffer protocol. The
> seam is the design ([S11](../SRFI_TASKS.md): "strategy logic reads unboxed
> doubles and the hot loops stay on the Python side of the seam"). The goal is
> not to make Scheme execute numeric loops quickly; it is to keep the
> interpreter out of the hot path while making the part you change every day
> auditable. This page records the measured numbers behind that claim, the
> working patterns, the backtest checklist, and the limits — every Scheme
> snippet here was evaluated against this repository's build, and the outputs
> shown are the real ones.

**Who this is for.** A developer who already has a research stack — pandas,
numpy, maybe numba — and wants a rule layer on top that is easier to read,
review and test than a pile of Python callbacks, without giving up vectorized
performance. It is also for the same developer six months later, trying to
remember why a backtest looked better than live trading.

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

The snippets on this page are **one program in document order**: a later
fence leans on earlier definitions (the rule macros of §5 are used in §10, and
so on). [`tests/test_quant.py`](../../tests/test_quant.py) runs them exactly
that way — see §18.

## 1. The one design decision: where each piece lives

The most important quant decision in this codebase is not which indicator to
use. It is **where the loop lives**. Put each kind of code where it is cheap:

| Kind of code | Where it runs | Why |
| --- | --- | --- |
| data loading, auth, vendor APIs | Python | libraries, retries, rate limits |
| cleaning, resampling, alignment, joins | pandas (host) | years of tooling; do not reimplement |
| corporate actions, point-in-time universes | Python (host) | data-engineering problem, not a rule |
| indicator kernels over full history (SMA, EMA, zscore, ATR, vol) | numpy / numba (host) | 3+ orders of magnitude faster per element |
| feature storage and snapshots | Python (host) | reproducibility, cheap replay |
| session filters, calendar windows | `(srfi 19)` in Scheme | stdlib-backed, loud, exact |
| signal interpretation from precomputed features | Scheme | the part you iterate on daily |
| position/risk state machines | Scheme | explicit, testable, close to the decision |
| order policy and pre-trade checks | Scheme | must be auditable line by line |
| event loop over bars | Python host loop → Scheme callback (Pattern B), or full Scheme for small data | ~14 µs per pre-parsed decision |
| broker I/O, fills, reconciliation | Python | network, retries, state, secrets |
| portfolio accounting and metrics | Python | volume and libraries |
| strategy configuration and parameters | Scheme data | readable, diffable, replayable |

A useful heuristic is **change frequency × failure cost**:

- **Changes often, failure is expensive** — strategy rules, risk gates, order
  policy. Keep them in Scheme, small, pure, and tested.
- **Changes rarely, volume is high** — data cleaning, kernels, accounting. Keep
  them in Python/numpy.
- **Changes often, failure is cheap** — research scripts, notebooks. Either
  home is fine; use whichever is faster to iterate.
- **Changes rarely, failure is cheap** — do not build it yet.

The DSL is not the place to win a microbenchmark. It is the place to make a
rule reviewable by a risk officer and changeable without a redeploy of the
numeric stack.

## 2. Reference architecture

The production shape this page recommends:

```
vendor / broker
   │
   ▼
Python data plane        ingest → clean → adjust → align → as-of join
   │
   ▼
Feature snapshot         {name: f64vector} + one shared timestamp index
   │                     + snapshot id / data version
   ▼
Scheme strategy plane    decide(ctx) -> decision   (pure, no I/O, no clock)
   │
   ▼
Scheme risk plane        pre-trade checks -> ok / err
   │
   ▼
Python execution plane   order router, fills, retries, idempotency
   │
   ▼
Python ledger/metrics    positions, cash, P&L, exposure, drawdown
   │
   └──────────────► next ctx (position, equity, clock)
```

The arrows are the contract boundaries. Three rules keep the architecture
honest:

1. **The strategy never talks to the network.** It receives values and returns
   a decision. The host executes.
2. **The strategy never reads the wall clock.** The timestamp is part of the
   context, injected by the host. Backtests and live runs use the same code.
3. **The strategy never mutates a shared feature vector.** Feature vectors are
   immutable by convention; new features come back as new vectors.

Once those three hold, a backtest and a live session are the same `decide`
closure with different drivers.

## 3. The data seam

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

1. **One `f64vector` per column, one conversion per column. Cache it.** Do not
   rebuild the vectors per bar.
2. **Vectors cross the seam unboxed; decisions cross as values** — symbols,
   variants, records or small lists. The seam is not a dataframe API.
3. **Treat feature vectors as immutable.** Fresh features from numpy go back as
   new `f64vector`s (Pattern C), not as side effects on shared buffers, so
   backtests stay reproducible.
4. **Align before you ship.** Every vector must have the same length and the
   same timestamp index. Assert it at the seam, not inside the rule.
5. **Make the NaN policy explicit.** Trading data has gaps. Decide once whether
   NaN poisons a window, is skipped, or is forward-filled, and encode it at the
   feature boundary. Do not let every strategy invent its own rule.
6. **Decide adjusted vs raw prices once.** Signals usually want adjusted
   prices; execution and P&L must use the raw print with corporate actions
   accounted for. Mixing the two is a classic silent backtest bug.
7. **The empty list is `()`.** A host column of length zero is an empty
   `f64vector`, not `NIL`; do not pass `NIL` to `array.array`.

A useful host-side guard:

```python
def freeze_features(cols, expected_len):
    """Check the seam boundary once, not in every rule."""
    for name, vec in cols.items():
        if vec.typecode != "f64":
            raise TypeError(f"{name}: expected f64vector, got {vec.typecode}")
        if len(vec) != expected_len:
            raise ValueError(f"{name}: {len(vec)} elements, expected {expected_len}")
    return cols
```

## 4. The strategy contract

A strategy is a **pure function from context to decision**. The context is the
complete input for one event; the decision is a closed variant the host can
execute or reject.

```scheme
;; The complete input to one decision. The host builds a fresh one per event.
(define-record-type ctx
  (make-ctx i ts fast slow position equity)
  ctx?
  (i ctx-i)                 ;; bar index, exact integer
  (ts ctx-ts)               ;; decision time, UTC seconds or a date
  (fast ctx-fast)           ;; f64vector
  (slow ctx-slow)           ;; f64vector
  (position ctx-position)   ;; 'flat, 'long, 'short, ...
  (equity ctx-equity))      ;; exact rational or integer

;; A closed decision type: the host must handle every case.
(define-variant decision
  (hold)
  (enter side size reason)
  (exit reason)
  (reject reason))
```

The rule:

```scheme
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

(define (decide c)
  (let ((i (ctx-i c)))
    (cond ((cross-over? (ctx-fast c) (ctx-slow c) i)
           (enter 'long 100 'cross-over))
          ((cross-under? (ctx-fast c) (ctx-slow c) i)
           (exit 'cross-under))
          (else (hold)))))
```

The host-facing translation is deliberately boring:

```scheme
(define (decision->order d price)
  (variant-match d
    ((hold) '())
    ((enter side size reason) (list 'order side size price reason))
    ((exit reason) (list 'close reason))
    ((reject reason) (list 'reject reason))))
```

Why a variant rather than a string or a symbol? Because `variant-match` is
exhaustive: when you add a `scale` decision, the compiler of your rules — the
matcher — names the case you forgot instead of quietly returning `#f` and
trading nothing.

## 5. Expressing strategy rules in Scheme

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

**Parameters are closures, not globals.** A strategy factory keeps the
parameters explicit and makes a sweep a loop over values:

```scheme
(define (make-threshold-strategy threshold size)
  (lambda (ctx)
    (if (> (f64vector-ref (ctx-fast ctx) (ctx-i ctx)) threshold)
        (enter 'long size 'above-threshold)
        (hold))))
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
;; exact: rationals, so no float drift to round away
(* equity risk stop-distance)      ;; => 750
```

The conversion to shares is a *policy* decision, not an accident. Use `floor`,
`ceiling` or `round` explicitly, and convert the inexact result back to an
exact integer so the ledger does not carry a float share count:

```scheme
(define (shares-for notional price)
  (inexact->exact (floor (/ notional price))))   ;; integer shares, deliberately floored
(shares-for 750 227.48)            ;; => 3
```

## 6. Typed decisions, Results, and risk gates

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
;; => (ok #f64(1.0 2.0))

(define (checked-ref v i)
  (if (< -1 i (f64vector-length v))
      (ok (f64vector-ref v i))
      (err "index out of range")))

(define closes (f64vector 101.0 102.5 99.0 103.25 104.0))
(result-bind (checked-ref closes 1)     ;; 102.5
  (lambda (x) (ok (* x 2.0))))
;; => (ok 205.0)
```

A pre-trade gate is the same shape. It belongs in Scheme because it is a rule,
not a data-engineering step:

```scheme
(define (decision-notional d price)
  (variant-match d
    ((hold) 0.0)
    ((enter side size reason) (* size price))
    ((exit reason) 0.0)
    ((reject reason) 0.0)))

(define (pre-trade-check d equity price)
  (variant-match d
    ((hold) (ok d))
    ((enter side size reason)
     (if (> (decision-notional d price) (* equity 1/10))
         (err (list 'max-notional (decision-notional d price)))
         (ok d)))
    ((exit reason) (ok d))
    ((reject reason) (err reason))))

(pre-trade-check (enter 'long 40 'cross) 100000 227.48)
;; => (ok (enter long 40 cross))

(pre-trade-check (enter 'long 1000 'cross) 100000 227.48)
;; => (err (max-notional 227480.0))
```

The gate returns data, not a side effect. The host decides what to do with an
`err`: log it, reject the order, page the trader, or trip the kill switch.

## 7. Time: sessions, broker clocks, lookbacks

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

**Clock injection is not optional.** A strategy must never call
`current-time` or `current-date`; the host passes the decision timestamp in
`ctx-ts`. That one rule is the difference between a replayable backtest and a
strategy that behaves differently on the second run.

**Timezones and calendars.** `(srfi 19)` has integer offsets, not named zones;
the host supplies the right offset per timestamp (Python's `zoneinfo` does the
DST work). A real session gate also needs the exchange holiday calendar and
half-days — weekday plus hour is a first approximation, not a market calendar.

**Lookbacks: bars or time?** A 20-bar lookback and a 20-minute lookback are
different things. Keep the distinction explicit in the context and in the
feature builder; do not let a rule infer it from vector length.

## 8. Streaming: one stream vocabulary for backtest and live

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

Use generators for **control flow** (replay, merge, live feed), not as a
replacement for vectorized feature computation. A `gmap` with a Scheme lambda
over a million bars is the same interpreter loop as any other per-bar callback.

## 9. The smallest end-to-end loop

Before the patterns, the shape: one pre-parsed strategy, one host loop, one
executed decision.

```python
import array
from shslisp import make_env, run
from shslisp.evaluator import apply_procedure
from shslisp.types import Srfi160Vector, intern, NIL

env = make_env()
run("""
(define (decide closes i position equity)
  (cond ((or (< i 1) (not (eq? position 'flat))) '())
        ((> (f64vector-ref closes i) (f64vector-ref closes (- i 1)))
         (list 'order 'long 100 'momentum))
        (else '())))
""", env)
decide = env.lookup(intern("decide"))

closes = Srfi160Vector("f64", array.array("d", [100.0, 101.0, 100.5, 102.0]))
for i in range(1, len(closes)):
    decision = apply_procedure(decide, [closes, i, intern("flat"), 100000])
    if decision is not NIL:
        print(i, decision)
# 1 [order, long, 100, momentum]
# 3 [order, long, 100, momentum]
```

The important properties: the strategy is parsed **once**, the decision is a
value, and the host owns the loop, the clock, the broker and the book. The
next sections make each of those explicit.

## 10. Execution patterns

### Pattern A — full-Scheme event loop (small data)

For daily bars or small universes, where the whole history is a few tens of
thousands of bars. The loop *is* the book: position, entry and cash are
explicit state, not hidden globals.

`f64vector-fold` passes **elements**, not indices. If the vector holds prices,
carry the index yourself or use a named `let` loop — this is the corrected
shape:

```scheme
(import (srfi 160 f64))
;; cross-over? / cross-under? are the §5 rule macros (one program, document order)
(define fast (f64vector 1.0 2.0 3.0 4.0))
(define slow (f64vector 1.5 1.5 2.5 2.5))

(define (backtest fast slow equity)
  (let ((n (min (f64vector-length fast) (f64vector-length slow))))
    (let loop ((i 1) (book (list 'flat 0.0 equity)))
      (if (>= i n)
          book
          (loop (+ i 1)
                (cond ((cross-over? fast slow i)
                       (list 'long (f64vector-ref fast i) (list-ref book 2)))
                      ((cross-under? fast slow i)
                       (list 'flat 0.0 (list-ref book 2)))
                      (else book)))))))

(backtest fast slow 100000)
;; => (long 2.0 100000)
```

This is a **skeleton**: it shows where the book lives, not a complete P&L. A
real transition must add fill price, quantity, fees, slippage and realized
P&L. The point is that every one of those is an explicit argument to the next
iteration, so it is testable.

Pattern A is budget-bound (see §11). Keep it for small histories; for large
ones use Pattern B or a host kernel.

### Pattern B — Python loop, Scheme decisions (the tick-scale default)

Parse the strategy *once*, apply it per event; the host owns the data plumbing:

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

closes_vec = make_close_vector(df["close"].to_numpy())   # §3: one f64vector
for i, bar in enumerate(bars):                           # host loop, host clock
    signal = apply_procedure(strategy, [closes_vec, i])
```

Measured in §11: **~13.6 µs per pre-parsed decision** on this machine — one rule
over 1M bars is ~13 s; twenty rules is minutes. Daily bars and single-symbol
minute replays are comfortable; at tick scale the Scheme callback must be the
*decision*, not the *computation*. Each per-bar `apply_procedure` is its own
root evaluation, so Pattern B does not accumulate the global step budget.

### Pattern C — host features and signals, Scheme risk/order layer (the daily driver)

Compute rolling features **and the signal vector** vectorized host-side, hand
them over, and keep only the decision and the gates in Scheme. Do not use
`f64vector-map` with a Scheme lambda over a full 1M-row history: that is an
interpreter loop with a callback per element — ~3.6 s for the simplest body,
and a branchier rule hits the 5M-step budget before the vector ends.

```python
import array, numpy as np
from shslisp.types import Srfi160Vector, intern

def f64col(arr):
    return Srfi160Vector("f64", array.array("d", np.ascontiguousarray(arr, dtype=np.float64)))

fast = f64col(df["close"].rolling(10).mean().fillna(0.0).to_numpy())
slow = f64col(df["close"].rolling(50).mean().fillna(0.0).to_numpy())

# The signal is a column too; numpy does the 1M comparisons.
fast_a = np.frombuffer(fast.data, dtype=np.float64)
slow_a = np.frombuffer(slow.data, dtype=np.float64)
signal = f64col(np.where(fast_a > slow_a, 1.0, np.where(fast_a < slow_a, -1.0, 0.0)))

env.define(intern("fast"), fast)
env.define(intern("slow"), slow)
env.define(intern("signal"), signal)
```

```scheme
(import (srfi 160 f64))
(define (decide i position)
  (let ((s (f64vector-ref signal i)))
    (cond ((and (> s 0.0) (eq? position 'flat)) (enter 'long 100 'signal))
          ((and (< s 0.0) (eq? position 'long)) (exit 'signal))
          (else (hold)))))
```

This is the daily driver: numpy owns the 1M-element math, Scheme owns the
branch, the sizing and the risk gate. If the history is small enough to stay
under the budget, `f64vector-map` is a convenient way to compute a signal in
Scheme — but treat it as a small-data convenience, not as a vectorized kernel.

### Pattern D — parameter sweep / walk-forward

A sweep is a host loop over parameters; the strategy source is parsed once:

```python
for fast_n, slow_n in grid:
    features = build_features(bars, fast_n, slow_n)   # host-side, vectorized
    env.define(intern("fast"), features["fast"])
    env.define(intern("slow"), features["slow"])
    pnl = run("(backtest fast slow 100000)", env)     # or the host-loop driver
    results.append((fast_n, slow_n, pnl))
```

Use walk-forward splits, not one long in-sample optimization. The DSL makes the
rule readable; it does not protect you from overfitting.

### Pattern E — live event loop

The live loop is Pattern B with three host adapters:

- **Feed**: replay file → live socket. Both answer `next_event()`.
- **Clock**: simulated timestamp → real UTC clock. Both return the event time.
- **Broker**: paper fill → real order router. Both accept an idempotent order.

The Scheme strategy is unchanged. If it is not unchanged, the backtest is not a
backtest of the live strategy.

## 11. Performance: measured costs and the step budget

Measured on this machine (Python 3.14.7, Apple M1 / arm64), 1M `f64`
elements. The numpy row is an order-of-magnitude reference from a host that
has numpy installed — this repository's environment deliberately does not:

| Operation | Time | Note |
| --- | --- | --- |
| numpy `sum` over 1M f64 | ~0.3–1 ms | host-side, *when* numpy is installed |
| `(f64vector-fold + 0.0 v)` over 1M | **~1.1 s** | the callback is the `+` primitive; no Scheme eval per element |
| `(f64vector-fold (lambda (a x) (+ a x)) 0.0 v)` over 1M | **~3.8 s** | a Scheme lambda is an interpreter call per element — ~3.5× the primitive |
| `(f64vector-map (lambda (x) (+ x 1.0)) v)` over 1M | **~3.6 s** | completes; the budget lands near 1.3M for this body |
| Scheme tail loop step | ~10 µs | `(loop (- i 1) (+ acc 1.0))` |
| per-bar `evaluate_program` (read+eval) | ~10 µs minimal; ~25 µs for `(decide closes i)` | parse included; expression-dependent |
| per-bar **pre-parsed** callback | **~12–14 µs/bar** | `apply_procedure(strategy, [vec, i])` — 1M bars ≈ 12–14 s per rule pass |

The conclusion is not "Scheme is slow" — it is **put each kind of code where
it is cheap**. The single most important limit is the evaluator's step budget:

- `STEPS_BUDGET = 5_000_000` per **root evaluation**.
- The threshold is a property of the rule body, not the vector: a one-operation
  lambda (`(+ x 1.0)`) survives 1.2M elements and raises at 1.3M; a rule with
  one comparison and a branch (`(if (> x 0.5) 1.0 -1.0)`) raises at ~900k; one
  with two arithmetic branches (`(if (> x 0.5) (* x 2.0) (- x 1.0))`) raises
  at ~550k. Each is a `LispBudgetError` naming the 5,000,000-step ceiling —
  loud, and the same error a runaway tail loop gets.
- Pattern B does not accumulate the budget: each per-event `apply_procedure`
  is a fresh root. That is another reason it is the default for large histories.
- Chunking a vector helps only if you carry the strategy state across chunks and
  keep each chunk under the budget. A chunked `f64vector-map` that restarts from
  scratch is not the same computation.
- If you need a longer single evaluation, the honest options are: a host-side
  kernel (numpy/numba), a per-bar host loop (Pattern B), or a documented
  configurable budget — not a quiet monkeypatch of the module constant.

**How to benchmark.** Warm up first, use `time.perf_counter`, run enough
iterations, report the expression and the hardware, and separate primitive
callbacks from Scheme closures. A number without the expression is not a
benchmark; it is a rumour.

**Where the time goes.** `f64vector-ref` is cheap; the expensive part is
entering the evaluator per element (`apply_procedure` on a closure). That is
why `(f64vector-fold + ...)` with a primitive is fast, while the same fold with
a Scheme lambda is ~3.5× slower — and why the budget becomes the wall just
past a million elements for the simplest body.

## 12. What a backtest must model

This is the part that separates a research script from a backtest you can
defend. Pin each item in a test or a config file:

| Concern | What to decide | Where it lives |
| --- | --- | --- |
| point-in-time universe | delisted symbols included; universe as of each date | Python |
| corporate actions | adjusted signals vs raw execution; dividends/splits in P&L | Python |
| timestamps | UTC internally; exchange zone at the boundary; DST | Python + `(srfi 19)` |
| sessions | holidays, half-days, auctions, halts | Python calendar |
| bar construction | trades vs quotes, last vs mid, OHLC aggregation | Python |
| lookahead | only trailing windows; decision at close, fill at next open (or explicit same-close assumption) | Scheme + tests |
| costs | commission, spread, slippage, market impact, borrow, financing | Python ledger |
| fill model | market/limit/stop, partial fills, queue position, latency | Python execution |
| sizing | cash, margin, leverage, buying power, integer shares | Scheme policy + Python ledger |
| shorting | locate/borrow, recalls, hard-to-borrow | Python |
| risk | max order/position, gross/net exposure, sector, correlation, drawdown kill switch | Scheme gates |
| delistings/mergers | cash/stock treatment, forced exits | Python |
| liquidity | participation rate, ADV filter, capacity | Python |
| validation | walk-forward, out-of-sample, multiple-testing correction | Python |
| metrics | Sharpe, Sortino, Calmar, turnover, hit rate, payoff, max DD, exposure | Python |
| reproducibility | data snapshot id, code version, params, seed, logs | Python |
| reconciliation | positions/cash vs broker; break investigation | Python |

A backtest that omits costs and fill assumptions is not conservative or
aggressive; it is undefined.

## 13. Risk and portfolio layer

Keep the **pre-trade** checks in Scheme: they are small, rule-shaped, and must
be auditable line by line. Keep **post-trade** accounting in Python: it is
high-volume and belongs with the ledger.

A useful ordering for a pre-trade gate:

1. **Session / instrument** — is the market open, is the symbol restricted,
   is there a halt?
2. **Order sanity** — side, quantity, price collar, duplicate id, max order
   notional.
3. **Position limits** — max position, gross/net exposure, sector/country
   concentration, correlation budget.
4. **Capital** — buying power, margin, leverage, borrow availability.
5. **Kill switch** — daily loss, drawdown, reject-rate spike, data staleness.

The gate returns `ok`/`err`; the host owns the action. A risk check that
silently clips an order without logging is worse than a rejection.

**Money and size.** Keep sizing arithmetic exact (integers/rationals) until the
broker boundary; convert to integer shares with an explicit rounding policy;
keep fees and residual cash in the ledger, not in the rule.

**Exposure.** Gross and net are different limits. A market-neutral book can
have large gross and small net; a risk gate that checks only one of them is
incomplete.

## 14. Backtest/live parity

The same `decide` closure should run in research and production. The host
supplies four adapters:

| Adapter | Backtest | Live |
| --- | --- | --- |
| `Feed` | snapshot replay | socket / vendor stream |
| `Clock` | simulated event time | real UTC clock |
| `Broker` | fill simulator | order router |
| `Ledger` | in-memory/Parquet | durable database |

Practical rules:

- **No `current-time` / `current-date` in strategy code.** The event time comes
  from the context.
- **No network, no file I/O, no global mutable state in strategy code.**
- **Idempotent order ids.** Reconnects and retries must not double-fill. The
  id is generated by the host and logged with the decision.
- **Reconcile on restart.** Positions and cash come from the broker, not from
  a hopeful in-memory variable.
- **Log the decision inputs, not just the order.** A hash of the feature
  snapshot, the rule version, the parameters and the context is what lets you
  reproduce a surprising fill.
- **Paper trading is a first-class mode**, not a separate code path.

## 15. Testing a strategy

Pin the behaviour in tests, not in comments:

- **Rule unit tests** — hand-built vectors, exact expected decisions, including
  the boundaries (`i == 0`, empty vector, single bar).
- **Golden backtests** — one fixed data snapshot, one expected ledger. Update
  the golden only with a written explanation.
- **No-lookahead property test** — at index `i`, mutate every future value and
  assert the decision is unchanged. This is the highest-value test in the
  suite.
- **Invariants** — position never exceeds the limit; cash + marked positions =
  equity; no negative quantity unless shorts are allowed; every fill has an
  order.
- **Reproducibility** — same snapshot + same parameters + same code → same
  ledger, bit for bit.
- **Sensitivity** — small parameter changes should produce plausible changes,
  not a cliff. A cliff is usually an overfit or a bug.
- **Edge cases** — NaN, zero volatility, missing bar, holiday, DST transition,
  leap day, split, delisting, halted symbol.
- **Cost/fill sensitivity** — rerun with doubled fees and worse slippage; if
  the edge disappears, it was never there.

A no-lookahead test sketch (host side):

```python
import array

from shslisp.evaluator import apply_procedure
from shslisp.types import Srfi160Vector

def assert_no_lookahead(strategy, args_before, feature_vectors, args_after, i, trials=20):
    args = args_before + feature_vectors + args_after
    baseline = apply_procedure(strategy, args)
    for _ in range(trials):
        mutated = []
        for vec in feature_vectors:
            data = array.array("d", vec.data)
            for j in range(i + 1, len(data)):
                data[j] = data[j] * 1.01 + 0.01     # perturb the future
            mutated.append(Srfi160Vector("f64", data))
        assert apply_procedure(strategy, args_before + mutated + args_after) == baseline
```

The exact plumbing varies; the property is the point.

## 16. Anti-patterns

- **Parsing or evaluating a strategy string per bar.** Parse once; call a
  closure. The read+eval cost is pure overhead.
- **A Scheme lambda over a 1M-element vector.** It is an interpreter loop:
  seconds per pass for the simplest body, and the step budget for anything
  branchier. Use numpy/numba or Pattern B.
- **Calling `current-time` inside a rule.** The backtest stops being a replay.
- **Hidden global state.** The book must be an argument, not a `set!` in a
  module.
- **Floating-point money in the rule.** Use exact integers/rationals until the
  broker boundary.
- **Recomputing features per bar.** Compute once per snapshot and cache.
- **Mixing adjusted signals with raw execution P&L.** Decide and document.
- **Ignoring NaN.** A single gap can poison a rolling window.
- **Today's universe in a 10-year backtest.** Survivorship bias is a silent
  upward tilt.
- **No costs, no slippage, no capacity.** The backtest becomes a fantasy.
- **Optimizing on the test period.** Walk-forward or admit it is in-sample.
- **Treating a green backtest as a live-ready strategy.** Paper trade,
  reconcile, monitor.

## 17. What to build next (the S14 candidate)

The seams above work today; these are the edges that would still hurt. The
guiding rule is the same: **new numeric kernels are host code; new rules are
Scheme; the core stays zero-dependency.**

- **A `(quant)` extension library, pure Scheme.** Order/decision variants,
  risk gates, session helpers, sizing policies, ledger-facing event shapes.
  This is a natural home for the rules that should not live in the core.
- **Host kernels, installed as primitives.** Rolling mean/std/min/max, EMA,
  zscore, ATR, true range, gap detection, returns/log-returns, crossover
  signal vectors. Implement them over `f64vector.data` with numpy/numba when
  the host has it, and keep a pure-Python fallback if the dependency is
  optional. Do not add numpy to the core.
- **A NaN policy.** Decide "NaN poisons the window", "skip and renormalize", or
  "forward-fill", and encode it once. This should land before rolling
  primitives.
- **OHLCV helpers.** True range and ATR from four vectors are small, pure, and
  easy to pin.
- **A configurable step budget or a chunking helper.** The 5M constant is a
  safety feature, but a quant host needs a documented way to process a long
  history without monkeypatching a module global.
- **A fill/execution simulator.** Market, limit, stop, partial fill, queue
  position, latency, fees, slippage. This is host code, but its *contract* is
  part of the strategy API.
- **Feature snapshot/versioning.** A snapshot id, a data version, and a
  reproducible manifest are worth more than another indicator.
- **A golden-backtest harness.** One command that replays a snapshot and
  compares the ledger, including costs and reconciliation.

A candidate like this enters [`../SRFI_TASKS.md`](../SRFI_TASKS.md) only after
it states its user value and passes the "meets its semantics or fails loudly"
gate — the same bar S10–S13 cleared.

## 18. How to verify

From a checkout of this project:

```bash
# the SRFI surface this page relies on
python -m pytest tests/test_srfi160.py tests/test_srfi19.py tests/test_generators.py -q

# the page's own harness: every Scheme snippet, in document order
python -m pytest tests/test_quant.py -q

# the docs guard (links, referenced files, cited tests)
python -m pytest tests/test_docs.py -q

# the whole suite
python -m pytest -q
```

Every Scheme snippet on this page was evaluated against this build — and
that claim is now machine-kept, not remembered. The Python fences are host
programs: numpy/pandas/numba are host dependencies, not repository ones (see
[`shslisp/embed.py`](../../shslisp/embed.py)'s contract), so the suite does not
execute them; the one primitive this page installs itself
(`make-close-vector`) is rebuilt inside the harness, which is enough to
exercise the Scheme half of the seam. The benchmark numbers are from Python
3.14.7 on an Apple M1 (arm64); they are costs, not constants — rerun them on
your target hardware before making a latency decision, and report the
expression alongside the number.

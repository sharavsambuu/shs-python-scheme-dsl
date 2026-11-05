# SRFI tasks: the ledger

> **The claim, in one paragraph.** The SRFI layer grows by ledger entry, never
> by accretion. A task either lands a library that meets its SRFI's semantics —
> audited name by name, with the tests to show it — or it is not scheduled.
> The checkable truth is the matrix in [`srfi.md`](srfi.md) and the tables in
> [`tests/test_srfi.py`](../tests/test_srfi.py); this page is the plan, and
> where a plan and a test disagree, the test wins.

> **Honesty note.** This file was cited by [`srfi.md`](srfi.md),
> [`lisp-dsl.md`](lisp-dsl.md), and [`capabilities.md`](capabilities.md) before
> it was committed — the drift [`tests/test_docs.py`](../tests/test_docs.py)
> now prevents. The S0–S8 per-task notes were therefore never preserved in
> version control; the entries below are reconstructed from the evidence the
> repository does keep (the matrices, the test tables, the status lines), and
> they claim exactly that and no more.

## Landed

| Tasks | What landed | Where the truth lives |
| --- | --- | --- |
| S0–S6 | The six `(srfi N)` libraries — `(srfi 1)`, `(srfi 26)`, `(srfi 88)`, `(srfi 89)`, `(srfi 197)`, `(srfi 241)` — plus the library system that hosts them | the matrix in [`srfi.md`](srfi.md); the `MUST_IMPORT`/`MUST_BIND` tables in [`tests/test_srfi.py`](../tests/test_srfi.py) |
| S7 | The SRFI matrix page, audited name by name, with the deviations | [`srfi.md`](srfi.md) |
| S8 | The profiles: `dsl` (the default; SRFIs pre-imported with the documented collision table) and `r7rs` (the strict subset, no SRFIs) | [`shslisp/profile.py`](../shslisp/profile.py), [`tests/test_profile.py`](../tests/test_profile.py) |
| S9 | The generator library: lazy sequences as prelude (`shslisp/generators.scm`), both profiles, `(srfi 158)` still unclaimed | [`srfi.md`](srfi.md) (the generator section), [`tests/test_generators.py`](../tests/test_generators.py), chapter [19](lisp_tutorial/19-generators.md) |
| S10 | `(srfi 19)` time and date, core-backed on the Python stdlib, both profiles, documented deviations | [`srfi.md`](srfi.md), [`shslisp/srfi19.py`](../shslisp/srfi19.py), [`tests/test_srfi19.py`](../tests/test_srfi19.py) |
| S11 | `(srfi 160 base)` + `(srfi 160 f64)` — the buffer-protocol numeric vectors and the numpy bridge, `#f64(...)` reader/printer round-trip | [`srfi.md`](srfi.md), [`shslisp/srfi160.py`](../shslisp/srfi160.py), [`tests/test_srfi160.py`](../tests/test_srfi160.py) |
| S12 | The `(srfi 158)` audit-and-complete: eof-object protocol, the full combinator set, the accumulators | [`srfi.md`](srfi.md), [`shslisp/generators.scm`](../shslisp/generators.scm), [`tests/test_generators.py`](../tests/test_generators.py) |

`(srfi 204)` is recorded in the matrix as *withdrawn*: it is never
implemented, and importing it fails, naming `(srfi 241)`.

## Open

*(A new S-task enters here only after it states its user value and passes the
"meets its semantics or fails loudly" gate. The trading layer was scheduled
on 2026-11-05 and landed the same day — the three entries below are the
record. Nothing else is open. The R7RS-track candidates — source locations,
the numeric-tower follow-ups — live in [`R7RS_TASKS.md`](R7RS_TASKS.md).)*

### ~~S10 — `(srfi 19)`: time and date~~ — landed

Landed as `shslisp/srfi19.py` — core-backed primitives registered in
`shslisp/builtins.py`, scoped by the library entry. The pre-declared
deviations landed as declared: `time-tai`/`time-thread` exist as constants
and their clocks refuse loudly; no leap seconds; integer zone offsets only.
Truth: `tests/test_srfi19.py`, with the Julian Day pinned against 2451545.0.

**User value.** A trading strategy is time-conditioned: session filters
("only 9:30–16:00"), window slices, lookback spans, and reconciling Quant Data
Manager's UTC timestamps with MetaTrader 5's broker server time. The only
time primitive today is `(scheme time)`'s clock (`current-second`,
`current-jiffy`) — no calendar, no parsing, no date arithmetic.

**Shape.** Core-backed, the `(srfi 88)` way: Python primitives over
`datetime`/`zoneinfo`/`timedelta`, registered in `shslisp/library.py` with an
explicit export list — not a pure-Lisp port, because the Gregorian machinery
would be slow and wrong-prone in Lisp while the stdlib is battle-tested.

**Scope.** The workhorse subset — `time-utc`, `time-duration`, `date`,
`current-time`, `time->date`, `date->time-utc`, `date->string`,
`string->date`, the date accessors and arithmetic, Julian day — with the
export list a documented, checked subset, the `(srfi 1)` precedent.

**Deviations, decided up front.** No TAI (omitted, or shimmed as UTC —
documented either way); no leap seconds (Python `datetime` cannot represent
second 60); timezone offsets are SRFI 19's integer offsets, with named zones
published by the host where a strategy needs one.

### ~~S11 — `(srfi 160)`: numeric vectors — the numpy bridge~~ — landed

Landed as `shslisp/srfi160.py` over an `array.array` payload
(`Srfi160Vector` in `shslisp/types.py`): `(srfi 160 base)` for all twelve
types, `(srfi 160 f64)` with the full SRFI-133-shaped set, and the
`#f64(...)` reader/printer round-trip for eleven types (`#u8(` stays the R7RS
bytevector). `@vector-comparator` was omitted as pre-declared. Truth:
`tests/test_srfi160.py`.

**User value.** The type that speaks pandas/numpy: a DataFrame becomes
*columns of `f64vector`s*, never a list of boxed values, so strategy logic
reads unboxed doubles and the hot loops stay on the Python side of the seam.

**Shape.** `(srfi 160 base)` and `(srfi 160 f64)` first. `f64vector` is
backed by the buffer protocol — `array.array('d')` by default (the
zero-dependency promise holds), zero-copy views to and from numpy arrays
when the host provides them. The operations are core-backed Python
primitives, so a numpy backing can serve them vectorized instead of through
the tree walker. `u8vector` joins when binary plumbing needs it.

**Deviations, decided up front.** `@vector-comparator` is omitted — it
requires SRFI 128, which stays unscheduled; the omission is documented, not
shimmed. The remaining ten numeric types ride the same generic kernel later.

### ~~S12 — the `(srfi 158)` audit-and-complete of the generator prelude~~ — landed

Landed in `shslisp/generators.scm`: the eof-object exhaustion protocol (the
S9 `generator-end` sentinel still defined and accepted, so pre-S12 code keeps
running), the full combinator set, the multi-generator drains, the searching
half, and the accumulators. `make-coroutine-generator`/
`make-for-each-generator` fail loudly — they need re-entrant continuations
(`docs/r7rs.md`, Tier 1). Truth: `tests/test_generators.py`.

**User value.** `shslisp/generators.scm` (S9) is the laziness story; the
audit turns it into an honest `(srfi 158)` claim and adds the accumulator
half — `sum`/`product`/`max`/`min`/`count` and the collection accumulators —
which are running-stats primitives over tick and bar streams.

**Scope.** The protocol decision first: SRFI 158's exhaustion value is the
*eof-object* (already in the core), the prelude's is the custom
`generator-end` pair — align on the eof-object, a contained change to the
prelude and its tests. Then the missing names — the coroutine/unfold/iota
constructors, `gappend`, `gcombine`, `gfilter-map`, `gindex`, `gselect`, the
`gtake-while`/`gdrop-while`/`gdelete` family, and the drains' optional forms
— audited name by name against the SRFI 158 index;
`tests/test_generators.py` grows the behavioural pins.

**Landing.** Each task flips its `srfi.md` matrix row from *scheduled* to
*supported* in the same change that binds it, and adds its feature identifier
to `shslisp/profile.py`.

### ~~S9 — generators / lazy sequences~~ — landed

~~The one scheduled feature~~ Landed as `shslisp/generators.scm`: lazy sequences
as ordinary closures — a generator is a 0-argument procedure answering the
next value or the unique `generator-end` object — with `gmap`/`gfilter`/
`gtake`/`gdrop` and the drains. No evaluator change, no re-entrant
continuations. See the landed table above.

## Deliberately not scheduled

Everything else — 64, 125, 128, 132, 133, 146, 151, 152, 170, 173, 180, 193,
and the rest of the catalog — has no open task. Breadth is not the goal.
A candidate must state its user value, pass the "meets its semantics or
fails loudly" gate, and enter this ledger as a task before any code. Deferring
is the default. Three candidates examined on 2026-11-05 with the trading use
in mind were sent back here on purpose:

- **41 (streams).** Memoized lazy pairs retain every element — a memory trap
  over multi-year 1-minute histories — cost a thunk per element, and lean on
  re-entrant lazy semantics this dialect's escape-only `call/cc` cannot
  underwrite. Generators (S9/S12) plus the core promises cover the idioms;
  if a self-referential series idiom ever demands it, a small in-house
  prelude over `delay`/`force` answers without a claim.
- **133 (vector library).** Deferred: its operation set is shape-identical
  to SRFI 160's. Build the 160 kernel generically and derive 133 only if a
  real need for heterogeneous vector algorithms appears.
- **189 (Maybe/Either).** `shslisp/rope.scm` already is the project's Either
  library — the `Result` variant, `result-bind`, `>=>`, `result-do`, with the
  monad laws pinned by `tests/test_rop.py`. A second idiom would fork the
  vocabulary; an option-shaped variant belongs in `rope.scm`, not a new SRFI.

SRFI 27 (random sources — Monte Carlo, bootstrap and permutation tests,
random-entry baselines) is the next candidate under consideration, not yet
scheduled. The numeric-tower decision in [`R7RS_TASKS.md`](R7RS_TASKS.md)
still outranks all of them.

## How to verify

```bash
python -m pytest tests/test_srfi.py -q
```

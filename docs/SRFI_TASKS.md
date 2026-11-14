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
| S13 | The audit pass over S10–S12: the sixteen review findings fixed — fill validation, overlap-safe copies, loud `string->date`, a lazy `gmerge`, f64 type strictness, the spec corners, and the strict-profile scoping — each with the test that pins it | [`tests/test_srfi160.py`](../tests/test_srfi160.py), [`tests/test_srfi19.py`](../tests/test_srfi19.py), [`tests/test_generators.py`](../tests/test_generators.py), [`tests/test_profile.py`](../tests/test_profile.py) |
| S14 | `(srfi 125)` hash tables: core-backed over the `equal?`-keyed `HashTable`, twelve audited names, `O(1)` lookups; comparator accepted and ignored, missing key loud | [`srfi.md`](srfi.md), [`shslisp/srfi125.py`](../shslisp/srfi125.py), [`tests/test_s14_to_s18_srfis_tdd.py`](../tests/test_s14_to_s18_srfis_tdd.py) |
| S15 | `(srfi 132)` sorting: Python Timsort behind the caller's comparator, the six non-destructive names, vector `[start end]` subranges | [`srfi.md`](srfi.md), [`shslisp/srfi132.py`](../shslisp/srfi132.py), [`tests/test_s14_to_s18_srfis_tdd.py`](../tests/test_s14_to_s18_srfis_tdd.py) |
| S16 | `(srfi 64)` a Scheme API for test suites: assertion macros (`test-assert`/`-equal`/`-eqv`/`-eq`/`-error`), groups, and the simple runner with pass/fail counts | [`srfi.md`](srfi.md), [`shslisp/srfi64.scm`](../shslisp/srfi64.scm), [`tests/test_s14_to_s18_srfis_tdd.py`](../tests/test_s14_to_s18_srfis_tdd.py) |
| S17 | `(srfi 180)` JSON: `json-read`/`json-write` over stdlib `json`, objects ↔ string-keyed alists, arrays ↔ vectors, `null` ↔ `'null`, loud on malformed input | [`srfi.md`](srfi.md), [`shslisp/srfi180.py`](../shslisp/srfi180.py), [`tests/test_s14_to_s18_srfis_tdd.py`](../tests/test_s14_to_s18_srfis_tdd.py) |
| S18 | `(srfi 28)` `format` (`~a`, `~s`, `~%`, `~~`) + `(srfi 152)`'s seven string utilities; `string-trim` is both-ends (the locked test, documented) | [`srfi.md`](srfi.md), [`shslisp/srfi28.py`](../shslisp/srfi28.py), [`shslisp/srfi152.py`](../shslisp/srfi152.py), [`tests/test_s14_to_s18_srfis_tdd.py`](../tests/test_s14_to_s18_srfis_tdd.py) |

`(srfi 204)` is recorded in the matrix as *withdrawn*: it is never
implemented, and importing it fails, naming `(srfi 241)`.

## Open

*(A new S-task enters here only after it states its user value and passes the
"meets its semantics or fails loudly" gate. The trading layer was scheduled
on 2026-11-05 and landed the same day; the standard-library wave (S14–S18)
was scheduled and landed on 2026-11-14 — the entries below are the record.
Nothing else is open. The R7RS-track candidates — source locations, the
numeric-tower follow-ups — live in [`R7RS_TASKS.md`](R7RS_TASKS.md).)*

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
shimmed. The remaining eleven numeric types ride the same generic kernel later.

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

### ~~S13 — the audit pass over S10–S12 (the review findings)~~ — landed

A post-landing review of the trading layer (2026-11-05) found sixteen
semantic defects the first tests missed; all sixteen are fixed, each with
the test that would have caught it. The findings, by library:

- **`(srfi 160)`.** `make-@vector` passed its fill straight to the
  `array.array` payload, silently coercing invalid elements (an exact `1`
  became `1.0`; `#t` became `1.0`; an out-of-range integer leaked a host
  `OverflowError`) — the fill is now validated like every other insert, and
  the storage backstop raises a Lisp type error. `@vector-copy!`/
  `@vector-reverse-copy!` always copied forward, so a self-overlapping copy
  smeared — they now copy "as if the source is first copied into a temporary
  vector" (SRFI 133). The f64 operations accepted any homogeneous vector
  (an `f64vector-map` over a `u8vector` answered a *u8vector*!) — they now
  require f64vectors and `f64vector-map` answers an f64vector. The spec
  corners: `@vector-any` on an empty vector returns `#t` (SRFI 160's
  explicit rule); `@vector=` with zero or one vector returns `#t` (SRFI
  133's); `@vector-concatenate` refuses a non-list instead of quietly
  returning an empty vector, and `list->f64vector` of the empty list is the
  empty vector; `@vector-index-right`/`skip-right` require equal lengths;
  `@vector-partition` answers the predicate once per element.
- **`(srfi 19)`.** `string->date` validated only the calendar day — it now
  range-checks hour/minute/second like `make-date`, caps the readers' widths
  like the reference's (so `~Y~m~d` parses concatenated input field by
  field), and requires the whole input to match the template. `date-week-number`
  now matches the SRFI 19 reference implementation (`quotient(year-day −
  days-before-first-week, 7)`, the partial first week sharing week 0), and
  `~U`/`~W` are zero-padded per Table 1 with the reference's rule that a
  partial first week bumps the numbering. `time-resolution` validates its
  optional time-type instead of answering any junk; `time-utc->julian-day`/
  `time-utc->modified-julian-day` require a `time-utc`.
- **`(srfi 158)`.** `gmerge` pulled one value from every source at
  construction time, against the SRFI's rule that generator operations
  "return a new generator without consuming any elements from the source
  generator(s)" — the merge is lazy now: heads are pulled on the first call
  of the returned generator.
- **The strict profile.** `install_core` bound the `(srfi 19)`/`(srfi 160)`
  primitives into the core floor unconditionally, so `make_env(profile="r7rs")`
  had `current-time`, `f64vector`, and `date->string` without any import —
  contradicting the docs. They are core-*backed* now, not core-*bound*: the
  primitives install into the libraries' own private scopes on first import
  (`shslisp/library.py`'s `_core_backed_builder`), the default profile's
  pre-import binds the same objects, and `(srfi 160 base)`/`(srfi 160 f64)`
  share one scope so both export lists hand back identical bindings. `(srfi
  158)` deliberately rides the prelude in both profiles, as documented.
- **The doc drift.** "The other ten per-type full libraries" is eleven (twelve
  types, f64 ships) — corrected in `srfi.md`, this ledger, the module
  docstring, and the test docstring.

**The follow-up sweep** then closed the remaining edges the sixteen findings
did not cover. Every base `list-><type>vector` accepts `()`, and every
`<type>vector->list` (plus the f64 slices, reverse conversion, and
`f64vector-segment`) answers an empty list as `NIL`, so `null?`, `list?`, and
`equal?` behave. The Julian Day and date converters reject non-finite or
out-of-range inputs with a Lisp type error instead of leaking a host
`OverflowError`, and `~Y` is four digits per Table 1. `date->string` defaults
to `~c` and prints `Z` at a zero offset, as the reference does; `string->date`
now distinguishes abbreviated from long weekday and month names (exact,
case-insensitive matches, not prefixes) and reads `~z` as exactly `HHMM` or
`HH:MM` after the sign. Each edge has a regression test in
`tests/test_srfi19.py`/`tests/test_srfi160.py`.

Truth: the audit-pass tests in `tests/test_srfi160.py`, `tests/test_srfi19.py`,
`tests/test_generators.py` (the `gmerge` laziness pin), and
`tests/test_profile.py` (the strict-profile and shared-scope pins).

### ~~S9 — generators / lazy sequences~~ — landed

~~The one scheduled feature~~ Landed as `shslisp/generators.scm`: lazy sequences
as ordinary closures — a generator is a 0-argument procedure answering the
next value or the unique `generator-end` object — with `gmap`/`gfilter`/
`gtake`/`gdrop` and the drains. No evaluator change, no re-entrant
continuations. See the landed table above.

### ~~S14 — `(srfi 125)`: hash tables~~ — landed

Landed as `shslisp/srfi125.py`, core-backed over the existing `equal?`-keyed
`HashTable`; ten names are the core's own bindings re-exported, three
(`hash-table-contains?`, `hash-table-size`, `alist->hash-table`) are the new
SRFI spellings. Truth: `tests/test_s14_to_s18_srfis_tdd.py`; the deviations
(comparator ignored, missing key loud, `->alist` entry shape) are in
[`srfi.md`](srfi.md#deviations).

**User value & origin.** Surfaced in `shs-scheme-trading-exps` (the swarm
cross-symbol correlation matrices and per-symbol agent lookup), where `O(N)`
`assoc`/`assq` list scans burn trampoline steps under the `5,000,000`-step
budget.

**Shape & scope.** Core-backed over Python `dict`: `make-hash-table`,
`hash-table?`, `hash-table-ref`, `hash-table-ref/default`, `hash-table-set!`,
`hash-table-delete!`, `hash-table-contains?`, `hash-table-size`,
`hash-table-keys`, `hash-table-values`, `hash-table->alist`,
`alist->hash-table`. Loud errors on missing keys without a default.

### ~~S15 — `(srfi 132)`: sort libraries~~ — landed

Landed as `shslisp/srfi132.py`: the six non-destructive names, Python Timsort
behind a three-way comparison derived from the caller's `less?`, and the
vector variants' optional `[start end]`. Truth:
`tests/test_s14_to_s18_srfis_tdd.py`; the mutation/merge/median omission is in
[`srfi.md`](srfi.md#deviations).

**User value & origin.** Surfaced by `sort-agents-desc` in the swarm
module, where hand-written Scheme sorting loops spend unnecessary interpreter
steps on every bar.

**Shape & scope.** Core-backed over Python Timsort (`sorted`): `list-sorted?`,
`list-sort`, `list-stable-sort`, `vector-sorted?`, `vector-sort`,
`vector-stable-sort`.

### ~~S16 — `(srfi 64)`: a Scheme API for test suites~~ — landed

Landed as `shslisp/srfi64.scm` (pure Lisp): the assertion forms are
`syntax-rules` macros wrapping each expression in a thunk, so `test-error` can
receive `(car 1)` unevaluated and every assertion catches a raising expression
as a test error. The runner is a vector with pass/fail/total, and
`test-end` prints one summary line. Truth:
`tests/test_s14_to_s18_srfis_tdd.py`; the deviations (predicate error-type,
simple runner only, summary format) are in [`srfi.md`](srfi.md#deviations).

**User value & origin.** `shs-scheme-trading-exps` built a custom testing
prelude (`T-127`) to write Scheme-native unit specs (`define-test-suite`,
`check=`, `check-raises`, `check-match`). Providing `(srfi 64)` inside
`shslisp` makes Scheme-native testing available to every host project without
local boilerplate.

**Shape & scope.** Core/prelude library exposing `test-begin`, `test-end`,
`test-group`, `test-assert`, `test-equal`, `test-eqv`, `test-eq`, `test-error`,
`test-runner-current`, `test-runner-simple`, and summary counts.

### ~~S17 — `(srfi 180)`: JSON~~ — landed

Landed as `shslisp/srfi180.py`: `json-read` and `json-write` over the stdlib
`json` module, with the ledger's mapping (objects ↔ string-keyed alists,
arrays ↔ vectors, `null` ↔ `'null`, booleans/numbers preserved) and a loud
error on malformed JSON. Truth: `tests/test_s14_to_s18_srfis_tdd.py`; the
text-only deviation is in [`srfi.md`](srfi.md#deviations).

**User value & origin.** Surfaced by standalone CLI scripts (e.g. the swarm
capstone script) that had to concatenate JSON strings by hand to emit
structured machine-readable telemetry.

**Shape & scope.** Core-backed over Python stdlib `json`: `json-read`,
`json-write`, mapping JSON objects to alists (`symbol`/`string` keys), arrays to
vectors, `null` to `'null`, and booleans/numbers faithfully.

### ~~S18 — `(srfi 28)` + `(srfi 152)`: basic format strings & string utilities~~ — landed

Landed as `shslisp/srfi28.py` (`format`) and `shslisp/srfi152.py` (the seven
string utilities). One deliberate departure: **`string-trim` trims both ends**
— that is the dialect core's established meaning (`shslisp/builtins.py`) and
what the locked S18 test pins; making the imported name left-only would
silently change existing programs, so `string-trim-both` is its alias and the
right-only spelling is not claimed. Truth:
`tests/test_s14_to_s18_srfis_tdd.py`; the deviations are in
[`srfi.md`](srfi.md#deviations).

**User value & origin.** Eliminates repetitive `(display ...)` chains in CLI
scripts and provides standard string splitting/joining/searching (`string-split`,
`string-join`, `string-contains`, `string-trim`) for symbol and path handling.

**Shape & scope.** `(srfi 28)` `format` (`~a`, `~s`, `~%`, `~~`) and a clean,
core-backed `(srfi 152)` subset over Python `str`.

*(See [`TRADING_PLATFORM_TASKS.md`](TRADING_PLATFORM_TASKS.md) for the companion
Runtime/CLI tasks `R-01`–`R-04`.)*

## Deliberately not scheduled

Everything else — 128, 133, 146, 151, 170, 173, 193,
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

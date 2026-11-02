# The numeric tower: a design note

> **What this is.** The design decision the ledger gates on
> ([`R7RS_TASKS.md`](R7RS_TASKS.md)): exact rationals come to the tower
> (Python's `fractions.Fraction`), complex numbers come only after, and every
> behaviour this changes is named here *before* any code moves. The order was
> fixed in the ledger — write the semantics down first, then change what the
> table says changes, deliberately, in the change that lands rationals.
>
> **What this is not.** It is not an implementation. Nothing in `lisp/`
> changes until the R-phase tasks below land, each with its tests updated in
> the same change — the house rule.
>
> **Status.** R1–R4 landed: the tower holds `fractions.Fraction`, arithmetic
> and `/` preserve exactness, inexact zero division answers IEEE, the
> reader/printer round-trip rational literals (`1/3`, `#e1.5` → `3/2`,
> `#e0.1` → `1/10`), `exact`/`rationalize` are fully general, `expt`/`sqrt`
> answer exact rationals when the exact answer exists, the division family
> takes rationals and preserves inexactness, `gcd`/`lcm` take rationals,
> `min`/`max` contaminate, and `integer?` is the mathematical property.
> **Every CHANGE row of the table is live.** The KEEP rows held throughout.
> **C1–C2 have landed**: the exact complex pair of the phase C section exists
> (`lisp/types.py`'s `Complex`), with rows 1–3, 5–12 live — `make-rectangular`,
> `real-part`, `imag-part`, the polar half (`magnitude`, `angle`, `make-polar`),
> exact arithmetic, exact `sqrt` of negative perfect squares, `(log -1)` →
> `+iπ`, the complex transcendentals, contagion, `eqv?`/`equal?`, and
> the real-only family's guard. Rows 13–14 (reader literals and the
> round-trip) are C3's work. The "Today" column below records the pre-R1
> tower this note was written against.

## Where the tower stands

Two types, and the interpreter says so out loud (`exact?`/`inexact?`):

- **exact integers** — Python `int`, unbounded (`(expt 2 100)` is exact);
- **inexact reals** — Python `float`, IEEE double arithmetic, with the
  written specials `+inf.0`, `-inf.0`, `+nan.0` reading and printing.

The documented deviations (pinned in [`r7rs.md`](r7rs.md), [`language.md`](language.md),
and [`lisp-dsl.md`](lisp-dsl.md)) all have one root cause: *there is no exact
rational type*, so every operation whose mathematical result is not an integer
escapes to `float` — or refuses. Probed against today's interpreter:

| Expression | Today | Why |
| --- | --- | --- |
| `(/ 3 4)` | `0.75` | no rational to answer |
| `(/ 4 2)` | `2` | even division stays exact |
| `#e1.5` | `1.5` | `#e` cannot honour its promise |
| `1/3` | a *symbol* | the reader refuses rational literals |
| `(exact 3.5)` | error | nothing exact to return |
| `(rationalize 3.5 0.1)` | error | same root cause |
| `(expt 2 -1)` | `0.5` | negative exact power escapes |
| `(gcd 2.0 4)` | error | integers-only `gcd` |
| `(quotient 7.0 2)` | `3` | drops inexactness (`modulo -7.0 2` gives `1.0` — inconsistent) |
| `(min 1 2.0)` | `1` | no exactness contagion |
| `(/ 1 0.0)` | error | IEEE says `+inf.0` |
| `(integer? 3.0)` | `#f` | R7RS says `#t` — `3.0` is an integer |
| `(numerator 3.5)` | `7.0` | inexact in, inexact out — **correct R7RS, keep** |

## The proposal

**Phase R — exact rationals.** The tower becomes three types: exact integers
(`int`), exact rationals (`fractions.Fraction`, *only* when the value is not
an integer), and inexact reals (`float`). A `Fraction` whose denominator is 1
is **normalized to `int`** at every construction — the tower never holds
`Fraction(2, 1)`, so `eqv?`, hashing, and printing keep one spelling for one
value.

**Phase C — complex.** Only after R is landed and settled: Python `complex`,
the six `(scheme complex)` names leaving `KNOWN_MISSING`, and the `sqrt`/`log`
of negatives. Sketched at the end; not decided here.

## The compatibility table

Every pinned deviation, its future, and the verdict. **CHANGE** rows are the
deliberate breaks: each lands with its tests and its doc pins updated in the
same change, and each is R7RS-correct — that is the whole point of the phase.

| # | Behaviour | Today | Becomes | Verdict |
| --- | --- | --- | --- | --- |
| 1 | `(/ 3 4)` | `0.75` | `3/4`, exact | **CHANGE** — the headline; exactness is preserved by `/` |
| 2 | `#e1.5` | `1.5` | `3/2`, exact | **CHANGE** — `#e` honours its promise |
| 3 | `1/3` | a symbol | the rational `1/3` | **CHANGE** — `p/q` reads as a rational when both parts are decimal digits and `q ≠ 0`; `1/x` stays a symbol |
| 4 | `(exact 3.5)` | error | `7/2` | **CHANGE** — the implementation-restriction error disappears |
| 5 | `(rationalize 3.5 0.1)` | error | the R7RS nearest-rational answer; inexact args give an inexact result | **CHANGE** |
| 6 | `(expt 2 -1)` | `0.5` | `1/2`, exact | **CHANGE** — exact base, exact negative integer exponent |
| 7 | `(sqrt 4)` | `2` | `2` (unchanged) | KEEP — perfect squares stay exact; `(sqrt 2)` stays inexact; `(sqrt 1/4)` becomes `1/2` |
| 8 | `(gcd 2.0 4)` | error | `2.0` — integral inexact integers are accepted, the result is inexact | **CHANGE** — R7RS's whole-value rule; same for `lcm` |
| 9 | `(quotient 7.0 2)` | `3` | `3.0` — inexactness preserved | **CHANGE** — makes `quotient`/`remainder` consistent with `modulo`, which already preserves |
| 10 | `(min 1 2.0)` | `1` | `1.0` — any inexact argument contaminates | **CHANGE** — R7RS exactness contagion for `min`/`max` |
| 11 | `(/ 1 0.0)` | error | `+inf.0` (sign by numerator; `(/ 0.0 0.0)` is `+nan.0`) | **CHANGE** — IEEE-style, consistent with the inexact specials; **exact** `(/ 1 0)` stays an error, full stop |
| 12 | `(integer? 3.0)` | `#f` | `#t` — `integer?` is the mathematical property | **CHANGE** — `exact-integer?` stays `#f` for `3.0`; that distinction is the point of having both |
| 13 | `(numerator 3.5)` → `7.0` | inexact in, inexact out | unchanged | KEEP — already R7RS |
| 14 | `(floor 2.5)` → `2.0` (ties-to-even `round`) | preserves inexactness | unchanged; on exact rationals the four return exact integers | KEEP |
| 15 | `(+ 0.1 0.2)` → `0.3000000000000004…` | IEEE double | unchanged | KEEP — inexact arithmetic is IEEE, untouched by phase R |
| 16 | `(eqv? 1 1.0)` → `#f` | exactness distinguishes | unchanged; `(eqv? 3/4 0.75)` is `#f` by the same rule | KEEP |
| 17 | `(string->number "3/4")` | `#f` | `3/4` | **CHANGE** — the reader's twin |
| 18 | `#x10`, `#e#x10` | work | unchanged for integers; rational literals are **decimal only** (`#x1/3` is not recognized) | KEEP — R7RS requires no radix-rational spelling |
| 19 | `(sqrt -1)` | error | still an error in phase R | KEEP (for now) — phase C's gate |
| 20 | `1/0` | a symbol | a **read error** (denominator must be nonzero) | **CHANGE** — a rational literal that means nothing must not become a symbol |

## Decisions behind the table

- **Normalization is the load-bearing rule.** `Fraction` exists only for
  non-integral exacts. This keeps `exact?` a type check (`int` or `Fraction`),
  keeps `eqv?` cheap, and means phase R changes *no* existing exact-integer
  behaviour — `(/ 4 2)` is `2` before and after.
- **Contagion follows R7RS, not Python.** Python's `Fraction op float` already
  gives `float`; the explicit rules are: exact op exact → exact (rational when
  not integral); any inexact operand → inexact (`float`), computed by
  converting the exact operand(s) to float first. `min`/`max`/`gcd`/`lcm`
  follow the same contamination rule.
- **Exact zero division stays an error.** IEEE infinities answer only for
  inexact zero, where the question has an IEEE answer. An exact `(/ 1 0)` has
  no answer in any tower this project will build; an error that says so is the
  honest result.
- **`integer?` is a property, not a type test.** This is the subtlest row: the
  current `#f` for `3.0` reads as "exactness pedantry", but R7RS is clear —
  `3.0` *is* an integer, and `exact-integer?` exists precisely to ask the
  type-strict question.
- **Performance is acknowledged, not feared.** `Fraction` arithmetic is slower
  than `int`/`float` and can grow denominators; the step budget already bounds
  runaway programs, and unbounded `int` bignums were accepted for the same
  reason. Programs that want speed use `inexact` — the same advice every
  Scheme gives.

## Mechanics, one layer at a time

- **Reader** (`lisp/reader.py`): `p/q` with optional sign, both parts decimal
  digits, `q ≠ 0` → `Fraction`; `q = 0` → read error; anything else with a
  slash stays a symbol. `#e` before any numeric literal converts the value to
  exact (rational when needed); `#i` forces inexact.
- **Printer** (`lisp/printer.py`): a `Fraction` prints `p/q` — and the reader
  must read it back to the same value. The round-trip is a test, not a hope
  (`tests/test_reader.py`).
- **Predicates** (`lisp/builtins.py`): `exact?` accepts `int`/`Fraction`;
  `inexact?` stays `isinstance(float)`; `rational?`/`real?`/`complex?` extend
  to `Fraction`; `integer?` becomes the mathematical property (row 12);
  `exact-integer?` stays strict.
- **Arithmetic**: `+ - * /` with the contagion rules; `expt` exact-negative
  case; `sqrt` checks for a perfect rational square before escaping to float;
  `floor`/`ceiling`/`truncate`/`round` and the `quotient`/`remainder`/`modulo`
  family operate on exact rationals (answers exact integers, inexactness
  preserved for inexact inputs); `gcd`/`lcm` take rationals and integral
  inexact integers.
- **The bool guard**: every `isinstance(x, int)` numeric check must keep
  excluding `bool` and must not accidentally admit or reject `Fraction`
  (`Fraction` is not an `int` subclass — the risk is the checks that *should*
  now accept it).

## Rollout

| Task | Lands | Watch out for |
| --- | --- | --- |
| R1 | Representation, normalization, `+ - * /`, `exact?`/`rational?`, `eqv?`/`equal?` exactness | `tests/test_r7rs.py`'s `test_division_is_inexact_when_not_even_but_never_zero` changes name *and* verdict — that is the point |
| R2 | Reader + printer round-trip, `string->number`/`number->string`, `#e`/`#i` | `1/3` as a symbol is pinned in three docs — updated in the same change |
| R3 | `exact`/`inexact`/`rationalize`/`numerator`/`denominator` | the implementation-restriction errors disappear; their tests flip |
| R4 | `sqrt`/`expt` exact cases, the integer-division family, `gcd`/`lcm`, `min`/`max` contagion, `integer?` | row 12's blast radius: any test or doc pinning `(integer? 3.0)` → `#f` |
| R5 | Doc sweep: [`r7rs.md`](r7rs.md) matrix + deviations, [`language.md`](language.md), [`lisp-dsl.md`](lisp-dsl.md), [`capabilities.md`](capabilities.md) | the matrix counts move; the deviations sections shrink |
| C | Complex numbers, after R settles | the six `KNOWN_MISSING` names leave; `sqrt -1`, `log -1`, `magnitude` on rationals-turned-complex; NaN/inf corners (`(make-rectangular +inf.0 0)`) get their own table then — see [the phase C section](#phase-c--the-complex-tower-its-own-table-as-promised) |

## What this note decides

Rows 1–12 and 17–20 of the table: rationals land, those behaviours change
deliberately, and the KEEP rows stay. Phase C is deliberately *not* decided
here beyond its ordering — it gets its own table when R is settled, per the
ledger's gate.

## Phase C — the complex tower (its own table, as promised)

R has settled: every CHANGE row is live, the suite is green, and the ledger
records it. This is the table the gate asked for. It is a **plan** — nothing
below is implemented yet, and the tests it cites do not exist until C lands.

**The one structural decision:** R7RS requires an exact complex number to be
exact when both of its parts are exact (`6.2.2`), so the tower gains an exact
complex pair — two exact components, normalized like a `Fraction` — while
Python's `complex` continues to serve as the inexact half. Without the exact
pair, `(make-rectangular 1 2)` would have to lie about exactness, and lying
is the one thing this tower does not do.

| # | Expression | Today | Proposed | Verdict |
| --- | --- | --- | --- | --- |
| 1 | `(make-rectangular 1 2)` | error — `KNOWN_MISSING` | the exact complex `1+2i` | **CHANGE** |
| 2 | `(make-rectangular 1 0)` | error | `1` — an exact complex with zero imaginary part *is* its real part | **CHANGE** |
| 3 | `(make-rectangular 1.0 0.0)` | error | `1.0+0.0i` — an inexact zero imaginary part stays visible (signed zero is honest) | **CHANGE** |
| 4 | `(make-polar 2 0)` / `(make-polar 2 1/2)` | error | `2` / inexact — a nonzero exact angle has no exact cosine, so the answer is honestly inexact | **CHANGE** |
| 5 | `(real-part 1+2i)` / `(imag-part 1+2i)` | error | `1` / `2`, each with its own exactness | **CHANGE** |
| 6 | `(magnitude 3+4i)` | error | `5` — exact, via the R4 perfect-square `sqrt` on `9+16`; `(magnitude 1+1i)` is inexact | **CHANGE** |
| 7 | `(angle 1)` / `(angle -1)` | error | `0` / `+3.14159…` (inexact — π is not rational); `angle` honours signed zero like IEEE `atan2` | **CHANGE** |
| 8 | `(sqrt -1)` / `(sqrt -4)` | error | the exact imaginary unit / exact `2i`; `(sqrt -2)` is inexact | **CHANGE** |
| 9 | `(+ 1+2i 3+4i)` and friends | error | schoolbook exact complex arithmetic; any inexact part contaminates the whole, as everywhere else in the tower | **CHANGE** |
| 10 | `(floor 1+2i)`, `(quotient 1+2i 2)` | error | still an error — the real-only family refuses non-reals, loudly, with a Lisp error | **KEEP** (the error stays, the reason changes) |
| 11 | `(eqv? 1+2i 1.0+2.0i)` | error | `#f` — exactness distinguishes, the same rule that separates `1` from `1.0` | **CHANGE** |
| 12 | `(real? 1+2i)` / `(real? 1.0+0.0i)` | error | `#f` / `#t` — the mathematical property, row 12's spirit | **CHANGE** |
| 13 | `1+2i` in the reader; `(number->string 1+2i)` | reads as a symbol; error | R7RS lexical `p+qi` with `#e`/`#i` prefixes; printer round-trip pinned like R2 | **CHANGE** |
| 14 | `(string->number "1+2i")` | `#f` | `1+2i`; garbage stays `#f` | **CHANGE** |

**The corners the table pins deliberately:** `(make-rectangular +inf.0 0)`
is the complex with an infinite real part and answers `magnitude` `+inf.0`;
a NaN in either part makes every arithmetic answer `+nan.0+nan.0i`-shaped
garbage honestly rather than hiding it; `(exact 1.0+0.0i)` is the exact
complex `1+0i` — which collapses to `1` by row 2.

**Matrix impact:** the six `KNOWN_MISSING` names leave
(`magnitude`, `angle`, `real-part`, `imag-part`, `make-rectangular`,
`make-polar`); `(scheme complex)` moves 0/6 → 6/6; `(scheme r5rs)` moves
190/198 → 196/198, leaving only `transcript-on`/`transcript-off`, which R7RS
itself excludes. The base-library `sqrt`/`log` verdict changes (row 8) —
their tests flip in the same change, R1-style.

**Rollout:** C1 — the exact complex pair, normalization, predicates,
arithmetic, `eqv?`/`equal?`; C2 — the six procedures, `sqrt`/`log` of
negatives, the real-only family's guard; C3 — reader/printer round-trip and
`string->number`/`number->string`; C4 — the doc sweep
([`r7rs.md`](r7rs.md), [`language.md`](language.md), [`lisp-dsl.md`](lisp-dsl.md))
and the matrix counts. Each stage lands with its tests and its doc pins, as
R did. The tests live in `tests/test_r7rs.py` beside the numeric-tower
blocks, with reader cases in `tests/test_reader.py`.
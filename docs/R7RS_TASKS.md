# R7RS tasks: the ledger

> **The claim, in one paragraph.** The base language grows the same way the
> SRFI layer does: a task lands a name that behaves the way the corrected
> R7RS-small report specifies, or the name stays honestly absent in
> `KNOWN_MISSING`. The checkable truth is the matrix in [`r7rs.md`](r7rs.md),
> the manifest in [`tests/r7rs_manifest.py`](../tests/r7rs_manifest.py), and
> the behavioural tests in [`tests/test_r7rs.py`](../tests/test_r7rs.py); this
> page is the plan, and where a plan and a test disagree, the test wins.

> **Honesty note.** This file was cited by [`r7rs.md`](r7rs.md) and
> [`lisp-dsl.md`](lisp-dsl.md) before it was committed — the drift
> [`tests/test_docs.py`](../tests/test_docs.py) now prevents. The A0–A15
> per-task notes were therefore never preserved in version control; the landed
> range is recorded as a range, from the evidence the repository does keep,
> and claims exactly that and no more.

## Landed

- **A0–A15** — the R7RS-small subset itself: every library the
  [`r7rs.md`](r7rs.md) matrix marks *supported* (`(scheme base)` at 200/200
  procedures and 32/32 syntax, plus `char`, `cxr`, `eval`, `file`, `inexact`,
  `lazy`, `load`, `process-context`, `read`, `repl`, `time`, `write`,
  `case-lambda`), the A0 manifest that machine-checks it, and the library
  system (A13) the SRFI layer is hosted on. The per-task notes are gone; the
  matrix and `KNOWN_MISSING` in [`lisp/manifest.py`](../lisp/manifest.py) are
  the truth.
- **A6/A7** — the `(scheme r5rs)` library imports whole. What it took, and
  why it was more than the two aliases the plan named:
  - `exact->inexact` / `inexact->exact` — aliases of `exact`/`inexact` in the
    core (one semantics, two names);
  - `null-environment` / `scheme-report-environment` — the report's two
    environment procedures, which the import could not resolve without
    (`null-environment` is a binding-free root scope; the report environment
    is the `(scheme r5rs)` exports in one, via `environment_from_specs`);
  - the manifest's r5rs `syntax` list carried `else`/`unquote`/
    `unquote-splicing` as if they were bindings — they are auxiliary syntax,
    and now sit in the `auxiliary` field exactly as `(scheme base)`'s do.
  The matrix is 190/198 procedures ([`r7rs.md`](r7rs.md)); the eight absent
  are the six complex numbers below plus `transcript-on`/`transcript-off`,
  which R7RS itself excludes.

## Open

### The numeric tower, phase R — exact rationals

**The gate's step 1 is done**: the design note is written —
[`numeric-tower.md`](numeric-tower.md), with a compatibility table covering
every pinned deviation, probed against the interpreter as it stands, and a
verdict (CHANGE/KEEP) for each. The decisions were accepted, and the R-phase
is underway:

1. ~~Write the exactness semantics down first~~ — done: the note decides rows
   1–12 and 17–20 (headline: `(/ 3 4)` becomes `3/4`; `1/3` reads as a
   rational; `#e1.5` becomes `3/2`; the KEEP rows — IEEE doubles, inexact
   `numerator`/`denominator`, exact zero division as an error — stay).
2. **R1 — landed.** The tower holds `fractions.Fraction` (always reduced,
   whole values normalized to `int`); `+ - * /` and `abs`/`expt`/`square`
   preserve exactness; `(/ 1 0.0)` answers IEEE (`+inf.0`/`-inf.0`/`+nan.0`)
   while an exact zero divisor stays an error; `exact?`/`rational?`/`real?`/
   `complex?`/`number?` admit rationals; `eqv?` distinguishes exactness by
   type; the printer writes `p/q`. The pinned division test flipped name and
   verdict, as the note promised.
3. **R2 — landed.** The reader accepts rational literals (`1/3` reduced,
   `2/2` an integer, `1/0` a *read error*, `1/x` still a symbol), `#e`
   denotes the exact rational the decimal spells (`#e1.5` → `3/2`, `#e0.1` →
   `1/10`), `#i` forces inexact, literals are decimal-only (`#x1/3`
   refused), and `string->number` parses what the reader reads (`"1/0"` →
   `#f`). The printer round-trip is pinned in `tests/test_reader.py`.
4. **R3 — landed.** `exact` converts any inexact value to the exact rational
   numerically equal to it (`(exact 3.5)` is `7/2`; `(exact 0.1)` is the
   honest binary value — write `#e0.1` for `1/10`; an infinity or NaN
   raises), and `rationalize` is the R7RS simplest-rational algorithm
   (`(rationalize 7/2 1/5)` is `7/2`; inexact operands give an inexact
   result). The two implementation-restriction errors are gone.
5. **R4 — landed.** `expt` with a negative exact exponent answers a rational
   (`(expt 2 -1)` is `1/2`; a non-integral exact exponent is honestly
   inexact); `sqrt` of a rational stays exact when numerator and denominator
   are both perfect squares (`(sqrt 1/4)` is `1/2`); the division family
   (`quotient`, `remainder`, `modulo`, `floor-`/`truncate-` variants) takes
   rationals and preserves inexactness (`(quotient 7.0 2)` is `3.0`), and a
   zero divisor is a Lisp error in every member (the family used to leak a
   raw `ZeroDivisionError`); `gcd`/`lcm` take rationals and integral inexact
   integers (`(gcd 1/2 1/3)` is `1/6`); `min`/`max` contaminate; `integer?`
   is the mathematical property (`(integer? 3.0)` is `#t`).
6. **R5 — landed.** The doc sweep happened incrementally — each of R1–R4
   updated its own pins in the same change (`r7rs.md`'s reader bullet and
   Numbers matrix row, [`language.md`](language.md)'s syntax sheet and
   deviations table, [`lisp-dsl.md`](lisp-dsl.md), [`capabilities.md`](capabilities.md))
   — and a final grep for the old claims (`0.75`, "reads as a symbol", "no
   exact rationals") finds them only in the design note's clearly-labeled
   historical column. The matrix's *name* counts do not move: R changed
   behaviours, not the bound-name set.
7. **Phase C — table drafted, implementation next.** The compatibility table
   the gate required is in [`numeric-tower.md`](numeric-tower.md)'s phase C
   section: an exact complex pair (R7RS 6.2.2's exactness rule), the six
   `KNOWN_MISSING` procedures, `sqrt`/`log` of negatives, reader/printer
   literals, and the NaN/inf corners — staged C1–C4 like R was. Nothing is
   implemented yet; the table is the contract the implementation will be
   held to.

Do not start phase C before R settles. [`capabilities.md`](capabilities.md)
records the gap as Tier 2; nothing else in either ledger outranks it.

## How to verify

```bash
python -m pytest tests/test_r7rs.py -q
```

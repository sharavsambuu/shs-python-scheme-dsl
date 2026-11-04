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

`(srfi 204)` is recorded in the matrix as *withdrawn*: it is never
implemented, and importing it fails, naming `(srfi 241)`.

## Open

*(Nothing. The next candidates — the numeric-tower design note and source
locations — live in [`R7RS_TASKS.md`](R7RS_TASKS.md); a new S-task enters
here only after it states its user value and passes the "meets its semantics
or fails loudly" gate.)*

### ~~S9 — generators / lazy sequences~~ — landed

~~The one scheduled feature~~ Landed as `shslisp/generators.scm`: lazy sequences
as ordinary closures — a generator is a 0-argument procedure answering the
next value or the unique `generator-end` object — with `gmap`/`gfilter`/
`gtake`/`gdrop` and the drains. No evaluator change, no re-entrant
continuations. See the landed table above.

## Deliberately not scheduled

Everything else — 19, 64, 125, 128, 132, 133, 146, 151, 152, 170, 173, 180,
189, 193, and the rest of the catalog — has no open task. Breadth is not the
goal. A candidate must state its user value, pass the "meets its semantics or
fails loudly" gate, and enter this ledger as a task before any code. Deferring
is the default, and the numeric-tower decision in
[`R7RS_TASKS.md`](R7RS_TASKS.md) outranks all of them.

## How to verify

```bash
python -m pytest tests/test_srfi.py -q
```

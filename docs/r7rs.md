# R7RS-small: the supported subset

> **The claim, in one paragraph.** This project is an **R7RS-small subset**, not
> a conforming implementation. Every name marked *supported* below behaves the
> way the corrected R7RS report specifies; every name marked *missing* fails
> loudly rather than doing something else; every deviation is written down with
> its consequence. The measurement is
> [`tests/test_r7rs.py`](../tests/test_r7rs.py) and the manifest it reads is
> [`tests/r7rs_manifest.py`](../tests/r7rs_manifest.py). The umbrella language
> contract — including the SRFI layer and the default profile — is
> [`lisp-dsl.md`](lisp-dsl.md).

The matrix is deliberately about the *base language*, before the DSL profile
adds `(srfi 1)`, `(srfi 26)`, `(srfi 88)`, `(srfi 89)`, `(srfi 197)`, and
`(srfi 241)`. A name can be missing here and still be available in the default
DSL through an SRFI; the SRFI matrices live in `srfi.md` (S7).

## How to read the matrix

- **procedure** names must evaluate to a procedure in
  `make_env(profile="r7rs")`.
- **syntax** names must be a special form, a macro binding, or documented
  auxiliary syntax (`else`, `=>`, `_`, `...`, `unquote`, `unquote-splicing`, and
  `syntax-rules`, which `define-syntax` parses structurally).
- `supported` means every export in that namespace is present. `partial` means
  some are. `missing` means none are. `optional` means the library is measured
  but does not gate the subset claim.

Presence is not semantics. The behavioural table in `tests/test_r7rs.py` pins a
representative slice (equivalence, pairs, numbers, chars, strings, vectors,
continuations, `dynamic-wind`, `guard`, `values`, ports); a name that is bound
but behaves differently is a **deviation**, listed below, not a pass.

## Library matrix

| Library | Procedures | Syntax | Status |
| --- | --- | --- | --- |
| `(scheme base)` | 200/200 | 32/32 | supported |
| `(scheme case-lambda)` | 0/0 | 1/1 | supported |
| `(scheme char)` | 22/22 | 0/0 | supported |
| `(scheme complex)` | 0/6 | 0/0 | missing |
| `(scheme cxr)` | 24/24 | 0/0 | supported |
| `(scheme eval)` | 2/2 | 0/0 | supported |
| `(scheme file)` | 10/10 | 0/0 | supported |
| `(scheme inexact)` | 12/12 | 0/0 | supported |
| `(scheme lazy)` | 3/3 | 2/2 | supported |
| `(scheme load)` | 1/1 | 0/0 | supported |
| `(scheme process-context)` | 5/5 | 0/0 | supported |
| `(scheme read)` | 1/1 | 0/0 | supported |
| `(scheme repl)` | 1/1 | 0/0 | supported |
| `(scheme time)` | 3/3 | 0/0 | supported |
| `(scheme write)` | 4/4 | 0/0 | supported |
| `(scheme r5rs)` | 186/198 | 23/23 | optional |

The `(scheme r5rs)` library is optional in the report itself. It is measured
for completeness and does not gate the subset claim; its `exact->inexact` and
`inexact->exact` aliases are absent until A6/A7.

## The missing names

The list below is machine-checked against `KNOWN_MISSING` in
`tests/r7rs_manifest.py`. When a task implements a name it must remove it from
both places in the same change; the test fails in either direction, so the page
cannot rot.

<!-- r7rs-missing:start -->
angle imag-part magnitude make-polar make-rectangular real-part
<!-- r7rs-missing:end -->

## External representations

The reader and printer are a matched pair: `write` emits text that `read`
accepts, and re-writing the result is stable. `tests/test_r7rs.py` pins a
round-trip corpus covering every form below.

- **Numbers.** Radix prefixes `#b`, `#o`, `#d`, `#x`; exactness prefixes `#e`,
  `#i`; the prefixes may appear in either order (`#e#x10`, `#x#e10`); the
  written inexact specials `+inf.0`, `-inf.0`, `+nan.0`, `-nan.0` read and
  print. `#e` on a non-integral value returns the inexact value (there are no
  exact rationals); `1/3` reads as a *symbol*, not a number.
- **Symbols.** `|...|` preserves case and spaces. The printer wraps any symbol
  that is not a plain R7RS identifier in bars and escapes `\|` and `\\`;
  `\xHH;` is accepted inside the bars. A symbol such as `1+` therefore reads
  and writes as `|1+|`.
- **Strings.** `\"`, `\\`, `\a`, `\b`, `\t`, `\n`, `\r`, `\|`, `\xHH;`, and
  the line continuation (`\` followed by a newline and indentation). The
  printer escapes `"`, `\`, newline, tab, and carriage return.
- **Characters.** The R7RS names (`space`, `newline`, `tab`, `return`, `alarm`,
  `backspace`, `delete`, `escape`, `nul`/`null`) and `#\xHH`. Any other
  multi-character name is an error rather than a silent first letter.
- **Compound data.** Lists, dotted pairs, vectors `#(...)`, bytevectors
  `#u8(...)`, and the quote/quasiquote sugar.
- **Directives.** `#!fold-case` and `#!no-fold-case` change identifier folding
  for the rest of the input; folding is **off** by default, and strings,
  characters, and `|quoted symbols|` are never folded.

Still missing: datum labels (`#1=`, `#1#`) and cyclic structure (A14), and
complex literals (A7).

## Deviations

These are the differences that matter to a user. Each one says what happens
instead.

| Area | Deviation | Consequence |
| --- | --- | --- |
| Continuations | `call/cc` is escape-only; a continuation cannot be re-entered after its `dynamic-wind` extent ends. | Generators and coroutines built on re-entry do not work. `guard`, `dynamic-wind`, and escape continuations do. |
| Libraries | `define-library`/`import`/`export` are supported (A13), with import sets `only`/`except`/`prefix`/`rename`. A `define-library` library's exports are validated at import time. | `(load ...)` remains the loader's own mechanism; `(environment ...)` returns a *restricted* import. |
| Numbers | Exact integers and inexact reals only; no exact rationals, no complex tower. `(/ 3 4)` is `0.75` (never `0`), and `/` keeps an exact integer result when the division is even. `exact` of a non-integral float raises an implementation-restriction error, and `rationalize` accepts only exact integers. `floor`, `ceiling`, `truncate`, and `round` preserve inexactness (ties-to-even). | `1/3` is not an exact rational; complex procedures are missing (A7). |
| Strings | Literals are immutable Python `str`; `make-string` and `string-copy` return a mutable wrapper. | `string-set!` on a literal raises a clear "immutable" error; mutate a `make-string`/`string-copy` result instead. |
| Cycles | No datum labels (`#1=`, `#1#`); `write` does not detect shared structure. | Cyclic data cannot be read or printed; `equal?` can recurse forever on a cycle. |
| Complex | `(scheme complex)` is not implemented; the numeric tower is real only. | `make-rectangular`, `real-part`, and complex literals are absent; `sqrt` of a negative number is an error, not a complex value. |
| Ports | Text and binary ports, `read`, bytevector I/O, and file predicates are supported. `write-shared`/`write-simple` share `write` and do not detect sharing (A14). | A program can read one datum at a time; cyclic data still cannot be printed. |

### Non-standard extensions

These are **not** R7RS and are not claimed as such:

- `defmacro` (unhygienic, in addition to hygienic `define-syntax`);
- `define-variant` and the project matcher (renamed `variant-match` in the
  target DSL; SRFI 241 `match` is separate);
- hash tables (`make-hash-table`, `hash-table-*`);
- the `Result` type and ROP vocabulary (`result-*`, `>=>`, `pipe-results`,
  `result-do`, `attempt`);
- tagged values and host vocabulary;
- `->`/`->>`, `partial`/`curry`, `range`, `sort`, and the rest of the prelude.

They are documented in [Appendix A](lisp_tutorial/appendix-a-reference.md) and
in the [DSL specification](lisp-dsl.md), not in this page's R7RS matrix.

## How to verify

From a checkout of this project:

```bash
# the conformance harness (this page's matrix) — it runs the strict profile
python -m pytest tests/test_r7rs.py -q

# the rest of the language suite
python -m pytest -q
```

`tests/test_r7rs.py` fails with a sorted, library-by-library list when the
environment and the manifest disagree, so the fix is mechanical: implement the
name or move it between `KNOWN_MISSING` and the matrix.

## Related

- [`lisp-dsl.md`](lisp-dsl.md) — the umbrella contract: R7RS subset + SRFIs +
  default profile + Python seam.
- [`docs/R7RS_TASKS.md`](../../docs/R7RS_TASKS.md) — A0–A15, including A13.
- [`docs/SRFI_TASKS.md`](../../docs/SRFI_TASKS.md) — S0–S8.
- [`lisp_tutorial/appendix-a-reference.md`](lisp_tutorial/appendix-a-reference.md)
  — the user-facing lookup sheet.

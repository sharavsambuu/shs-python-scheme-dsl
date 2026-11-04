# Capability assessment: the DSL against the modern-language checklist

> **What this page is.** An honest answer to the question "does this DSL have
> ~90% of modern language features?" — kept as a document so the answer does
> not rot into folklore. It is an *assessment*, not a specification: the
> checkable truth remains the matrices in [`r7rs.md`](r7rs.md) and
> [`srfi.md`](srfi.md), the contract in [`lisp-dsl.md`](lisp-dsl.md), and the
> tests. Where a claim here and a test disagree, the test wins.
>
> **Status.** First assessed 2026-10-31, after S8 (the profiles) and the
> `.scm` rename. Re-assessed 2026-11-03 after phase C of the numeric tower
> (C1–C4: exact complex pairs, the polar half, complex literals) — the full
> suite is 872 passing tests, `(scheme complex)` is 6/6, and `KNOWN_MISSING`
> is empty. The [fitness-for-use section](#fitness-for-use-what-to-build-with-it)
> below answers the follow-up this re-assessment was asked for: *what is it
> good enough to build?*

## The verdict, in one paragraph

For the **"modern scripting language" checklist** — the features a working
programmer touches daily in Python, JavaScript, or Ruby — the DSL is at
roughly **85–90%**, and ahead of those languages on metaprogramming and error
handling. For **"modern language design" as a whole** — concurrency, object
orientation, static analysis — it is closer to **65–70%**, and the difference
is mostly *deliberate*: nearly every structural gap is written down as a
documented non-goal rather than an accident. For the domain the language
targets — pure domain rules, pipelines, typed control flow, embedded
scripting — the coverage is effectively complete. The numeric/stdlib edge
that the first assessment logged as Tier 2 has since closed: the complex
tower landed whole (phase C, C1–C4), so the tower is now exact integers,
exact rationals, exact complex pairs, and inexact reals, with literals that
round-trip.

## Where the DSL is at parity (or ahead)

| Axis | What the DSL has | Where it is pinned |
| --- | --- | --- |
| Functional core | first-class functions, closures, lexical scope, HOFs, tail calls (trampoline + deep-stack runner), recursion budgets | `tests/test_r7rs.py`, `lisp/stack.py` |
| Metaprogramming | hygienic `syntax-rules` *and* classic `defmacro`, `macroexpand` — most mainstream languages have nothing here | `tests/test_r7rs.py`, ch. [06](lisp_tutorial/06-macros.md) |
| Data modeling | `define-variant` (closed ADTs), records, pattern matching twice over (SRFI 241 + `variant-match`), alists, hash tables, vectors, bytevectors | `tests/test_rop.py`, ch. [09](lisp_tutorial/20-typed-control-flow.md) |
| Error handling | conditions (`guard`/`raise`/error objects) plus ROP as a library — better than plain exceptions | `tests/test_rop.py`, ch. [10](lisp_tutorial/21-railway-oriented.md) |
| Control flow | multiple values, `dynamic-wind`, parameters (dynamic scope), promises, escape continuations, `case-lambda` | `tests/test_r7rs.py` |
| Argument passing | optional, named (keywords), defaults, rest — the full SRFI 89 surface | `tests/test_srfi.py`, ch. [25](lisp_tutorial/17-srfi-89-optional-and-named-parameters.md) |
| Modularity | `define-library`/`import` with `only`/`except`/`prefix`/`rename`, load-once file modules, profiles + `cond-expand` | `tests/test_library.py`, `tests/test_profile.py` |
| Interop & tooling | declared Python seam, string ports, file I/O, `process-context`, REPL, feature detection | `tests/test_embed.py`, `tests/test_ports.py`, `tests/test_profile.py`, ch. [21](lisp_tutorial/27-embedding-in-python.md) |

The point of the table: the missing percentages do not live here. A reader
coming from Python finds every daily-driver feature present, and finds two
things Python does not have (hygienic macros, a condition system) already
load-bearing in the shipped code.

## The gaps, in three tiers

### Tier 1 — structural, deliberate, documented

- **No re-entrant `call/cc`.** Continuations are escape-only: the one-shot
  exit shape works, re-entry after the `dynamic-wind` extent ends does not.
  Consequence: no generators, coroutines, or green threads *built on
  continuations*. Documented in `r7rs.md`.
- **No concurrency or async.** The host could expose threads through the
  seam, but the language itself has no story. Not begun.
- **No object orientation.** No classes, inheritance, or generic dispatch.
  Records + variants + closures are the intended substitute; they hold up
  for DDD-style domain code, but there is no late-binding story.
- **No static typing or contracts.** Variants give closed sets and loud
  refusals at run time; nothing checks a program before it runs.

### Tier 2 — the numeric/stdlib edge, small and documented

- Numeric tower: exact integers, exact rationals (R1), exact complex pairs
  (C1–C4: the rectangular and polar halves, complex literals with `#e`/`#i`,
  the complex transcendentals — `r7rs.md`, `numeric-tower.md`), and inexact
  reals. The "no complex numbers" gap this tier used to list is closed.
- Immutable string literals; no datum labels, so cyclic data cannot be read
  or printed.
- No regexps, no date-time library (SRFI 19 is not ingested), no JSON or
  networking in the core.

### Tier 3 — cheap to close at the library level

This tier is where the "90%" claim earns itself, because the language's own
extension mechanisms (macros, the prelude, the Python seam) are exactly the
tools for closing it:

- **Generators / lazy sequences** — **landed as S9** (`lisp/generators.scm`,
  chapter [28](lisp_tutorial/18-generators.md)): closures and `set!`, no
  continuation re-entry, shipped in both profiles. The sketch below was the
  pre-S9 shape, kept for the record:

  ```lisp
  (define (make-generator lst)
    (let ((rest lst) (done #f))
      (lambda ()
        (if done
            (eof-object)
            (let ((v (car rest)))
              (set! rest (cdr rest))
              (if (null? rest) (set! done #t))
              v)))))

  (define g (make-generator (list 10 20 30)))
  (list (g) (g) (g) (g))       ;=> (10 20 30 #<eof>)
  ```

- **String interpolation** — a small `syntax-rules` macro over
  `string-append`.
- **SRFI 19 date-time, JSON, regexp** — thin Python-seam libraries, exactly
  the `install_primitives` path chapter
  [21](lisp_tutorial/27-embedding-in-python.md) teaches.

## Hardening findings (2026-10-31 probe)

An adversarial probe of ~60 corner cases surfaced four findings, all now
fixed or pinned by `tests/test_hardening.py`:

1. **Booleans passed as numbers.** Python's `bool` subclasses `int`, so
   `(+ #t 1)` answered `2` while `number?` said `#f`. Every arithmetic and
   comparison primitive now gates through `_expect_number`, which rejects
   booleans.
2. **A rename could silently replace a core primitive.**
   `(import (rename (srfi 1) (fold car)))` put `fold` where `car` was. The
   library system now refuses a rename onto a name the core floor defined
   (`env.core_names`); plain library imports keep R7RS shadowing semantics,
   and the profile's prelude→SRFI replacements are unchanged.
3. **Truthiness prose vs. the interpreter.** The tutorial claimed `'()` is
   false; the interpreter (R7RS-correctly) treats only `#f` as false. The
   prose is fixed — and the discipline it now teaches ("a missing answer is
   `#f`, never `'()`") is load-bearing.
4. **A latent host bug the old behaviour masked.** An adapter returning `()`
   for "missing" — in the game edition, `piece_record(None)` did exactly that —
   returns a *truthy* value, so a guard written as `(if (piece-record ...) …)`
   passed on "no piece", and the bool-as-int accident turned the bogus
   comparisons into a silently wrong action. The adapter now returns `#f`, and
   the guard works.

**Still open (the systemic audit):** other adapter seams in a host edition can
have the same flaw — returning `NIL` for "missing" (`result-tx`,
`result-error`, `event-field` in the game edition). Under R7RS truthiness
those values are *truthy*, so any script that guards on them with `if`/`when`
rather than `null?` is a latent bug of the same shape. The convention to adopt
in your own host: **`#f` for missing, `NIL` only where a list is expected** —
and audit the seam seam by seam.

## How to read the two numbers

The percentages are a judgement about *feature surface*, not a measurement.
The defensible statements are the specific ones: every name in the parity
table is pinned by a test; every gap in Tiers 1–2 is listed in a matrix that
a test keeps honest (`KNOWN_MISSING` in `tests/r7rs_manifest.py`, the
withdrawn `(srfi 204)` handler in `lisp/library.py`). The tier-3 items are
neither claimed nor tested — they are the roadmap.

## Fitness for use: what to build with it

Asked and answered 2026-11-03: *is this good enough to use for various
ideas, with the impossible parts implemented through Python?* Yes — with a
clear-eyed view of what it is good for and where the walls are. The escape
hatch the question assumes is not a workaround; it is the design.

### Use it confidently for

- **Embedded scripting and rules/policy layers** in a Python application —
  the sweet spot. The profiles decide how much power to hand over
  (`make_env(profile="r7rs")` vs the default with the SRFI layer), the step
  budget makes runaway scripts impossible, and the game edition is a working
  proof of the pattern at 60 FPS.
- **Teaching and tutorials** — the docs are written and machine-checked, and
  the exact tower means `(+ 1/3 1/6)` is `1/2`, not `0.5`.
- **Prototyping algorithms where exactness matters** — rationals, bignums,
  and exact complex arithmetic (`(sqrt -4)` is `2i`, `(log -1)` is `+iπ`)
  are genuinely useful for math-heavy sketches.
- **Building your own DSL** — `syntax-rules`, `define-variant`,
  `variant-match`, hash tables, and `define-library` are the material.

### The walls (so they are not surprises)

1. **Performance.** A tree-walking interpreter on CPython: expect 10–100×
   slower than native Schemes for hot loops. The honest pattern is
   *Scheme orchestrates, Python computes* — push the compute into a
   primitive.
2. **No threads.** Concurrency is generators-and-coroutines-shaped, not
   parallel; an embedding must not share an env across OS threads.
3. **The FFI is manual and loud.** Every Python capability is an explicit
   `install_primitives` registration (chapter
   [21](lisp_tutorial/27-embedding-in-python.md)) — a feature for safety,
   but work per capability.
4. **Tooling depth.** The error messages are honest and the REPL exists, but
   there is no debugger or profiler; source locations are the known next
   step (the recommendation below).
5. **An ecosystem of one.** The SRFI layer covers the useful core; you will
   be writing libraries, not downloading them.

### The escape hatch, precisely

Three layers, all already in the repo. **Primitives** — `install_primitives`
or `Primitive(...)` in `make_env` — expose a Python capability as a
first-class Scheme procedure. **The prelude** (`lisp/prelude.scm`) is
library code written *in Scheme* over those primitives — 86 defines, the
pattern every host edition follows. **Embedding** — `make_env` →
`run`/`evaluate`, output redirection, host exceptions surfacing as catchable
Lisp errors. Anything a Python process can do, a Scheme program in this
tower can call; the only design question is which side of the seam a given
idea belongs on.

## Memory management: outsourced, by design

The interpreter has **no memory manager of its own**. Every Lisp value *is*
a Python object — proper lists are host `list`s, pairs are a `Pair` class,
strings are `str`, closures and environments are Python objects. Garbage
collection is therefore exactly CPython's: reference counting for the common
case, plus the cyclic collector for the cases reference counting cannot see
(closures capturing each other, `set-cdr!` building a cycle in `Pair` cells,
a `memoize` cache holding its own closure).

The practical consequences, stated plainly:

- **No GC to write, tune, or debug.** This is one reason `lisp/` is small
  enough to hold in your head, and why the prelude never mentions memory.
- **Cycles are reclaimed when the cyclic collector runs**, not
  deterministically — the same contract Python gives. Fine for scripts,
  policy layers, and IDE-driven evaluation; not a real-time allocator.
- **Values are heavier than in a native Scheme** (a cons is a refcounted
  Python object). The Tetris edition runs its full game logic through this at
  60 FPS, so the envelope is proven — but this is not a high-throughput
  compute engine.
- **The budgets bound compute, not memory.** `DEPTH_LIMIT` and
  `STEPS_BUDGET` catch runaway evaluation; a runaway allocation is caught by
  the OS, like any Python process.

## Fit assessment: an ontology-driven cybernetics LISP IDE

Asked and answered 2026-10-31: *does this Scheme+Python stack fit an
ontology-driven cybernetics LISP IDE?* The fit is concentrated in the
**runtime layer**; the **IDE tooling layer** is where a project like that
would build new machinery rather than fight the interpreter.

**Where the three parts map well:**

- **Ontology-driven → homoiconicity.** Ontology entries and program logic
  share one representation: a category can be a `define-variant` case
  (closed, tagged, exhaustively matched), a relation an alist record, a rule
  a lambda stored in a hash table, and metadata-about-definitions is
  an established pattern (a host can publish its own, the way `design-meta`
  does in the game edition). `define-library` gives ontologies
  module boundaries; `variant-tags` is runtime reflection over declared
  categories.
- **Cybernetics → the architecture is already a control loop.** The
  host-edition pattern is a working example: a pure domain step with a fact
  journal is the regulated plant; the host's hooks are the
  observers/controllers; the rules-may-not-load-adapters fence is
  plant/actuator separation; the budgets are homeostatic guardrails; ROP
  makes every regulation path a railway with explicit refusals.
- **The IDE host → the seam was built for embedding.** The REPL accepts
  injectable `out`/`env`/`in_stream` and exposes `eval_source`
  (`lisp/repl.py`); `make_env(out=...)` redirects all output;
  `install_primitives` is declared and loud; host exceptions surface as
  catchable Lisp errors. `eval`, `interaction-environment`,
  `macroexpand`/`macroexpand-1`, the `write`/`read` round-trip,
  `procedure-arity`, `loaded-modules`, and `features` are the IDE-relevant
  primitives already present.

**What such a project would have to build** (all additive from Python, none
requiring a fork of the evaluator):

1. **Source locations.** The reader attaches no line/column spans
   (verified: no position tracking in `lisp/reader.py`), and errors carry no
   coordinates. Squiggles, go-to-definition, and precise error markers need
   this; it is a contained but real change to reader, printer, and error
   paths.
2. **A symbol-table / completion API.** `Environment.find`/`lookup`/
   `is_bound` are public, so the data is reachable — but there is no
   enumerate-bindings API, no scope-aware completions, no cross-reference
   index. A Python-side analysis module is the natural home.
3. **Debugger instrumentation.** No breakpoints or stepping; the trampoline
   is a good interception point for a step hook (which would also give
   coverage), but the hook does not exist yet.
4. **Background analysis threading.** The interpreter has no concurrency
   story; an IDE indexer should run in a separate process or a throwaway
   `make_env(profile=None)`, never share an env across threads.
5. **Ontology reflection as a layer.** `variant-tags` and alists are atoms;
   a query/traversal layer over nodes, edges, and types is a pure-Lisp
   library — application work, not interpreter work.

**The named risks:** `define-variant` is a *closed* set — right for
exhaustive dispatch, wrong for open-world ontologies that grow at runtime;
model the ontology as *data* (records, hash tables, tagged values) and keep
variants for the fixed machinery. And the interpreter's speed is fine for
interactive evaluation and logic, not for bulk in-process analysis — index
Python-side.

**Verdict:** for ontology-driven cybernetics specifically, the stack is
close to purpose-built — homoiconic Scheme for the ontology/program
unification, a proven feedback-loop architecture to copy, and a declared
Python seam for the IDE itself. The recommended first step is a spike: embed
`Repl` in a minimal Python GUI, evaluate a scratch buffer against a live
`make_env()`, and feel the eval/inspect loop before committing to the
ontology layer.

## The recommendation

The S9 recommendation below has **landed**: generators are a prelude library
(`lisp/generators.scm`), with tests, a chapter ([28](lisp_tutorial/18-generators.md)),
and a matrix row in [`srfi.md`](srfi.md). The next Tier-3 item by the same
logic — user value, no interpreter change — is **source locations** for the
IDE, which is the first step of the numeric/IDE sequence in
[`SRFI_TASKS.md`](SRFI_TASKS.md) and [`R7RS_TASKS.md`](R7RS_TASKS.md).

> *(The original text, for the record: if exactly one Tier-3 item is taken
> next, take generators / lazy sequences as a prelude library — the
> most-asked-for "modern" feature, needing no interpreter change.)*

## See also

- [`lisp-dsl.md`](lisp-dsl.md) — the umbrella contract (R7RS subset + SRFIs +
  profiles + Python seam).
- [`r7rs.md`](r7rs.md) — the base-language matrix, including every deviation
  above.
- [`srfi.md`](srfi.md) — the SRFI matrix.
- [`language.md`](language.md) — the one-stop language guide.
- [`docs/SRFI_TASKS.md`](SRFI_TASKS.md) — the task ledger, where an
  S9 (generator library) would be entered.


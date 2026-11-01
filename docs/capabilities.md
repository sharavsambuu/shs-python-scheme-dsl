# Capability assessment: the DSL against the modern-language checklist

> **What this page is.** An honest answer to the question "does this DSL have
> ~90% of modern language features?" — kept as a document so the answer does
> not rot into folklore. It is an *assessment*, not a specification: the
> checkable truth remains the matrices in [`r7rs.md`](r7rs.md) and
> [`srfi.md`](srfi.md), the contract in [`lisp-dsl.md`](lisp-dsl.md), and the
> tests. Where a claim here and a test disagree, the test wins.
>
> **Status.** Assessed 2026-10-31, after S8 (the profiles) and the `.scm`
> rename, at 1095 passing tests.

## The verdict, in one paragraph

For the **"modern scripting language" checklist** — the features a working
programmer touches daily in Python, JavaScript, or Ruby — the DSL is at
roughly **85–90%**, and ahead of those languages on metaprogramming and error
handling. For **"modern language design" as a whole** — concurrency, object
orientation, static analysis — it is closer to **65–70%**, and the difference
is mostly *deliberate*: nearly every structural gap is written down as a
documented non-goal rather than an accident. For the domain the language
targets — pure domain rules, pipelines, typed control flow, embedded
scripting — the coverage is effectively complete.

## Where the DSL is at parity (or ahead)

| Axis | What the DSL has | Where it is pinned |
| --- | --- | --- |
| Functional core | first-class functions, closures, lexical scope, HOFs, tail calls (trampoline + deep-stack runner), recursion budgets | `tests/test_r7rs.py`, `lisp/stack.py` |
| Metaprogramming | hygienic `syntax-rules` *and* classic `defmacro`, `macroexpand` — most mainstream languages have nothing here | `tests/test_r7rs.py`, ch. [06](lisp_tutorial/06-macros.md) |
| Data modeling | `define-variant` (closed ADTs), records, pattern matching twice over (SRFI 241 + `variant-match`), alists, hash tables, vectors, bytevectors | `tests/test_rop.py`, ch. [09](lisp_tutorial/09-typed-control-flow.md) |
| Error handling | conditions (`guard`/`raise`/error objects) plus ROP as a library — better than plain exceptions | `tests/test_rop.py`, ch. [10](lisp_tutorial/10-railway-oriented.md) |
| Control flow | multiple values, `dynamic-wind`, parameters (dynamic scope), promises, escape continuations, `case-lambda` | `tests/test_r7rs.py` |
| Argument passing | optional, named (keywords), defaults, rest — the full SRFI 89 surface | `tests/test_srfi.py`, ch. [25](lisp_tutorial/25-srfi-89-optional-and-named-parameters.md) |
| Modularity | `define-library`/`import` with `only`/`except`/`prefix`/`rename`, load-once file modules, profiles + `cond-expand` | `tests/test_library.py`, `tests/test_profile.py` |
| Interop & tooling | declared Python seam, string ports, file I/O, `process-context`, REPL, feature detection | `tests/test_architecture.py`, ch. [21](lisp_tutorial/21-embedding-in-python.md) |

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

- Numeric tower stops at exact integers + inexact reals: no exact rationals,
  no complex numbers (`r7rs.md`).
- Immutable string literals; no datum labels, so cyclic data cannot be read
  or printed.
- No regexps, no date-time library (SRFI 19 is not ingested), no JSON or
  networking in the core.

### Tier 3 — cheap to close at the library level

This tier is where the "90%" claim earns itself, because the language's own
extension mechanisms (macros, the prelude, the Python seam) are exactly the
tools for closing it:

- **Generators / lazy sequences** — no continuation re-entry needed; a
  closure over the remaining list is enough, and it works today:

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
  [21](lisp_tutorial/21-embedding-in-python.md) teaches.

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
4. **A latent game bug the old behaviour masked.** `piece_record(None)`
   returned `()` — truthy — so the AI's steering guard passed on "no piece"
   and the bool-as-int accident turned the bogus comparisons into a silent
   refused slam. It now returns `#f`, and the guard works.

**Still open (the systemic audit):** other adapter seams
(`tetris/adapters.py`) also return `NIL` for "missing" — `result-tx`,
`result-error`, `event-field`. Under R7RS truthiness those values are
*truthy*, so any script that guards on them with `if`/`when` rather than
`null?` is a latent bug of the same shape. The shipped scripts happen to use
them as values, not guards, so nothing currently misbehaves — but the audit
(seam by seam: `#f` for missing, `NIL` only where a list is expected) is
real follow-up work and belongs in the task ledger.

## How to read the two numbers

The percentages are a judgement about *feature surface*, not a measurement.
The defensible statements are the specific ones: every name in the parity
table is pinned by a test; every gap in Tiers 1–2 is listed in a matrix that
a test keeps honest (`KNOWN_MISSING` in `tests/r7rs_manifest.py`, the
withdrawn `(srfi 204)` handler in `lisp/library.py`). The tier-3 items are
neither claimed nor tested — they are the roadmap.

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
  game logic, and IDE-driven evaluation; not a real-time allocator.
- **Values are heavier than in a native Scheme** (a cons is a refcounted
  Python object). The game runs its logic through this at 60 FPS and
  `play --validate` passes headlessly, so the envelope is proven — but this
  is not a high-throughput compute engine.
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
  a lambda stored in a hash table, and metadata-about-definitions is already
  an established pattern (`design-meta`). `define-library` gives ontologies
  module boundaries; `variant-tags` is runtime reflection over declared
  categories.
- **Cybernetics → the architecture is already a control loop.** The Tetris
  tree is a working example: pure domain (`Tx` step, fact journals) is the
  regulated plant; the hooks are the observers/controllers; the
  rules-may-not-load-adapters fence is plant/actuator separation enforced by
  `tests/test_architecture.py`; the budgets are homeostatic guardrails; ROP
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

If exactly one Tier-3 item is taken next, take **generators / lazy sequences
as a prelude library**: it is the most-asked-for "modern" feature, it needs
no interpreter change (the sketch above runs on today's core), and it would
make the iteration code read closer to Python for newcomers. It is a natural
S9-sized task: prelude additions, a test file, and a chapter alongside
[22–27](lisp_tutorial/22-srfi-1-the-list-library.md).

## See also

- [`lisp-dsl.md`](lisp-dsl.md) — the umbrella contract (R7RS subset + SRFIs +
  profiles + Python seam).
- [`r7rs.md`](r7rs.md) — the base-language matrix, including every deviation
  above.
- [`srfi.md`](srfi.md) — the SRFI matrix.
- [`language.md`](language.md) — the one-stop language guide.
- [`docs/SRFI_TASKS.md`](../../docs/SRFI_TASKS.md) — the task ledger, where an
  S9 (generator library) would be entered.


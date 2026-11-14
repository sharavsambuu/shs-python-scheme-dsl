# 29 — Sorting, JSON, formatting, and strings

> **What this chapter teaches.** The four standard-library SRFIs a host script
> reaches for between the interesting parts: `(srfi 132)` sorting, `(srfi 180)`
> JSON, `(srfi 28)` format strings, and `(srfi 152)` string utilities. Each is
> one `(import ...)` away, each is backed by the Python standard library rather
> than a Scheme loop, and each replaces a block of boilerplate you would
> otherwise write by hand.
>
> **Before this:** 13, 18. · **Time:** ~20 min.
> **After this you can:** sort a list or vector without writing a merge loop,
> round-trip a record through JSON, assemble one output line with `format`, and
> split/join/search/trim text with the standard names.

## The wave, in one table

Chapter [13](13-dictionaries-alists-and-hash-tables.md) met the first of this
wave, `(srfi 125)`. These four are the rest. None of them is pre-imported by
the default profile — the profile's identifier list is a pinned, published
surface — so a program opts in:

```scheme
(import (srfi 132) (srfi 180) (srfi 28) (srfi 152))
```

| Library | You get | Backed by |
| --- | --- | --- |
| `(srfi 132)` | `list-sort`, `list-stable-sort`, `vector-sort`, `vector-stable-sort`, and the two `sorted?` predicates | Python Timsort, called through your Scheme comparator |
| `(srfi 180)` | `json-read`, `json-write` | the stdlib `json` module |
| `(srfi 28)` | `format` with `~a`, `~s`, `~%`, `~~` | the language's own printer |
| `(srfi 152)` | `string-split`, `string-join`, `string-contains`, `string-trim`, `string-prefix?`, `string-suffix?` | Python `str` |

The claim is deliberately narrow in every case: a *subset* of each SRFI, named
in [`docs/SRFI_TASKS.md`](../SRFI_TASKS.md) and audited in
[`docs/srfi.md`](../srfi.md). Everything a page here shows is in the export
list; nothing is shimmed into pretending.

## Sorting: `(srfi 132)`

`list-sort` takes the comparator **first** — SRFI 132's argument order, the
opposite of the prelude's `(sort-by key less? xs)`:

```scheme
(import (srfi 132))

(list-sort < '(3 1 4 1 5 9 2))          ;=> (1 1 2 3 4 5 9)
(list-sorted? < '(1 2 3))               ;=> #t
(list-stable-sort < '(3 1 2))           ;=> (1 2 3)
```

Two things worth knowing:

- **It is Timsort under the hood.** Your comparator is still a Scheme
  procedure — it is called once per comparison — but the call loop, the merge
  and the run detection are Python's. A hand-written Scheme merge sort spends a
  trampoline step per comparison; this does not.
- **Both list sorts are stable here.** SRFI 132 only promises stability for
  `list-stable-sort`; this implementation is stable for both, which is a
  stronger guarantee, never a different answer. Sorting `(3 1 3)` keeps the two
  `3`s in their original order.

The vector half returns a **fresh vector** (the input is untouched) and takes
the optional half-open `[start end]` subrange:

```scheme
(vector-sort < #(3 1 2))                ;=> #(1 2 3)
(vector-sort < #(9 3 1 2) 1 3)          ;=> #(1 3)
(vector-sorted? < #(1 2 3))             ;=> #t
```

The mutation operators (`vector-sort!`, `list-sort!`) and the
merge/median/selection families are **not** claimed; importing looks for the six
exported names only. If you need an in-place sort, sort a copy and use
`vector-copy!` — the copy is cheap relative to the comparisons.

## JSON: `(srfi 180)`

`json-read` takes JSON **text** and `json-write` answers it. The value mapping
is the one the ledger pinned:

| JSON | Scheme |
| --- | --- |
| object | association list of dotted `("key" . value)` pairs — keys are **strings**, so `assoc` finds them |
| array | vector (`#(...)`) |
| `null` | the symbol `null` |
| `true` / `false` | `#t` / `#f` |
| number | unchanged: an integer stays exact, a decimal stays inexact |
| string | string |

```scheme
(import (srfi 180))

(json-write '((symbol . "SPY") (qty . 3) (ok . #t)))
;=> {"symbol": "SPY", "qty": 3, "ok": true}

(cdr (assoc "qty" (json-read "{\"qty\": 3}")))     ;=> 3
(json-read "{\"tags\": [1, 2]}")                   ;=> (("tags" . #(1 2)))
(json-read "{\"note\": null}")                     ;=> (("note" . null))
```

Note the spelling of the keys on the way back: **strings**, because that is
what the JSON had. If you want symbol keys, convert deliberately —
`(string->symbol key)` per entry — and then `assq` works. The asymmetry is the
point: a JSON object's keys *are* text.

Two failure modes are loud on purpose:

```scheme
(json-read "{oops}")                  ; raises: json-read: Expecting property name ...
(json-write (lambda (x) x))           ; raises: json-write: cannot encode Closure as JSON
```

`NaN` and `Infinity` are refused too — Python's `json` accepts them by default,
RFC 8259 does not, and a silent `NaN` in telemetry is the bug this library
exists to prevent.

## One line, not five: `(srfi 28)`

`format`'s destination is the first argument: `#f` answers the string, `#t`
writes to `(current-output-port)`, and a port writes to that port.

```scheme
(import (srfi 28))

(format #f "~a x~a costs ~s" "SPY" 3 1536)   ;=> "SPY x3 costs 1536"
(format #f "~s" "1536")                       ;=> "\"1536\"" — write, so quoted
(format #t "done~%")                          ; prints "done" and a newline
```

| Directive | Consumes | Prints |
| --- | --- | --- |
| `~a` | one value | like `display` — a string unquoted |
| `~s` | one value | like `write` — reader form, strings quoted |
| `~%` | nothing | a newline |
| `~~` | nothing | a literal `~` |

A missing argument, an unknown directive (`~q`), or an argument left over after
the string is a loud error — a format string that silently dropped a value is
exactly the class of bug this replaces. `~%` and `~~` are SRFI 48's directives,
not SRFI 28's; both are additive, and both are documented deviations in
[`docs/srfi.md`](../srfi.md).

## Strings: `(srfi 152)`

Four procedures cover the daily work; a fifth and sixth cover name checks:

```scheme
(import (srfi 152))

(string-split "spy,qqq,iwm" ",")        ;=> ("spy" "qqq" "iwm")
(string-join '("spy" "qqq") " | ")      ;=> "spy | qqq"
(string-contains "desk: spy" "spy")     ;=> 6 — an index, or #f
(string-trim "  spy  ")                 ;=> "spy"
(string-prefix? "spy" "spy.us")         ;=> #t
(string-suffix? ".us" "spy.us")         ;=> #t
```

The details that bite:

- **`string-split` requires its delimiter** and, like SRFI 152, takes the
  grammar and limit after it: `(string-split "a,b,c" "," 'infix 1)` ⇒
  `("a" "b,c")`. An empty string has no words, so it answers `()`.
- **`string-contains` returns an index** (or `#f`), not a boolean — unlike the
  core's `string-contains?` predicate, which is a different name for a
  different question.
- **`string-trim` trims both ends here.** SRFI 152 gives that name the
  left-only job; this dialect's core has always spelled the both-ends
  operation `string-trim`, and `(string-trim "  hi  ")` ⇒ `"hi"` is pinned by
  the S18 test. `string-trim-both` is its alias, and the right-only spelling is
  not claimed. That is a real difference from a portable SRFI 152 program —
  documented in [`docs/srfi.md`](../srfi.md) rather than papered over.

## Try it

```scheme
(import (srfi 132) (srfi 180) (srfi 28) (srfi 152))

;; sorting: a fresh list, a fresh vector, the predicate
(define lots '(("spy" . 3) ("qqq" . 1) ("iwm" . 2)))
(display (list-sort (lambda (a b) (< (cdr a) (cdr b))) lots)) (newline)
(display (vector->list (vector-sort > #(3 1 4 2)))) (newline)
(display (list-sorted? < '(1 2 3))) (newline)

;; strings: split, join, search, trim
(display (string-split "spy,qqq,iwm" ",")) (newline)
(display (string-join '("spy" "qqq" "iwm") " | ")) (newline)
(display (string-contains "desk: spy" "spy")) (newline)
(display (string-trim "  spy  ")) (newline)

;; JSON: write an alist, read it back
(define payload (json-write '((symbol . "SPY") (qty . 3) (ok . #t))))
(display payload) (newline)
(define back (json-read payload))
(display (cdr (assoc "symbol" back))) (newline)
(display (vector? (cdr (assoc "tags" (json-read "{\"tags\": [1, 2]}"))))) (newline)

;; format: one line instead of four displays
(display (format #f "~a x~a costs ~s  (~~ is a tilde)" "SPY" 3 (* 3 512))) (newline)
(display (format #f "~a~%" "done"))
```

```text
((qqq . 1) (iwm . 2) (spy . 3))
(4 3 2 1)
#t
(spy qqq iwm)
spy | qqq | iwm
6
spy
{"symbol": "SPY", "qty": 3, "ok": true}
SPY
#t
SPY x3 costs 1536  (~ is a tilde)
done
```

## Exercises

1. **Sort the book by value.** Given
   `'((spy . 512) (qqq . 430) (iwm . 71))`, write `(by-price book)` with
   `list-sort` that answers the entries ordered by descending price. Then
   answer: why does `(list-sort (lambda (a b) (> (cdr a) (cdr b))) book)` not
   need a tie-break to stay stable?
2. **Round-trip with string keys.** `json-write` an alist with symbol keys,
   then `json-read` it back. Where did the symbols go, and what is the smallest
   conversion that gives you a table `assq` can search? (Chapter
   [13](13-dictionaries-alists-and-hash-tables.md) has the table.)
3. **A report line.** Use `format` to print one line per row —
   `"SPY  qty=3  notional=1536"` — with `~a` for the symbol and `~s` for the
   number. Then explain what `~s` would have done to the symbol if you had used
   it there.
4. **Split, filter, join.** Take `"spy,qqq,,iwm"`, split it on `","`, drop the
   empty string with `filter` (chapter [12](12-srfi-1-the-list-library.md)),
   and re-join with `" | "`. What does the split alone tell you about
   consecutive delimiters?

## The shape you copy

> Reach for the wave when the alternative is a loop you would have to trust:
> a comparator loop for sorting, a string-concatenation loop for JSON, a
> `display` chain for one line, and a hand-written scanner for text. Each
> library is an `(import ...)` and a documented subset — and the deviations
> are one page away, not buried in behaviour.

Next: [30 Testing and debugging: `(srfi 64)`](30-testing-and-debugging-srfi-64.md).

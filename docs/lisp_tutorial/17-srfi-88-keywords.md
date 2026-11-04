# 17 — SRFI 88: keyword objects

> **What this chapter teaches.** What a keyword *is* in this dialect: how the
> reader makes one, how it differs from a symbol, and why a language needs a
> third name-like type at all.
>
> **Before this:** 02 (symbols and strings), 08. · **Time:** ~10 min.
> **After this you can:** read and write keyword literals, and know exactly
> when something is a keyword and when it only looks like one.

## The reader rule

A token that looks like a symbol but ends with a **colon** reads as a
*keyword object*:

```scheme
host:          ; the keyword named "host"
port:          ; the keyword named "port"
```

Keywords are **self-evaluating** — a keyword in expression position is the
keyword, the way `42` is `42`. That is the whole point: a keyword can appear
in a call without being evaluated, so it can *name* an argument rather than
compute one.

## Not a symbol, not a string

`Keyword` is a `str` subclass — like `Symbol` — but a *sibling* class, so the
two predicates are disjoint:

```scheme
(keyword? host:)        ;=> #t
(keyword? 'host)        ;=> #f
(keyword? ':host)       ;=> #f — a *leading* colon is just a symbol
(symbol? ':host)        ;=> #t
(string? host:)         ;=> #f
```

The three conversions are the library's whole surface:

```scheme
(keyword->string host:)                 ;=> host
(string->keyword "port")                ;=> port:
(keyword->string (string->keyword "port"))  ;=> port
```

Note the asymmetry the type carries: `keyword->string` answers the name
*without* the colon, and the printer adds the colon back so the value reads
back as itself. `types.py` says it in one line:

> *A keyword records its name without the trailing colon (which is what
> `keyword_to_string` answers), but it prints with the colon so it reads
> back.*

## Interned, like symbols

Keywords are interned — every `host:` in your program is the same object —
and two keywords with the same name are `equal?` however they were made:

```scheme
(eq? host: host:)                       ;=> #t
(equal? host: (string->keyword "host")) ;=> #t
```

## The dialect's spelling, stated plainly

This is SRFI 88 with two documented deviations, both of which save you from
guessing:

- the keyword syntax is the **suffix colon only** — there is no `#:foo`
  prefix spelling;
- a lone `:`, a leading `:host`, and `foo:bar` are **symbols**, not keywords.

So the colon is a *suffix marker*, not a prefix or a separator, and any
token you see ending in `:` is a keyword while anything else that contains a
colon is an ordinary symbol.

## What keywords are for

Their one job is to survive to the call site as a *name*. SRFI 89's
`define*`/`lambda*` use them for optional and named parameters — the subject
of the next chapter:

```scheme
(greet "ada" greeting: "hi")    ; greeting: names the argument
```

They are values, so they can be stored in alists and hash tables like any
other key — but their home turf is the argument list.

## Try it

```scheme
(display (keyword? host:)) (newline)
(display (keyword? 'host)) (newline)
(display (keyword? ':host)) (newline)
(display (keyword->string host:)) (newline)
(display (string->keyword "port")) (newline)
(display (eq? host: host:)) (newline)
(write host:) (newline)
(display (list 'mode host:)) (newline)
```

```text
#t
#f
#f
host
port:
#t
host:
(mode host:)
```

## Exercises

1. **Classify.** For each of `host:`, `:host`, `host`, `"host:"`, and
   `foo:bar`, say whether `keyword?` or `symbol?` accepts it, then check
   yourself at the REPL.
2. **Round trip.** Verify `(keyword->string (string->keyword "port"))` is
   `"port"` — no colon — and explain why the printer still shows `port:`.
3. **As data.** Build the alist `'((mode human) (seed 7))`, then build the
   same shape with keywords as keys, and read both back with `assoc`. What
   must you pass to `assoc` to find a keyword key?

## The shape you copy

> A keyword is a name that evaluates to itself — the type that lets a call
> say *which* argument without computing anything. Suffix colon is the whole
> syntax; everything else is the three conversion procedures.

Next: [18 SRFI 89 — optional and named parameters](18-srfi-89-optional-and-named-parameters.md).

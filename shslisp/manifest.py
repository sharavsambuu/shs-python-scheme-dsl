"""The R7RS-small export manifest measured by ``tests/test_r7rs.py``.

This is **not** a conformance suite and it is not copied from a test suite. It
is the project's own list of what R7RS-small says each standard library
exports, transcribed from Appendix A of the corrected R7RS report, so that
"supported", "missing", and "deviation" can be checked instead of asserted in
prose.

It lives in ``shslisp/`` because the library system (:mod:`shslisp.library`) derives
every built-in library's export list from it — the export list is *generated*
from this manifest, never typed twice. ``tests/r7rs_manifest.py`` re-exports
it so the conformance harness and the library system measure the same data.

Three namespaces are kept apart on purpose:

* ``procedures`` — names that must evaluate to a procedure value;
* ``syntax`` — names the evaluator must recognise as syntax (a special form or
  a macro binding);
* ``auxiliary`` — names that are *not* bindings at all but are part of the
  surface: ``else``/``=>`` in ``cond`` and ``case``, ``_`` and ``...`` in
  ``syntax-rules``, and the reader's ``unquote``/``unquote-splicing``.

A name in ``KNOWN_MISSING`` is intentionally absent today. The gate fails when
a name disappears from the environment without joining ``KNOWN_MISSING`` and
also when a name in ``KNOWN_MISSING`` starts working (so the set cannot rot).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Library:
    """One R7RS library's exports, split by namespace."""

    procedures: tuple[str, ...] = ()
    syntax: tuple[str, ...] = ()
    auxiliary: tuple[str, ...] = ()
    #: Optional libraries are listed for completeness but do not gate A0.
    optional: bool = False
    #: One line the conformance page (``docs/r7rs.md``) repeats.
    note: str = ""


def _names(text: str) -> tuple[str, ...]:
    """Whitespace-separated names, in a stable order."""
    return tuple(text.split())


# --------------------------------------------------------------------------- #
#  (scheme base)                                                              #
# --------------------------------------------------------------------------- #

_BASE_PROCEDURES = _names(
    """
    * + - / < <= = > >= abs append apply assoc assq assv
    binary-port? boolean=? boolean? bytevector bytevector-append bytevector-copy
    bytevector-copy! bytevector-length bytevector-u8-ref bytevector-u8-set!
    bytevector? caar cadr call-with-current-continuation call-with-port
    call-with-values call/cc car cdar cddr cdr ceiling char->integer
    char-ready? char<=? char<? char=? char>=? char>? char? close-input-port
    close-output-port close-port complex? cons current-error-port
    current-input-port current-output-port denominator dynamic-wind eof-object
    eof-object? eq? equal? eqv? error error-object-irritants
    error-object-message error-object? even? exact exact-integer-sqrt
    exact-integer? exact? expt features file-error? floor floor-quotient
    floor-remainder floor/ flush-output-port for-each gcd get-output-bytevector
    get-output-string inexact inexact? input-port-open? input-port?
    integer->char integer? lcm length list list->string list->vector list-copy
    list-ref list-set! list-tail list? make-bytevector make-list
    make-parameter make-string make-vector map max member memq memv min modulo
    negative? newline not null? number->string number? numerator odd?
    open-input-bytevector open-input-string open-output-bytevector
    open-output-string output-port-open? output-port? pair? peek-char peek-u8
    port? positive? procedure? quotient raise raise-continuable rational?
    rationalize read-bytevector read-bytevector! read-char read-error?
    read-line read-string read-u8 real? remainder reverse round set-car!
    set-cdr! square string string->list string->number string->symbol
    string->utf8 string->vector string-append string-copy string-copy!
    string-fill! string-for-each string-length string-map string-ref
    string-set! string<=? string<? string=? string>=? string>? string?
    substring symbol->string symbol=? symbol? textual-port? truncate
    truncate-quotient truncate-remainder truncate/ u8-ready? utf8->string
    values vector vector->list vector->string vector-append vector-copy
    vector-copy! vector-fill! vector-for-each vector-length vector-map
    vector-ref vector-set! vector? with-exception-handler write-bytevector
    write-char write-string write-u8 zero?
    """
)

_BASE_SYNTAX = _names(
    """
    and begin case cond cond-expand define define-record-type define-syntax
    define-values do guard if include include-ci lambda let let* let*-values
    let-syntax let-values letrec letrec* letrec-syntax or parameterize
    quasiquote quote set! syntax-error syntax-rules unless when
    """
)

#: Not bindings: clause keywords, template markers, and the reader's
#: quasiquote escapes (``,x`` reads as ``(unquote x)``).
_BASE_AUXILIARY = _names("=> ... _ else unquote unquote-splicing")

# --------------------------------------------------------------------------- #
#  The rest of the R7RS-small library set                                     #
# --------------------------------------------------------------------------- #

MANIFEST: dict[str, Library] = {
    "(scheme base)": Library(
        procedures=_BASE_PROCEDURES,
        syntax=_BASE_SYNTAX,
        auxiliary=_BASE_AUXILIARY,
        note="The foundation. Every other library is a facet of it.",
    ),
    "(scheme case-lambda)": Library(
        syntax=_names("case-lambda"),
        note="One syntax form; the evaluator already has case-lambda.",
    ),
    "(scheme char)": Library(
        procedures=_names(
            """
            char-alphabetic? char-ci<=? char-ci<? char-ci=? char-ci>=?
            char-ci>? char-downcase char-foldcase char-lower-case?
            char-numeric? char-upcase char-upper-case? char-whitespace?
            digit-value string-ci<=? string-ci<? string-ci=? string-ci>=?
            string-ci>? string-downcase string-foldcase string-upcase
            """
        ),
        note="Unicode-sensitive character and string procedures.",
    ),
    "(scheme complex)": Library(
        procedures=_names(
            "angle imag-part magnitude make-polar make-rectangular real-part"
        ),
        note="The complex tower (C1–C2): exact pairs and the polar half.",
    ),
    "(scheme cxr)": Library(
        procedures=_names(
            """
            caaaar caaadr caaar caadar caaddr caadr cadaar cadadr cadar
            caddar cadddr caddr cdaaar cdaadr cdaar cdadar cdaddr cdadr
            cddaar cddadr cddar cdddar cddddr cdddr
            """
        ),
        note="The three- and four-level compositions.",
    ),
    "(scheme eval)": Library(
        procedures=_names("environment eval"),
        note="Environment specifiers backed by the library system (A13).",
    ),
    "(scheme file)": Library(
        procedures=_names(
            """
            call-with-input-file call-with-output-file delete-file
            file-exists? open-binary-input-file open-binary-output-file
            open-input-file open-output-file with-input-from-file
            with-output-to-file
            """
        ),
        note="Binary file ports depend on bytevectors (A4).",
    ),
    "(scheme inexact)": Library(
        procedures=_names(
            "acos asin atan cos exp finite? infinite? log nan? sin sqrt tan"
        ),
        note="Inexact-only procedures; sqrt is in base too.",
    ),
    "(scheme lazy)": Library(
        procedures=_names("force make-promise promise?"),
        syntax=_names("delay delay-force"),
        note="Promises already exist in the prelude.",
    ),
    "(scheme load)": Library(
        procedures=_names("load"),
        note="The loader's (load ...) is the current mechanism.",
    ),
    "(scheme process-context)": Library(
        procedures=_names(
            """
            command-line emergency-exit exit get-environment-variable
            get-environment-variables
            """
        ),
        note="Host-facing; values come from the Python process.",
    ),
    "(scheme read)": Library(
        procedures=_names("read"),
        note="The datum reader as a procedure.",
    ),
    "(scheme repl)": Library(
        procedures=_names("interaction-environment"),
        note="The REPL's environment object.",
    ),
    "(scheme time)": Library(
        procedures=_names("current-jiffy current-second jiffies-per-second"),
        note="Monotonic and wall-clock readings.",
    ),
    "(scheme write)": Library(
        procedures=_names("display write write-shared write-simple"),
        note="write-char and write-string are base, not here.",
    ),
    "(scheme r5rs)": Library(
        procedures=_names(
            """
            * + - / < <= = > >= abs acos angle append apply asin assoc assq
            assv atan boolean? caaaar caaadr caaar caadar caaddr caadr caar
            cadaar cadadr cadar caddar cadddr caddr cadr
            call-with-current-continuation call-with-input-file
            call-with-output-file call-with-values car cdaaar cdaadr cdaar
            cdadar cdaddr cdadr cdar cddaar cddadr cddar cdddar cddddr cdddr
            cddr cdr ceiling char->integer char-alphabetic? char-ci<=?
            char-ci<? char-ci=? char-ci>=? char-ci>? char-downcase
            char-lower-case? char-numeric? char-ready? char-upcase
            char-upper-case? char-whitespace? char<=? char<? char=? char>=?
            char>? char? close-input-port close-output-port complex? cons cos
            current-input-port current-output-port denominator display
            dynamic-wind eof-object? eq? equal? eqv? eval even? exact->inexact
            exact? exp expt floor for-each force gcd imag-part inexact->exact
            inexact? input-port? integer->char integer? interaction-environment
            lcm length list list->string list->vector list-ref list-tail list?
            load log magnitude make-polar make-rectangular make-string
            make-vector map max member memq memv min modulo negative? newline
            not null-environment null? number->string number? numerator odd?
            open-input-file open-output-file output-port? pair? peek-char
            positive? procedure? quotient rational? rationalize read read-char
            real-part real? remainder reverse round scheme-report-environment
            set-car! set-cdr! sin sqrt string string->list string->number
            string->symbol string-append string-ci<=? string-ci<? string-ci=?
            string-ci>=? string-ci>? string-copy string-fill! string-length
            string-ref string-set! string<=? string<? string=? string>=?
            string>? string? substring symbol->string symbol? tan truncate
            values vector vector->list vector-fill! vector-length vector-ref
            vector-set! vector? with-input-from-file with-output-to-file write
            write-char zero?
            """
        ),
        syntax=_names(
            """
            and begin case cond define define-syntax delay do if lambda
            let let* let-syntax letrec letrec-syntax or quasiquote quote set!
            syntax-rules
            """
        ),
        # `else`, `unquote`, and `unquote-splicing` are the report's exports
        # too, but they are not bindings — the same treatment `(scheme base)`
        # gives its clause keywords and reader escapes (A6/A7).
        auxiliary=_names("=> ... _ else unquote unquote-splicing"),
        optional=True,
        note=(
            "Optional compatibility library. It is measured but does not gate "
            "A0; transcript-on/transcript-off are excluded by R7RS itself."
        ),
    ),
}


#: Names that are deliberately absent today. Every procedure or syntax name
#: in a non-optional library must be either implemented or listed here. When a
#: task implements one, remove it from this set in the same change. The set is
#: **empty** as of C2: the complex tower finished the R7RS-small surface, and
#: only R7RS's own exclusions (`transcript-on`/`transcript-off`) remain.
KNOWN_MISSING: frozenset[str] = frozenset()

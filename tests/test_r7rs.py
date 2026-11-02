"""The Option A conformance harness: what R7RS-small surface actually exists.

This module measures the **documented subset** described in
``docs/lisp-dsl.md`` and ``docs/r7rs.md``. It is not a claim of full R7RS
conformance, and it does not import an external test suite: the manifest is
transcribed from Appendix A of the corrected R7RS report, and every name is
checked against the environment the interpreter really builds.

Two namespaces are checked separately:

* procedures must be bound in ``make_env(install_tetris=False)``;
* syntax must be a special form, a macro binding, or a documented auxiliary
  keyword (``else``, ``=>``, ``_``, ``...``, ``unquote``, ``unquote-splicing``).

``KNOWN_MISSING`` is the honest list of names that are deliberately absent
today. The gate is bidirectional: a name may not vanish without joining the
set, and a name in the set may not start working without leaving it.
"""

from __future__ import annotations

import math
import re
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from lisp.evaluator import _SPECIAL_FORMS, evaluate_program
from lisp.printer import to_string
from lisp.reader import read_all
from lisp.runtime import make_env
from lisp.types import Macro, Symbol, SyntaxRules

from r7rs_manifest import KNOWN_MISSING, MANIFEST

#: Names that are part of the surface without being bindings. The manifest
#: lists them per library; this is the union used by the recogniser.
_AUXILIARY = frozenset(
    name for library in MANIFEST.values() for name in library.auxiliary
)

#: Syntax the evaluator recognises structurally rather than as a binding.
#: ``syntax-rules`` is parsed by ``define-syntax``/``let-syntax``; it is not an
#: expression form, so it has no entry in ``_SPECIAL_FORMS``.
_STRUCTURAL_SYNTAX = frozenset({"syntax-rules"})


@pytest.fixture(scope="module")
def language_env():
    """One language-only environment; the manifest is read-only."""
    return make_env(install_tetris=False)


def _recognised_syntax(env) -> set[str]:
    """Syntax names the evaluator really recognises in *env*."""
    names = {str(form) for form in _SPECIAL_FORMS}
    for name, value in env.vars.items():
        if isinstance(value, (Macro, SyntaxRules)):
            names.add(str(name))
    return names | _AUXILIARY | _STRUCTURAL_SYNTAX


def _implemented(env) -> set[str]:
    """Every name that is either bound or recognised as syntax."""
    return {str(name) for name in env.vars} | _recognised_syntax(env)


def _required(library) -> tuple[tuple[str, ...], ...]:
    return (library.procedures, library.syntax)


def test_manifest_is_well_formed() -> None:
    """Each library is internally consistent and the names are unique."""
    for name, library in MANIFEST.items():
        procedures = set(library.procedures)
        syntax = set(library.syntax)
        auxiliary = set(library.auxiliary)
        assert not procedures & syntax, f"{name}: a name is both procedure and syntax"
        assert not procedures & auxiliary, f"{name}: a name is both procedure and auxiliary"
        assert not syntax & auxiliary, f"{name}: a name is both syntax and auxiliary"
        assert len(procedures) == len(library.procedures), f"{name}: duplicate procedure"
        assert len(syntax) == len(library.syntax), f"{name}: duplicate syntax"


def test_every_manifest_name_is_bound_or_declared_missing(language_env) -> None:
    """The gate: implemented names plus ``KNOWN_MISSING`` cover the manifest.

    The failure message is the readable sorted difference, library by library,
    so an agent can paste the new names into ``KNOWN_MISSING`` (or implement
    them) without guessing.
    """
    implemented = _implemented(language_env)
    problems: list[str] = []
    for library_name, library in MANIFEST.items():
        if library.optional:
            continue
        for namespace, names in zip(("procedure", "syntax"), _required(library)):
            missing = sorted(
                name
                for name in names
                if name not in implemented and name not in KNOWN_MISSING
            )
            if missing:
                problems.append(
                    f"{library_name} ({namespace}): " + " ".join(missing)
                )
    assert not problems, (
        "R7RS manifest names are neither implemented nor in KNOWN_MISSING:\n  "
        + "\n  ".join(problems)
    )


def test_known_missing_has_not_rotted(language_env) -> None:
    """A name in ``KNOWN_MISSING`` must still be missing.

    This is the other half of the gate: when a task implements a name it must
    remove it from the set in the same change, so the conformance page cannot
    keep claiming a gap that no longer exists.
    """
    implemented = _implemented(language_env)
    stale = sorted(name for name in KNOWN_MISSING if name in implemented)
    assert not stale, (
        "these names are in KNOWN_MISSING but are now implemented; remove them:\n  "
        + " ".join(stale)
    )


def test_known_missing_names_exist_in_the_manifest() -> None:
    """No typos or ghosts in the declaration."""
    manifest_names = {
        name
        for library in MANIFEST.values()
        for names in (library.procedures, library.syntax, library.auxiliary)
        for name in names
    }
    ghosts = sorted(KNOWN_MISSING - manifest_names)
    assert not ghosts, "KNOWN_MISSING names not in the manifest:\n  " + " ".join(ghosts)


def test_conformance_page_matches_the_manifest() -> None:
    """``docs/r7rs.md``'s machine-checked block is the manifest's complement.

    The page is prose, but the list of missing names is not allowed to drift:
    it is delimited by HTML comments and compared as a set. A task that adds a
    name must edit the page and the manifest together.
    """
    page = Path(__file__).resolve().parent.parent / "docs" / "r7rs.md"
    text = page.read_text(encoding="utf-8")
    match = re.search(
        r"<!-- r7rs-missing:start -->(.*?)<!-- r7rs-missing:end -->",
        text,
        re.DOTALL,
    )
    assert match, "docs/r7rs.md is missing the r7rs-missing block"
    documented = set(match.group(1).split())
    assert documented == set(KNOWN_MISSING), (
        "docs/r7rs.md and tests/r7rs_manifest.py disagree; "
        f"only in doc: {sorted(documented - set(KNOWN_MISSING))}; "
        f"only in manifest: {sorted(set(KNOWN_MISSING) - documented)}"
    )


def test_optional_library_is_reported_separately(language_env) -> None:
    """``(scheme r5rs)`` is measured, but does not gate A0."""
    r5rs = MANIFEST["(scheme r5rs)"]
    assert r5rs.optional
    implemented = _implemented(language_env)
    supported = sorted(
        name for name in (*r5rs.procedures, *r5rs.syntax) if name in implemented
    )
    # The optional library is a superset of base; at least the core must be
    # there even though we do not require the whole R5RS surface.
    assert {"car", "cdr", "cons", "lambda", "quote"} <= set(supported)


# --------------------------------------------------------------------------- #
#  Behavioural cases for the parts that already work                          #
# --------------------------------------------------------------------------- #
#
# Each row is (source, expected write-mode output). ``write`` mode is used so
# strings, chars, and vectors are unambiguous. These are the behaviours later
# tasks must not regress while they add names.

BEHAVIOUR: list[tuple[str, str]] = [
    # truthiness: only #f is false
    ("(if '() 'yes 'no)", "yes"),
    ("(if 0 'yes 'no)", "yes"),
    ("(if \"\" 'yes 'no)", "yes"),
    ("(if #f 'yes 'no)", "no"),
    ("(not '())", "#f"),
    ("(and '() 1)", "1"),
    ("(or #f '())", "()"),
    ("(and)", "#t"),
    ("(or)", "#f"),
    ("(cond ('() 'yes) (else 'no))", "yes"),
    ("(when '() 'yes)", "yes"),
    # equivalence
    ("(eq? 'a 'a)", "#t"),
    ("(eqv? 1.0 1.0)", "#t"),
    ("(equal? '(1 (2 #(3))) '(1 (2 #(3))))", "#t"),
    ("(equal? '(1 2) '(1 2 3))", "#f"),
    # pairs and lists
    ("'(1 2 . 3)", "(1 2 . 3)"),
    ("(list 1 2 3)", "(1 2 3)"),
    ("(append '(1 2) '(3))", "(1 2 3)"),
    ("(reverse '(1 2 3))", "(3 2 1)"),
    ("(list-ref '(a b c) 1)", "b"),
    # numbers
    ("42", "42"),
    ("-7", "-7"),
    ("3.5", "3.5"),
    ("(+ 1 2 3)", "6"),
    ("(exact? 1)", "#t"),
    ("(inexact? 1.0)", "#t"),
    ("(number->string 255 16)", '"ff"'),
    # chars and strings
    ("#\\a", "#\\a"),
    ("#\\space", "#\\space"),
    ('"hi"', '"hi"'),
    ('(string-append "a" "b")', '"ab"'),
    ('(string->symbol "hi")', "hi"),
    ("(symbol->string 'hi)", '"hi"'),
    ("(string->list \"ab\")", "(#\\a #\\b)"),
    # vectors
    ("(vector 1 2 3)", "#(1 2 3)"),
    ("(vector->list #(1 2))", "(1 2)"),
    ("(list->vector '(1 2))", "#(1 2)"),
    ("(let ((v (make-vector 3 0))) (vector-set! v 1 9) v)", "#(0 9 0)"),
    # continuations and dynamic extent
    ("(call/cc (lambda (k) (+ 1 (k 41))))", "41"),
    ("(dynamic-wind (lambda () 1) (lambda () 2) (lambda () 3))", "2"),
    # exceptions and multiple values
    ("(guard (e (else 'caught)) (raise 'boom))", "caught"),
    ("(call-with-values (lambda () (values 1 2)) list)", "(1 2)"),
    # ports
    (
        '(let ((p (open-input-string "ab")))'
        " (list (read-char p) (read-char p) (eof-object? (read-char p))))",
        "(#\\a #\\b #t)",
    ),
    ('(let ((p (open-output-string))) (write-string "ok" p) (get-output-string p))', '"ok"'),
]


@pytest.mark.parametrize(("source", "expected"), BEHAVIOUR, ids=[row[0] for row in BEHAVIOUR])
def test_supported_behaviour(language_env, source: str, expected: str) -> None:
    """The supported subset behaves the way the page says it does."""
    value: Any = evaluate_program(read_all(source), language_env)
    assert to_string(value, write=True) == expected


# --------------------------------------------------------------------------- #
#  A3: define-record-type                                                    #
# --------------------------------------------------------------------------- #

POINT = """
(define-record-type point
  (make-point x y)
  point?
  (x point-x set-point-x!)
  (y point-y))
"""

BOX = """
(define-record-type box
  (make-box value)
  box?
  (value box-value))
"""


def test_record_type_construction_predicate_and_accessors(ev) -> None:
    ev(POINT)
    assert ev("(point? (make-point 1 2))") is True
    assert ev("(point? 5)") is False
    assert ev("(point-x (make-point 1 2))") == 1
    assert ev("(point-y (make-point 1 2))") == 2


def test_record_type_modifier_mutates_in_place(ev) -> None:
    ev(POINT)
    assert ev("(let ((p (make-point 1 2))) (set-point-x! p 9) (point-x p))") == 9


def test_record_type_without_modifier_does_not_bind_one(ev) -> None:
    ev(POINT)
    with pytest.raises(Exception) as caught:
        ev("(set-point-y! (make-point 1 2) 9)")
    assert "set-point-y!" in str(caught.value)


def test_record_type_field_missing_from_constructor_starts_false(ev) -> None:
    ev(
        """
        (define-record-type pair2
          (make-pair2 a)
          pair2?
          (a pair2-a)
          (b pair2-b set-pair2-b!))
        """
    )
    assert ev("(pair2-b (make-pair2 1))") is False
    assert ev("(let ((p (make-pair2 1))) (set-pair2-b! p 2) (pair2-b p))") == 2


def test_record_type_constructor_arity_is_checked(ev) -> None:
    from lisp.errors import LispArityError

    ev(POINT)
    with pytest.raises(LispArityError):
        ev("(make-point 1)")


def test_record_type_accessor_refuses_the_wrong_record(ev) -> None:
    from lisp.errors import LispTypeError

    ev(POINT)
    ev(BOX)
    with pytest.raises(LispTypeError):
        ev("(box-value (make-point 1 2))")
    with pytest.raises(LispTypeError):
        ev("(point-x 5)")


def test_record_type_equality_is_identity(ev) -> None:
    ev(POINT)
    assert ev("(equal? (make-point 1 2) (make-point 1 2))") is False
    assert ev("(let ((p (make-point 1 2))) (equal? p p))") is True


def test_record_type_works_inside_a_local_body(ev) -> None:
    assert (
        ev(
            """
            (let ()
              (define-record-type local
                (make-local a)
                local?
                (a local-a))
              (local-a (make-local 7)))
            """
        )
        == 7
    )


def test_record_type_name_is_bound_to_a_descriptor(ev) -> None:
    from lisp.types import RecordType

    ev(POINT)
    descriptor = ev("point")
    assert isinstance(descriptor, RecordType)
    assert str(descriptor.name) == "point"


def test_record_type_printing_is_stable(ev) -> None:
    ev(POINT)
    assert to_string(ev("(make-point 1 2)"), write=True) == "#<record:point 1 2>"
    assert (
        to_string(ev("(list (make-point 1 2))"), write=True)
        == "(#<record:point 1 2>)"
    )


# --------------------------------------------------------------------------- #
#  A4: bytevectors                                                           #
# --------------------------------------------------------------------------- #


def test_bytevector_construction_and_access(ev) -> None:
    assert ev("(bytevector? #u8(1 2))") is True
    assert ev("(bytevector? 5)") is False
    assert ev("(bytevector-length #u8(1 2 3))") == 3
    assert ev("(bytevector-u8-ref #u8(1 2 3) 1)") == 2
    assert ev("(bytevector-u8-ref (make-bytevector 2 9) 0)") == 9
    assert ev("(bytevector-u8-ref (make-bytevector 2) 1)") == 0


def test_bytevector_mutation_and_bounds(ev) -> None:
    from lisp.errors import LispTypeError

    assert (
        to_string(
            ev("(let ((b (bytevector 1 2))) (bytevector-u8-set! b 0 255) b)"),
            write=True,
        )
        == "#u8(255 2)"
    )
    with pytest.raises(LispTypeError):
        ev("(let ((b (bytevector 1))) (bytevector-u8-set! b 0 256))")
    with pytest.raises(LispTypeError):
        ev("(let ((b (bytevector 1))) (bytevector-u8-set! b 5 0))")
    with pytest.raises(LispTypeError):
        ev("(bytevector 256)")


def test_bytevector_copy_append_and_overlap(ev) -> None:
    assert to_string(ev("(bytevector-copy #u8(1 2 3) 1)"), write=True) == "#u8(2 3)"
    assert (
        to_string(ev("(bytevector-append #u8(1) #u8(2 3))"), write=True)
        == "#u8(1 2 3)"
    )
    # The source is snapshotted, so an overlapping copy behaves like R7RS's
    # "as if copied first".
    assert (
        to_string(
            ev(
                """
                (let ((b (bytevector 1 2 3 4)))
                  (bytevector-copy! b 1 b 0 3)
                  b)
                """
            ),
            write=True,
        )
        == "#u8(1 1 2 3)"
    )


def test_bytevector_utf8_round_trip(ev) -> None:
    assert ev('(utf8->string (string->utf8 "héllo"))') == "héllo"
    assert to_string(ev('(string->utf8 "é")'), write=True) == "#u8(195 169)"
    assert ev('(utf8->string #u8(104 105))') == "hi"


def test_bytevector_reader_printer_round_trip(ev) -> None:
    from lisp.types import ByteVector

    value = ev("#u8(0 255 7)")
    assert isinstance(value, ByteVector)
    text = to_string(value, write=True)
    assert text == "#u8(0 255 7)"
    assert ev(f"(equal? {text} #u8(0 255 7))") is True


def test_bytevector_reader_rejects_bad_elements() -> None:
    from lisp.errors import LispSyntaxError
    from lisp.reader import read_all

    for source in ("#u8(1 256)", "#u8(1 -1)", '#u8("x")'):
        with pytest.raises(LispSyntaxError):
            read_all(source)


def test_bytevector_equality_is_structural_but_eqv_is_identity(ev) -> None:
    assert ev("(equal? (bytevector 1 2) (bytevector 1 2))") is True
    assert ev("(equal? (bytevector 1 2) (bytevector 1 3))") is False
    assert ev("(eqv? (bytevector 1) (bytevector 1))") is False


# --------------------------------------------------------------------------- #
#  A5: external representations round-trip                                    #
# --------------------------------------------------------------------------- #

#: Every datum here must survive ``read -> write -> read -> write`` unchanged.
ROUND_TRIP = [
    "42",
    "-7",
    "3.5",
    "-0.5",
    "1e3",
    ".5",
    "#b101",
    "#o17",
    "#d42",
    "#xff",
    "#e1.0",
    "#i1",
    "#e#x10",
    "#x#e10",
    "+inf.0",
    "-inf.0",
    "+nan.0",
    "#t",
    "#f",
    '"plain"',
    '"quote \\" backslash \\\\ tab \\t newline \\n return \\r"',
    '"bell \\a backspace \\b bar \\|"',
    "#\\a",
    "#\\space",
    "#\\newline",
    "#\\x41",
    "()",
    "(1 2 3)",
    "(1 . 2)",
    "(1 2 . 3)",
    "(a (b c) . d)",
    "'quoted",
    "#(1 2 3)",
    "#(a #(b) (c . d))",
    "#u8(0 1 255)",
    "|a symbol with spaces|",
    "|1+|",
    "|a\\|b|",
    "|#x|",
]


@pytest.mark.parametrize("source", ROUND_TRIP, ids=ROUND_TRIP)
def test_written_form_reads_back(source: str) -> None:
    """``write`` produces text the reader accepts, and re-writing is stable."""
    from lisp.reader import read_one

    first = read_one(source)
    written = to_string(first, write=True)
    second = read_one(written)
    assert to_string(second, write=True) == written


def test_radix_and_exactness_prefixes() -> None:
    from lisp.reader import read_one

    assert read_one("#b101") == 5
    assert read_one("#o17") == 15
    assert read_one("#d42") == 42
    assert read_one("#xff") == 255
    assert read_one("#x1F") == 31
    assert read_one("#e1.0") == 1
    assert type(read_one("#e1.0")) is int
    assert read_one("#i1") == 1.0
    assert type(read_one("#i1")) is float
    # Either order is legal (R7RS §7.1.1).
    assert read_one("#e#x10") == 16
    assert read_one("#x#e10") == 16


def test_inexact_special_literals_are_numbers(ev) -> None:
    assert ev("+inf.0") == float("inf")
    assert ev("-inf.0") == float("-inf")
    assert ev("+nan.0") != ev("+nan.0")  # NaN is never equal to itself
    assert ev("(= +inf.0 +inf.0)") is True
    assert ev("(< -inf.0 0 +inf.0)") is True
    assert to_string(float("nan"), write=True) == "+nan.0"
    assert to_string(float("inf"), write=True) == "+inf.0"


def test_quoted_symbols_preserve_case_and_spaces(ev) -> None:
    assert ev("(symbol->string '|Hello World|)") == "Hello World"
    assert ev("(symbol->string '|1+|)") == "1+"
    assert ev("(eq? '|foo| 'foo)") is True
    # A symbol the reader could not read bare is printed between bars.
    assert to_string(ev("'|a b|"), write=True) == "|a b|"
    assert to_string(ev("'plain"), write=True) == "plain"
    assert to_string(ev("'+"), write=True) == "+"


def test_fold_case_directive_folds_following_identifiers() -> None:
    from lisp.reader import read_all

    forms = read_all("#!fold-case Foo BAR")
    assert [str(form) for form in forms] == ["foo", "bar"]
    # Strings, characters, and |quoted symbols| keep their case.
    forms = read_all('#!fold-case "ABC" #\\A |ABC|')
    assert forms[0] == "ABC"
    assert forms[1].value == "A"
    assert str(forms[2]) == "ABC"
    # #!no-fold-case turns it back off.
    forms = read_all("#!fold-case Foo #!no-fold-case BAR")
    assert [str(form) for form in forms] == ["foo", "BAR"]
    # Numbers are never folded into identifiers.
    assert read_all("#!fold-case 123 ABC") == [123, Symbol("abc")]


def test_fold_case_is_off_by_default() -> None:
    from lisp.reader import read_one

    assert str(read_one("Foo")) == "Foo"


def test_string_escapes_and_line_continuation() -> None:
    from lisp.reader import read_one

    assert read_one(r'"a\bb"') == "a\bb"
    assert read_one(r'"a\|b"') == "a|b"
    assert read_one(r'"\x41;"') == "A"
    # Backslash, newline, and following indentation are elided.
    assert read_one('"one\\\n   two"') == "onetwo"
    assert to_string("a\rb", write=True) == '"a\\rb"'


def test_char_names_are_strict() -> None:
    from lisp.errors import LispSyntaxError
    from lisp.reader import read_one

    assert read_one("#\\x41").value == "A"
    assert read_one("#\\escape").value == "\x1b"
    with pytest.raises(LispSyntaxError):
        read_one("#\\nosuchname")


# --------------------------------------------------------------------------- #
#  A6: base numeric procedures                                                #
# --------------------------------------------------------------------------- #

def test_exactness_conversions_and_predicate(ev) -> None:
    assert ev("(exact 3.0)") == 3
    assert type(ev("(exact 3.0)")) is int
    assert ev("(inexact 3)") == 3.0
    assert type(ev("(inexact 3)")) is float
    assert ev("(exact-integer? 32)") is True
    assert ev("(exact-integer? 32.0)") is False
    assert ev("(exact-integer? 1.5)") is False


def test_exact_converts_an_inexact_value_to_its_exact_equal(ev) -> None:
    # Row 4: the implementation-restriction error is gone. The conversion is
    # honest about the double — the exact value *numerically equal* to it.
    assert ev("(exact 3.5)") == Fraction(7, 2)
    assert ev("(exact 0.5)") == Fraction(1, 2)
    assert ev("(exact 2.0)") == 2
    assert type(ev("(exact 2.0)")) is int
    assert ev("(exact 0.1)") == Fraction(0.1)  # the binary double, not 1/10
    assert ev("(exact (/ 3 4))") == Fraction(3, 4)  # an exact value passes through
    from lisp.errors import LispTypeError

    with pytest.raises(LispTypeError, match="no exact equal"):
        ev("(exact +inf.0)")


def test_the_r5rs_aliases_are_the_same_conversions(ev) -> None:
    # A6/A7: the historical R5RS spellings are aliases of `exact`/`inexact` —
    # one semantics (the same underlying function), two names.
    assert ev("(exact->inexact 3)") == 3.0
    assert type(ev("(exact->inexact 3)")) is float
    assert ev("(inexact->exact 3.0)") == 3
    assert type(ev("(inexact->exact 3.0)")) is int
    assert ev("(inexact->exact 3.5)") == Fraction(7, 2)  # R3: converts, not raises
    assert ev("(procedure? exact->inexact)") is True


def test_scheme_r5rs_imports_whole(ev) -> None:
    # The manifest always promised these names; before A6/A7 the import
    # failed with "exports inexact->exact, but it is not bound".
    ev("(import (scheme r5rs))")
    assert ev("(exact->inexact (inexact->exact 2.0))") == 2.0


def test_the_r5rs_environment_procedures(ev) -> None:
    from lisp.errors import LispError

    # A6/A7 grew one pair of hands: the import could not resolve until the
    # report's two environment procedures existed either.
    assert ev("(eval '(if #t 1 2) (null-environment 5))") == 1
    # Syntax works, bindings do not: `car` is unbound in the null environment.
    with pytest.raises(LispError, match="car"):
        ev("(eval '(car '(1)) (null-environment 5))")
    assert ev("(eval '(car '(1 2)) (scheme-report-environment 5))") == 1
    assert ev("(eval '(exact->inexact 3) (scheme-report-environment 5))") == 3.0
    # A name outside the R5RS surface is unbound there, as the report intends.
    with pytest.raises(LispError, match="generator->list"):
        ev("(eval '(generator->list (generator 1)) (scheme-report-environment 5))")
    with pytest.raises(LispError, match="version 5"):
        ev("(null-environment 4)")


def test_division_preserves_exactness_and_never_divides_by_zero(ev) -> None:
    # R1: `/` answers an exact rational when the exact division is not even —
    # the design note's headline change (row 1).
    assert ev("(/ 3 4)") == Fraction(3, 4)
    assert ev("(/ 12 4)") == 3
    assert type(ev("(/ 12 4)")) is int
    assert ev("(/ 12 4.0)") == 3.0
    assert type(ev("(/ 12 4.0)")) is float
    assert ev("(/ 1 3 3)") == Fraction(1, 9)


def test_exact_rationals_are_a_type(ev) -> None:
    # R1: the tower grows Fraction — exact, reduced, whole values normalized.
    value = ev("(/ 6 4)")
    assert value == Fraction(3, 2)
    assert type(value) is Fraction
    assert ev("(exact? (/ 3 4))") is True
    assert ev("(inexact? (/ 3 4))") is False
    assert ev("(rational? (/ 3 4))") is True
    assert ev("(real? (/ 3 4))") is True
    assert ev("(number? (/ 3 4))") is True
    assert ev("(integer? (/ 4 2))") is True
    assert ev("(exact-integer? (/ 4 2))") is True


def test_rational_arithmetic_normalizes(ev) -> None:
    # A whole rational is an integer: the tower never holds Fraction(2, 1).
    assert ev("(+ (/ 1 2) (/ 1 2))") == 1
    assert type(ev("(+ (/ 1 2) (/ 1 2))")) is int
    assert ev("(* (/ 2 3) (/ 3 2))") == 1
    assert ev("(- (/ 1 2) (/ 1 4))") == Fraction(1, 4)
    assert ev("(/ 2)") == Fraction(1, 2)
    assert ev("(/ (/ 1 2))") == 2
    assert ev("(abs (- (/ 1 2)))") == Fraction(1, 2)
    assert ev("(expt (/ 2 3) 2)") == Fraction(4, 9)


def test_inexact_operands_contaminate(ev) -> None:
    # Exact op exact is exact; any inexact operand makes the result inexact.
    assert ev("(+ (/ 1 2) 0.5)") == 1.0
    assert type(ev("(+ (/ 1 2) 0.5)")) is float
    assert ev("(* (/ 1 3) 3.0)") == 1.0
    assert type(ev("(* (/ 1 3) 3.0)")) is float
    assert ev("(/ 1.0 3)") == pytest.approx(1 / 3)


def test_division_by_inexact_zero_answers_ieee(ev) -> None:
    # Row 11: an inexact zero divisor has IEEE answers; an exact zero divisor
    # is an error, full stop — even for an inexact dividend.
    assert ev("(/ 1 0.0)") == float("inf")
    assert ev("(/ -1 0.0)") == float("-inf")
    assert ev("(/ 1.0 0.0)") == float("inf")
    assert math.isnan(ev("(/ 0 0.0)"))
    from lisp.errors import LispTypeError

    with pytest.raises(LispTypeError, match="division by zero"):
        ev("(/ 1 0)")
    with pytest.raises(LispTypeError, match="division by zero"):
        ev("(/ 1.0 0)")


def test_eqv_and_equal_distinguish_exactness(ev) -> None:
    # Row 16: exactness distinguishes eqv?; = stays numerical.
    assert ev("(eqv? (/ 3 4) 0.75)") is False
    assert ev("(eqv? (/ 3 4) (/ 3 4))") is True
    assert ev("(eqv? (/ 4 2) 2)") is True
    assert ev("(equal? (/ 3 4) (/ 3 4))") is True
    assert ev("(= (/ 3 4) 0.75)") is True


def test_rationals_print_and_convert(ev) -> None:
    # The printer's ``p/q`` is what R2's reader will read back.
    assert ev("(number->string (/ 3 4))") == "3/4"
    assert ev("(number->string (/ -3 4))") == "-3/4"
    assert ev("(exact->inexact (/ 3 4))") == 0.75
    assert ev("(inexact (/ 3 4))") == 0.75
    assert ev("(exact (/ 3 4))") == Fraction(3, 4)
    assert ev("(numerator (/ 3 4))") == 3
    assert ev("(denominator (/ 3 4))") == 4


def test_string_to_number_reads_rationals(ev) -> None:
    # Row 17: the reader's twin. A rational string parses; "1/0" is not a
    # number, so #f rather than the error the *reader* raises.
    assert ev('(string->number "3/4")') == Fraction(3, 4)
    assert ev('(string->number "-3/4")') == Fraction(-3, 4)
    assert ev('(string->number "2/2")') == 1
    assert ev('(string->number "1/0")') is False
    assert ev('(string->number "1/x")') is False
    assert ev('(string->number "3/4" 16)') is False  # row 18: decimal only


def test_exactness_prefix_denotes_the_rational(ev) -> None:
    # Row 2, from the evaluator side: `#e1.5` is the exact rational the
    # decimal spells, not the binary double.
    assert ev("#e1.5") == Fraction(3, 2)
    assert ev("#e0.1") == Fraction(1, 10)
    assert ev("#e1/3") == Fraction(1, 3)


def test_division_by_zero_is_a_lisp_error(ev) -> None:
    from lisp.errors import LispTypeError

    with pytest.raises(LispTypeError, match="division by zero"):
        ev("(/ 1 0)")


def test_square_and_integer_sqrt(ev) -> None:
    assert ev("(square 42)") == 1764
    assert ev("(square 2.0)") == 4.0
    assert ev("(call-with-values (lambda () (exact-integer-sqrt 4)) list)") == [2, 0]
    assert ev("(call-with-values (lambda () (exact-integer-sqrt 5)) list)") == [2, 1]
    assert ev("(call-with-values (lambda () (exact-integer-sqrt 17)) list)") == [4, 1]


def test_floor_and_truncate_division(ev) -> None:
    assert ev("(floor-quotient -7 2)") == -4
    assert ev("(floor-remainder -7 2)") == 1
    assert ev("(truncate-quotient -7 2)") == -3
    assert ev("(truncate-remainder -7 2)") == -1
    assert ev("(call-with-values (lambda () (floor/ 5 2)) list)") == [2, 1]
    assert ev("(call-with-values (lambda () (floor/ -5 2)) list)") == [-3, 1]
    assert ev("(call-with-values (lambda () (truncate/ 5 2)) list)") == [2, 1]
    assert ev("(call-with-values (lambda () (truncate/ -5 2)) list)") == [-2, -1]


def test_numerator_and_denominator(ev) -> None:
    assert ev("(numerator 6)") == 6
    assert ev("(denominator 6)") == 1
    assert type(ev("(denominator 6)")) is int
    assert ev("(numerator 0.5)") == 1.0
    assert ev("(denominator 0.5)") == 2.0


def test_rationalize_answers_the_simplest_rational(ev) -> None:
    # Row 5: the R7RS algorithm, on exact rationals. The classic example:
    # the simplest rational within 1/5 of 7/2 is 7/2 itself.
    assert ev("(rationalize (/ 7 2) (/ 1 5))") == Fraction(7, 2)
    assert ev("(rationalize (/ 1 3) (/ 1 100))") == Fraction(1, 3)
    assert ev("(rationalize 5 0)") == 5
    assert ev("(rationalize 0 1)") == 0
    assert ev("(rationalize (/ -1 2) (/ 1 4))") == Fraction(-1, 2)
    # An inexact operand makes the result inexact: computed exactly, then
    # converted — the textbook answer for (3.5, 0.1) is 7/2, i.e. 3.5.
    assert ev("(rationalize 3.5 0.1)") == 3.5
    assert type(ev("(rationalize 3.5 0.1)")) is float
    assert ev("(rationalize 3 0.1)") == 3.0
    assert type(ev("(rationalize 3 0.1)")) is float
    from lisp.errors import LispTypeError

    with pytest.raises(LispTypeError, match="finite"):
        ev("(rationalize +inf.0 0.1)")


# --------------------------------------------------------------------------- #
#  R4: the exact cases, the division family, and the contagion rules          #
# --------------------------------------------------------------------------- #


def test_expt_exact_negative_exponent_answers_a_rational(ev) -> None:
    # Row 6: exact base, exact negative integer exponent.
    assert ev("(expt 2 -1)") == Fraction(1, 2)
    assert ev("(expt 2 -3)") == Fraction(1, 8)
    assert ev("(expt (/ 2 3) -2)") == Fraction(9, 4)
    assert ev("(expt 2 10)") == 1024
    assert type(ev("(expt 2 10)")) is int
    # A non-integral exact exponent is generally irrational: inexact.
    assert ev("(expt 2 (/ 1 2))") == pytest.approx(2 ** 0.5)
    assert ev("(expt 4 (/ 1 2))") == 2.0
    from lisp.errors import LispTypeError

    with pytest.raises(LispTypeError, match="division by zero"):
        ev("(expt 0 -1)")


def test_sqrt_of_a_rational_stays_exact_when_it_can(ev) -> None:
    # Row 7: numerator and denominator both perfect squares.
    assert ev("(sqrt (/ 1 4))") == Fraction(1, 2)
    assert ev("(sqrt (/ 9 4))") == Fraction(3, 2)
    assert ev("(sqrt 4)") == 2
    assert ev("(sqrt 2)") == pytest.approx(2 ** 0.5)  # irrational stays inexact
    assert ev("(sqrt (/ 2 4))") == pytest.approx(2 ** -0.5)  # 1/2 has no rational root


def test_the_division_family_takes_rationals(ev) -> None:
    # Row 9's exact half: the family operates on exact rationals.
    # (quotient 7/2 2) is truncate(7/4) = 1 — the divisor divides the quotient.
    assert ev("(quotient (/ 7 2) 2)") == 1
    assert ev("(quotient (/ -7 2) 2)") == -1  # truncation, not floor
    assert ev("(remainder (/ 7 2) 2)") == Fraction(3, 2)
    assert ev("(modulo (/ 7 2) 2)") == Fraction(3, 2)
    assert ev("(floor-quotient (/ 7 2) 2)") == 1
    assert ev("(floor-remainder (/ -7 2) 2)") == Fraction(1, 2)
    assert ev("(call-with-values (lambda () (floor/ (/ 7 2) 2)) list)") == [1, Fraction(3, 2)]


def test_the_division_family_preserves_inexactness(ev) -> None:
    # Row 9: `(quotient 7.0 2)` is `3.0` — consistent with `modulo`, which
    # always preserved it.
    assert ev("(quotient 7.0 2)") == 3.0
    assert type(ev("(quotient 7.0 2)")) is float
    assert ev("(remainder 7.0 2)") == 1.0
    assert type(ev("(remainder 7.0 2)")) is float
    assert ev("(floor-quotient 7.0 2)") == 3.0
    assert ev("(floor-remainder 7.0 2)") == 1.0
    assert ev("(modulo -7.0 2)") == 1.0


def test_the_division_family_refuses_a_zero_divisor_loudly(ev) -> None:
    # A hazard closed while in the family: `modulo`/`quotient` by exact zero
    # used to leak a raw Python ZeroDivisionError.
    from lisp.errors import LispTypeError

    for source in (
        "(modulo 1 0)",
        "(quotient 1 0)",
        "(remainder 1 0)",
        "(floor-quotient 1 0)",
        "(floor-remainder 1 0)",
    ):
        with pytest.raises(LispTypeError, match="division by zero"):
            ev(source)


def test_gcd_and_lcm_take_rationals_and_integral_inexact_integers(ev) -> None:
    # Row 8: gcd(a/b, c/d) = gcd(a·d, c·b)/(b·d); the whole-value rule for
    # inexact arguments, and exactness contagion.
    assert ev("(gcd 2 4)") == 2
    assert ev("(gcd (/ 1 2) (/ 1 3))") == Fraction(1, 6)
    assert ev("(lcm (/ 1 2) (/ 1 3))") == 1
    assert ev("(lcm (/ 2 3) (/ 3 4))") == 6  # lcm(8, 9) / gcd(3, 4) = 72/12
    assert ev("(gcd 2.0 4)") == 2.0
    assert type(ev("(gcd 2.0 4)")) is float
    assert ev("(lcm 4.0 6)") == 12.0
    assert ev("(gcd)") == 0
    assert ev("(lcm)") == 1
    from lisp.errors import LispTypeError

    with pytest.raises(LispTypeError, match="non-integral float"):
        ev("(gcd 2.5 4)")


def test_min_and_max_contaminate(ev) -> None:
    # Row 10: any inexact argument makes the result inexact.
    assert ev("(min 1 2.0)") == 1.0
    assert type(ev("(min 1 2.0)")) is float
    assert ev("(max 1 2.0)") == 2.0
    assert type(ev("(max 1 2.0)")) is float
    assert ev("(min (/ 1 2) 0.4)") == 0.4
    assert ev("(min 1 2)") == 1
    assert type(ev("(min 1 2)")) is int
    assert ev("(min (/ 1 2) (/ 1 3))") == Fraction(1, 3)


def test_integer_predicate_is_the_mathematical_property(ev) -> None:
    # Row 12: `3.0` is an integer; `exact-integer?` stays type-strict.
    assert ev("(integer? 3.0)") is True
    assert ev("(integer? 3.5)") is False
    assert ev("(integer? 3)") is True
    assert ev("(integer? (/ 4 2))") is True
    assert ev("(integer? (/ 3 4))") is False
    assert ev("(integer? #t)") is False
    assert ev("(exact-integer? 3.0)") is False
    assert ev("(exact-integer? 3)") is True


def test_rounding_preserves_inexactness_and_is_ties_to_even(ev) -> None:
    assert ev("(floor 3.7)") == 3.0
    assert type(ev("(floor 3.7)")) is float
    assert ev("(ceiling 3.2)") == 4.0
    assert ev("(truncate -3.7)") == -3.0
    assert ev("(round 3.5)") == 4.0
    assert ev("(round 2.5)") == 2.0
    assert type(ev("(round 3.5)")) is float
    assert ev("(floor 3)") == 3
    assert type(ev("(floor 3)")) is int


def test_sqrt_stays_exact_for_perfect_squares(ev) -> None:
    assert ev("(sqrt 4)") == 2
    assert type(ev("(sqrt 4)")) is int
    assert ev("(sqrt 4.0)") == 2.0
    assert type(ev("(sqrt 4.0)")) is float
    assert ev("(sqrt 2)") == pytest.approx(2 ** 0.5)


def test_number_and_string_radix(ev) -> None:
    assert ev('(number->string 255 16)') == "ff"
    assert ev('(number->string 5 2)') == "101"
    assert ev('(string->number "ff" 16)') == 255
    assert ev('(string->number "101" 2)') == 5
    assert ev('(string->number "nope" 10)') is False


# --------------------------------------------------------------------------- #
#  A7: the inexact library (complex is deliberately out)                      #
# --------------------------------------------------------------------------- #

def test_finite_infinite_and_nan_predicates(ev) -> None:
    assert ev("(finite? 1.0)") is True
    assert ev("(finite? +inf.0)") is False
    assert ev("(finite? +nan.0)") is False
    assert ev("(infinite? +inf.0)") is True
    assert ev("(infinite? -inf.0)") is True
    assert ev("(infinite? 1.0)") is False
    assert ev("(nan? +nan.0)") is True
    assert ev("(nan? 1.0)") is False


def test_transcendental_functions(ev) -> None:
    assert ev("(exp 0)") == 1.0
    assert ev("(log 1)") == 0.0
    assert ev("(log 8 2)") == pytest.approx(3.0)
    assert ev("(sin 0)") == 0.0
    assert ev("(cos 0)") == 1.0
    assert ev("(tan 0)") == 0.0
    assert ev("(asin 0)") == 0.0
    assert ev("(acos 1)") == 0.0
    assert ev("(atan 0)") == 0.0
    assert ev("(atan 1 1)") == pytest.approx(0.7853981633974483)


def test_inexact_domain_errors_are_lisp_errors(ev) -> None:
    from lisp.errors import LispTypeError

    with pytest.raises(LispTypeError, match="log"):
        ev("(log 0)")
    with pytest.raises(LispTypeError, match="asin"):
        ev("(asin 2)")


# --------------------------------------------------------------------------- #
#  A8: cxr, chars, strings, symbols, vectors                                  #
# --------------------------------------------------------------------------- #

def test_all_cxr_compositions(ev) -> None:
    assert ev("(caaar '(((1))))") == 1
    assert ev("(cadar '((1 2) 3))") == 2
    assert ev("(cddar '((1 2 3) 4))") == [3]
    assert ev("(cadddr '(1 2 3 4))") == 4
    assert ev("(cddddr '(1 2 3 4 5))") == [5]
    assert ev("(cdar '((1 . 2) 3))") == 2


def test_string_constructor_and_symbol_equality(ev) -> None:
    assert ev("(string #\\a #\\b #\\c)") == "abc"
    assert ev("(string)") == ""
    assert ev("(symbol=? 'a 'a)") is True
    assert ev("(symbol=? 'a 'b)") is False
    assert ev("(symbol=? 'a 'a 'a)") is True


def test_case_insensitive_char_comparisons(ev) -> None:
    assert ev("(char-ci=? #\\a #\\A)") is True
    assert ev("(char-ci<? #\\a #\\B)") is True
    assert ev("(char-ci>? #\\b #\\A)") is True
    assert ev("(char-ci<=? #\\a #\\A)") is True
    assert ev("(char-ci>=? #\\a #\\A)") is True
    assert to_string(ev("(char-foldcase #\\A)"), write=True) == "#\\a"


def test_digit_value(ev) -> None:
    assert ev("(digit-value #\\0)") == 0
    assert ev("(digit-value #\\7)") == 7
    assert ev("(digit-value #\\a)") is False
    assert ev("(digit-value #\\space)") is False


def test_case_insensitive_string_comparisons(ev) -> None:
    assert ev('(string-ci=? "Ab" "aB")') is True
    assert ev('(string-ci<? "a" "B")') is True
    assert ev('(string-ci>? "b" "A")') is True
    assert ev('(string-ci<=? "a" "A")') is True
    assert ev('(string-ci>=? "a" "A")') is True
    assert ev('(string-foldcase "AbC")') == "abc"


def test_vector_copy_bang_and_overlap(ev) -> None:
    assert (
        to_string(
            ev("(let ((v (vector 1 2 3 4))) (vector-copy! v 1 v 0 3) v)"),
            write=True,
        )
        == "#(1 1 2 3)"
    )
    assert (
        to_string(
            ev("(let ((v (vector 0 0 0))) (vector-copy! v 0 (vector 7 8)) v)"),
            write=True,
        )
        == "#(7 8 0)"
    )
    from lisp.errors import LispTypeError

    with pytest.raises(LispTypeError):
        ev("(vector-copy! (vector 1) 0 (vector 1 2))")


# --------------------------------------------------------------------------- #
#  A8b: mutable strings                                                       #
# --------------------------------------------------------------------------- #

def test_make_string_is_mutable(ev) -> None:
    assert ev("(string? (make-string 2))") is True
    assert ev("(let ((s (make-string 3 #\\a))) (string-set! s 1 #\\b) s)") == "aba"
    assert to_string(ev("(make-string 2 #\\x)"), write=True) == '"xx"'


def test_string_set_on_a_literal_is_an_error(ev) -> None:
    from lisp.errors import LispTypeError

    with pytest.raises(LispTypeError, match="immutable"):
        ev('(string-set! "abc" 0 #\\z)')
    with pytest.raises(LispTypeError, match="immutable"):
        ev('(string-fill! "abc" #\\z)')


def test_string_set_bounds(ev) -> None:
    from lisp.errors import LispTypeError

    with pytest.raises(LispTypeError, match="out of range"):
        ev("(string-set! (make-string 2) 5 #\\z)")


def test_string_fill_and_copy_bang(ev) -> None:
    assert ev("(let ((s (make-string 4 #\\a))) (string-fill! s #\\z 1 3) s)") == "azza"
    assert ev('(let ((s (string-copy "abcd"))) (string-copy! s 1 "XY") s)') == "aXYd"
    assert (
        ev(
            """
            (let ((s (string-copy "abcd")))
              (string-copy! s 1 s 0 3)
              s)
            """
        )
        == "aabc"
    )


def test_string_copy_returns_a_mutable_string(ev) -> None:
    assert ev('(let ((s (string-copy "ab"))) (string-set! s 0 #\\z) s)') == "zb"
    assert ev('(equal? (string-copy "ab") "ab")') is True


# --------------------------------------------------------------------------- #
#  A9: ports and I/O                                                          #
# --------------------------------------------------------------------------- #

def test_read_one_datum_at_a_time(ev) -> None:
    assert (
        ev(
            """
            (let ((p (open-input-string "1 2 (3 4)")))
              (list (read p) (read p) (read p) (eof-object? (read p))))
            """
        )
        == [1, 2, [3, 4], True]
    )


def test_read_error_is_a_read_condition(ev) -> None:
    assert (
        ev(
            """
            (let ((p (open-input-string "(1 2")))
              (guard (e (#t (read-error? e))) (read p)))
            """
        )
        is True
    )


def test_textual_and_binary_port_predicates(ev) -> None:
    assert ev("(textual-port? (open-input-string \"\"))") is True
    assert ev("(binary-port? (open-input-bytevector #u8(1)))") is True
    assert ev("(textual-port? (open-input-bytevector #u8(1)))") is False
    assert ev("(binary-port? (open-input-string \"\"))") is False


def test_port_open_predicates_and_directional_close(ev) -> None:
    assert (
        ev(
            """
            (let ((p (open-output-string)))
              (close-output-port p)
              (output-port-open? p))
            """
        )
        is False
    )
    assert (
        ev(
            """
            (let ((p (open-input-string "")))
              (close-input-port p)
              (input-port-open? p))
            """
        )
        is False
    )


def test_call_with_port_closes_it(ev) -> None:
    assert (
        ev(
            """
            (let ((p (open-output-string)))
              (call-with-port p (lambda (q) (display "hi" q)))
              (output-port-open? p))
            """
        )
        is False
    )


def test_binary_bytevector_port_round_trip(ev) -> None:
    assert (
        to_string(
            ev(
                """
                (let ((p (open-output-bytevector)))
                  (write-u8 65 p)
                  (write-bytevector #u8(66 67) p)
                  (get-output-bytevector p))
                """
            ),
            write=True,
        )
        == "#u8(65 66 67)"
    )


def test_read_u8_peek_and_eof(ev) -> None:
    assert (
        ev(
            """
            (let ((p (open-input-bytevector #u8(1 2))))
              (list (read-u8 p) (peek-u8 p) (read-u8 p) (eof-object? (read-u8 p))))
            """
        )
        == [1, 2, 2, True]
    )


def test_read_bytevector_and_read_bytevector_bang(ev) -> None:
    assert (
        to_string(ev("(read-bytevector 2 (open-input-bytevector #u8(1 2 3)))"), write=True)
        == "#u8(1 2)"
    )
    assert (
        to_string(
            ev(
                """
                (let ((p (open-input-bytevector #u8(1 2 3)))
                      (b (make-bytevector 2)))
                  (list (read-bytevector! b p) b))
                """
            ),
            write=True,
        )
        == "(2 #u8(1 2))"
    )


def test_file_exists_delete_and_file_error(ev, tmp_path) -> None:
    target = tmp_path / "made-by-lisp.txt"
    assert ev(f'(file-exists? "{target}")') is False
    target.write_text("hi", encoding="utf-8")
    assert ev(f'(file-exists? "{target}")') is True
    ev(f'(delete-file "{target}")')
    assert ev(f'(file-exists? "{target}")') is False
    assert (
        ev(
            """
            (guard (e (#t (file-error? e)))
              (delete-file "/no/such/file/anywhere"))
            """
        )
        is True
    )


def test_binary_file_round_trip(ev, tmp_path) -> None:
    target = tmp_path / "bytes.bin"
    ev(
        f"""
        (let ((p (open-binary-output-file "{target}")))
          (write-bytevector #u8(1 2 255) p)
          (close-port p))
        """
    )
    assert (
        to_string(
            ev(
                f"""
                (let ((p (open-binary-input-file "{target}")))
                  (let ((b (read-bytevector 3 p)))
                    (close-port p)
                    b))
                """
            ),
            write=True,
        )
        == "#u8(1 2 255)"
    )


# --------------------------------------------------------------------------- #
#  A10: features, cond-expand, include, eval environments                     #
# --------------------------------------------------------------------------- #

def test_features_are_true_claims_only(ev) -> None:
    names = {str(symbol) for symbol in ev("(features)")}
    assert "lisppy" in names
    assert "ieee-float" in names
    # The interpreter is a subset, so it must not claim full R7RS.
    assert "r7rs" not in names
    import os
    import sys

    if os.name == "posix":
        assert "posix" in names
    if sys.platform.startswith("darwin"):
        assert "darwin" in names
    elif sys.platform.startswith("linux"):
        assert "linux" in names


def test_cond_expand_and_or_not_and_else(ev) -> None:
    assert ev("(cond-expand (lisppy 1) (else 2))") == 1
    assert ev("(cond-expand ((and posix lisppy) 1) (else 2))") in (1, 2)
    assert ev("(cond-expand ((or no-such-feature lisppy) 1) (else 2))") == 1
    assert ev("(cond-expand ((not no-such-feature) 1) (else 2))") == 1
    assert ev("(cond-expand (no-such-feature 1) (else 2))") == 2


def test_cond_expand_library_requirement(ev) -> None:
    assert ev("(cond-expand ((library (scheme base)) 1) (else 2))") == 1
    # (scheme complex) is half-landed (C1), so the feature test answers true;
    # the polar half is still in KNOWN_MISSING — C2 does not change this test.
    assert ev("(cond-expand ((library (scheme complex)) 1) (else 2))") == 1
    assert ev("(cond-expand ((library (no such)) 1) (else 2))") == 2


def test_cond_expand_can_define(ev) -> None:
    ev("(cond-expand (lisppy (define *feature* 7)) (else (define *feature* 0)))")
    assert ev("*feature*") == 7


def test_cond_expand_without_a_match_is_an_error(ev) -> None:
    from lisp.errors import LispSyntaxError

    with pytest.raises(LispSyntaxError, match="no clause matched"):
        ev("(cond-expand (no-such-feature 1))")


def test_include_resolves_relative_to_the_calling_file(env, ev, tmp_path) -> None:
    (tmp_path / "included.scm").write_text("(define *included* 42)\n", encoding="utf-8")
    env.loader.add_search_paths([tmp_path])
    ev('(include "included")')
    assert ev("*included*") == 42


def test_include_ci_folds_case(env, ev, tmp_path) -> None:
    (tmp_path / "ci.scm").write_text("(define Mixed 5)\n", encoding="utf-8")
    env.loader.add_search_paths([tmp_path])
    ev('(include-ci "ci")')
    assert ev("mixed") == 5


def test_include_reports_a_cycle(env, ev, tmp_path) -> None:
    from lisp.errors import LispError

    (tmp_path / "loop.scm").write_text('(include "loop")\n', encoding="utf-8")
    env.loader.add_search_paths([tmp_path])
    with pytest.raises(LispError, match="circular"):
        ev('(include "loop")')


def test_eval_accepts_an_environment(ev) -> None:
    assert ev("(eval '(+ 1 2) (interaction-environment))") == 3
    assert ev("(eval '(+ 1 2) (environment '(scheme base)))") == 3


def test_environment_isolates_definitions(ev) -> None:
    ev("(eval '(define *local* 1) (environment '(scheme base)))")
    from lisp.errors import LispNameError

    with pytest.raises(LispNameError):
        ev("*local*")


def test_environment_rejects_an_unknown_library(ev) -> None:
    from lisp.errors import LispError, LispNameError
    from lisp.types import Complex

    with pytest.raises(LispError, match="no such library"):
        ev("(environment '(scheme no-such))")
    # (scheme complex) is half-landed (C1): the rectangular half imports and
    # works, and the polar half is still honestly absent — C2 finishes it.
    assert ev("(eval '(make-rectangular 1 2) (environment '(scheme complex)))") == Complex(1, 2)
    with pytest.raises(LispNameError, match="magnitude"):
        ev("(eval 'magnitude (environment '(scheme complex)))")


def test_environment_rejects_a_non_library_spec(ev) -> None:
    from lisp.errors import LispTypeError

    with pytest.raises(LispTypeError, match="library name"):
        ev("(environment 3)")


# --------------------------------------------------------------------------- #
#  C1 — the exact complex pair                                                 #
# --------------------------------------------------------------------------- #


def test_the_exact_complex_pair_is_a_tower_citizen(ev) -> None:
    """Rows 1–3 and 12: the pair exists, collapses, and answers honestly."""
    from lisp.types import Complex

    assert ev("(make-rectangular 1 2)") == Complex(1, 2)
    # Row 2: an exact zero imaginary part *is* the real.
    assert ev("(make-rectangular 1 0)") == 1
    assert ev("(make-rectangular 1/2 1/3)") == Complex(Fraction(1, 2), Fraction(1, 3))
    # Row 3: an inexact zero imaginary part stays visible — signed zero is
    # honest, and the value is a plain inexact complex.
    inexact = ev("(make-rectangular 1.0 0.0)")
    assert inexact == complex(1.0, 0.0) and isinstance(inexact, complex)
    assert ev("(exact? (make-rectangular 1 2))") is True
    assert ev("(inexact? (make-rectangular 1 2))") is False
    assert ev("(complex? (make-rectangular 1 2))") is True
    assert ev("(number? (make-rectangular 1 2))") is True
    assert ev("(real? (make-rectangular 1 2))") is False
    assert ev("(rational? (make-rectangular 1 2))") is False
    assert ev("(integer? (make-rectangular 1 2))") is False
    # Row 12's property, on the inexact half:
    assert ev("(real? (make-rectangular 1.0 0.0))") is True
    assert ev("(rational? (make-rectangular 1.0 0.0))") is True


def test_the_rectangular_accessors_keep_their_parts_exact(ev) -> None:
    """Row 5: each part answers with its own exactness."""
    assert ev("(real-part (make-rectangular 1 2))") == 1
    assert ev("(imag-part (make-rectangular 1 2))") == 2
    assert ev("(real-part (make-rectangular 1/2 1/3))") == Fraction(1, 2)
    assert ev("(imag-part (make-rectangular 1/2 1/3))") == Fraction(1, 3)
    assert ev("(imag-part 3)") == 0
    assert ev("(imag-part 3.0)") == 0.0
    assert ev("(exact? (imag-part 3))") is True
    assert ev("(exact? (imag-part 3.0))") is False


def test_exact_complex_arithmetic_is_schoolbook(ev) -> None:
    """Row 9's exact half: the field operations, exactly."""
    from lisp.types import Complex

    assert ev("(+ (make-rectangular 1 2) (make-rectangular 3 4))") == Complex(4, 6)
    assert ev("(- (make-rectangular 1 2))") == Complex(-1, -2)
    assert ev("(- (make-rectangular 1 2) (make-rectangular 3 4))") == Complex(-2, -2)
    assert ev("(* (make-rectangular 1 2) (make-rectangular 3 4))") == Complex(-5, 10)
    assert ev("(/ (make-rectangular 1 2) (make-rectangular 3 4))") == Complex(
        Fraction(11, 25), Fraction(2, 25)
    )
    # Division by an exact real keeps the pair exact.
    assert ev("(/ (make-rectangular 3 4) 2)") == Complex(Fraction(3, 2), 2)
    # A rational numerator over a complex denominator is exact, too.
    assert ev("(/ 1/2 (make-rectangular 1 2))") == Complex(
        Fraction(1, 10), Fraction(-1, 5)
    )
    # Cancellation answers the exact real zero — the collapse is the point.
    assert ev("(+ (make-rectangular 1 2) (make-rectangular -1 -2))") == 0
    assert ev("(square (make-rectangular 1 2))") == Complex(-3, 4)
    assert ev("(expt (make-rectangular 1 2) 2)") == Complex(-3, 4)
    assert ev("(expt (make-rectangular 1 2) -1)") == Complex(
        Fraction(1, 5), Fraction(-2, 5)
    )
    # |3+4i| is exactly 5 — the perfect-square root R4 built.
    assert ev("(abs (make-rectangular 3 4))") == 5
    assert ev("(exact? (abs (make-rectangular 3 4)))") is True
    assert ev("(exact? (abs (make-rectangular 1 1)))") is False


def test_inexact_contagion_reaches_the_complex_pair(ev) -> None:
    """Row 9's inexact half: any float contaminates the whole, everywhere."""
    from lisp.types import Complex

    result = ev("(+ (make-rectangular 1 2) 0.5)")
    assert result == complex(1.5, 2.0) and isinstance(result, complex)
    assert ev("(exact? (+ (make-rectangular 1 2) 0.5))") is False
    assert ev("(* (make-rectangular 1 2) 0.5)") == complex(0.5, 1.0)
    assert ev("(/ (make-rectangular 1 2) 0.5)") == complex(2.0, 4.0)
    assert ev("(- (make-rectangular 1 2) 1.0)") == complex(0.0, 2.0)
    # A rational next to an inexact complex goes through its float image…
    assert ev("(/ 1/2 (make-rectangular 1.0 2.0))") == complex(0.1, -0.2)
    # …but exact over exact stays exact (row 9's first rule).
    assert ev("(/ 1/2 (make-rectangular 1 2))") == Complex(
        Fraction(1, 10), Fraction(-1, 5)
    )
    # Row 2 does not extend to the inexact half:
    assert ev("(exact? (make-rectangular 1.0 0.0))") is False


def test_complex_values_print_as_r7rs_text(ev) -> None:
    """Row 13's printing half; the reader round-trip is C3's pin."""
    assert ev("(number->string (make-rectangular 1 2))") == "1+2i"
    assert ev("(number->string (make-rectangular 1 -2))") == "1-2i"
    assert ev("(number->string (make-rectangular 0 1))") == "0+i"
    assert ev("(number->string (make-rectangular 0 -1))") == "0-i"
    assert ev("(number->string (make-rectangular 1/2 1/3))") == "1/2+1/3i"
    assert ev("(number->string (make-rectangular 1.0 0.0))") == "1.0+0.0i"
    assert ev("(number->string (make-rectangular 1.0 -0.0))") == "1.0-0.0i"


def test_eqv_and_equal_distinguish_complex_exactness(ev) -> None:
    """Row 11: exactness distinguishes, value equality does not."""
    assert ev("(eqv? (make-rectangular 1 2) (make-rectangular 1 2))") is True
    assert ev("(equal? (make-rectangular 1 2) (make-rectangular 1 2))") is True
    assert ev("(eqv? (make-rectangular 1 2) (+ (make-rectangular 1 2) 0.0))") is False
    # The same rule that separates 1 from 1.0:
    assert ev("(= (make-rectangular 1 2) (+ (make-rectangular 1 2) 0.0))") is True
    assert ev("(= 1/2 (make-rectangular 0.5 0))") is True  # exact collapse


def test_the_real_only_family_refuses_complex_loudly(ev) -> None:
    """Row 10: the error stays; the reason changes to a Lisp error."""
    from lisp.errors import LispError

    for src in (
        "(floor (make-rectangular 1 2))",
        "(ceiling (make-rectangular 1 2))",
        "(truncate (make-rectangular 1 2))",
        "(round (make-rectangular 1 2))",
        "(quotient (make-rectangular 1 2) 2)",
        "(remainder (make-rectangular 1 2) 2)",
        "(modulo (make-rectangular 1 2) 2)",
        "(floor-quotient (make-rectangular 1 2) 2)",
        "(gcd (make-rectangular 1 2) 3)",
        "(lcm (make-rectangular 1 2) 3)",
        "(min (make-rectangular 1 2) 3)",
        "(max (make-rectangular 1 2) 3)",
        "(< (make-rectangular 1 2) 3)",
        "(> (make-rectangular 1 2) 3)",
        "(numerator (make-rectangular 1 2))",
        "(denominator (make-rectangular 1 2))",
        "(rationalize (make-rectangular 1 2) 1)",
        "(sqrt (make-rectangular 1 2))",
        "(sin (make-rectangular 1 2))",
        "(log (make-rectangular 1 2))",
        "(make-rectangular (make-rectangular 1 2) 3)",
    ):
        with pytest.raises(LispError):
            ev(src)


def test_exact_and_inexact_convert_complex_honestly(ev) -> None:
    """The corners: exactness conversions round-trip through the pair."""
    from lisp.errors import LispError
    from lisp.types import Complex

    assert ev("(inexact (make-rectangular 1 2))") == complex(1.0, 2.0)
    assert ev("(exact (inexact (make-rectangular 1 2)))") == Complex(1, 2)
    # Row 2 again: the exact image of 1.0+0.0i collapses to the real 1.
    assert ev("(exact (make-rectangular 1.0 0.0))") == 1
    with pytest.raises(LispError):
        # An infinity has no exact equal, in either component.
        ev("(exact (make-rectangular +inf.0 0.0))")


def test_inexact_complex_zero_division_stays_ieee(ev) -> None:
    """Row 1's other half, extended to the complex plane."""
    from lisp.errors import LispError

    # The pure-real answers are unchanged from R1:
    assert ev("(/ 1.0 0.0)") == float("inf")
    assert ev("(/ -1.0 0.0)") == float("-inf")
    assert ev("(/ 0.0 0.0)") != ev("(/ 0.0 0.0)")  # NaN is not itself
    # A complex zero divisor answers component-wise (Annex G):
    result = ev("(/ (make-rectangular 1.0 2.0) (make-rectangular 0.0 0.0))")
    assert result == complex(float("inf"), float("inf"))
    zero_numerator = ev("(/ (make-rectangular 0.0 0.0) (make-rectangular 0.0 0.0))")
    assert zero_numerator != zero_numerator  # NaN in both components
    # An exact zero divisor is still an error, full stop:
    with pytest.raises(LispError):
        ev("(/ (make-rectangular 1 2) 0)")


def test_finite_infinite_and_nan_reach_the_complex_plane(ev) -> None:
    """The inexact library's predicates see both components."""
    assert ev("(finite? (make-rectangular 1 2))") is True
    assert ev("(finite? (make-rectangular 1.0 2.0))") is True
    assert ev("(infinite? (make-rectangular 1 2))") is False
    assert ev("(nan? (make-rectangular 1 2))") is False
    assert ev("(finite? (make-rectangular +inf.0 0.0))") is False
    assert ev("(infinite? (make-rectangular +inf.0 0.0))") is True
    assert ev("(nan? (make-rectangular +nan.0 0.0))") is True


def test_complex_values_hash_across_the_exactness_boundary(ev) -> None:
    """The same promise hash(1) == hash(1.0) makes, one dimension up."""
    from lisp.types import Complex

    assert hash(Complex(1, 2)) == hash(complex(1.0, 2.0))
    # And through the host bridge: an equal?-keyed table finds the value.
    ev("(define *h* (make-hash-table)) "
       "(hash-table-set! *h* (make-rectangular 1 2) 'ok)")
    assert ev("(hash-table-ref *h* (make-rectangular 1 2))") == Symbol("ok")

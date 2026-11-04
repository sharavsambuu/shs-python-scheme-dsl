"""Regression tests for a conformance review of the R7RS-small surface.

The tests keep the ``T01``-style tags they were filed under, so a commit from
this era can be matched to the test that closed each gap; the numbers are only
an index, and what each test pins is in its own comment. The rule is the
repository's own: a behaviour the docs claim, or a malformed input that must
fail *loudly*, gets a test.
"""
from __future__ import annotations

from fractions import Fraction

import pytest

from shslisp.errors import LispNameError, LispSyntaxError, ReadError
from shslisp.printer import to_string
from shslisp.reader import read_one
from shslisp.types import Vector, intern, intern_keyword, is_keyword, is_symbol


# --------------------------------------------------------------------------- #
#  P0 — malformed forms must never leak host exceptions                        #
# --------------------------------------------------------------------------- #

def test_t01_empty_binding_lists_are_valid(ev) -> None:
    # R7RS allows a binding list of zero entries in every binding form.
    assert ev("(let () 0)") == 0
    assert ev("(let* () 1)") == 1
    assert ev("(letrec () 2)") == 2
    assert ev("(letrec* () 3)") == 3


@pytest.mark.parametrize(
    "source",
    [
        "(let ((x)) x)",
        "(let loop ((x)) x)",
        "(let ((x 1 2)) x)",
        "(let* ((x)) x)",
        "(let* ((x 1 2)) x)",
        "(letrec ((x)) x)",
        "(letrec ((x 1 2)) x)",
        "(let ((1 2)) 1)",
        "(let ((x 1) . y) x)",
    ],
)
def test_t02_malformed_bindings_raise_a_syntax_error(ev, source: str) -> None:
    # A missing initializer, an extra form, a non-symbol name, or a dotted
    # binding list used to raise IndexError or silently drop data.
    with pytest.raises(LispSyntaxError):
        ev(source)


@pytest.mark.parametrize("source", ["(lambda)", "(lambda (x))"])
def test_t03_lambda_needs_a_body(ev, source: str) -> None:
    with pytest.raises(LispSyntaxError):
        ev(source)


@pytest.mark.parametrize(
    "source",
    [
        "(begin . 1)",
        "(and . 1)",
        "(or . 1)",
        "(when 1 . 2)",
        "(if #t 1 . 2)",
    ],
)
def test_t04_improper_forms_are_syntax_errors(ev, source: str) -> None:
    # A dotted form is not code; treating it as self-evaluating data turned a
    # typo into a value.
    with pytest.raises(LispSyntaxError):
        ev(source)


def test_t05_read_ignores_parens_inside_strings(ev) -> None:
    # ``_balanced_end`` must treat a string as one datum, or ``read`` splits
    # the stream in the middle of it.
    source = r'''
    (let ((p (open-input-string "(display \"h)\") (2)")))
      (list (read p) (read p)))
    '''
    assert ev(source) == [[intern("display"), "h)"], [2]]


def test_t05_read_skips_datum_comments_when_balancing(ev) -> None:
    # ``#;`` hides a datum whose parens must not count toward the balance.
    source = '(let ((p (open-input-string "1 #;(2 3) 4"))) (list (read p) (read p)))'
    assert ev(source) == [1, 4]


def test_t05_a_stream_starting_with_a_dispatch_form_is_not_truncated(ev) -> None:
    # ``read`` grows its buffer until the text is one complete datum. A lone
    # ``#`` must not lex as the symbol ``#``, or every ``#;``, ``#|`` or ``#(``
    # at the *start* of a stream is consumed as ``#`` after one character —
    # the mid-stream case above is only the visible half of the bug.
    assert ev('(read (open-input-string "#|c|# 1"))') == 1
    assert ev('(read (open-input-string "#;1 2"))') == 2
    assert ev('(read (open-input-string "#(1 2)"))') == Vector([1, 2])


def test_t05_a_lone_hash_is_never_a_symbol(ev) -> None:
    # R7RS §7.1.1: ``#`` is not an <initial>, so no identifier begins with it.
    # At the end of the text it is an *incomplete* dispatch (a stream reader
    # must pull more characters); with text after it and no dispatch body it is
    # malformed. Either way it is never the symbol ``(intern "#")``.
    with pytest.raises(LispSyntaxError):
        read_one("#")
    with pytest.raises(LispSyntaxError):
        ev('(read-from-string "#")')
    with pytest.raises(ReadError):
        ev('(read (open-input-string "#"))')
    # The quoted spelling still names the symbol, so nothing is lost.
    assert read_one("|#|") is intern("#")


def test_t05_a_stream_starting_with_a_directive_is_not_truncated(ev) -> None:
    # The same shape of bug, one prefix over: ``#!fold-case`` is longer than
    # ``#!``, so a buffer that stops at ``#!`` must be grown, not read as a
    # symbol. ``read`` steps over the directive and returns the datum after it;
    # a whole source *does* apply the fold (see ``Reader._skip_noise``).
    assert ev('(read (open-input-string "#!fold-case 1"))') == 1
    assert ev('(read (open-input-string "#!no-fold-case 2"))') == 2
    assert ev("#!fold-case (eq? 'A 'a)") is True


# --------------------------------------------------------------------------- #
#  P1 — reader/numeric/equality conformance                                    #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "source, value",
    [
        ("#i#x10", 16.0),
        ("#x#i10", 16.0),
        ("#i#b101", 5.0),
        ("#i#o10", 8.0),
    ],
)
def test_t06_inexact_prefix_applies_to_radix_literals(ev, source: str, value: float) -> None:
    result = ev(source)
    assert result == value
    assert type(result) is float


def test_t07_read_string_reads_characters(ev) -> None:
    # R7RS ``read-string k [port]`` reads up to k characters, not a datum.
    assert (
        ev(
            '(let ((p (open-input-string "abcdef")))'
            "  (list (read-string 3 p) (read-string 3 p)"
            "        (eof-object? (read-string 1 p))))"
        )
        == ["abc", "def", True]
    )
    assert ev('(read-string 3 (open-input-string "ab"))') == "ab"
    assert ev('(read-string 0 (open-input-string "ab"))') == ""
    assert ev("(eof-object? (read-string 3 (open-input-string \"\")))") is True


def test_t07_read_from_string_parses_a_datum(ev) -> None:
    # The old (non-R7RS) behaviour survives under its own name.
    assert ev('(read-from-string "(a b)")') == [intern("a"), intern("b")]
    assert ev('(read-from-string "1 2")') == 1


def test_t08_equal_distinguishes_exactness(ev) -> None:
    assert ev("(equal? 1 1.0)") is False
    assert ev("(equal? 1/2 0.5)") is False
    assert ev("(equal? 1 1)") is True
    assert ev("(equal? 1.0 1.0)") is True
    assert ev("(equal? 1/2 1/2)") is True


def test_t09_case_memv_and_assv_use_eqv(ev) -> None:
    assert ev("(case 1 ((1.0) 'yes) (else 'no))") == intern("no")
    assert ev("(case 1.0 ((1) 'no) ((1.0) 'yes) (else 'other))") == intern("yes")
    assert ev("(memv 1 '(1.0))") is False
    assert ev("(memv 1 '(1))") == [1]
    assert ev("(assv 1 '((1.0 . x)))") is False
    assert ev("(cdr (assv 1 '((1 . x))))") == intern("x")


def test_t09_hash_tables_key_on_equal_question(ev) -> None:
    # ``equal?`` distinguishes 1 from 1.0, so the hash key must too.
    assert (
        ev(
            "(let ((h (make-hash-table)))"
            "  (hash-table-set! h 1 'exact)"
            "  (hash-table-ref/default h 1.0 'missing))"
        )
        == intern("missing")
    )
    assert (
        ev(
            "(let ((h (make-hash-table)))"
            "  (hash-table-set! h 1 'exact)"
            "  (hash-table-ref h 1))"
        )
        == intern("exact")
    )


def test_t10_symbols_ending_in_colon_are_quoted(ev) -> None:
    symbol = intern("a:")
    written = to_string(symbol, write=True)
    assert written == "|a:|"
    assert read_one(written) is symbol
    assert is_symbol(read_one(written))


@pytest.mark.parametrize("name", ["host", "a b", "a:", "123", ""])
def test_t10_keywords_round_trip_through_write_read(name: str) -> None:
    keyword = intern_keyword(name)
    written = to_string(keyword, write=True)
    assert read_one(written) is keyword
    assert is_keyword(read_one(written))


def test_t11_syntax_rules_cache_returns_fresh_quoted_data(ev) -> None:
    # Two identical uses must not share the same mutable quoted list.
    assert ev(
        """
        (define-syntax m (syntax-rules () ((_) (quote (1 2)))))
        (define a (m))
        (define b (m))
        (list (eq? a b) (begin (set-car! a 9) b))
        """
    ) == [False, [1, 2]]


# --------------------------------------------------------------------------- #
#  P2 — documented deviations (characterisation tests, not endorsements)        #
# --------------------------------------------------------------------------- #

def test_t12_let_syntax_hides_a_sibling(ev) -> None:
    # R7RS: let-syntax bindings are not recursive, so a template's ``b`` is not
    # the sibling — it is whatever ``b`` means where the macro was defined,
    # which here is nothing at all. (Before T12 this silently found the sibling
    # at the use site.)
    with pytest.raises(LispNameError):
        ev(
            """
            (let-syntax
                ((a (syntax-rules () ((_ x) (b x))))
                 (b (syntax-rules () ((_ x) 2))))
              (a 1))
            """
        )


def test_t12_letrec_syntax_sibling_is_visible(ev) -> None:
    # The recursive form is the one that puts the siblings in scope.
    assert (
        ev(
            """
            (letrec-syntax
                ((a (syntax-rules () ((_ x) (b x))))
                 (b (syntax-rules () ((_ x) 2))))
              (a 1))
            """
        )
        == 2
    )


def test_t12_a_caller_frame_cannot_capture_a_free_identifier(ev) -> None:
    # The template's ``helper`` is the definition site's; a caller's local of
    # the same name is invisible to it.
    assert (
        ev(
            """
            (define (helper n) (* n 2))
            (define-syntax cap (syntax-rules () ((_ v) (helper v))))
            (let ((helper (lambda (n) 999))) (cap 3))
            """
        )
        == 6
    )


def test_t12_a_later_top_level_definition_still_answers(ev) -> None:
    # Late binding survives: a macro may name a helper defined after it, which
    # is why the fix pins the definition site rather than rejecting the name.
    assert (
        ev(
            """
            (define-syntax fwd (syntax-rules () ((_ v) (later v))))
            (define (later v) (* v 10))
            (fwd 4)
            """
        )
        == 40
    )


def test_t12_a_self_recursive_macro_still_finds_itself(ev) -> None:
    # A template that names its own macro is the case that a strict "unbound is
    # an error" rule would break; the definition-site pin resolves it.
    assert (
        ev(
            """
            (define-syntax nest
              (syntax-rules ()
                ((_ ()) 0)
                ((_ (a rest ...)) (+ a (nest (rest ...))))))
            (nest (1 2 3))
            """
        )
        == 6
    )


def test_t12_quoted_data_in_a_template_is_not_renamed(ev) -> None:
    # Quoted data is data: ``'x`` must still be the symbol ``x``, and a quoted
    # list must not sprout hygiene aliases.
    assert (
        ev(
            """
            (define-syntax m (syntax-rules () ((_) 'x)))
            (m)
            """
        )
        is intern("x")
    )
    assert (
        to_string(
            ev(
                """
                (define-syntax q (syntax-rules () ((_ v) `(list ,v))))
                (q 1)
                """
            ),
            write=True,
        )
        == "(list 1)"
    )
# --------------------------------------------------------------------------- #
#  P3 — the literal grammar, and a directive that outlives its datum           #
# --------------------------------------------------------------------------- #

def test_t13_a_ratio_keeps_its_radix(ev) -> None:
    # ``<ureal R>`` is ``<uinteger R> / <uinteger R>``, so the radix applies to
    # both halves and a whole result is an integer again (row 18 reversed).
    assert ev("#x1/2") == Fraction(1, 2)
    assert type(ev("#x1/2")) is Fraction
    assert ev("#x1/2") == 0.5  # equal in value, different exactness
    assert ev("#i#x1/2") == 0.5
    assert type(ev("#i#x1/2")) is float
    assert ev("#x2/2") == 1
    assert ev("#b11/10") == Fraction(3, 2)
    with pytest.raises(LispSyntaxError):
        ev("#x1/0")
    # A radix *decimal* is not in the report: ``<decimal 10>`` fixes the radix
    # at ten, so this stays a bad literal rather than being guessed at.
    with pytest.raises(LispSyntaxError):
        ev("#x1.8")


@pytest.mark.parametrize(
    "source", ["#i#e10", "#e#i10", "#x#x10", "#d#b10", "#e#e#x10", "#x#e#x10"]
)
def test_t14_one_radix_and_one_exactness_prefix(ev, source: str) -> None:
    # ``<prefix R>`` is one radix and one exactness, in either order. A second
    # of either is a malformed literal, not a last-one-wins.
    with pytest.raises(LispSyntaxError):
        ev(source)


def test_t14_either_order_still_works(ev) -> None:
    assert ev("#e#x10") == 16
    assert ev("#x#e10") == 16
    assert ev("#i#x10") == 16.0
    assert type(ev("#i#x10")) is float


def test_t15_a_port_carries_a_case_directive(ev) -> None:
    # A ``#!`` directive outlives the datum it precedes, exactly as it does in
    # a file, so a stream reader applies it to every later datum too.
    source = '(let ((p (open-input-string "#!fold-case A B"))) (list (read p) (read p)))'
    assert ev(source) == [intern("a"), intern("b")]


def test_t15_no_fold_case_cancels_it(ev) -> None:
    source = (
        '(let ((p (open-input-string "#!fold-case A #!no-fold-case B")))'
        "  (list (read p) (read p)))"
    )
    assert ev(source) == [intern("a"), intern("B")]


def test_t15_the_folded_datum_is_what_read_returns(ev) -> None:
    # The datum after the directive is folded, so the identifiers inside it are
    # lower-cased — not the directive's own name, which must never leak.
    assert ev('(read (open-input-string "#!fold-case (EQ? 1 1)"))') == [
        intern("eq?"),
        1,
        1,
    ]
    assert ev('(read (open-input-string "A"))') == intern("A")

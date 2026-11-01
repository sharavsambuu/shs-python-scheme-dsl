"""The reader: text in, forms out."""
from __future__ import annotations

import pytest

from lisp.errors import LispSyntaxError
from lisp.printer import to_string
from lisp.reader import read_all, read_one
from lisp.types import NIL, Char, Pair, Vector, intern, is_nil, is_symbol


def test_reads_numbers() -> None:
    assert read_one("42") == 42
    assert read_one("-7") == -7
    assert read_one("3.5") == 3.5
    assert isinstance(read_one("42"), int)


def test_reads_symbols() -> None:
    value = read_one("piece-locked")
    assert is_symbol(value)
    assert value == "piece-locked"
    assert value is intern("piece-locked")  # symbols are interned


def test_reads_booleans_and_nil() -> None:
    assert read_one("#t") is True
    assert read_one("#f") is False
    assert read_one("()") is NIL
    assert is_nil(read_one("()"))


def test_reads_strings_with_escapes() -> None:
    assert read_one('"hello"') == "hello"
    assert read_one('"a\\nb"') == "a\nb"
    assert read_one('"quote: \\""') == 'quote: "'


def test_reads_nested_lists() -> None:
    assert read_one("(a (b c) 1)") == [intern("a"), [intern("b"), intern("c")], 1]


def test_reads_multiple_forms() -> None:
    assert read_all("1 2 (3 4)") == [1, 2, [3, 4]]


def test_quote_sugar_expands() -> None:
    assert read_one("'x") == [intern("quote"), intern("x")]
    assert read_one("`x") == [intern("quasiquote"), intern("x")]
    assert read_one(",x") == [intern("unquote"), intern("x")]
    assert read_one(",@x") == [intern("unquote-splicing"), intern("x")]


def test_comments_are_skipped() -> None:
    assert read_all("; a comment\n42 ; trailing\n") == [42]


def test_parentheses_inside_strings_are_not_read() -> None:
    assert read_one('"(not a list)"') == "(not a list)"


def test_dotted_parameter_list_reads_as_a_pair() -> None:
    # ``(a b . rest)`` is a real dotted pair chain: ``a . (b . rest)``.
    form = read_one("(a b . rest)")
    assert isinstance(form, Pair)
    assert form.car == intern("a")
    assert form.cdr.car == intern("b")
    assert form.cdr.cdr == intern("rest")
    assert to_string(form, write=True) == "(a b . rest)"


def test_dotted_data_round_trips() -> None:
    # No more silent lie: a dotted datum prints back as itself and re-reads.
    form = read_one("'(1 2 . 3)")
    assert to_string(form, write=True) == "(quote (1 2 . 3))"
    assert to_string(read_one(to_string(form, write=True)), write=True) == (
        "(quote (1 2 . 3))"
    )


def test_reads_characters() -> None:
    assert read_one("#\\a") == Char("a")
    assert read_one("#\\space") == Char(" ")
    assert read_one("#\\newline") == Char("\n")
    assert read_one("#\\x41") == Char("A")
    assert to_string(read_one("#\\tab"), write=True) == "#\\tab"


def test_reads_vectors() -> None:
    v = read_one("#(1 #\\a \"s\")")
    assert isinstance(v, Vector)
    assert v.items[0] == 1 and v.items[1] == Char("a") and v.items[2] == "s"
    assert to_string(v, write=True) == '#(1 #\\a "s")'


def test_datum_and_block_comments() -> None:
    assert read_all("(1 #;2 3)") == [[1, 3]]
    assert read_one("#| a #| nested |# b |# 42") == 42
    assert read_all("1 #;2 3") == [1, 3]


def test_number_prefixes() -> None:
    assert read_one("#x1f") == 31
    assert read_one("#b1010") == 10
    assert read_one("#o17") == 15


def test_unbalanced_open_paren_raises() -> None:
    with pytest.raises(LispSyntaxError):
        read_one("(a b")


def test_stray_close_paren_raises() -> None:
    with pytest.raises(LispSyntaxError):
        read_one(")")


def test_read_one_rejects_trailing_data() -> None:
    with pytest.raises(LispSyntaxError):
        read_one("1 2")


def test_unterminated_string_raises() -> None:
    with pytest.raises(LispSyntaxError):
        read_one('"oops')


def test_printer_round_trips() -> None:
    source = '(define (f x) (list x "s" 1.5 #t))'
    assert to_string(read_one(source), write=True) == source


def test_quote_sugar_expands_on_read() -> None:
    # The reader expands 'x before the printer ever sees it — code becomes data.
    assert to_string(read_one("'x"), write=True) == "(quote x)"

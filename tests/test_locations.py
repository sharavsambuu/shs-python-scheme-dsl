"""H9: source locations — line/column through the reader and errors.

The reader now tracks offsets (``tokenize_located``) and returns
``SourceLocation`` alongside forms (``read_all_located`` / ``read_one_located``).
Syntax errors carry the location of the token that failed. Full datum-span
tracking is still ahead (this is the form-start location, not a span), but
an IDE can already point at the offending form.
"""
from __future__ import annotations

import pytest

from shslisp.errors import LispSyntaxError, SourceLocation
from shslisp.reader import read_all_located, read_one_located


def test_located_form_starts_on_first_line():
    pairs = read_all_located("(+ 1 2)", file="test.scm")
    assert len(pairs) == 1
    form, loc = pairs[0]
    assert loc == SourceLocation(file="test.scm", line=1, col=1)


def test_located_multiline():
    # "(\n  + 1)"
    pairs = read_all_located("(\n  + 1)", file="multi.scm")
    assert len(pairs) == 1
    form, loc = pairs[0]
    # First token "(" is line 1 col 1
    assert loc.line == 1 and loc.col == 1
    # Second form starts on line 2 if present
    two = read_all_located("(+ 1)\n(+ 2)", file="multi.scm")
    assert two[0][1].line == 1
    assert two[1][1].line == 2
    assert two[1][1].col == 1


def test_located_second_form_line_col():
    # form on line 2 indented by two spaces
    pairs = read_all_located("(define x 1)\n  (define y 2)", file="f.scm")
    assert pairs[0][1].line == 1
    assert pairs[1][1].line == 2
    assert pairs[1][1].col == 3  # two spaces then "("


def test_read_one_located():
    form, loc = read_one_located("  42", file="one.scm")
    assert form == 42
    assert loc.line == 1 and loc.col == 3


def test_syntax_error_carries_location():
    with pytest.raises(LispSyntaxError) as excinfo:
        read_all_located("(define x 1)\n  )", file="bad.scm")
    err = excinfo.value
    assert err.source is not None
    assert err.source.line == 2
    assert err.source.file == "bad.scm"
    # Message includes the location (LispError prefixes it)
    assert "bad.scm:2:" in str(err)


def test_default_file_is_string():
    pairs = read_all_located("42")
    assert pairs[0][1].file == "<string>"

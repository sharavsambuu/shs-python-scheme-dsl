"""Locked Frontier TDD suite for Wave 3: S14 (SRFI 125), S15 (132), S16 (64), S17 (180), S18 (28+152)."""
from __future__ import annotations

import pytest

from shslisp import make_env, run
from shslisp.errors import LispError


def test_s14_srfi_125_hash_tables() -> None:
    env = make_env(profile="r7rs")
    run("(import (srfi 125))", env)
    assert run(
        "(let ((ht (make-hash-table))) "
        "  (hash-table-set! ht 'a 10) "
        "  (hash-table-set! ht 'b 20) "
        "  (list (hash-table? ht) "
        "        (hash-table-ref ht 'a) "
        "        (hash-table-ref/default ht 'missing -1) "
        "        (hash-table-contains? ht 'b) "
        "        (hash-table-size ht)))",
        env,
    ) == [True, 10, -1, True, 2]

    run("(let ((ht (alist->hash-table '((x . 1) (y . 2))))) (hash-table-delete! ht 'x) (hash-table-size ht))", env)
    with pytest.raises(LispError):
        run("(hash-table-ref (make-hash-table) 'missing)", env)


def test_s15_srfi_132_sorting() -> None:
    env = make_env(profile="r7rs")
    run("(import (srfi 132))", env)
    assert run("(list-sort < '(3 1 4 1 5 9 2))", env) == [1, 1, 2, 3, 4, 5, 9]
    assert run("(list-sorted? < '(1 2 3))", env) is True
    assert run("(list-sorted? < '(3 1 2))", env) is False
    assert run("(vector->list (vector-sort > #(3 1 4 2)))", env) == [4, 3, 2, 1]
    assert run("(vector-sorted? < #(1 2 3))", env) is True


def test_s16_srfi_64_testing() -> None:
    env = make_env(profile="r7rs")
    run("(import (srfi 64))", env)
    res = run(
        "(begin "
        "  (test-begin \"s16-demo\") "
        "  (test-equal 4 (+ 2 2)) "
        "  (test-assert (= 3 3)) "
        "  (test-error (car 1)) "
        "  (test-end \"s16-demo\"))",
        env,
    )
    assert res is not None


def test_s17_srfi_180_json() -> None:
    env = make_env(profile="r7rs")
    run("(import (srfi 180))", env)
    encoded = run("(json-write '((symbol . \"XAUUSD\") (ok . #t) (n . 3)))", env)
    assert '"XAUUSD"' in encoded
    decoded = run('(json-read "{\\"a\\": 1, \\"b\\": [2, 3], \\"c\\": null}")', env)
    assert decoded is not None
    assert run('(cdr (assoc "a" (json-read "{\\"a\\": 42}")))', env) == 42


def test_s18_srfi_28_format_and_srfi_152_strings() -> None:
    env = make_env(profile="r7rs")
    run("(import (srfi 28) (srfi 152))", env)
    assert run('(format #f "sym=~a n=~s" "XAUUSD" 7)', env) == 'sym=XAUUSD n=7'
    assert run('(string-split "a,b,c" ",")', env) == ["a", "b", "c"]
    assert run('(string-join \'("a" "b" "c") "-")', env) == "a-b-c"
    assert run('(string-contains "hello world" "world")', env) is not False
    assert run('(string-trim "  hi  ")', env) == "hi"

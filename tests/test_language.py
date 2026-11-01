"""The rest of the language: pairs, chars, vectors, tables, conditions,
multiple values, continuations, and hygienic macros.

These are the features that turn a "small Lisp" into a *full* one. Each group
is small on its own; together they are the difference between driving the game
and being a language.
"""
from __future__ import annotations

import pytest

from lisp.errors import (
    LispError,
    LispRecursionError,
    LispSyntaxError,
    LispTypeError,
)
from lisp.printer import to_string
from lisp.reader import read_one
from lisp.types import NIL, Char, Pair, Vector, intern, is_nil, is_symbol


# --------------------------------------------------------------------------- #
#  The stack budget                                                            #
# --------------------------------------------------------------------------- #

def test_non_tail_recursion_goes_deep(ev) -> None:
    """The ceiling is a promise: a real recursive program fits under it.

    Twenty thousand (the old limit) is less than a list of a hundred thousand
    elements; a million is more stack than an ordinary program will use.
    """
    ev("(define (s n) (if (= n 0) 0 (+ n (s (- n 1)))))")
    assert ev("(s 5000)") == 12502500
    assert ev("(s 100000)") == 5000050000


def test_the_ceiling_is_still_a_clean_lisp_error(ev, monkeypatch) -> None:
    """Over the limit is a Lisp error, never the host's — at any ceiling.

    Lowering ``DEPTH_LIMIT`` keeps the test instant; the check itself is the
    same code path a million-deep runaway takes.
    """
    from lisp import evaluator

    monkeypatch.setattr(evaluator, "DEPTH_LIMIT", 500)
    ev("(define (s n) (if (= n 0) 0 (+ n (s (- n 1)))))")
    assert ev("(s 400)") == 80200
    with pytest.raises(LispRecursionError):
        ev("(s 1000)")


def test_tail_recursion_is_unbounded_in_depth_only(ev, monkeypatch) -> None:
    # Tail recursion never costs depth, so an *endless* one is not the stack
    # budget's business: its only ceiling is the step budget (a clean Lisp
    # error, tested in test_recursion.py). With the step budget raised, a
    # two-million-iteration loop completes — nothing about depth was ever
    # the thing that stopped it.
    monkeypatch.setattr("lisp.evaluator.STEPS_BUDGET", 100_000_000)
    assert ev("(let loop ((i 0)) (if (= i 2000000) i (loop (+ i 1))))") == 2000000


def test_a_budget_change_resizes_the_host_stack(ev, monkeypatch) -> None:
    """Lowering the budget and raising it again must not leave the host small.

    The host limit used to be sized *once*, from whatever ``DEPTH_LIMIT``
    happened to be when the first form was evaluated; a test (or an embedder)
    that tuned the budget then got a perfectly legal recursion killed with
    "the host stack ran out".
    """
    from lisp import evaluator

    monkeypatch.setattr(evaluator, "DEPTH_LIMIT", 500)
    ev("(define (s n) (if (= n 0) 0 (+ n (s (- n 1)))))")
    with pytest.raises(LispRecursionError):
        ev("(s 1000)")
    monkeypatch.undo()
    assert ev("(s 50000)") == 1250025000


# --------------------------------------------------------------------------- #
#  Improper pairs                                                              #
# --------------------------------------------------------------------------- #

def test_cons_builds_proper_lists_or_pairs(ev) -> None:
    assert ev("(cons 1 '())") == [1]
    assert ev("(cons 1 (list 2 3))") == [1, 2, 3]
    pair = ev("(cons 1 2)")
    assert isinstance(pair, Pair) and pair.car == 1 and pair.cdr == 2


def test_car_cdr_accept_pairs(ev) -> None:
    assert ev("(car (cons 1 2))") == 1
    assert ev("(cdr (cons 1 2))") == 2
    assert isinstance(ev("(cdr (cons 1 2))"), int)


def test_pair_and_list_predicates(ev) -> None:
    assert ev("(pair? (cons 1 2))") is True
    assert ev("(pair? (list 1))") is True
    assert ev("(pair? '())") is False
    assert ev("(list? (cons 1 2))") is False
    assert ev("(list? (list 1 2))") is True


def test_dotted_pair_prints_and_reads(ev) -> None:
    assert to_string(ev("(cons 1 (cons 2 3))"), write=True) == "(1 2 . 3)"


def test_append_allows_an_improper_tail(ev) -> None:
    assert ev("(append (list 1 2) 3)") == Pair(1, Pair(2, 3))
    assert ev("(append (list 1) (list 2) (list 3))") == [1, 2, 3]


def test_length_refuses_an_improper_list(ev) -> None:
    with pytest.raises(LispError):
        ev("(length (cons 1 2))")


def test_list_tail(ev) -> None:
    assert ev("(list-tail (list 1 2 3 4) 2)") == [3, 4]
    assert ev("(list-tail (cons 1 2) 1)") == 2


def test_make_list(ev) -> None:
    assert ev("(make-list 3 'x)") == [intern("x"), intern("x"), intern("x")]


def test_dotted_rest_parameter(ev) -> None:
    ev("(define (f a . rest) rest)")
    assert ev("(f 1 2 3)") == [2, 3]
    assert is_nil(ev("(f 1)"))
    ev("(define (all . args) args)")
    assert ev("(all 1 2 3)") == [1, 2, 3]


# --------------------------------------------------------------------------- #
#  Characters                                                                  #
# --------------------------------------------------------------------------- #

def test_char_type_and_conversions(ev) -> None:
    assert ev("#\\a") == Char("a")
    assert ev("(char? #\\a)") is True
    assert ev("(char? \"a\")") is False
    assert ev("(char->integer #\\A)") == 65
    assert ev("(integer->char 97)") == Char("a")


def test_char_comparison_and_predicates(ev) -> None:
    assert ev("(char<? #\\a #\\b)") is True
    assert ev("(char=? #\\a #\\a)") is True
    assert ev("(char>=? #\\b #\\a)") is True
    assert ev("(char-alphabetic? #\\a)") is True
    assert ev("(char-numeric? #\\7)") is True
    assert ev("(char-whitespace? #\\space)") is True
    assert ev("(char-upcase #\\a)") == Char("A")


def test_chars_are_interned(ev) -> None:
    assert ev("(eq? #\\a #\\a)") is True


# --------------------------------------------------------------------------- #
#  Strings                                                                     #
# --------------------------------------------------------------------------- #

def test_string_comparisons(ev) -> None:
    assert ev('(string<? "a" "b")') is True
    assert ev('(string>? "b" "a")') is True
    assert ev('(string<=? "a" "a")') is True


def test_string_conversions(ev) -> None:
    assert ev('(string->list "abc")') == [Char("a"), Char("b"), Char("c")]
    assert ev("(list->string (list #\\h #\\i))") == "hi"
    assert ev('(string-ref "abc" 1)') == Char("b")
    assert ev('(make-string 3 #\\x)') == "xxx"


def test_string_helpers(ev) -> None:
    assert ev('(string-split "a,b,c" ",")') == ["a", "b", "c"]
    assert ev('(string-join (list "a" "b") "-")') == "a-b"
    assert ev('(string-contains? "hello" "ell")') is True


# --------------------------------------------------------------------------- #
#  Vectors                                                                     #
# --------------------------------------------------------------------------- #

def test_vectors(ev) -> None:
    assert ev("(vector? (vector 1 2))") is True
    assert ev("(vector-length (vector 1 2 3))") == 3
    assert ev("(vector-ref (vector 'a 'b) 1)") == intern("b")
    assert ev("(vector->list (vector 1 2 3))") == [1, 2, 3]
    assert ev("(list->vector (list 1 2))") == Vector([1, 2])
    assert to_string(ev("(vector 1 #\\a)"), write=True) == '#(1 #\\a)'


def test_vector_is_mutable(ev) -> None:
    result = ev("(define v (vector 1 2 3)) (vector-set! v 0 9) (vector-fill! v 7) v")
    assert result == Vector([7, 7, 7])


def test_vector_map_and_append(ev) -> None:
    assert ev("(vector-map + (vector 1 2) (vector 10 20))") == Vector([11, 22])
    assert ev("(vector-append (vector 1) (vector 2 3))") == Vector([1, 2, 3])


def test_vector_map_refuses_mismatched_lengths(ev) -> None:
    # As with the list `map`, a silent truncation is a bug met much later.
    with pytest.raises(LispTypeError, match="same length"):
        ev("(vector-map + (vector 1 2) (vector 3))")
    with pytest.raises(LispTypeError, match="same length"):
        ev("(vector-for-each + (vector 1 2) (vector 3))")


def test_negative_and_out_of_range_indices_are_refused(ev) -> None:
    # Python's negative indexing must not leak into a Scheme-shaped API.
    for form in (
        "(list-ref (list 1 2) -1)",
        "(list-tail (list 1 2) -1)",
        '(string-ref "ab" -1)',
        "(vector-ref (vector 1 2) -1)",
        "(vector-set! (vector 1 2) -1 9)",
        '(substring "abc" -1)',
        '(substring "abc" 0 9)',
    ):
        with pytest.raises(LispTypeError):
            ev(form)


def test_vectors_compare_by_value(ev) -> None:
    assert ev("(equal? (vector 1 2) (vector 1 2))") is True
    assert ev("(equal? (vector 1 2) (vector 1 3))") is False


# --------------------------------------------------------------------------- #
#  Hash tables                                                                 #
# --------------------------------------------------------------------------- #

def test_hash_table_basics(ev) -> None:
    assert ev("(hash-table? (make-hash-table))") is True
    assert ev("(define h (make-hash-table)) (hash-table-set! h 'a 1) (hash-table-ref h 'a)") == 1
    assert ev("(hash-table-ref/default h 'z 99)") == 99
    assert ev("(hash-table-has-key? h 'a)") is True
    assert ev("(hash-table-count h)") == 1


def test_hash_table_keys_use_equal(ev) -> None:
    # A list key is not hashable in Python — the table makes it so.
    result = ev(
        "(define h (make-hash-table))"
        " (hash-table-set! h (list 1 2) 'hit)"
        " (hash-table-ref h (list 1 2))"
    )
    assert result == intern("hit")


def test_hash_table_keeps_symbols_and_strings_apart(ev) -> None:
    # ``equal?`` now distinguishes them, and ``hash_key`` always did — so a
    # symbol key must not be found by a string lookalike.
    ev("(define h (make-hash-table)) (hash-table-set! h 'a 1)")
    assert ev("(hash-table-has-key? h \"a\")") is False
    assert ev("(hash-table-ref/default h \"a\" 'missing)") == intern("missing")
    assert ev("(hash-table-ref h 'a)") == 1


def test_hash_table_views_and_delete(ev) -> None:
    assert ev(
        "(define h (make-hash-table))"
        " (hash-table-set! h 'a 1) (hash-table-set! h 'b 2)"
        " (list (hash-table-keys h) (sort (hash-table-values h) <))"
    ) == [[intern("a"), intern("b")], [1, 2]]
    assert ev("(hash-table-delete! h 'a) (hash-table-count h)") == 1
    assert ev("(hash-table-clear! h) (hash-table-count h)") == 0


def test_hash_table_update(ev) -> None:
    assert ev(
        "(define h (make-hash-table))"
        " (hash-table-update! h 'n (lambda (x) (+ x 1)) 0)"
        " (hash-table-update! h 'n (lambda (x) (+ x 1)) 0)"
        " (hash-table-ref h 'n)"
    ) == 2


def test_hash_table_to_alist(ev) -> None:
    assert ev(
        "(define h (make-hash-table)) (hash-table-set! h 'a 1) (hash-table->alist h)"
    ) == [[intern("a"), 1]]


# --------------------------------------------------------------------------- #
#  Conditions                                                                  #
# --------------------------------------------------------------------------- #

def test_raise_and_guard_bind_the_value(ev) -> None:
    assert ev("(guard (e (else e)) (raise 'boom))") == intern("boom")
    assert ev("(guard (e ((symbol? e) 'caught)) (raise 'boom))") == intern("caught")


def test_guard_test_only_clause_runs_the_test_once(buffered_env) -> None:
    # A guard clause with no body yields the test's value; the test must run
    # exactly once (its side effect, once).
    env, buffer = buffered_env
    from lisp.evaluator import evaluate_program
    from lisp.reader import read_all

    result = evaluate_program(
        read_all('(guard (e ((begin (display "g") 1))) (raise \'boom))'), env
    )
    assert result == 1
    assert buffer.getvalue() == "g"


def test_error_objects(ev) -> None:
    assert ev("(guard (e (else (error-object? e))) (error \"broken\"))") is True
    assert ev("(guard (e (else (error-object-message e))) (error \"broken\" 1 2))") == "broken"
    assert ev("(guard (e (else (error-object-irritants e))) (error \"b\" 1 2))") == [1, 2]
    assert ev("(guard (e (else (error-object-message e))) (error 'oops))") == "oops"


def test_guard_catches_implementation_errors(ev) -> None:
    # A type error from the host arrives as an error object, not a crash.
    assert ev("(guard (e (else (error-object? e))) (car '()))") is True
    assert ev("(guard (e (else (error-object? e))) (+ 1 'x))") is True


def test_guard_with_arrow_and_no_match_reraises(ev) -> None:
    assert ev("(guard (e (e => (lambda (x) (list 'got x)))) (raise 5))") == [
        intern("got"),
        5,
    ]
    with pytest.raises(LispError):
        ev("(guard (e ((string? e) e)) (raise 'nope))")


def test_guard_does_not_catch_a_continuation(ev) -> None:
    # Escaping through a guard must not be turned into a condition.
    assert ev("(call/cc (lambda (k) (guard (e (else 'caught)) (k 42))))") == 42


def test_with_exception_handler_runs_then_rereases(ev) -> None:
    with pytest.raises(LispError):
        ev("(with-exception-handler (lambda (e) e) (lambda () (raise 'x)))")
    assert ev(
        "(call/cc (lambda (k)"
        "  (with-exception-handler"
        "    (lambda (e) (k 'handled))"
        "    (lambda () (raise 'x)))))"
    ) == intern("handled")


def test_dynamic_wind_runs_the_after_thunk(ev) -> None:
    assert ev(
        "(define log '())"
        " (dynamic-wind"
        "   (lambda () (set! log (cons 'before log)))"
        "   (lambda () (set! log (cons 'during log)))"
        "   (lambda () (set! log (cons 'after log))))"
        " (reverse log)"
    ) == [intern("before"), intern("during"), intern("after")]
    # The after thunk runs even when the body escapes.
    assert ev(
        "(define log '())"
        " (call/cc (lambda (k)"
        "   (dynamic-wind"
        "     (lambda () (set! log (cons 'before log)))"
        "     (lambda () (k 'jump))"
        "     (lambda () (set! log (cons 'after log))))))"
        " (reverse log)"
    ) == [intern("before"), intern("after")]


# --------------------------------------------------------------------------- #
#  Multiple values                                                             #
# --------------------------------------------------------------------------- #

def test_values_and_call_with_values(ev) -> None:
    assert ev("(call-with-values (lambda () (values 1 2 3)) +)") == 6
    assert ev("(call-with-values (lambda () (values)) (lambda () 'none))") == intern("none")
    assert ev("(call-with-values (lambda () 42) (lambda (x) x))") == 42
    assert ev("(values 5)") == 5


def test_let_values_parallel_and_sequential(ev) -> None:
    assert ev("(let-values (((a b) (values 1 2)) ((c) (values 3))) (list a b c))") == [1, 2, 3]
    assert ev("(let*-values (((a b) (values 1 2)) ((c) (+ a b))) (list a b c))") == [1, 2, 3]


def test_define_values(ev) -> None:
    assert ev("(define-values (x y) (values 1 2)) (list x y)") == [1, 2]


def test_values_arity_is_checked(ev) -> None:
    with pytest.raises(LispError):
        ev("(let-values (((a b) (values 1))) (list a b))")


# --------------------------------------------------------------------------- #
#  Continuations                                                               #
# --------------------------------------------------------------------------- #

def test_call_cc_escape(ev) -> None:
    assert ev("(call/cc (lambda (k) (+ 1 (k 42))))") == 42
    assert ev(
        "(define (find-first p xs)"
        "  (call/cc (lambda (return)"
        "    (for-each (lambda (x) (if (p x) (return x) #f)) xs)"
        "    #f)))"
        " (find-first (lambda (x) (> x 2)) (list 1 2 3 4))"
    ) == 3


def test_call_cc_can_return_multiple_values(ev) -> None:
    assert ev(
        "(call-with-values (lambda () (call/cc (lambda (k) (k 1 2)))) +)"
    ) == 3


# --------------------------------------------------------------------------- #
#  Hygienic macros                                                             #
# --------------------------------------------------------------------------- #

def test_syntax_rules_hygiene_blocks_capture(ev) -> None:
    # The classic capture: the macro's `t` must not see the caller's `t`.
    assert ev(
        "(define-syntax my-or (syntax-rules () ((_ a b) (let ((t a)) (if t t b)))))"
        " (let ((t 'outer)) (my-or #f t))"
    ) == intern("outer")


def test_syntax_rules_hygiene_blocks_being_captured(ev) -> None:
    # A caller rebinding `list` must not change what the template's `list` means.
    assert ev(
        "(define-syntax pair-up (syntax-rules () ((_ x y) (list x y))))"
        " (let ((list (lambda args 'hijacked))) (pair-up 1 2))"
    ) == [1, 2]


def test_syntax_rules_ellipsis(ev) -> None:
    assert ev(
        "(define-syntax my-list (syntax-rules () ((_ x ...) (list x ...))))"
        " (my-list 1 2 3)"
    ) == [1, 2, 3]
    assert ev(
        "(define-syntax rows (syntax-rules () ((_ (a ...) ...) (list (list a ...) ...))))"
        " (rows (1 2) (3 4 5))"
    ) == [[1, 2], [3, 4, 5]]


def test_syntax_rules_literals(ev) -> None:
    assert ev(
        "(define-syntax my-if"
        "  (syntax-rules (then else)"
        "    ((_ c then t else e) (cond (c t) (else e)))))"
        " (my-if #f then 1 else 2)"
    ) == 2


def test_syntax_rules_list_pattern_against_a_non_list_falls_through(ev) -> None:
    """A sequence pattern *fails* on a non-sequence; it must not raise.

    This is what lets a macro accept both `(m x (f a))` and `(m x f)` by
    listing the list case first.
    """
    assert ev(
        "(define-syntax call"
        "  (syntax-rules ()"
        "    ((_ f (g a ...)) (g f a ...))"
        "    ((_ f g) (g f))))"
        " (list (call 2 (expt 3)) (call 2 inc))"
    ) == [8, 3]


def test_syntax_rules_recursion(ev) -> None:
    assert ev(
        "(define-syntax my-and"
        "  (syntax-rules ()"
        "    ((_) #t)"
        "    ((_ x) x)"
        "    ((_ x y ...) (if x (my-and y ...) #f))))"
        " (my-and 1 2 3)"
    ) == 3


def test_syntax_rules_no_match_is_an_error(ev) -> None:
    ev("(define-syntax foo (syntax-rules () ((_ x) x)))")
    with pytest.raises(LispSyntaxError):
        ev("(foo a b)")


def test_syntax_rules_letrec_is_hygienic(ev) -> None:
    # A mutually recursive template pair must see its own renamed binders.
    assert ev(
        "(define-syntax counters"
        "  (syntax-rules ()"
        "    ((_ a) (letrec ((up (lambda (n) (if (= n 0) 'done (down (- n 1)))))"
        "                    (down (lambda (n) (up n))))"
        "       (up a)))))"
        " (counters 3)"
    ) == intern("done")


def test_syntax_rules_memo_survives_host_values(ev) -> None:
    # A form holding an opaque host value must not be served a stale expansion.
    ev("(define-syntax first-arg (syntax-rules () ((_ x) x)))")
    assert ev("(first-arg (list 1 2))") == [1, 2]
    assert ev("(first-arg (list 3 4))") == [3, 4]


def test_a_macro_is_not_a_value(ev) -> None:
    ev("(define-syntax foo (syntax-rules () ((_ x) x)))")
    with pytest.raises(LispError):
        ev("foo")


# --------------------------------------------------------------------------- #
#  The additions to the standard library                                       #
# --------------------------------------------------------------------------- #

def test_do_and_dotimes(ev) -> None:
    assert ev("(do ((i 0 (+ i 1)) (acc '() (cons i acc))) ((= i 4) acc))") == [3, 2, 1, 0]
    assert ev("(define t 0) (dotimes (i 5) (set! t (+ t i))) t") == 10


def test_push_and_pop_are_hygienic(ev) -> None:
    assert ev("(define v 99) (define xs (list 1 2)) (push! xs 0) (pop! xs) v") == 99
    assert ev("(define xs (list 1 2 3)) (pop! xs) xs") == [2, 3]


def test_more_list_algorithms(ev) -> None:
    assert ev("(take (list 1 2 3 4) 2)") == [1, 2]
    assert ev("(drop (list 1 2 3 4) 2)") == [3, 4]
    assert ev("(any even? (list 1 3 4))") is True
    assert ev("(every even? (list 2 4))") is True
    assert ev("(count even? (list 1 2 3 4))") == 2
    assert ev("(find even? (list 1 3 4))") == 4
    assert ev("(find-index even? (list 1 3 4))") == 2
    assert ev("(zip (list 1 2) (list 'a 'b))") == [[1, intern("a")], [2, intern("b")]]
    assert ev("(delete 2 (list 1 2 3 2))") == [1, 3]
    assert ev("(iota 3 5)") == [5, 6, 7]
    assert ev("(sum (list 1 2 3))") == 6


def test_alist_set_returns_a_new_alist(ev) -> None:
    assert ev("(alist-set (list (list 'a 1)) 'a 9)") == [[intern("a"), 9]]
    assert ev("(alist-set '() 'b 2)") == [[intern("b"), 2]]


def test_string_extras(ev) -> None:
    assert ev('(string-prefix? "hello" "he")') is True
    assert ev('(string-suffix? "hello" "lo")') is True
    assert ev('(string-index "hello" #\\l)') == 2
    assert ev('(string-index "hello" #\\z)') is False


def test_hash_table_for_each(ev) -> None:
    assert ev(
        "(define h (make-hash-table)) (hash-table-set! h 'a 1)"
        " (define acc '())"
        " (hash-table-for-each (lambda (k v) (set! acc (cons (list k v) acc))) h)"
        " acc"
    ) == [[intern("a"), 1]]


def test_do_is_a_derived_macro(ev) -> None:
    # `do` expands to a named `let`; the loop name cannot be captured.
    assert ev("(do ((i 0 (+ i 1))) ((= i 3) i))") == 3


def test_sort(ev) -> None:
    assert ev("(sort (list 3 1 2) <)") == [1, 2, 3]
    assert ev("(sort (list \"b\" \"a\" \"c\") string<?)") == ["a", "b", "c"]


# --------------------------------------------------------------------------- #
#  The rest of the numeric tower                                                #
# --------------------------------------------------------------------------- #

def test_rounding_is_the_four_scheme_names(ev) -> None:
    assert ev("(floor 2.7)") == 2
    assert ev("(ceiling 2.1)") == 3
    assert ev("(truncate -2.7)") == -2
    assert ev("(round 2.5)") == 2      # half-to-even, as Scheme asks
    assert ev("(round 3.5)") == 4


def test_gcd_and_lcm_are_variadic(ev) -> None:
    assert ev("(gcd 12 18)") == 6
    assert ev("(gcd 12 18 24)") == 6
    assert ev("(gcd)") == 0
    assert ev("(lcm 4 6)") == 12
    assert ev("(lcm 4 6 0)") == 0


def test_exactness_predicates_name_the_two_types(ev) -> None:
    assert ev("(exact? 3)") is True
    assert ev("(exact? 3.0)") is False
    assert ev("(inexact? 3.0)") is True
    assert ev("(inexact? 3)") is False
    assert ev("(rational? 3.5)") is True
    assert ev("(real? 3)") is True
    assert ev("(complex? 3)") is True


def test_number_to_string_takes_a_radix(ev) -> None:
    assert ev("(number->string 255 16)") == "ff"
    assert ev("(number->string 255 2)") == "11111111"
    assert ev("(number->string -8 8)") == "-10"
    assert ev("(number->string 42)") == "42"


def test_string_to_number_takes_a_radix(ev) -> None:
    assert ev('(string->number "ff" 16)') == 255
    assert ev('(string->number "101" 2)') == 5
    assert ev('(string->number "nope" 16)') is False
    assert ev('(string->number "12.5")') == 12.5


def test_eqv_distinguishes_exactness(ev) -> None:
    assert ev("(eqv? 1 1)") is True
    assert ev("(eqv? 1 1.0)") is False
    assert ev("(eqv? 1.0 1.0)") is True
    assert ev("(eqv? 'a 'a)") is True
    assert ev("(eqv? #\\a #\\a)") is True


# --------------------------------------------------------------------------- #
#  Strings and vectors cover the same ground as lists                          #
# --------------------------------------------------------------------------- #

def test_string_map_walks_one_or_more_strings(ev) -> None:
    assert ev('(string-map char-upcase "abc")') == "ABC"
    assert ev('(string-map (lambda (a b) (if (char<? a b) a b)) "adc" "bbe")') == "abc"


def test_string_for_each_is_for_effect(ev) -> None:
    assert ev('(begin (string-for-each (lambda (c) c) "ab") 1)') == 1


def test_string_and_vector_convert(ev) -> None:
    assert ev('(vector->string (string->vector "hi"))') == "hi"
    assert ev('(vector-length (string->vector "abc"))') == 3


def test_list_set_mutates_in_place(ev) -> None:
    assert ev("(let ((xs (list 1 2 3))) (list-set! xs 1 9) xs)") == [1, 9, 3]


# --------------------------------------------------------------------------- #
#  letrec* and case-lambda                                                      #
# --------------------------------------------------------------------------- #

def test_letrec_star_is_letrec_plus_sequencing(ev) -> None:
    assert ev("(letrec* ((f (lambda (n) (if (= n 0) 1 (* n (f (- n 1))))))) (f 5))") == 120
    assert ev("(letrec* ((a 1) (b (+ a 1))) b)") == 2


def test_case_lambda_dispatches_on_arity(ev) -> None:
    source = """
    (define f (case-lambda
                 (() 'none)
                 ((a) a)
                 ((a b) (+ a b))
                 ((a . rest) (list a rest))))
    """
    ev(source)
    assert ev("(f)") == intern("none")
    assert ev("(f 7)") == 7
    assert ev("(f 2 3)") == 5
    assert ev("(f 1 2 3 4)") == [1, [2, 3, 4]]


def test_case_lambda_refuses_an_unhandled_arity(ev) -> None:
    ev("(define g (case-lambda ((a) a)))")
    with pytest.raises(LispError, match="no clause accepts"):
        ev("(g 1 2)")

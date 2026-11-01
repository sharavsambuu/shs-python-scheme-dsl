"""Typed control flow and the ROP library — ``define-variant``, ``match``, Result.

The Lisp edition of the story the pure-Python toolkit tells next door
(``python_tetris/fp/result.py``, ``fp/kleisli.py``): a fallible computation
returns a value that carries *which rail* it is on, and the pipeline — not a
nest of ``if``s — is the control flow. Two things are pinned here:

* **typed control flow** — a variant is declared once, and ``match`` refuses to
  guess: a case you forgot raises and *names* the closed set;
* **the monad laws** — left identity, right identity, associativity — which is
  what makes "just compose the arrows" a safe thing to say.
"""
from __future__ import annotations

import pytest

from lisp.errors import LispArityError, LispError, LispSyntaxError, LispTypeError
from lisp.printer import to_string
from lisp.types import NIL, Tagged, intern, is_nil, make_tagged


def tag(name: str, *fields):
    return make_tagged(intern(name), fields)


# --------------------------------------------------------------------------- #
#  Tagged values                                                               #
# --------------------------------------------------------------------------- #

def test_tag_builds_a_value_from_a_symbol_and_fields(ev) -> None:
    assert ev("(tag 'foo 1 2)") == tag("foo", 1, 2)
    assert ev("(tag 'nothing)") == tag("nothing")


def test_tagged_predicate_and_readers(ev) -> None:
    assert ev("(tagged? (ok 1))") is True
    assert ev("(tagged? '(ok 1))") is False
    assert ev("(tagged? 3)") is False
    assert ev("(tag-of (ok 1))") == intern("ok")
    assert ev("(tag-fields (err 'x))") == [intern("x")]


def test_tag_readers_refuse_a_non_tagged_value(ev) -> None:
    with pytest.raises(LispTypeError):
        ev("(tag-of 3)")
    with pytest.raises(LispTypeError):
        ev("(tag-fields '(1 2))")


def test_a_tag_must_be_a_symbol(ev) -> None:
    with pytest.raises(LispTypeError):
        ev('(tag "ok" 1)')


def test_a_tagged_value_prints_as_its_constructor_call(ev) -> None:
    assert to_string(ev("(ok 3)"), write=True) == "(ok 3)"
    assert to_string(ev("(err \"boom\")"), write=True) == '(err "boom")'


def test_tagged_values_are_structurally_equal_but_not_lists(ev) -> None:
    assert ev("(equal? (ok 3) (ok 3))") is True
    assert ev("(equal? (ok 3) (ok 4))") is False
    assert ev("(equal? (ok 3) (err 3))") is False
    # The printer makes them look alike; `tagged?` is what tells them apart.
    assert ev("(equal? (ok 3) '(ok 3))") is False
    assert ev("(tagged? (car (list (ok 3))))") is True


def test_a_tagged_value_can_key_a_hash_table(ev) -> None:
    assert ev(
        "(define h (make-hash-table)) (hash-table-set! h (ok 1) 'yes) "
        "(hash-table-ref h (ok 1))"
    ) == intern("yes")


# --------------------------------------------------------------------------- #
#  define-variant — the closed set                                             #
# --------------------------------------------------------------------------- #

def test_define_variant_makes_constructors_a_predicate_and_accessors(ev) -> None:
    ev("(define-variant shape (circle radius) (square side))")
    assert ev("(circle 5)") == tag("circle", 5)
    assert ev("(shape? (circle 5))") is True
    assert ev("(shape? (square 5))") is True
    assert ev("(shape? (ok 5))") is False
    assert ev("(shape? 5)") is False
    assert ev("(circle-radius (circle 5))") == 5
    assert ev("(square-side (square 7))") == 7


def test_a_constructor_checks_its_arity(ev) -> None:
    ev("(define-variant shape (circle radius) (square side))")
    with pytest.raises(LispArityError):
        ev("(circle)")
    with pytest.raises(LispArityError):
        ev("(circle 1 2)")


def test_an_accessor_refuses_the_wrong_tag_by_name(ev) -> None:
    ev("(define-variant shape (circle radius) (square side))")
    with pytest.raises(LispTypeError) as info:
        ev("(circle-radius (square 1))")
    assert "circle" in str(info.value)


def test_the_declared_set_is_recorded_and_closed(ev) -> None:
    assert ev("(variant-tags 'result)") == [intern("ok"), intern("err")]
    assert ev("(variant-of 'ok)") == intern("result")
    assert ev("(variant-of 'nope)") is False
    assert ev("(variant-tags 'nope)") is False
    ev("(define-variant shape (circle radius) (square side))")
    assert ev("(variant-tags 'shape)") == [intern("circle"), intern("square")]


def test_a_variant_declaration_refuses_a_duplicate_tag(ev) -> None:
    with pytest.raises(LispSyntaxError):
        ev("(define-variant bad (a x) (a y))")


def test_a_variant_declaration_refuses_a_bad_case(ev) -> None:
    with pytest.raises(LispSyntaxError):
        ev("(define-variant bad a)")
    with pytest.raises(LispSyntaxError):
        ev('(define-variant bad ("a" x))')


# --------------------------------------------------------------------------- #
#  match — typed control flow                                                  #
# --------------------------------------------------------------------------- #

def test_match_binds_inside_a_list_pattern(ev) -> None:
    assert ev("(variant-match '(1 2) ((a b) (+ a b)))") == 3
    assert ev("(variant-match '(1 2) ((a b) (list b a)))") == [2, 1]


def test_match_wildcard_matches_without_binding(ev) -> None:
    assert ev("(variant-match 'anything (_ 'ok))") == intern("ok")


def test_match_a_bare_symbol_binds_the_whole_value(ev) -> None:
    assert ev("(variant-match '(1 2) (whole (length whole)))") == 2


def test_match_a_literal_matches_by_equal(ev) -> None:
    assert ev("(variant-match 2 (1 'one) (2 'two) (else 'other))") == intern("two")
    assert ev('(variant-match "hi" ("hi" 1) (else 2))') == 1
    assert ev("(variant-match #\\a (#\\a 'yes) (else 'no))") == intern("yes")
    assert ev("(variant-match '() (() 'empty) (else 'no))") == intern("empty")


def test_match_a_quoted_datum_is_a_literal_too(ev) -> None:
    assert ev("(variant-match 'b ('a 1) ('b 2) (else 3))") == 2
    assert ev("(variant-match '(1 2) ('(1 2) 'exact) (else 'no))") == intern("exact")


def test_match_destructures_a_tagged_value(ev) -> None:
    assert ev("(variant-match (ok 3) (('ok v) (list 'got v)) (('err e) (list 'bad e)))") == [
        intern("got"),
        3,
    ]
    assert ev("(variant-match (err 'why) (('ok v) v) (('err e) e))") == intern("why")


def test_a_declared_tag_in_head_position_dispatches_without_a_quote(ev) -> None:
    # `ok`/`err` are declared by `(define-variant result ...)`, so the head is
    # read as the tag, not as a binder.
    assert ev("(variant-match (ok 3) ((ok v) (list 'got v)) ((err e) (list 'bad e)))") == [
        intern("got"),
        3,
    ]
    assert ev("(variant-match (err 'why) ((ok v) 'no) ((err e) e))") == intern("why")
    ev("(define-variant shape (circle radius) (square side))")
    assert ev("(variant-match (square 4) ((circle r) (* 2 r)) ((square s) (* s s)))") == 16


def test_an_undeclared_symbol_head_still_binds(ev) -> None:
    # `mystery` was never declared a tag, so `(mystery v)` binds both cells.
    assert ev("(variant-match '(1 2) ((a b) (+ a b)))") == 3
    assert ev("(variant-match '(1 2) ((mystery v) (list mystery v)))") == [1, 2]


def test_a_declared_tag_pattern_also_reads_a_like_list(ev) -> None:
    # A tagged value views as `(tag . fields)`, so a like-shaped list matches too.
    assert ev("(variant-match '(ok 3) ((ok v) v))") == 3
    assert ev("(variant-match '(err 3) ((ok v) 'no) (else 'not-ok))") == intern("not-ok")


def test_match_nests_patterns(ev) -> None:
    assert ev(
        "(variant-match '(1 (2 3)) ((a (b c)) (+ a b c)))"
    ) == 6
    assert ev(
        "(variant-match (list (ok 1) (ok 2)) (((ok a) (ok b)) (+ a b)) (else 'no))"
    ) == 3
    assert ev(
        "(variant-match (list (ok 1) (err 2)) (((ok a) (ok b)) 'both) (else 'not-both))"
    ) == intern("not-both")


def test_match_a_dotted_pattern_binds_the_rest(ev) -> None:
    assert ev("(variant-match '(1 2 3) ((a . rest) (list a rest)))") == [1, [2, 3]]
    assert ev("(variant-match '(1 2 3) ((a b . rest) rest))") == [3]


def test_match_else_is_the_explicit_catch_all(ev) -> None:
    assert ev("(variant-match 5 (1 'one) (else 'other))") == intern("other")
    assert ev("(variant-match (err 'x) (else 'anything))") == intern("anything")


def test_match_else_must_be_last(ev) -> None:
    with pytest.raises(LispSyntaxError):
        ev("(variant-match 1 (else 'now) (1 'later))")


def test_a_non_exhaustive_match_names_the_closed_set(ev) -> None:
    with pytest.raises(LispError) as info:
        ev("(variant-match (ok 1) (('err e) e))")
    message = str(info.value)
    assert "no clause matched" in message
    assert "result" in message  # which union
    assert "ok" in message and "err" in message  # the cases it was given


def test_a_non_exhaustive_match_on_a_plain_value_still_refuses(ev) -> None:
    with pytest.raises(LispError):
        ev("(variant-match 42 (1 'one))")


def test_a_matched_clause_runs_a_whole_body(ev) -> None:
    assert ev("(variant-match 1 (1 (define x 2) (+ x 3)))") == 5


def test_match_bindings_do_not_leak_into_the_outer_scope(ev) -> None:
    with pytest.raises(LispError):
        ev("(variant-match 1 ((a) 1)) a")


def test_match_does_not_match_a_dotted_pair_to_a_fixed_list_pattern(ev) -> None:
    # `(cons 1 2)` is a pair, not a list, so a length-2 list pattern cannot match.
    assert ev("(variant-match (cons 1 2) ((a b) 'list) (else 'pair))") == intern("pair")


def test_match_stays_in_tail_position(ev) -> None:
    # A match in the tail of a loop must not grow the stack.
    assert ev(
        """
        (define (count n acc)
          (if (= n 0)
              acc
              (variant-match 'step
                ('step (count (- n 1) (+ acc 1)))
                (else acc))))
        (count 50000 0)
        """
    ) == 50000


# --------------------------------------------------------------------------- #
#  The Result library                                                          #
# --------------------------------------------------------------------------- #

def test_result_predicates(ev) -> None:
    assert ev("(result? (ok 1))") is True
    assert ev("(result? (list 'ok 1))") is False
    assert ev("(result-ok? (ok 1))") is True
    assert ev("(result-err? (ok 1))") is False
    assert ev("(result-err? (err 1))") is True
    assert ev("(result-ok? 3)") is False


def test_result_tags_reads_the_closed_set(ev) -> None:
    assert ev("(result-tags)") == [intern("ok"), intern("err")]


def test_result_map_touches_only_the_success_rail(ev) -> None:
    assert ev("(result-map (ok 3) (lambda (x) (* x x)))") == tag("ok", 9)
    assert ev("(result-map (err 'e) (lambda (x) (* x x)))") == tag("err", intern("e"))


def test_result_map_err_is_the_mirror(ev) -> None:
    assert ev("(result-map-err (err 2) (lambda (e) (* e 10)))") == tag("err", 20)
    assert ev("(result-map-err (ok 2) (lambda (e) (* e 10)))") == tag("ok", 2)


def test_result_map2_short_circuits(ev) -> None:
    assert ev("(result-map2 (ok 2) (ok 3) +)") == tag("ok", 5)
    assert ev("(result-map2 (ok 2) (err 'b) +)") == tag("err", intern("b"))
    assert ev("(result-map2 (err 'a) (ok 3) +)") == tag("err", intern("a"))


def test_result_bimap_handles_both_rails(ev) -> None:
    assert ev("(result-bimap (ok 1) inc (lambda (e) e))") == tag("ok", 2)
    assert ev("(result-bimap (err 1) inc (lambda (e) (* e 100)))") == tag("err", 100)


def test_result_fold_forces_both_rails_to_be_named(ev) -> None:
    assert ev("(result-fold (ok 1) (lambda (v) (list 'ok v)) (lambda (e) 'no))") == [
        intern("ok"),
        1,
    ]
    assert ev("(result-fold (err 1) (lambda (v) v) (lambda (e) (list 'err e)))") == [
        intern("err"),
        1,
    ]


def test_result_pure_lifts_a_value(ev) -> None:
    assert ev("(result-pure 5)") == tag("ok", 5)


def test_unwrap_family(ev) -> None:
    assert ev("(result-unwrap (ok 5))") == 5
    assert ev("(result-unwrap-or (err 'e) 9)") == 9
    assert ev("(result-unwrap-or (ok 5) 9)") == 5
    assert ev("(result-unwrap-or-else (err 2) (lambda (e) (* e 10)))") == 20
    with pytest.raises(LispError):
        ev("(result-unwrap (err 'e))")
    with pytest.raises(LispError):
        ev('(result-expect (err "why") "custom")')
    assert ev("(result-expect (ok 1) \"unused\")") == 1


def test_result_to_list(ev) -> None:
    assert ev("(result->list (ok 5))") == [5]
    assert is_nil(ev("(result->list (err 5))"))


# --------------------------------------------------------------------------- #
#  The monad laws — what makes "just compose" safe                             #
# --------------------------------------------------------------------------- #

def test_left_identity(ev) -> None:
    ev("(define (f x) (if (> x 0) (ok (* x 2)) (err 'neg)))")
    assert ev("(equal? (result-bind (ok 5) f) (f 5))") is True


def test_right_identity(ev) -> None:
    assert ev("(equal? (result-bind (ok 5) ok) (ok 5))") is True
    assert ev("(equal? (result-bind (err 'x) ok) (err 'x))") is True


def test_associativity(ev) -> None:
    ev(
        """
        (define (f x) (if (> x 0) (ok (* x 2)) (err 'neg)))
        (define (g x) (ok (+ x 1)))
        """
    )
    assert ev(
        "(equal? (result-bind (result-bind (ok 5) f) g) "
        "        (result-bind (ok 5) (lambda (x) (result-bind (f x) g))))"
    ) is True


def test_map_is_bind_composed_with_ok(ev) -> None:
    assert ev(
        "(equal? (result-map (ok 3) inc) (result-bind (ok 3) (lambda (x) (ok (inc x)))))"
    ) is True


# --------------------------------------------------------------------------- #
#  Kleisli composition and do-notation                                         #
# --------------------------------------------------------------------------- #

def test_the_fish_operator_composes_two_arrows(ev) -> None:
    assert ev("((>=> (lambda (x) (ok (+ x 1))) (lambda (x) (ok (* x 2)))) 4)") == tag(
        "ok", 10
    )
    assert ev("((>=> (lambda (x) (err 'stop)) (lambda (x) (ok x))) 4)") == tag(
        "err", intern("stop")
    )


def test_pipe_results_threads_a_value_and_short_circuits(ev) -> None:
    assert ev(
        "(pipe-results 1 (lambda (x) (ok (+ x 1))) (lambda (x) (ok (* x 10))))"
    ) == tag("ok", 20)
    assert ev(
        "(pipe-results 1 (lambda (x) (err 'halt)) (lambda (x) (ok (* x 10))))"
    ) == tag("err", intern("halt"))


def test_pipe_results_list_takes_the_arrows_as_a_list(ev) -> None:
    assert ev(
        "(pipe-results-list 1 (list (lambda (x) (ok (+ x 1))) (lambda (x) (ok (* x 2)))))"
    ) == tag("ok", 4)


def test_result_do_reads_like_imperative_code(ev) -> None:
    assert ev("(result-do (a <- (ok 2)) (b <- (ok 3)) (ok (+ a b)))") == tag("ok", 5)
    assert ev("(result-do (a <- (ok 2)) (b <- (err 'stop)) (ok (+ a b)))") == tag(
        "err", intern("stop")
    )
    # `_` discards a step's value.
    assert ev("(result-do (_ <- (ok 2)) (b <- (ok 3)) (ok b))") == tag("ok", 3)
    # A single binding with no final expression yields a void success.
    assert ev("(result-do (a <- (ok 1)))") == tag("ok", NIL)


def test_attempt_puts_a_raised_value_on_the_failure_rail(ev) -> None:
    assert ev("(attempt (lambda () (+ 1 1)))") == tag("ok", 2)
    result = ev('(attempt (lambda () (car (quote ()))))')
    assert ev('(result-err? (attempt (lambda () (car (quote ())))))') is True
    assert isinstance(result, Tagged)


# --------------------------------------------------------------------------- #
#  Collections of results                                                      #
# --------------------------------------------------------------------------- #

def test_sequence_results(ev) -> None:
    assert ev("(sequence-results (list (ok 1) (ok 2)))") == tag("ok", [1, 2])
    assert ev("(sequence-results (list (ok 1) (err 2) (ok 3)))") == tag("err", 2)
    assert ev("(sequence-results '())") == tag("ok", NIL)


def test_traverse_results(ev) -> None:
    assert ev(
        "(traverse-results (lambda (x) (if (> x 0) (ok x) (err 'neg))) (list 1 2 3))"
    ) == tag("ok", [1, 2, 3])
    assert ev(
        "(traverse-results (lambda (x) (if (> x 0) (ok x) (err 'neg))) (list 1 -2 3))"
    ) == tag("err", intern("neg"))


def test_reading_a_list_of_results(ev) -> None:
    ev("(define rs (list (ok 1) (err 'a) (ok 3)))")
    assert ev("(ok-values rs)") == [1, 3]
    assert ev("(err-reasons rs)") == [intern("a")]
    assert ev("(first-err rs)") == tag("err", intern("a"))
    assert ev("(count-errs rs)") == 1


"""The SRFI layer: ``(srfi 1)`` semantics, import collisions, shared names.

These are the S1 tests. The SRFI 1 library is an audit-and-complete task, not
an alias task: every name here is checked against the SRFI 1 semantics. The
export list is a checked constant in ``lisp/library.py``; a test asserts every
exported name is bound in the library's own environment.
"""
from __future__ import annotations

import pytest

from lisp.errors import LispError, LispNameError, LispSyntaxError, LispTypeError
from lisp.evaluator import evaluate_program
from lisp.reader import read_all
from lisp.runtime import make_env
from lisp.types import intern


def run(env, source: str):
    return evaluate_program(read_all(source), env)


#: The documented combined import: (scheme base) + renamed SRFI 1 map/for-each.
COMBINED_IMPORT = """
(import (scheme base)
        (rename (srfi 1)
                (map srfi-1:map)
                (for-each srfi-1:for-each)))
"""


@pytest.fixture
def srfi1():
    """An environment with the documented combined import applied."""
    env = make_env(install_tetris=False)
    run(env, COMBINED_IMPORT)
    return env


# --------------------------------------------------------------------------- #
#  The export list is complete and bound                                      #
# --------------------------------------------------------------------------- #

def test_every_srfi1_export_is_bound_in_the_library_env() -> None:
    from lisp.library import _SRFI1_EXPORTS, lisp_file_library
    from pathlib import Path

    env = make_env(install_tetris=False)
    library = lisp_file_library(
        env, ("srfi", "1"), Path("lisp/srfi1.scm"), _SRFI1_EXPORTS
    )
    lib_env = library.instantiate()
    unbound = [n for n in _SRFI1_EXPORTS if lib_env.find(intern(n)) is None]
    assert not unbound, f"exports declared but not defined: {unbound}"


#: The documented (import ...) forms — each must succeed. The combined
#: (scheme base) + (rename (srfi 1) ...) form is the umbrella's documented
#: combined import; the collision test below pins the plain form's refusal.
MUST_IMPORT = [
    "(srfi 1)",
    "(srfi 26)",
    "(srfi 88)",
    "(srfi 89)",
    "(srfi 197)",
    "(srfi 241)",
    COMBINED_IMPORT,
    "(scheme base) (rename (srfi 241) (match srfi-match))",
    "(only (srfi 1) map filter)",
    "(prefix (srfi 26) s26:)",
    "(scheme base) (srfi 26) (srfi 88)",
]

#: The (library, name) pairs that must be bound after the import.
MUST_BIND = [
    ("(srfi 1)", "filter"), ("(srfi 1)", "member"), ("(srfi 1)", "fold-right"),
    ("(srfi 26)", "cut"), ("(srfi 26)", "cute"),
    ("(srfi 88)", "keyword?"), ("(srfi 88)", "string->keyword"),
    ("(srfi 89)", "define*"), ("(srfi 89)", "lambda*"),
    ("(srfi 197)", "chain"), ("(srfi 197)", "nest"),
    ("(srfi 241)", "match"),
]


@pytest.mark.parametrize("form", MUST_IMPORT)
def test_the_documented_import_forms_succeed(form) -> None:
    env = make_env(install_tetris=False)
    if form.strip().startswith("(import"):
        run(env, form)  # a documented combined import, already spelled out
    else:
        run(env, f"(import {form})")


@pytest.mark.parametrize("library,name", MUST_BIND)
def test_the_documented_names_are_bound(library, name) -> None:
    from lisp.evaluator import _SPECIAL_FORMS

    env = make_env(install_tetris=False)
    run(env, f"(import {library})")
    # `match` (SRFI 241) is a global special form: nothing to bind, the
    # evaluator matches it before any lookup — like (scheme base)'s syntax.
    if name not in _SPECIAL_FORMS:
        assert env.find(intern(name)) is not None


# --------------------------------------------------------------------------- #
#  Import collisions and shared names                                         #
# --------------------------------------------------------------------------- #

def test_plain_combined_import_is_a_named_collision() -> None:
    env = make_env(install_tetris=False)
    with pytest.raises(LispError, match="collision on (map|for-each)"):
        run(env, "(import (scheme base) (srfi 1))")


def test_shared_names_are_the_same_binding(srfi1) -> None:
    run(srfi1, """
    (import (scheme base)
            (rename (srfi 1)
                    (car srfi-1:car)
                    (member srfi-1:member)
                    (map srfi-1:map)
                    (for-each srfi-1:for-each)))
    """)
    # re-exported names are the SAME binding objects, not divergent aliases
    assert run(srfi1, "(eq? car srfi-1:car)") is True
    assert run(srfi1, "(eq? member srfi-1:member)") is True


def test_map_and_for_each_split_on_unequal_lengths(srfi1) -> None:
    # SRFI 1 stops at the shortest; (scheme base) still raises.
    assert run(srfi1, "(srfi-1:map + '(1 2) '(10 20 30))") == [11, 22]
    with pytest.raises(LispError):
        run(srfi1, "(map + '(1 2) '(10 20 30))")
    collected = []


def test_member_assoc_accept_the_comparator_through_both(srfi1) -> None:
    assert run(srfi1, '(member "b" \'("a" "b") string=?)') == ["b"]
    assert run(srfi1, '(assoc "b" \'(("a" . 1) ("b" . 2)) string=?)') is not None
    assert run(srfi1, '(equal? (assoc "b" \'(("a" . 1) ("b" . 2)) string=?) \'("b" . 2))') is True
    assert run(srfi1, "(member 2 '(1 2 3) =)") == [2, 3]
    # the 2-argument form is unchanged
    assert run(srfi1, "(member 2 '(1 2 3))") == [2, 3]


# --------------------------------------------------------------------------- #
#  SRFI 1 semantics                                                           #
# --------------------------------------------------------------------------- #

def test_reduce_empty_vs_non_empty(srfi1) -> None:
    assert run(srfi1, "(reduce + 0 '())") == 0
    assert run(srfi1, "(reduce + 0 '(1 2 3))") == 6
    assert run(srfi1, "(reduce max 0 '(3 1 4))") == 4


def test_fold_and_fold_right(srfi1) -> None:
    assert run(srfi1, "(fold + 0 '(1 2 3))") == 6
    assert run(srfi1, "(fold cons '() '(1 2 3))") == [3, 2, 1]
    assert run(srfi1, "(fold-right cons '() '(1 2 3))") == [1, 2, 3]
    # multi-list fold stops at the shortest
    assert run(srfi1, "(fold + 0 '(1 2 3) '(10 20))") == 33


def test_zip_with_one_two_three_lists(srfi1) -> None:
    assert run(srfi1, "(zip '(1 2 3))") == [[1], [2], [3]]
    assert run(srfi1, "(zip '(1 2) '(a b))") == [[1, "a"], [2, "b"]]
    assert run(srfi1, "(zip '(1 2) '(a b) '(10 20))") == [[1, "a", 10], [2, "b", 20]]


def test_iota_with_start_and_step(srfi1) -> None:
    assert run(srfi1, "(iota 5)") == [0, 1, 2, 3, 4]
    assert run(srfi1, "(iota 5 10)") == [10, 11, 12, 13, 14]
    assert run(srfi1, "(iota 5 10 -2)") == [10, 8, 6, 4, 2]


def test_partition_span_break_split_at_return_two_values(srfi1) -> None:
    assert run(srfi1, "(call-with-values (lambda () (partition odd? '(1 2 3 4))) list)") == [[1, 3], [2, 4]]
    assert run(srfi1, "(call-with-values (lambda () (span even? '(2 4 5 6))) list)") == [[2, 4], [5, 6]]
    assert run(srfi1, "(call-with-values (lambda () (break even? '(1 3 4 5))) list)") == [[1, 3], [4, 5]]
    assert run(srfi1, "(call-with-values (lambda () (split-at '(1 2 3 4) 2)) list)") == [[1, 2], [3, 4]]
    assert run(srfi1, "(call-with-values (lambda () (car+cdr '(1 2))) list)") == [1, [2]]
    assert run(srfi1, "(call-with-values (lambda () (unzip2 '((1 2) (3 4)))) list)") == [[1, 3], [2, 4]]


def test_any_and_every_return_true_values(srfi1) -> None:
    assert run(srfi1, "(any odd? '(2 4 5))") is True
    assert run(srfi1, "(any (lambda (x) (and (odd? x) (* x 10))) '(2 3 4))") == 30
    assert run(srfi1, "(any odd? '(2 4 6))") is False
    assert run(srfi1, "(every (lambda (x) (* x 2)) '(1 2 3))") == 6
    assert run(srfi1, "(every odd? '(1 3 5))") is True


def test_count_is_variadic_and_stops_at_the_shortest(srfi1) -> None:
    assert run(srfi1, "(count odd? '(1 2 3 4 5))") == 3
    assert run(srfi1, "(count < '(1 2 3) '(10 0 30))") == 2


def test_delete_with_a_custom_comparator(srfi1) -> None:
    assert run(srfi1, "(delete 2 '(1 2 3 2) =)") == [1, 3]
    assert run(srfi1, '(delete "b" \'("a" "b") string=?)') == ["a"]


def test_list_predicates_partition_all_values(srfi1) -> None:
    assert run(srfi1, "(proper-list? '())") is True
    assert run(srfi1, "(proper-list? '(1 2 3))") is True
    assert run(srfi1, "(circular-list? (cons* 1 2 3))") is False
    assert run(srfi1, "(dotted-list? (cons* 1 2 3))") is True
    assert run(srfi1, "(null-list? '())") is True
    assert run(srfi1, "(null-list? '(1))") is False
    assert run(srfi1, "(not-pair? '())") is True


def test_circular_lists(srfi1) -> None:
    assert run(srfi1, "(circular-list? (circular-list 1 2))") is True
    assert run(srfi1, "(proper-list? (circular-list 1 2))") is False
    assert run(srfi1, "(dotted-list? (circular-list 1 2))") is False
    assert run(srfi1, "(length+ (circular-list 1 2))") is False


def test_set_car_and_set_cdr_mutate_a_pair(srfi1) -> None:
    assert run(srfi1, "(define p (cons 1 2)) (set-car! p 9) (car p)") == 9
    assert run(srfi1, "(define p (cons 1 2)) (set-cdr! p 9) (cdr p)") == 9
    with pytest.raises(LispTypeError):
        run(srfi1, "(set-cdr! '(1 2) 3)")  # a proper list's tail cannot change in place


def test_linear_update_aliases_return_the_same_values(srfi1) -> None:
    assert run(srfi1, "(append! '(1) '(2))") == [1, 2]
    assert run(srfi1, "(reverse! '(1 2))") == [2, 1]
    assert run(srfi1, "(map! (lambda (x) (* 2 x)) '(1 2))") == [2, 4]


def test_set_operations(srfi1) -> None:
    assert run(srfi1, "(lset-union equal? '(1 2 2) '(2 3))") == [1, 2, 2, 3]
    assert run(srfi1, "(null? (lset-union equal?))") is True
    assert run(srfi1, "(lset-intersection equal? '(1 2 3) '(2 3 4))") == [2, 3]
    assert run(srfi1, "(lset-difference equal? '(1 2 3) '(2))") == [1, 3]
    assert run(srfi1, "(lset-xor equal? '(1 2 3) '(2 3 4))") == [1, 4]
    assert run(srfi1, "(lset= equal? '(1 2) '(2 1))") is True
    assert run(srfi1, "(lset<= equal? '(1) '(1 2))") is True
    assert run(srfi1, "(lset-adjoin equal? '(1 2) 2 3)") == [1, 2, 3]
    assert run(
        srfi1,
        "(call-with-values (lambda () (lset-diff+intersection equal? '(1 2 3) '(2 3 4))) list)",
    ) == [[1], [2, 3]]


def test_unfold_and_unfold_right(srfi1) -> None:
    assert run(srfi1, "(unfold (lambda (x) (> x 5)) (lambda (x) (* x x)) (lambda (x) (+ x 1)) 1)") == [1, 4, 9, 16, 25]
    assert run(srfi1, "(unfold-right (lambda (x) (> x 5)) (lambda (x) (* x x)) (lambda (x) (+ x 1)) 1)") == [25, 16, 9, 4, 1]


def test_list_eq_and_delete_duplicates(srfi1) -> None:
    assert run(srfi1, "(list= '(1 2) '(1 2))") is True
    assert run(srfi1, "(list= '(1 2) '(1 2 3))") is False
    assert run(srfi1, "(list=)") is True
    assert run(srfi1, "(list= = '(1) '(1.0))") is True
    assert run(srfi1, "(delete-duplicates '(1 2 1 3 2))") == [1, 2, 3]


def test_selectors_and_constructors(srfi1) -> None:
    assert run(srfi1, "(third '(1 2 3 4))") == 3
    assert run(srfi1, "(tenth '(1 2 3 4 5 6 7 8 9 10))") == 10
    assert run(srfi1, "(last '(1 2 3))") == 3
    assert run(srfi1, "(take-right '(1 2 3 4) 2)") == [3, 4]
    assert run(srfi1, "(drop-right '(1 2 3 4) 2)") == [1, 2]
    assert run(srfi1, "(xcons '(2 3) 1)") == [1, 2, 3]
    assert run(srfi1, "(list-tabulate 4 (lambda (i) (* i i)))") == [0, 1, 4, 9]
    assert run(srfi1, "(last-pair '(1 2 3))") == [3]


def test_filter_map_and_find_family(srfi1) -> None:
    assert run(srfi1, "(filter-map (lambda (x) (and (odd? x) (* x x))) '(1 2 3 4 5))") == [1, 9, 25]
    assert run(srfi1, "(find-tail odd? '(2 3 4))") == [3, 4]
    assert run(srfi1, "(find odd? '(2 3 4))") == 3
    assert run(srfi1, "(find-right odd? '(1 2 3 4))") == 3
    assert run(srfi1, "(list-index odd? '(2 3 4))") == 1
    assert run(srfi1, "(take-while odd? '(1 3 5 2 7))") == [1, 3, 5]
    assert run(srfi1, "(drop-while odd? '(1 3 5 2 7))") == [2, 7]
    assert run(srfi1, "(take-while-right odd? '(1 2 3 5 7))") == [1]
    assert run(srfi1, "(pair-fold (lambda (pair acc) (cons (car pair) acc)) '() '(1 2 3))") == [1, 2, 3]


def test_alist_procedures(srfi1) -> None:
    assert run(srfi1, "(equal? (alist-cons 'a 1 '((b . 2))) '((a . 1) (b . 2)))") is True
    assert run(srfi1, "(equal? (alist-copy '((a . 1))) '((a . 1)))") is True
    assert run(srfi1, "(equal? (alist-delete 'b '((a . 1) (b . 2))) '((a . 1)))") is True


def test_the_game_still_uses_the_prelude_helpers() -> None:
    # Without the default profile (S8), a plain make_env keeps the prelude's
    # fold/any/every semantics: fold aliases foldl, any returns #t/#f.
    env = make_env(install_tetris=False)
    assert run(env, "(fold cons '() '(1 2 3))") == [3, 2, 1]
    assert run(env, "(any odd? '(2 4))") is False
    assert run(env, "(zip '(1 2) '(a b))") == [[1, "a"], [2, "b"]]


# --------------------------------------------------------------------------- #
#  SRFI 26 — cut / cute                                                       #
# --------------------------------------------------------------------------- #

@pytest.fixture
def srfi26():
    env = make_env(install_tetris=False)
    run(env, "(import (srfi 26))")
    return env


def test_cut_examples(srfi26) -> None:
    assert run(srfi26, "(equal? ((cut cons (+ 1 1) 5)) (cons 2 5))") is True
    assert run(srfi26, "((cut list 1 <> 3 <> 5) 2 4)") == [1, 2, 3, 4, 5]
    assert run(srfi26, "(null? ((cut list)))") is True
    assert run(srfi26, "((cut list 1 <> 3 <...>) 2 4 5 6)") == [1, 2, 3, 4, 5, 6]
    assert run(srfi26, "((cut <> 1 2) (lambda args args))") == [1, 2]


def test_cut_in_map(srfi26) -> None:
    run(srfi26, "(import (srfi 1))")
    assert run(srfi26, "(map (cut * 2 <>) '(1 2 3))") == [2, 4, 6]


def test_cute_evaluates_non_slots_once(srfi26) -> None:
    run(srfi26, "(define n 0)")
    run(srfi26, "(define f (cute list (begin (set! n (+ n 1)) n) <>))")
    assert run(srfi26, "(list (f 1) (f 2))") == [[1, 1], [1, 2]]
    # cut re-evaluates per call
    run(srfi26, "(set! n 0)")
    run(srfi26, "(define g (cut list (begin (set! n (+ n 1)) n) <>))")
    assert run(srfi26, "(list (g 1) (g 2))") == [[1, 1], [2, 2]]


def test_cut_is_syntax_not_a_procedure(srfi26) -> None:
    with pytest.raises(LispError):
        run(srfi26, "(procedure? cut)")


def test_cut_malformed_forms_raise(srfi26) -> None:
    with pytest.raises(LispError, match="last expression"):
        run(srfi26, "((cut list 1 <...> 3))")
    with pytest.raises(LispError, match="follow a <>"):
        run(srfi26, "((cut list 1 <...>))")
    with pytest.raises(LispError, match="no arguments"):
        run(srfi26, "(cut)")
    with pytest.raises(LispError, match="expected 1"):
        run(srfi26, "((cut list 1 <> 3) 1 2)")


# --------------------------------------------------------------------------- #
#  SRFI 88 — keyword objects                                                  #
# --------------------------------------------------------------------------- #

@pytest.fixture
def srfi88():
    env = make_env(install_tetris=False)
    run(env, "(import (srfi 88))")
    return env


def test_keyword_literals_are_self_evaluating(srfi88) -> None:
    assert run(srfi88, "host:") is not None
    assert run(srfi88, "(keyword? host:)") is True
    assert run(srfi88, "(symbol? host:)") is False
    assert run(srfi88, "(string? host:)") is False
    assert run(srfi88, "(keyword? (quote host:))") is True
    assert run(srfi88, "(keyword? (car (quote (host: 1))))") is True


def test_keyword_read_syntax_boundaries(srfi88) -> None:
    # `:` alone is a symbol, `:host` is a symbol (SRFI 88 spells it `host:`),
    # and `foo:bar` is an ordinary identifier.
    assert run(srfi88, "(keyword? (quote :))") is False
    assert run(srfi88, "(symbol? (quote :))") is True
    assert run(srfi88, "(keyword? (quote foo:bar))") is False
    assert run(srfi88, "(keyword? (quote foo:))") is True
    with pytest.raises(LispNameError):
        run(srfi88, ":host")  # a symbol, so it is looked up


def test_keywords_are_their_own_kind(srfi88) -> None:
    assert run(srfi88, "(equal? host: host:)") is True
    assert run(srfi88, "(eq? host: host:)") is True
    assert run(srfi88, "(equal? host: (quote host))") is False
    assert run(srfi88, '(equal? host: "host")') is False
    assert run(srfi88, '(keyword? "host")') is False
    assert run(srfi88, "(keyword? (quote host))") is False


def test_keyword_conversions(srfi88) -> None:
    assert run(srfi88, "(keyword->string host:)") == "host"
    assert run(srfi88, '(string? (keyword->string host:))') is True
    assert run(srfi88, '(eq? (string->keyword "host") host:)') is True
    assert run(srfi88, '(eq? (string->keyword "a") (string->keyword "a"))') is True
    with pytest.raises(LispTypeError):
        run(srfi88, '(keyword->string "host")')


def test_keywords_work_as_hash_table_keys(srfi88) -> None:
    assert run(srfi88, """
    (define t (make-hash-table))
    (hash-table-set! t host: 42)
    (list (hash-table-ref t host: #f) (hash-table-ref t (quote host) #f))
    """) == [42, False]


def test_keyword_prefix_import_still_works(srfi88) -> None:
    # `(prefix ... base:)` — the prefix is a keyword now; it binds `base:car`.
    run(srfi88, "(import (prefix (only (scheme base) car cdr) base:))")
    assert run(srfi88, "(base:car '(1 2))") == 1
    assert run(srfi88, "(base:cdr '(1 2))") == [2]


# --------------------------------------------------------------------------- #
#  SRFI 89 — define* / lambda*                                                #
# --------------------------------------------------------------------------- #

@pytest.fixture
def srfi89():
    env = make_env(install_tetris=False)
    run(env, "(import (srfi 89))")
    return env


def test_lambda_star_optional_positionals(srfi89) -> None:
    run(srfi89, "(define* (f a (b #f)) (list a b))")
    assert run(srfi89, "(f 1)") == [1, False]
    assert run(srfi89, "(f 1 2)") == [1, 2]
    with pytest.raises(LispError, match="too many arguments"):
        run(srfi89, "(f 1 2 3)")


def test_lambda_star_defaults_see_previous_parameters(srfi89) -> None:
    run(srfi89, "(define* (g a (b a) (key: k (* a b))) (list a b k))")
    assert run(srfi89, "(g 3)") == [3, 3, 9]
    assert run(srfi89, "(g 3 4)") == [3, 4, 12]
    assert run(srfi89, "(g 3 4 key: 5)") == [3, 4, 5]


def test_lambda_star_named_parameter_errors(srfi89) -> None:
    run(srfi89, "(define* (g a (b a) (key: k (* a b))) (list a b k))")
    with pytest.raises(LispError, match="without a value"):
        run(srfi89, "(g 3 4 key:)")
    with pytest.raises(LispError, match="unknown keyword"):
        run(srfi89, "(g 3 4 zoo: 5)")
    with pytest.raises(LispError, match="duplicate keyword"):
        run(srfi89, "(g 3 4 key: 5 key: 6)")
    run(srfi89, "(define* (bad1 (key: k)) k)")
    with pytest.raises(LispError, match="missing required keyword"):
        run(srfi89, "(bad1)")


def test_lambda_star_named_and_rest(srfi89) -> None:
    run(srfi89, "(define* (h1 a (key: k #f) . r) (list a k r))")
    assert run(srfi89, "(equal? (h1 7) '(7 #f ()))") is True
    assert run(srfi89, "(equal? (h1 7 8 9 10) '(7 #f (8 9 10)))") is True
    assert run(srfi89, "(equal? (h1 7 key: 8 9 10) '(7 8 (9 10)))") is True
    run(srfi89, "(define* (h2 (key: k #f) a . r) (list a k r))")
    assert run(srfi89, "(equal? (h2 key: 8 9 10) '(9 8 (10)))") is True


def test_lambda_star_named_before_positional(srfi89) -> None:
    run(srfi89, "(define* (d2 (key: k 1) a (b (* a 2))) (list a b k))")
    assert run(srfi89, "(d2 3)") == [3, 6, 1]
    with pytest.raises(LispError, match="unknown keyword"):
        run(srfi89, "(d2 3 b: 9)")  # b is positional, not named


def test_lambda_star_defaults_evaluated_left_to_right_once(srfi89) -> None:
    run(srfi89, "(define n 0)")
    run(srfi89, "(define* (f a (b (begin (set! n (+ n 1)) a)) (c (+ a b))) (list a b c))")
    assert run(srfi89, "(f 2)") == [2, 2, 4]
    assert run(srfi89, "n") == 1  # b's default ran once; c's saw the bound b
    assert run(srfi89, "(f 2)") == [2, 2, 4]
    assert run(srfi89, "n") == 2  # once per call


def test_lambda_star_pure_r7rs_formals_behave_like_lambda(srfi89) -> None:
    assert run(srfi89, "((lambda* (a b) (+ a b)) 1 2)") == 3
    assert run(srfi89, "((lambda* (a . r) (list a r)) 1 2 3)") == [1, [2, 3]]
    with pytest.raises(LispError, match="argument"):
        run(srfi89, "((lambda* (a b) (+ a b)) 1)")


def test_lambda_star_works_with_apply_and_procedure_arity(srfi89) -> None:
    run(srfi89, "(define f (lambda* (a (b 2)) (list a b)))")
    assert run(srfi89, "(f 1)") == [1, 2]
    assert run(srfi89, "(apply f 1 (list 9))") == [1, 9]
    assert run(srfi89, "(procedure? f)") is True


def test_define_star_variable_form(srfi89) -> None:
    run(srfi89, "(define* v 42)")
    assert run(srfi89, "v") == 42


def test_define_star_rejects_duplicate_parameters(srfi89) -> None:
    with pytest.raises(LispError, match="duplicate parameter name"):
        run(srfi89, "(define* (f (a 1) (a 2)) a)")
    with pytest.raises(LispError, match="duplicate"):
        run(srfi89, "(define* (f (key: k 1) (key: k 2)) k)")


# --------------------------------------------------------------------------- #
#  SRFI 197 — pipeline operators                                              #
# --------------------------------------------------------------------------- #

@pytest.fixture
def srfi197():
    env = make_env(install_tetris=False)
    run(env, "(import (srfi 197))")
    run(env, '(define (exclamation x) (string-append x "!"))')
    run(env, '(define (foo+bar x) (values (string-append x "foo") (string-append x "bar")))')
    return env


def test_chain_threads_values(srfi197) -> None:
    assert run(srfi197, '(chain "" (string-append "foo" _) (string-append "bar" _) (string-append "baz" _) (exclamation _))') == "bazbarfoo!"
    assert run(srfi197, '(chain "" (string-append _ "foo") (string-append "bar" _) (string-append _ "baz"))') == "barfoobaz"
    assert run(srfi197, "(chain + (_ 1 2))") == 3  # _ in operator position


def test_chain_step_without_placeholder_ignores_the_value(srfi197) -> None:
    assert run(srfi197, '(chain "" (string-append _ "foo") (string-append "bar" "baz") (string-append _ "qux"))') == "barbazqux"


def test_chain_multiple_values_fan_out(srfi197) -> None:
    assert run(srfi197, '(chain "qux" (foo+bar _) (string-append _ "/" _))') == "quxfoo/quxbar"


def test_chain_rest_slot_forwards_remaining_values(srfi197) -> None:
    assert run(srfi197, '(chain "qux" (foo+bar _) (string-append "baz" _ ...))') == "bazquxfooquxbar"
    assert run(srfi197, '(chain "qux" (foo+bar _) (string-append _ "baz" _ ...))') == "quxfoobazquxbar"


def test_chain_custom_placeholder_and_ellipsis(srfi197) -> None:
    assert run(srfi197, '(chain "" <> (string-append "foo" <>) (exclamation <>))') == "foo!"
    assert run(srfi197, '(chain "qux" - --- (foo+bar -) (string-append "baz" - ---))') == "bazquxfooquxbar"


def test_chain_and_short_circuits(srfi197) -> None:
    run(srfi197, '(define (compared x) (equal? x "bar"))')
    run(srfi197, '(define (boom) (error "must not be evaluated"))')
    assert run(srfi197, '(chain-and "" (string-append "foo" _) (compared _) (string-append "baz" _))') is False
    assert run(srfi197, "(chain-and #f (not _))") is False
    # the step after the #f is never evaluated
    assert run(srfi197, '(chain-and "" (string-append "foo" _) (compared _) (boom))') is False


def test_chain_and_checks_values_without_placeholders(srfi197) -> None:
    assert run(srfi197, '(chain-and "" (string-append "foo" _) (string-append "bar" "baz") (string-append _ "qux"))') == "barbazqux"
    run(srfi197, '(define (falsy) #f)')
    # a no-placeholder step's value is still checked
    assert run(srfi197, '(chain-and "" (string-append "foo" _) (falsy) (boom))') is False


def test_chain_when_skips_and_reuses(srfi197) -> None:
    assert run(srfi197, '(chain-when "" ((= (+ 2 2) 4) (string-append "foo" _)) ((= (+ 2 2) 5) (string-append "bar" _)) (#t (string-append "baz" _)))') == "bazfoo"
    assert run(srfi197, '(chain-when "" (#t (string-append _ "foo")) (#t (string-append "bar" _)) (#f (string-append _ "baz")) (#t (string-append _ "qux")))') == "barfooqux"
    assert run(srfi197, '(chain-when "" (#t (string-append _ "foo")) (#t (string-append "bar")) (#f (string-append _ "baz")) (#t (string-append _ "qux")))') == "barqux"
    assert run(srfi197, '(chain-when "" <> (#t (string-append "foo" <>)))') == "foo"


def test_chain_lambda_arity_follows_the_first_step(srfi197) -> None:
    assert run(srfi197, '((chain-lambda (string-append "foo" _) (exclamation _)) "")') == "foo!"
    assert run(srfi197, '((chain-lambda (string-append _ "bar" _) (string-append _ "qux")) "foo" "baz")') == "foobarbazqux"
    assert run(srfi197, "((chain-lambda (string-append \"bar\")))") == "bar"
    assert run(srfi197, '((chain-lambda (string-append "bar") (string-append _ "qux")))') == "barqux"


def test_chain_lambda_variadic(srfi197) -> None:
    assert run(srfi197, '((chain-lambda (string-append "foo" _ ...) (string-append _ "qux")) "bar" "baz")') == "foobarbazqux"
    assert run(srfi197, '((chain-lambda (string-append _ "bar" _ ...) (string-append _ "quux")) "foo" "baz" "qux")') == "foobarbazquxquux"


def test_nest_builds_quoted_data(srfi197) -> None:
    assert run(srfi197, "(nest (quote _) (1 2 _) (3 _ 5) (_) 4)") == [1, 2, [3, [4], 5]]
    assert run(srfi197, "(nest <> (quote <>) (1 2 <>) (3 <> 5) (<>) 4)") == [1, 2, [3, [4], 5]]


def test_nest_nests_inside_itself(srfi197) -> None:
    assert run(srfi197, "(nest (nest _2 (quote _2) (1 2 3 _2) _ 6) (_ 5 _2) 4)") == [1, 2, 3, [4, 5, 6]]


def test_nest_reverse(srfi197) -> None:
    assert run(srfi197, "(nest-reverse 4 (_) (3 _ 5) (1 2 _) (quote _))") == [1, 2, [3, [4], 5]]
    assert run(srfi197, "(nest-reverse 4 <> (<>) (3 <> 5) (1 2 <>) (quote <>))") == [1, 2, [3, [4], 5]]


def test_threading_macros_are_unchanged() -> None:
    # -> / ->> remain project extensions with their Clojure-style semantics.
    env = make_env(install_tetris=False)
    assert run(env, "(-> 5 (- 1) (+ 2))") == 6
    assert run(env, "(->> 5 (- 1) (+ 2))") == -2


# --------------------------------------------------------------------------- #
#  SRFI 241 — the standard match                                              #
# --------------------------------------------------------------------------- #

@pytest.fixture
def srfi241():
    env = make_env(install_tetris=False)
    run(env, "(import (srfi 241))")
    return env


def test_match_pattern_variables_and_wildcards(srfi241) -> None:
    assert run(srfi241, "(match 42 [,x x])") == 42
    assert run(srfi241, "(match (quote (1 2 3 4)) [(1 ,_ ,b . ,r) (list b r)])") == [3, [4]]
    assert run(srfi241, "(match (quote (1 2)) [(,a ,b) (+ a b)])") == 3


def test_match_constants_and_symbol_constants(srfi241) -> None:
    # A pattern symbol is a constant; a comma-prefixed variable binds.
    assert run(srfi241, "(match 'sym [sym 'same])") == intern("same")
    assert run(srfi241, '(match "str" ["str" \'yes])') == intern("yes")
    assert run(srfi241, "(match (quote (ok 5)) [(ok ,v) v])") == 5
    assert run(srfi241, "(match (quote (1 2)) [(3 ,x) 'no] [,other 'other])") == intern("other")


def test_match_srfi_examples(srfi241) -> None:
    assert run(srfi241, "(match '(a 17 37) [(a ,x) 1] [(b ,x ,y) 2] [(a ,x ,y) 3])") == 3
    assert run(srfi241, "(match '(a 17 37) [(a ,x* ...) x*])") == [17, 37]
    assert run(
        srfi241,
        "(match '(begin (1 5) (2 6) (3 7) (4 8)) [(begin (,x* ,y*) ...) (append x* y*)])",
    ) == [1, 2, 3, 4, 5, 6, 7, 8]


def test_match_nested_ellipsis(srfi241) -> None:
    assert run(
        srfi241,
        "(match '((a b c d) (e f g) (h i) (j)) [((,x* ,y** ...) ...) (list x* y**)])",
    ) == [[intern("a"), intern("e"), intern("h"), intern("j")],
          [[intern("b"), intern("c"), intern("d")],
           [intern("f"), intern("g")],
           [intern("i")],
           []]]


def test_match_guards(srfi241) -> None:
    assert run(srfi241, "(match 5 [,i (guard (integer? i)) i] [,x 'no])") == 5
    assert run(srfi241, '(match "x" [,i (guard (integer? i)) i] [,x \'no])') == intern("no")
    # a failed guard continues with the next clause; its bindings do not leak
    assert run(srfi241, "(match 5 [,x (guard (> x 10)) 'big] [,y y])") == 5
    # a guard that is false with no later clause raises
    with pytest.raises(LispError):
        run(srfi241, "(match 5 [,x (guard #f) 1])")


def test_match_dotted_and_empty_patterns(srfi241) -> None:
    assert run(srfi241, "(match '(1 2 3) [(,a . ,rest) (list a rest)])") == [1, [2, 3]]
    assert run(srfi241, "(match '() [() 'empty])") == intern("empty")
    with pytest.raises(LispError):
        run(srfi241, "(match '(1 2 3) [(,a ,b) 1])")


def test_match_vectors(srfi241) -> None:
    assert run(srfi241, "(match (vector 1 2 3) [#(1 ,a ,b) (+ a b)])") == 5
    assert run(srfi241, "(match (vector 1 2 3 4) [#(1 ,a* ...) a*])") == [2, 3, 4]
    with pytest.raises(LispError):
        run(srfi241, "(match (vector 1 2) [#(1 2 3) 'no])")


def test_match_no_clause_raises(srfi241) -> None:
    with pytest.raises(LispError, match="no clause matched"):
        run(srfi241, "(match '(1 2) [(3 ,x) 1])")


def test_match_catamorphism_recurses_to_the_same_match(srfi241) -> None:
    run(srfi241, "(define (fold-right kons knil lis) (match lis [(,x . ,[x*]) (kons x x*)] [() knil]))")
    assert run(srfi241, "(fold-right cons '() '(1 2 3))") == [1, 2, 3]
    # cons onto a non-list tail builds a Pair: compare in Lisp.
    assert run(srfi241, "(equal? (fold-right (lambda (a b) (cons a b)) 0 '(1 2 3)) '(1 2 3 . 0))") is True
    run(srfi241, "(define (len lst) (match lst [() 0] [(,x . ,[y]) (+ 1 y)]))")
    assert run(srfi241, "(len '(a b c d))") == 4


def test_match_catamorphism_multiple_values(srfi241) -> None:
    assert run(
        srfi241,
        "(call-with-values"
        " (lambda ()"
        "   (let ([split (lambda (lis)"
        "                 (match lis"
        "                   [() (values '() '())]"
        "                   [(,x) (values `(,x) '())]"
        "                   [(,x ,y . ,[odds evens])"
        "                    (values `(,x . ,odds)"
        "                            `(,y . ,evens))]))])"
        "     (split '(a b c d e f))))"
        " (lambda (odds evens)"
        "   (and (equal? odds '(a c e)) (equal? evens '(b d f)))))",
    ) is True


def test_match_catamorphism_explicit_operator(srfi241) -> None:
    assert run(srfi241, "(match 5 [,[(lambda (v) (* v 2)) -> y] y])") == 10
    assert run(srfi241, "(match 5 [,[(lambda (v) (values v (* v 2))) -> a b] (list a b)])") == [5, 10]
    assert run(srfi241, "(match '(1 2 3 4) [(,x . ,[(lambda (l) (length l)) -> n]) n])") == 3
    with pytest.raises(LispError, match="cata operator returned"):
        run(srfi241, "(match 5 [,[(lambda (v) 9) -> a b] 1])")


def test_match_repeated_pattern_variable_is_an_equality_constraint(srfi241) -> None:
    assert run(srfi241, "(match '(1 1) [(,a ,a) 'same])") == intern("same")
    with pytest.raises(LispError):
        run(srfi241, "(match '(1 2) [(,a ,a) 'same])")


def test_match_bodies_use_ellipsis_aware_quasiquote(srfi241) -> None:
    assert run(srfi241, "(match 5 [,x `(a ,x)])") == [intern("a"), 5]
    assert run(srfi241, "(match '(1 2 3) [(,a* ...) `(a ,a* ...)])") == [intern("a"), 1, 2, 3]
    assert run(srfi241, "(match 5 [,x `(1 ,(+ 1 2) ,(map abs '(4 -5 6)) ... b)])") == [1, 3, 4, 5, 6, intern("b")]
    assert run(srfi241, "(match 5 [,x `(... ,x)])") == 5  # `...` loses its meaning; the comma still evaluates
    assert run(srfi241, "(match 5 [,x `(a ,@(map (lambda (v) (* v 2)) '(1 2)))])") == [intern("a"), 2, 4]


def test_variant_match_is_the_project_matcher(env) -> None:
    # The tag-dispatch matcher keeps working under its new name.
    run(env, "(define-variant shape (circle radius) (square side))")
    assert run(env, "(variant-match (circle 3) ((circle r) (* r r)) ((square s) (* s s)))") == 9
    assert run(env, "(variant-match 5 (else 'other))") == intern("other")
    with pytest.raises(LispSyntaxError):
        run(env, "(variant-match 1 (else 'now) (1 'later))")


def test_srfi241_import_rename_resolves_the_collision(env) -> None:
    # match is a global special form, so the import is bookkeeping; the rename
    # form succeeds without a cross-set collision.
    run(env, "(import (scheme base) (rename (srfi 241) (match srfi-match)))")
    assert run(env, "(match 1 [,x x])") == 1


def test_reader_reads_square_brackets_as_parens() -> None:
    # Option A: `[` / `]` are list delimiters, so SRFI 241's clauses read as
    # written.
    env = make_env(install_tetris=False)
    assert run(env, "(length '[1 2 3])") == 3
    assert run(env, "(car '[1 2])") == 1
    assert run(env, "(match '(1 2) [(,a ,b) (+ a b)])") == 3




"""Quasiquotation and macros — the language rewriting itself."""
from __future__ import annotations

import pytest

from lisp.errors import LispBudgetError, LispSyntaxError, LispTypeError
from lisp.printer import to_string
from lisp.types import NIL, Vector, intern


def _head_text(printed: str) -> str:
    """The head symbol of a printed form, bare or ``|quoted|``.

    A gensym like ``list#h12`` is not an R7RS identifier, so ``write`` may
    print it between bars; either spelling names the same symbol.
    """
    head = printed[1:].split(" ", 1)[0]
    return head[1:-1] if head.startswith("|") and head.endswith("|") else head


def test_quasiquote_is_a_template(ev) -> None:
    assert ev("`(1 2 3)") == [1, 2, 3]
    assert ev("`(a b)") == [intern("a"), intern("b")]


def test_unquote_evaluates(ev) -> None:
    ev("(define x 5)")
    assert ev("`(a ,x)") == [intern("a"), 5]
    assert ev("`(,x ,(+ x 1))") == [5, 6]


def test_unquote_splicing_splices(ev) -> None:
    assert ev("`(1 ,@(list 2 3) 4)") == [1, 2, 3, 4]
    assert ev("`(,@(list 1 2) ,@(list 3))") == [1, 2, 3]
    # Splicing nothing is fine.
    assert ev("`(1 ,@'() 2)") == [1, 2]


def test_nested_quasiquote_keeps_inner_unquote(ev) -> None:
    ev("(define x 1)")
    # The inner `,x` belongs to the inner quasiquote; it must survive intact.
    assert to_string(ev("`(a `(b ,x))"), write=True) == "(a (quasiquote (b (unquote x))))"


def test_defmacro_swap_is_hygienic_enough(ev) -> None:
    ev("(define left 1)")
    ev("(define right 2)")
    ev(
        """
        (defmacro (swap! a b)
          (let ((tmp (gensym)))
            `(let ((,tmp ,a))
               (set! ,a ,b)
               (set! ,b ,tmp))))
        """
    )
    ev("(swap! left right)")
    assert ev("(list left right)") == [2, 1]


def test_macro_does_not_evaluate_its_arguments(ev) -> None:
    # `while` must not evaluate its body when the test is false.
    assert ev("(define hit 0) (while #f (set! hit 1)) hit") == 0


def test_while_macro_loops(ev) -> None:
    assert ev("(define n 0) (while (< n 10) (++ n)) n") == 10


def test_increment_and_decrement_macros(ev) -> None:
    ev("(define x 5)")
    assert ev("(++ x)") == 6
    assert ev("(-- x)") == 5
    assert ev("(-- x) (-- x) x") == 3


def test_custom_macro_builds_a_cond_chain(ev) -> None:
    ev(
        """
        (defmacro (unless-zero expr . body)
          `(if (= ,expr 0) 'zero (begin ,@body)))
        """
    )
    assert ev("(unless-zero 0 'ran)") == intern("zero")
    assert ev("(unless-zero 3 (+ 1 1))") == 2


# --------------------------------------------------------------------------- #
#  syntax-rules: patterns                                                     #
# --------------------------------------------------------------------------- #

def test_ellipsis_repeats_in_pattern_and_template(ev) -> None:
    ev("(define-syntax my-list (syntax-rules () ((_ x ...) (list x ...))))")
    assert ev("(my-list 1 2 3)") == [1, 2, 3]
    assert ev("(my-list)") is NIL
    # Fixed elements may bracket the repeated middle.
    ev("(define-syntax tag (syntax-rules () ((_ n x ...) (list n (list x ...)))))")
    assert ev("(tag 0 1 2)") == [0, [1, 2]]


def test_a_dotted_pattern_collects_the_tail(ev) -> None:
    """A dotted tail works both as a datum and as a repetition — the two ways a
    variadic macro needs it."""
    ev("(define-syntax head-of (syntax-rules () ((_ a . rest) 'a)))")
    assert ev("(head-of 1 2 3)") == 1
    # As a datum: the tail is the list of the remaining forms.
    ev("(define-syntax body-of (syntax-rules () ((_ a . rest) 'rest)))")
    assert ev("(body-of 1 2 3)") == [2, 3]
    assert ev("(body-of 1)") is NIL
    # As a repetition: `rest ...` splices it.
    ev("(define-syntax tag-all (syntax-rules () ((_ . rest) (list 'head rest ...))))")
    assert ev("(tag-all 1 2 3)") == [intern("head"), 1, 2, 3]


def test_literals_must_match_and_order_decides_the_clause(ev) -> None:
    ev(
        """
        (define-syntax arrow
          (syntax-rules (=>)
            ((_ a => b) 'then)
            ((_ a b) 'plain)))
        """
    )
    assert ev("(arrow 1 => 2)") == intern("then")
    assert ev("(arrow 1 2)") == intern("plain")


def test_a_macro_may_expand_to_itself(ev) -> None:
    """Recursion is the pattern: `my-and` rewrites to one step of itself."""
    ev(
        """
        (define-syntax my-and
          (syntax-rules ()
            ((_) #t)
            ((_ e) e)
            ((_ e1 e2 ...) (if e1 (my-and e2 ...) #f))))
        """
    )
    assert ev("(my-and 1 2 3)") == 3
    assert ev("(my-and)") is True
    assert ev("(my-and 1 #f 3)") is False


# --------------------------------------------------------------------------- #
#  syntax-rules: ellipsis depth                                               #
# --------------------------------------------------------------------------- #

def test_nested_ellipsis_keeps_the_shape(ev) -> None:
    ev("(define-syntax grid (syntax-rules () ((_ (x ...) ...) (list (list x ...) ...))))")
    assert ev("(grid (1 2) (3 4))") == [[1, 2], [3, 4]]


def test_stacked_ellipsis_flattens(ev) -> None:
    """`x ... ...` descends one level per ellipsis — the flat spelling of a
    doubly-repeated pattern variable."""
    ev("(define-syntax flat (syntax-rules () ((_ (x ...) ...) (list x ... ...))))")
    assert ev("(flat (1 2) (3 4))") == [1, 2, 3, 4]
    # Three levels, three ellipses.
    ev(
        """
        (define-syntax deep
          (syntax-rules () ((_ ((x ...) ...) ...) (list x ... ... ...))))
        """
    )
    assert ev("(deep ((1 2) (3)) ((4)))") == [1, 2, 3, 4]


def test_stack_too_shallow_for_the_ellipses_is_an_error(ev) -> None:
    ev("(define-syntax one (syntax-rules () ((_ x ...) (list x ... ...))))")
    with pytest.raises(LispSyntaxError, match="too many"):
        ev("(one 1 2)")


# --------------------------------------------------------------------------- #
#  syntax-rules: vectors                                                      #
# --------------------------------------------------------------------------- #

def test_a_vector_is_a_pattern_and_a_template(ev) -> None:
    ev("(define-syntax pair-of (syntax-rules () ((_ #(a b)) (list a b))))")
    assert ev("(pair-of #(1 2))") == [1, 2]
    # A vector pattern does not match a list.
    ev("(define-syntax kind (syntax-rules () ((_ #(a b)) 'vec) ((_ x) 'other)))")
    assert ev("(kind (1 2))") == intern("other")
    # Ellipsis works inside a vector pattern, and a vector template builds one.
    ev("(define-syntax as-vector (syntax-rules () ((_ x ...) #(x ...))))")
    assert ev("(as-vector 1 2 3)") == Vector([1, 2, 3])
    ev("(define-syntax rebuild (syntax-rules () ((_ #(x ...)) #(x ... x ...))))")
    assert ev("(rebuild #(1 2))") == Vector([1, 2, 1, 2])


# --------------------------------------------------------------------------- #
#  Hygiene, from the caller's side                                            #
# --------------------------------------------------------------------------- #

def test_a_template_binder_cannot_capture_the_caller(ev) -> None:
    ev("(define-syntax hy-or (syntax-rules () ((_ a b) (let ((t a)) (if t t b)))))")
    ev("(define t 99)")
    assert ev("(hy-or #f t)") == 99


def test_a_free_template_identifier_is_pinned_by_resolution(ev) -> None:
    """A caller that rebinds `list` cannot break a template that uses it: the
    template's `list` resolved where the macro was defined and became an alias."""
    ev("(define-syntax mk (syntax-rules () ((_ x) (list x x))))")
    ev("(define (f list) (mk 7))")
    assert ev("(f (lambda (a) 'nope))") == [7, 7]


# --------------------------------------------------------------------------- #
#  Macros that define things                                                  #
# --------------------------------------------------------------------------- #

def test_a_macro_may_expand_to_a_define(ev) -> None:
    ev("(define-syntax def-k (syntax-rules () ((_ name v) (define name v))))")
    # `define` yields the name it bound (as it does at top level).
    assert ev("(def-k answer 42)") == intern("answer")
    assert ev("answer") == 42


def test_a_macro_may_expand_to_a_macro(ev) -> None:
    """Macro-writing-macro: syntactic sugar that mints more syntactic sugar."""
    ev(
        """
        (define-syntax make-const
          (syntax-rules ()
            ((_ name val)
             (define-syntax name (syntax-rules () ((_) val))))))
        """
    )
    ev("(make-const forty-two 42)")
    assert ev("(forty-two)") == 42


# --------------------------------------------------------------------------- #
#  Local macros: let-syntax / letrec-syntax                                   #
# --------------------------------------------------------------------------- #

def test_let_syntax_binds_a_macro_for_the_body_only(ev) -> None:
    assert ev("(let-syntax ((m (syntax-rules () ((_ x) (+ x 1))))) (m 41))") == 42
    # It is gone once the body ends: a later let-syntax may reuse the name with
    # a different meaning, and an outer binding of the name is shadowed, not
    # clobbered.
    ev("(define (f x) (* x 10))")
    assert ev("(let-syntax ((f (syntax-rules () ((_ x) (+ x 1))))) (f 41))") == 42
    assert ev("(f 4)") == 40


def test_letrec_syntax_lets_a_template_name_a_sibling(ev) -> None:
    assert (
        ev(
            """
            (letrec-syntax
                ((a (syntax-rules () ((_) (b))))
                 (b (syntax-rules () ((_) 'bee))))
              (a))
            """
        )
        == intern("bee")
    )


def test_let_syntax_rejects_a_bad_binding(ev) -> None:
    with pytest.raises(LispSyntaxError, match="each binding"):
        ev("(let-syntax (bad) 1)")
    with pytest.raises(LispSyntaxError, match="syntax-rules"):
        ev("(let-syntax ((m (lambda (x) x))) 1)")


# --------------------------------------------------------------------------- #
#  macroexpand: the macro author's microscope                                 #
# --------------------------------------------------------------------------- #

def test_macroexpand_1_takes_one_step(ev) -> None:
    ev("(define-syntax m (syntax-rules () ((_ x) (list x x))))")
    # `list` became a hygiene alias (`list#hN`) pinned to `list`; that is the
    # point of the alias, and `eval` still runs the result.
    expanded = to_string(ev("(macroexpand-1 '(m 1))"), write=True)
    assert _head_text(expanded).startswith("list#h") and expanded.endswith(" 1 1)")
    assert ev("(eval (macroexpand-1 '(m 1)))") == [1, 1]


def test_macroexpand_keeps_going_until_the_head_is_not_a_macro(ev) -> None:
    ev("(define-syntax outer (syntax-rules () ((_ x) (inner x))))")
    ev("(define-syntax inner (syntax-rules () ((_ x) (+ x 1))))")
    expanded = to_string(ev("(macroexpand '(outer 1))"), write=True)
    assert _head_text(expanded).startswith("+#h")
    assert ev("(eval (macroexpand '(outer 1)))") == 2
    # One step yields the still-a-macro form.
    assert _head_text(to_string(ev("(macroexpand-1 '(outer 1))"), write=True)).startswith(
        "inner"
    )


def test_macroexpand_passes_a_non_macro_through(ev) -> None:
    assert ev("(macroexpand '(if 1 2 3))") == [intern("if"), 1, 2, 3]
    assert ev("(macroexpand 'x)") == intern("x")
    assert ev("(macroexpand-1 '(1 2 3))") == [1, 2, 3]


def test_macroexpand_stops_a_divergent_macro_by_name(ev) -> None:
    """A self-expanding macro would spin forever outside the trampoline, so
    `macroexpand` has its own, small ceiling — and it says which macro."""
    ev("(define-syntax spin (syntax-rules () ((_ x) (spin x))))")
    with pytest.raises(LispBudgetError, match="macroexpand.*divergent"):
        ev("(macroexpand '(spin 1))")
    # One step is still allowed, and it is fine: it did not wander.
    printed = to_string(ev("(macroexpand-1 '(spin 1))"), write=True)
    assert _head_text(printed).startswith("spin#h")


def test_macroexpand_shows_a_defmacro_written_out(ev) -> None:
    ev("(defmacro (w t) `(when ,t 'yes))")
    assert ev("(macroexpand-1 '(w #t))") == [
        intern("when"),
        True,
        [intern("quote"), intern("yes")],
    ]


# --------------------------------------------------------------------------- #
#  A macro is syntax, not a value                                             #
# --------------------------------------------------------------------------- #

def test_a_macro_cannot_be_used_as_a_value(ev) -> None:
    ev("(define-syntax m (syntax-rules () ((_ x) x)))")
    with pytest.raises(LispTypeError, match="not a value"):
        ev("m")


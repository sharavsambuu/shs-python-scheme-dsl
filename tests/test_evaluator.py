"""The evaluator: values, scope, and the tail-call trampoline."""
from __future__ import annotations

import pytest

from shslisp.errors import LispError, LispNameError, LispTypeError
from shslisp.types import NIL, intern, is_nil


# --------------------------------------------------------------------------- #
#  Numbers and logic                                                           #
# --------------------------------------------------------------------------- #

def test_arithmetic_is_variadic(ev) -> None:
    assert ev("(+ 1 2 3)") == 6
    assert ev("(+)") == 0
    assert ev("(* 2 3 4)") == 24
    assert ev("(- 10 1 2)") == 7
    assert ev("(- 5)") == -5
    assert ev("(/ 12 4)") == 3.0
    assert ev("(/ 4)") == 0.25


def test_quotient_and_remainder_stay_exact(ev) -> None:
    # Exact integers must not be routed through a float: 10**20 // 3 is not
    # representable as a double, and the old `int(a / b)` lost the difference.
    big = 10 ** 20
    assert ev(f"(quotient {big} 3)") == big // 3
    assert ev(f"(remainder {big} 3)") == big % 3
    assert ev(f"(quotient {big} 3)") != int(big / 3)


def test_quotient_truncates_toward_zero_like_scheme(ev) -> None:
    assert ev("(quotient 7 2)") == 3
    assert ev("(quotient -7 2)") == -3
    assert ev("(quotient 7 -2)") == -3
    assert ev("(quotient -7 -2)") == 3
    # remainder takes the sign of the dividend, not the divisor
    assert ev("(remainder 7 2)") == 1
    assert ev("(remainder -7 2)") == -1
    assert ev("(remainder 7 -2)") == 1
    assert ev("(remainder -7 -2)") == -1


def test_comparisons_chain(ev) -> None:
    assert ev("(< 1 2 3)") is True
    assert ev("(< 1 3 2)") is False
    assert ev("(= 1 1 1)") is True
    assert ev("(>= 3 3 2)") is True


def test_only_false_is_false(ev) -> None:
    # R7RS truthiness: only #f is false; 0, "" and () are values.
    assert ev("(if 0 'truthy 'falsey)") == intern("truthy")
    assert ev("(if \"\" 'truthy 'falsey)") == intern("truthy")
    assert ev("(if '() 'truthy 'falsey)") == intern("truthy")
    assert ev("(if #f 'truthy 'falsey)") == intern("falsey")


def test_and_or_short_circuit_and_return_values(ev) -> None:
    assert ev("(and 1 2 3)") == 3
    assert ev("(and 1 #f 3)") is False
    assert ev("(or #f #f 5)") == 5
    assert ev("(and)") is True
    assert ev("(or)") is False
    # Short-circuit: the second form must not run.
    assert ev("(define hit 0) (and #f (set! hit 1)) hit") == 0


# --------------------------------------------------------------------------- #
#  Functions, closures, and scope                                              #
# --------------------------------------------------------------------------- #

def test_define_lambda_and_call(ev) -> None:
    ev("(define (add a b) (+ a b))")
    assert ev("(add 2 3)") == 5
    assert ev("((lambda (x) (* x x)) 6)") == 36


def test_closures_capture_their_environment(ev) -> None:
    ev("(define (make-counter) (let ((n 0)) (lambda () (set! n (+ n 1)) n)))")
    ev("(define counter (make-counter))")
    assert ev("(list (counter) (counter) (counter))") == [1, 2, 3]


def test_two_counters_do_not_share_state(ev) -> None:
    ev("(define (make-counter) (let ((n 0)) (lambda () (set! n (+ n 1)) n)))")
    ev("(define a (make-counter))")
    ev("(define b (make-counter))")
    assert ev("(a)") == 1
    assert ev("(a)") == 2
    assert ev("(b)") == 1


def test_scope_is_lexical_not_dynamic(ev) -> None:
    ev("(define x 10)")
    ev("(define (f y) (+ x y))")
    # The `x` inside f is the one where f was defined, not the caller's `x`.
    assert ev("(let ((x 100)) (f 1))") == 11


def test_rest_parameters(ev) -> None:
    ev("(define (sum . xs) (foldl + 0 xs))")
    assert ev("(sum 1 2 3 4)") == 10
    ev("(define (head-tail h . t) (list h t))")
    assert ev("(head-tail 1 2 3)") == [1, [2, 3]]


# --------------------------------------------------------------------------- #
#  Recursion and tail-call elimination                                         #
# --------------------------------------------------------------------------- #

def test_recursion(ev) -> None:
    ev("(define (fact n) (if (= n 0) 1 (* n (fact (- n 1)))))")
    assert ev("(fact 10)") == 3628800


def test_tail_calls_do_not_grow_the_stack(ev, monkeypatch) -> None:
    # A million iterations: impossible without the trampoline. How *long* a
    # loop may run is the step budget's job; this test raises it and pins what
    # matters here — the trampoline's depth is flat over every one of the
    # million steps, which is why a failure would have been a LispBudgetError
    # and never a stack error.
    monkeypatch.setattr("shslisp.evaluator.STEPS_BUDGET", 50_000_000)
    assert ev("(let loop ((i 0)) (if (= i 1000000) i (loop (+ i 1))))") == 1000000
    ev("(define (count-down n acc) (if (= n 0) acc (count-down (- n 1) (+ acc 1))))")
    assert ev("(count-down 200000 0)") == 200000


# --------------------------------------------------------------------------- #
#  Binding forms                                                               #
# --------------------------------------------------------------------------- #

def test_let_forms(ev) -> None:
    assert ev("(let ((x 2) (y 3)) (+ x y))") == 5
    assert ev("(let* ((x 1) (y (+ x 1))) (list x y))") == [1, 2]
    ev("(define (even? n) (if (= n 0) #t (odd? (- n 1))))")
    ev("(define (odd? n) (if (= n 0) #f (even? (- n 1))))")
    assert ev("(even? 10)") is True
    assert ev("(letrec ((f (lambda (n) (if (= n 0) 1 (* n (f (- n 1))))))) (f 5))") == 120


def test_let_star_binds_sequentially_beyond_two(ev) -> None:
    # Regression: with three or more bindings the rest must stay ``let*``, not
    # collapse into a parallel ``let`` — otherwise ``c`` cannot see ``b``.
    assert ev("(let* ((a 1) (b (+ a 1)) (c (+ b 1))) (list a b c))") == [1, 2, 3]
    assert ev(
        "(let* ((a 1) (b (+ a 1)) (c (+ b 1)) (d (+ c 1))) (list a b c d))"
    ) == [1, 2, 3, 4]
    # An initialiser may read any earlier name, in any order of use.
    assert ev("(let* ((x 2) (y 3) (z (* (+ x y) x))) z)") == 10


def test_named_let_is_a_loop(ev) -> None:
    assert ev("(let loop ((i 0) (acc 1)) (if (= i 5) acc (loop (+ i 1) (* acc 2))))") == 32
    assert ev("(define total 0) (let loop () (if (< total 3) (begin (set! total (+ total 1)) (loop)) total)) total") == 3


# --------------------------------------------------------------------------- #
#  Conditionals                                                                #
# --------------------------------------------------------------------------- #

def test_cond_case_when_unless(ev) -> None:
    assert ev("(cond ((= 1 2) 'no) ((= 1 1) 'yes) (else 'never))") == intern("yes")
    assert ev("(cond (#f 'no))") is NIL
    assert ev("(case 2 ((1) 'one) ((2 3) 'two) (else 'other))") == intern("two")
    assert ev("(case 9 ((1) 'one) (else 'other))") == intern("other")
    assert ev("(when #t 1 2 3)") == 3
    assert ev("(when #f 1)") is NIL
    assert ev("(unless #f 'ran)") == intern("ran")
    assert ev("(unless #t 'ran)") is NIL


def test_cond_test_only_clause_runs_the_test_once(buffered_env) -> None:
    # A clause with no body yields the test's own value — and must evaluate
    # the test exactly once, side effects included.
    from shslisp.evaluator import evaluate_program
    from shslisp.reader import read_all

    env, buffer = buffered_env
    result = evaluate_program(
        read_all('(cond ((begin (display "x") 1)))'), env
    )
    assert result == 1
    assert buffer.getvalue() == "x"


def test_cond_test_only_clause_falls_through_when_false(buffered_env) -> None:
    from shslisp.evaluator import evaluate_program
    from shslisp.reader import read_all

    env, buffer = buffered_env
    result = evaluate_program(
        read_all('(cond ((begin (display "y") #f)) (else \'ok))'), env
    )
    assert result == intern("ok")
    assert buffer.getvalue() == "y"


# --------------------------------------------------------------------------- #
#  Lists and higher-order procedures                                           #
# --------------------------------------------------------------------------- #

def test_list_operations(ev) -> None:
    assert ev("(cons 1 (list 2 3))") == [1, 2, 3]
    assert ev("(cons 1 '())") == [1]
    assert ev("(car (list 1 2 3))") == 1
    assert ev("(cdr (list 1 2 3))") == [2, 3]
    assert is_nil(ev("(cdr (list 1))"))
    assert ev("(length (list 1 2 3))") == 3
    assert ev("(append (list 1 2) (list 3) '())") == [1, 2, 3]
    assert ev("(reverse (list 1 2 3))") == [3, 2, 1]
    assert ev("(list-ref (list 'a 'b 'c) 1)") == intern("b")
    assert ev("(range 5)") == [0, 1, 2, 3, 4]
    assert ev("(range 1 6 2)") == [1, 3, 5]


def test_higher_order(ev) -> None:
    assert ev("(map (lambda (x) (* x x)) (list 1 2 3))") == [1, 4, 9]
    assert ev("(filter (lambda (x) (> x 2)) (list 1 2 3 4))") == [3, 4]
    assert ev("(foldl + 0 (list 1 2 3 4))") == 10
    assert ev("(foldl (lambda (x acc) (cons x acc)) '() (list 1 2 3))") == [3, 2, 1]
    assert ev("(foldr cons '() (list 1 2 3))") == [1, 2, 3]
    assert ev("(apply + (list 1 2 3))") == 6


def test_assoc_alists(ev) -> None:
    ev("(define alist (list (list 'a 1) (list 'b 2)))")
    assert ev("(assoc 'b alist)") == [intern("b"), 2]
    assert ev("(assoc 'z alist)") is False
    assert ev("(alist-ref alist 'a)") == 1
    assert ev("(alist-ref alist 'z)") is False


# --------------------------------------------------------------------------- #
#  Equality                                                                    #
# --------------------------------------------------------------------------- #

def test_equality(ev) -> None:
    assert ev("(equal? (list 1 2) (list 1 2))") is True
    assert ev("(equal? (list 1 2) (list 1 3))") is False
    assert ev("(equal? #t 1)") is False  # booleans are not numbers
    assert ev("(eq? 'a 'a)") is True
    assert ev("(equal? '(a (b)) '(a (b)))") is True


def test_symbols_and_strings_are_different_kinds_of_value(ev) -> None:
    # A symbol is an interned identifier, a string is text. A Symbol is a
    # str subclass, so the host ``==`` would conflate them — ``equal?`` must
    # not, because ``hash_key`` already keys them separately.
    assert ev("(equal? 'a \"a\")") is False
    assert ev("(eq? 'a \"a\")") is False
    assert ev("(equal? \"a\" \"a\")") is True
    assert ev("(equal? 'a 'a)") is True
    assert ev("(equal? (list 'a) (list \"a\"))") is False
    assert ev("(equal? (list 'a) (list 'a))") is True


# --------------------------------------------------------------------------- #
#  Strings, symbols, and input                                                 #
# --------------------------------------------------------------------------- #

def test_strings(ev) -> None:
    assert ev('(string-append "a" "b" "c")') == "abc"
    assert ev('(string-length "hello")') == 5
    assert ev('(substring "hello" 1 3)') == "el"
    assert ev('(number->string 42)') == "42"
    assert ev('(string->number "42")') == 42
    assert ev("(symbol->string 'foo)") == "foo"
    assert ev('(string=? "x" "x")') is True


def test_eval_reads_forms(ev) -> None:
    assert ev("(eval '(+ 1 2))") == 3
    assert ev("(read-string \"(a b)\")") == [intern("a"), intern("b")]


# --------------------------------------------------------------------------- #
#  Host hooks and errors                                                       #
# --------------------------------------------------------------------------- #

def test_display_writes_to_the_output_port(buffered_env) -> None:
    env, buffer = buffered_env
    from shslisp.evaluator import evaluate_program
    from shslisp.reader import read_all

    evaluate_program(read_all('(display "hi") (newline) (display 42)'), env)
    assert buffer.getvalue() == "hi\n42"


def test_unbound_symbol_raises(ev) -> None:
    with pytest.raises(LispNameError):
        ev("nope")


def test_car_of_empty_list_raises(ev) -> None:
    with pytest.raises(LispTypeError):
        ev("(car '())")


def test_error_primitive_raises_lisp_error(ev) -> None:
    with pytest.raises(LispError):
        ev('(error "boom" 1)')


def test_assert_failure_raises(ev) -> None:
    with pytest.raises(LispError):
        ev("(assert (= 1 2) \"one is not two\")")
    assert ev("(assert (= 1 1))") is NIL


def test_wrong_arity_raises(ev) -> None:
    ev("(define (f x) x)")
    with pytest.raises(LispError):
        ev("(f 1 2)")


def test_builtins_can_be_shadowed_lexically(ev) -> None:
    assert ev("(let ((car 5)) car)") == 5
    assert ev("(car (list 1 2))") == 1  # ...and the shadow ends with the scope

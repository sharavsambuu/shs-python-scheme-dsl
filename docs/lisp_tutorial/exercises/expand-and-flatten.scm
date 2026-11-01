;; Chapter 06, exercise 4 — the answer key.
;;
;; Three things a macro has to do once it stops being a toy:
;;
;;   1. take *any* number of forms and splice them back — a dotted tail
;;      (`(_ . body)`) read with `body ...`;
;;   2. flatten repetition that nests — `x ... ...` is one ellipsis per level;
;;   3. be inspectable — `macroexpand` hands back real code, so `eval` runs it.
;;
;; Run it:  ../python_tetris/env/bin/python -m lisp run this-file --no-tetris

;; 1. A variadic body macro. `body` is bound to the forms after the name, and
;;    `body ...` splices them back into a `begin`.
(define-syntax my-begin
  (syntax-rules ()
    ((_ . body) (begin body ...))))

(define n 0)
(my-begin (set! n (+ n 1)) (set! n (+ n 10)))
(display n) (newline)                       ; => 11

;; 2. Two levels of repetition, flattened by stacked ellipses. Written nested
;;    it would be `(list (list x ...) ...)`; here it is one flat list.
(define-syntax flatten
  (syntax-rules ()
    ((_ (x ...) ...) (list x ... ...))))
(display (flatten (1 2) (3) (4 5))) (newline)   ; => (1 2 3 4 5)

;; 3. The expansion is code, not a string: `eval` runs it.
(define-syntax double (syntax-rules () ((_ x) (* 2 x))))
(display (eval (macroexpand '(double 21)))) (newline)   ; => 42

;; ...and `macroexpand` leaves a form alone once its head is not a macro, so the
;; answer prints as the code it is.
(display (macroexpand '(if #t 1 2))) (newline)   ; => (if #t 1 2)

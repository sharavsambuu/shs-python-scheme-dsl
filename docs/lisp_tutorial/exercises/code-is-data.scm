;; Exercise, chapter 07 -- code is data, end to end.
;;
;; The chapter asks for three things: take a program apart with list
;; operations, write a program that writes a program, and run the result.
;; All three answers are here.
;;
;;   python -m shslisp run docs/lisp_tutorial/exercises/code-is-data.scm --no-tetris

;; 1. A program is a list: collect the leaves of a form.
(define (leaves form)
  (cond ((pair? form) (append (leaves (car form)) (leaves (cdr form))))
        ((null? form) '())
        (else (list form))))

(display (leaves '(define (square x) (* x x)))) (newline)

;; 2. A template: quasiquote builds the code, unquote fills the blanks.
(define (make-check name ok?)
  `(lambda (value)
     (if (,ok? value)
         (list 'ok ',name value)
         (list 'no ',name value))))

;; The generated program is data -- inspect it before running it.
(write (make-check 'count 'number?)) (newline)

;; 3. eval thaws it: one checker per field, no copy-paste.
(define check-count (eval (make-check 'count 'number?)))
(define check-name  (eval (make-check 'name  'string?)))

(display (check-count 3))       (newline)
(display (check-count "three")) (newline)
(display (check-name "ada"))    (newline)
(display (check-name 7))        (newline)

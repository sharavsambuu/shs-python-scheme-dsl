;; Exercise, chapter 10 — three Kleisli arrows that parse, validate, rename.
;;
;; The chapter asks for a pipeline whose early `(err ...)` skips the rest, and
;; for the monad law checked by hand. Both are here.
;;
;;   ../python_tetris/env/bin/python -m lisp run \
;;       docs/lisp_tutorial/exercises/rename-pipeline.scm --no-tetris

;; Each arrow is A -> Result.
(define (parse s)
  (if (string=? s "") (err "empty") (ok s)))

(define (validate s)
  (if (string-contains? s " ") (err "has space") (ok s)))

(define (rename s)
  (ok (string-append (string-upcase s) "!")))

(display (pipe-results "hi" parse validate rename))     ; (ok HI!)
(newline)
(display (pipe-results "a b" parse validate rename))    ; (err has space)
(newline)
(display (pipe-results "" parse validate rename))       ; (err empty)
(newline)

;; The left identity, checked: `(result-bind (ok x) f)` is `(f x)`.
(display (equal? (result-bind (ok "hi") rename) (rename "hi")))  ; #t
(newline)

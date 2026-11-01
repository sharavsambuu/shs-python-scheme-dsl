#!/usr/bin/env shs
;; fizzbuzz.scm — a first script for `shs run`.
;;
;;   shs run examples/fizzbuzz.scm
;;
;; Everything used here ships pre-imported: SRFI 1's `iota` list builder,
;; and the core's `display`/`newline` for output.

(define (fizzbuzz n)
  (cond ((= (modulo n 15) 0) "FizzBuzz")
        ((= (modulo n 3) 0) "Fizz")
        ((= (modulo n 5) 0) "Buzz")
        (else (number->string n))))

(for-each
  (lambda (n) (display (fizzbuzz n)) (newline))
  (iota 20 1))

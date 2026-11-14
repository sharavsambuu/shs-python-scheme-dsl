;;; SRFI 64 — a Scheme API for test suites (S16).
;;;
;;; This file is the (srfi 64) library's private implementation, loaded into a
;;; scope whose parent is the interaction environment. The trading lab grew a
;;; testing prelude of its own (`define-test-suite`, `check=`, `check-raises`);
;;; providing the standard surface here means a host project writes its Scheme
;;; specs against SRFI 64 instead of re-inventing it.
;;;
;;; Scope (the ledger's S16): `test-begin`, `test-end`, `test-group`,
;;; `test-assert`, `test-equal`, `test-eqv`, `test-eq`, `test-error`,
;;; `test-runner-current`, `test-runner-simple`.
;;;
;;; Design notes:
;;;
;;;  * The assertion forms are SYNTAX, not procedures: `(test-error (car 1))`
;;;    has to receive `(car 1)` unevaluated, or the error escapes before the
;;;    assertion can catch it. Each macro wraps the expression in a thunk and
;;;    hands it to a private checker, which catches a condition with `guard`.
;;;    `test-assert` catches too — an expression that raises is a test error,
;;;    not a crashed suite.
;;;
;;;  * The runner is a vector: `#(kind passed failed total)`. It is ordinary
;;;    data, so `test-runner-current` can hand it back and a caller can inspect
;;;    the counts. `test-end` prints one summary line and returns the runner.
;;;
;;;  * Documented deviations (docs/srfi.md): `test-error`'s optional
;;;    error-type is a PREDICATE over the caught condition (this dialect's
;;;    condition objects are `ErrorObject`s, not SRFI 64's type objects), and
;;;    the only runner is the simple one.

(define (srfi64:make-runner)
  (vector 'simple 0 0 0))

(define srfi64:current (srfi64:make-runner))

(define (test-runner-simple)
  "A fresh simple runner: #(kind passed failed total)."
  (srfi64:make-runner))

(define (test-runner-current . maybe)
  "The current runner; with one argument, install it and return it."
  (if (null? maybe)
      srfi64:current
      (begin
        (set! srfi64:current (car maybe))
        srfi64:current)))

;; -- counting ------------------------------------------------------------- #

(define (srfi64:bump! index)
  (let ((runner srfi64:current))
    (vector-set! runner index (+ 1 (vector-ref runner index)))))

(define (srfi64:passed!)
  (srfi64:bump! 1)
  (srfi64:bump! 3))

(define (srfi64:failed!)
  (srfi64:bump! 2)
  (srfi64:bump! 3))

(define (srfi64:show value)
  (write-to-string value))

(define (srfi64:report-failure name expected actual)
  (display "FAIL: ") (display name) (newline)
  (display "  expected: ") (display (srfi64:show expected)) (newline)
  (display "  actual:   ") (display (srfi64:show actual)) (newline))

(define (srfi64:report-error name condition)
  (display "ERROR: ") (display name) (newline)
  (display "  ")
  (display (if (error-object? condition)
               (error-object-message condition)
               (srfi64:show condition)))
  (newline))

(define (srfi64:report-no-error name)
  (display "FAIL: ") (display name)
  (display ": expected an error, none was raised") (newline))

;; -- the checkers (called by the macros, never exported) ------------------ #

(define (srfi64:check-true thunk name)
  (guard (condition
          (else (srfi64:report-error name condition) (srfi64:failed!) #f))
    (let ((value (thunk)))
      (if value
          (begin (srfi64:passed!) #t)
          (begin (srfi64:report-failure name #t value) (srfi64:failed!) #f)))))

(define (srfi64:check same? thunk expected name)
  (guard (condition
          (else (srfi64:report-error name condition) (srfi64:failed!) #f))
    (let ((actual (thunk)))
      (if (same? expected actual)
          (begin (srfi64:passed!) #t)
          (begin (srfi64:report-failure name expected actual) (srfi64:failed!) #f)))))

(define (srfi64:check-error thunk)
  (guard (condition
          (else (srfi64:passed!) #t))
    (thunk)
    (srfi64:report-no-error 'test-error)
    (srfi64:failed!)
    #f))

(define (srfi64:check-error-matching pred thunk name)
  (guard (condition
          (else
           (if (pred condition)
               (begin (srfi64:passed!) #t)
               (begin
                 (srfi64:report-failure name 'matching-error (srfi64:show condition))
                 (srfi64:failed!)
                 #f))))
    (thunk)
    (srfi64:report-no-error name)
    (srfi64:failed!)
    #f))

;; -- groups --------------------------------------------------------------- #

(define (test-begin . args)
  (if (pair? args)
      (begin (display ";; begin ") (display (car args)) (newline)))
  (if #f #f))

(define (test-end . args)
  (let ((runner srfi64:current))
    (display ";; ")
    (if (pair? args) (begin (display (car args)) (display ": ")))
    (display (vector-ref runner 1)) (display " passed, ")
    (display (vector-ref runner 2)) (display " failed, ")
    (display (vector-ref runner 3)) (display " total")
    (newline)
    runner))

(define-syntax test-group
  (syntax-rules ()
    ((_ name body ...)
     (begin (test-begin name) body ... (test-end name)))))

;; -- assertions ----------------------------------------------------------- #

(define-syntax test-assert
  (syntax-rules ()
    ((_ name expr) (srfi64:check-true (lambda () expr) name))
    ((_ expr) (srfi64:check-true (lambda () expr) 'test-assert))))

(define-syntax test-equal
  (syntax-rules ()
    ((_ name expected expr) (srfi64:check equal? (lambda () expr) expected name))
    ((_ expected expr) (srfi64:check equal? (lambda () expr) expected 'test-equal))))

(define-syntax test-eqv
  (syntax-rules ()
    ((_ name expected expr) (srfi64:check eqv? (lambda () expr) expected name))
    ((_ expected expr) (srfi64:check eqv? (lambda () expr) expected 'test-eqv))))

(define-syntax test-eq
  (syntax-rules ()
    ((_ name expected expr) (srfi64:check eq? (lambda () expr) expected name))
    ((_ expected expr) (srfi64:check eq? (lambda () expr) expected 'test-eq))))

(define-syntax test-error
  (syntax-rules ()
    ((_ pred expr) (srfi64:check-error-matching pred (lambda () expr) 'test-error))
    ((_ expr) (srfi64:check-error (lambda () expr)))))

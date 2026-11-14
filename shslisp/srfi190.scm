;;; srfi190.scm — (srfi 190) Coroutine Generators.
;;;
;;; Provides ``coroutine-generator``, ``define-coroutine-generator``, and
;;; ``yield`` on top of SRFI-158 ``make-coroutine-generator``.

(define (yield . args)
  (if (null? args)
      (%coro-yield #f)
      (%coro-yield (car args))))

(define-syntax coroutine-generator
  (syntax-rules ()
    ((_ body ...)
     (make-coroutine-generator
      (lambda (_ignored-yield)
        (begin body ...))))))

(define-syntax define-coroutine-generator
  (syntax-rules ()
    ((_ (name . args) body ...)
     (define (name . args)
       (coroutine-generator body ...)))))

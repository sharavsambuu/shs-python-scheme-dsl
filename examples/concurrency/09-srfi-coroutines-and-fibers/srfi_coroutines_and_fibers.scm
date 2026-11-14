;;; 09 · SRFI 226, 158/190, and 18 — built-in coroutines & cooperative fibers
;;;
;;; Run:
;;;   python -m shslisp run examples/concurrency/09-srfi-coroutines-and-fibers/srfi_coroutines_and_fibers.scm

(import (scheme base)
        (srfi 158)
        (srfi 190)
        (srfi 226)
        (srfi 18))

(define (section title)
  (display "--- ")
  (display title)
  (display " ---")
  (newline))

;; 1. (srfi 190) coroutine-generator + yield
(section "1. SRFI 190 coroutine-generator")
(define-coroutine-generator (fibonacci-up-to limit)
  (let loop ((a 0) (b 1))
    (when (<= a limit)
      (yield a)
      (loop b (+ a b)))))

(display "fib <= 34: ")
(display (generator->list (fibonacci-up-to 34)))
(newline)

;; 2. (srfi 158) make-for-each-generator
(section "2. SRFI 158 make-for-each-generator")
(define vec-gen (make-for-each-generator vector-for-each '#(alpha beta gamma)))
(display "vector stream: ")
(display (generator->list vec-gen))
(newline)

;; 3. (srfi 226) delimited prompt + one-shot composable continuation
(section "3. SRFI 226 delimited prompt & one-shot resume")
(define prompt-tag (make-continuation-prompt-tag 'stepper))
(define paused-k #f)

(define first-stop
  (call-with-continuation-prompt
   (lambda ()
     (+ 100
        (call-with-composable-continuation
         (lambda (k)
           (set! paused-k k)
           (abort-current-continuation prompt-tag 'awaiting-input))
         prompt-tag)))
   prompt-tag
   (lambda (msg) msg)))

(display "first stop: ")
(display first-stop)
(newline)
(display "after resume(23): ")
(display (call-with-continuation-prompt (lambda () (paused-k 23)) prompt-tag))
(newline)

;; 4. (srfi 18) cooperative threads + mutex + condition variable
(section "4. SRFI 18 producer/consumer fibers")
(define mu (make-mutex))
(define cv (make-condition-variable))
(define queue '())
(define done? #f)
(define consumed '())

(define producer
  (make-thread
   (lambda ()
     (for-each
      (lambda (item)
        (mutex-lock! mu)
        (set! queue (append queue (list item)))
        (condition-variable-signal! cv)
        (mutex-unlock! mu)
        (thread-yield!))
      '(job-1 job-2 job-3))
     (mutex-lock! mu)
     (set! done? #t)
     (condition-variable-broadcast! cv)
     (mutex-unlock! mu))
   'producer))

(define consumer
  (make-thread
   (lambda ()
     (let loop ()
       (mutex-lock! mu)
       (let wait ()
         (when (and (null? queue) (not done?))
           (mutex-unlock! mu cv)
           (mutex-lock! mu)
           (wait)))
       (if (pair? queue)
           (let ((item (car queue)))
             (set! queue (cdr queue))
             (set! consumed (cons item consumed))
             (mutex-unlock! mu)
             (loop))
           (mutex-unlock! mu))))
   'consumer))

(thread-start! consumer)
(thread-start! producer)
(thread-join! producer)
(thread-join! consumer)

(display "consumed order: ")
(display (reverse consumed))
(newline)

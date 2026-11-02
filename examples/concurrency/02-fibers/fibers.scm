#!/usr/bin/env shs
;; fibers.scm — cooperative fibers over the S9 generator protocol.
;;
;; Run with:  python -m lisp run examples/concurrency/02-fibers/fibers.scm
;;
;; A *fiber* here is a generator: call it, and it runs until its next
;; yield point, answers one value, and parks with all its local state
;; intact (closures + set! are state enough). generator-end means the
;; fiber has returned. A scheduler that round-robins over a set of
;; generators is therefore a cooperative multitasking runtime — the same
;; shape modern runtimes use for coroutines, and the shape this dialect
;; reaches honestly: its call/cc is escape-only, so continuations are not
;; the mechanism (docs/capabilities.md, Tier 1).
;;
;; What to notice in the transcript: the fibers interleave. Each line is a
;; different fiber making progress; no fiber ever blocks another, they
;; simply take turns, and each resumes exactly where it parked.

;; --- fiber 1: a lazy prime sieve ---------------------------------------------
;; Between yields it does real work (trial division). Parked state: the
;; candidate and the primes found so far.

(define (primes-fiber how-many)
  (let ((candidate 2) (found '()) (n 0))
    (lambda ()
      (let loop ()
        (if (>= n how-many)
            generator-end
            (let ((divides? (lambda (p) (= 0 (modulo candidate p)))))
              (cond ((any divides? found)
                     (set! candidate (+ candidate 1)) (loop))
                    (else
                     (set! found (cons candidate found))
                     (set! n (+ n 1))
                     (let ((v candidate))
                       (set! candidate (+ candidate 1))
                       (list 'prime v))))))))))

;; --- fiber 2: a fibonacci stream with its own pace ----------------------------

(define (fib-fiber how-many)
  (let ((a 0) (b 1) (n 0))
    (lambda ()
      (if (>= n how-many)
          generator-end
          (let ((v a))
            (set! n (+ n 1))
            (set! a b)
            (set! b (+ v b))
            (list 'fib v))))))

;; --- fiber 3: a heartbeat that ticks twice per round ---------------------------
;; Parks between its two ticks *within one call* is not possible — a fiber
;; runs to its next yield — so the heartbeat yields "halfway" states and lets
;; the scheduler call it again. Interleaving is the scheduler's job, always.

(define (heartbeat-fiber beats)
  (let ((n 0))
    (lambda ()
      (if (>= n beats)
          generator-end
          (let ((v n))
            (set! n (+ n 1))
            (list 'beat v))))))

;; --- the scheduler -------------------------------------------------------------
;; Round-robin: call each live fiber once per round, print what it yielded,
;; drop the fibers that have ended, continue until none are left.

(define (any pred lst)
  (cond ((null? lst) #f)
        ((pred (car lst)) #t)
        (else (any pred (cdr lst)))))

(define (keep-live fibers)
  ;; one scheduling pass; answers the fibers still alive afterwards
  (let loop ((rest fibers) (alive '()))
    (cond ((null? rest) (reverse alive))
          (else
           (let ((v ((car rest))))
             (if (generator-end? v)
                 (begin
                   (display "  [scheduler] a fiber finished")
                   (newline)
                   (loop (cdr rest) alive))
                 (begin
                   (display "  round -> ") (display v) (newline)
                   (loop (cdr rest) (cons (car rest) alive)))))))))

(define (run-fibers . fibers)
  (let loop ((live fibers) (round 0))
    (if (null? live)
        (begin (display "[scheduler] all fibers done") (newline) (void))
        (begin
          (display "[scheduler] round ") (display round) (newline)
          (loop (keep-live live) (+ round 1))))))

;; --- run it ----------------------------------------------------------------------

(display "== three fibers, one thread, round-robin ==") (newline)
(run-fibers (primes-fiber 5)
            (fib-fiber 4)
            (heartbeat-fiber 3))
(newline)
(display "(fib and prime interleaved with heartbeats; each fiber kept its own position)")
(newline)

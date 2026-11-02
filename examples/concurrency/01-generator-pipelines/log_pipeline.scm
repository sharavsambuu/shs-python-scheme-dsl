#!/usr/bin/env shs
;; log_pipeline.scm — a lazy log-analysis pipeline, built from generators (S9).
;;
;; Run with:  python -m lisp run examples/concurrency/01-generator-pipelines/log_pipeline.scm
;;
;; The point: every stage is a *closure holding its own position*, and values
;; flow one at a time. No stage after the source ever allocates a list of the
;; whole input — which matters in part 2, where the input is infinite. This is
;; concurrency of a gentle kind: producer and consumer are independent
;; activities joined by a lazy channel, all in one address space.
;;
;; (The multi-core versions of this idea live in 05-parallel-map and
;; 06-core-saturation; this one is the single-core foundation they relax.)

;; --- the data: web-server log lines, already fielded -------------------------
;; (time path status ms) — fielded up front so the example stays about the
;; pipeline, not about string splitting.

(define entries
  '(("2026-11-03T10:00:01" "/api/users"     200 12)
    ("2026-11-03T10:00:02" "/api/users"     200 18)
    ("2026-11-03T10:00:03" "/api/orders"    201 45)
    ("2026-11-03T10:00:04" "/api/orders"    500 9001)
    ("2026-11-03T10:00:05" "/api/users"     200 11)
    ("2026-11-03T10:00:06" "/api/flaky"     503 5000)
    ("2026-11-03T10:00:07" "/api/orders"    200 39)
    ("2026-11-03T10:00:08" "/api/users"     502 6000)
    ("2026-11-03T10:00:09" "/api/health"    200  2)
    ("2026-11-03T10:00:10" "/api/flaky"     503 4800)
    ("2026-11-03T10:00:11" "/api/orders"    200 51)
    ("2026-11-03T10:00:12" "/api/health"    200  3)))

;; --- the stages ---------------------------------------------------------------
;; Each definition *returns a generator*; nothing runs until pulled.

;; pass through only the 5xx lines
(define (errors source)
  (gfilter (lambda (e) (>= (list-ref e 2) 500)) source))

;; project the path field
(define (paths source)
  (gmap (lambda (e) (list-ref e 1)) (errors source)))

;; average of the ms field (a consumer — it drains its input).
;; One fold, accumulating (sum . count): a generator is single-use — folding
;; it twice would measure an already-drained stream (count 0, avg 0).

(define (avg-latency source)
  (let ((result (generator-fold
                 (lambda (e acc)
                   (cons (+ (car acc) (list-ref e 3))
                         (+ (cdr acc) 1)))
                 '(0 . 0)
                 source)))
    (if (= (cdr result) 0) 0 (quotient (car result) (cdr result)))))

;; count occurrences of each value a generator produces, into an alist
(define (tally gen)
  (generator-fold
   (lambda (v counts)
     (let ((hit (assoc v counts)))
       (if hit
           (cons (cons v (+ (cdr hit) 1)) (filter (lambda (c) (not (equal? (car c) v))) counts))
           (cons (cons v 1) counts))))
   '()
   gen))

;; smallest-to-largest by count (insertion sort; the input is tiny)
(define (by-count counts)
  (let insert ((sorted '()) (rest counts))
    (cond ((null? rest) sorted)
          (else (insert (let ((item (car rest)) (out '()))
                          (let loop ((s sorted))
                            (cond ((null? s) (reverse (cons item out)))
                                  ((> (cdar s) (cdr item))
                                   (append (reverse out) (list item) s))
                                  (else (set! out (cons (car s) out)) (loop (cdr s))))))
                        (cdr rest))))))

;; --- part 1: the finite pipeline ----------------------------------------------

(display "== 5xx errors in the real log ==") (newline)
(display "   avg latency of failing requests: ")
(display (avg-latency (errors (list->generator entries))))
(display " ms") (newline)
(display "   failures by path: ") (newline)
(for-each
 (lambda (c)
   (display "     ") (display (car c)) (display ": ")
   (display (cdr c)) (newline))
 (by-count (tally (paths (list->generator entries)))))
(newline)

;; --- part 2: the same pipeline over an infinite source -------------------------
;; `make-range-generator 0` never ends. The pipeline still terminates, because
;; the consumer decides how much to take — pull-based flow control for free.

(define (synthetic-events)
  (gmap
   (lambda (n)
     (if (= (modulo n 97) 0)
         (list n "/api/flaky" 503)
         (list n (string-append "/api/item/" (number->string (modulo n 7))) 200)))
   (make-range-generator 0)))

(display "== 20000 synthetic events, lazily ==") (newline)
(display "   failing paths: ") (newline)
(for-each
 (lambda (c)
   (display "     ") (display (car c)) (display ": ")
   (display (cdr c)) (newline))
 (by-count (tally (paths (gtake (synthetic-events) 20000)))))
(newline)
(display "(an infinite generator fed the whole second pipeline; only 20000 values were ever built)")
(newline)

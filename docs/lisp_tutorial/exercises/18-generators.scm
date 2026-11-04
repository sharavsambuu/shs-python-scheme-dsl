;; Exercise, chapter 18 — generators, lazily.
;;
;; The chapter asks for an infinite squares generator drained two ways, and a
;; one-line window over a generator. All three answers are here.
;;
;;   python -m lisp run docs/lisp_tutorial/exercises/18-generators.scm --no-tetris

;; 1. Squares, lazily: `gmap` over an infinite range, drained with `gtake`.
;;    (Each display uses a *fresh* generator — `squares` is stateful.)
(display (generator->list
          (gtake (gmap (lambda (x) (* x x)) (make-range-generator 1)) 6)))
; (1 4 9 16 25 36)
(newline)
;; `gdrop` after `gtake` skips within the taken window: 4, 9.
(display (generator->list
          (gdrop (gtake (gmap (lambda (x) (* x x)) (make-range-generator 1)) 3) 1)))
; (4 9)
(newline)

;; 2. A finite window: skip `i`, take `k`, drain — one line, and the values
;;    before the window are never built into a list.
(define (window gen i k) (generator->list (gtake (gdrop gen i) k)))
(display (window (make-range-generator 0) 4 3))         ; (4 5 6)
(newline)

;; 3. `(my-gen)` answers 42 forever: `gfilter`/`gtake` on it never end, but
;;    `generator->list` with a `k`-bound drain is where the step budget
;;    finally stops a runaway consumer. The protocol cannot be violated by
;;    the library; only the consumer decides when to stop pulling.
(display (generator->list (make-range-generator 42) 3)) ; (42 43 44)
(newline)
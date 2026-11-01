;; Exercise, chapter 09 — extend the declared set, then meet the refusal.
;;
;; The chapter asks for a `triangle` case and a `triangle-area` accessor, and
;; then for the `else` to be taken away so the reader can read the error.
;; `area-strict` is that second half: it handles two of the three tags and
;; nothing else, so a triangle is *refused by name*.
;;
;;   ../python_tetris/env/bin/python -m lisp run \
;;       docs/lisp_tutorial/exercises/shapes.scm --no-tetris

(define-variant shape
  (circle   radius)
  (rect     w h)
  (triangle base height))

;; `triangle-base` / `triangle-height` are the accessors `define-variant`
;; minted; the constructor is `triangle`.
(define (area s)
  (variant-match s
    ((circle r)   (* 3.14 r r))
    ((rect w h)   (* w h))
    ((triangle b h) (/ (* b h) 2))))

;; No `else`. A shape this function did not anticipate makes `match` raise and
;; name the declared cases.
(define (area-strict s)
  (variant-match s
    ((circle r) (* 3.14 r r))
    ((rect w h) (* w h))))

(display (area (triangle 6 4)))          ; 12 (exact: / keeps an even integer result)
(newline)
(display (variant-tags 'shape))          ; (circle rect triangle)
(newline)
(display (guard (e (#t (error-object-message e)))
           (area-strict (triangle 1 1)))) ; the refusal, naming the set
(newline)

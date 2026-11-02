;; generators.scm — lazy sequences as ordinary closures (S9).
;;
;; A *generator* is a procedure of zero arguments. Each call answers the next
;; value of a sequence; when the sequence is exhausted it answers the unique
;; `generator-end` object instead. That is the whole protocol — SRFI 158's
;; shape, implemented with closures and `set!`, because this dialect's `call/cc`
;; is escape-only and re-entrant continuations do not exist here (docs/r7rs.md).
;;
;; The library is part of the prelude: it ships in every environment, under
;; both profiles. It is *not* an SRFI claim — `(srfi 158)` still fails loudly
;; until its exports are audited name by name (docs/SRFI_TASKS.md, S9). Where
;; a name is this project's own spelling rather than SRFI 158's, it says so.
;;
;; Sharp edge, stated once: `generator-end` is a fresh pair, so it is a value
;; like any other — a generator that can produce it legitimately would confuse
;; its consumers. Generators over data that might contain the sentinel are out
;; of scope for this first shape.

;; ------------------------------------------------------------------------- ;;
;;  The end object                                                            ;;
;; ------------------------------------------------------------------------- ;;

;; A pair built once, at load time: no other value is `eq?` to it, and a
;; user's `(list 'generator-end)` is a *different* pair. Check with
;; `generator-end?`, never by structure.
(define generator-end (list 'generator-end))

(define (generator-end? v) (eq? v generator-end))

;; ------------------------------------------------------------------------- ;;
;;  Constructors                                                              ;;
;; ------------------------------------------------------------------------- ;;

;; A generator over a list, left to right. The list is *not* copied: `rest`
;; walks it, so draining the generator costs nothing extra.
(define (list->generator lst)
  (let ((rest lst))
    (lambda ()
      (if (null? rest)
          generator-end
          (let ((v (car rest)))
            (set! rest (cdr rest))
            v)))))

;; The variadic spelling: `(generator 1 2 3)`.
(define (generator . values) (list->generator values))

;; A generator over a vector, left to right.
(define (vector->generator vec)
  (let ((i 0) (n (vector-length vec)))
    (lambda ()
      (if (>= i n)
          generator-end
          (let ((v (vector-ref vec i)))
            (set! i (+ i 1))
            v)))))

;; An integer range. One argument is infinite: `(make-range-generator 0)` is
;; 0, 1, 2, ... — and is safe precisely because consumers decide how much to
;; take. With an end (and an optional step) it is finite; a negative step
;; counts down. The step must not be zero.
(define make-range-generator
  (case-lambda
    ((start)
     (make-range-generator start #f 1))
    ((start end)
     (make-range-generator start end 1))
    ((start end step)
     (let ((current start)
           (done? (cond ((not end) (lambda (v) #f))
                        ((>= step 0) (lambda (v) (>= v end)))
                        (else (lambda (v) (<= v end))))))
       (lambda ()
         (if (done? current)
             generator-end
             (let ((v current))
               (set! current (+ current step))
               v)))))))

;; The elements of a list, over and over, forever — the laziness showcase: an
;; infinite repetition that allocates nothing per cycle. The empty list ends
;; immediately rather than looping forever.
(define (make-cycle-generator lst)
  (if (null? lst)
      (lambda () generator-end)
      (let ((rest lst))
        (lambda ()
          (if (null? rest)
              (set! rest lst))
          (let ((v (car rest)))
            (set! rest (cdr rest))
            v)))))

;; ------------------------------------------------------------------------- ;;
;;  Draining                                                                  ;;
;; ------------------------------------------------------------------------- ;;

;; The values as a list. With a second argument `k`, at most `k` of them —
;; the one place `gtake`'s work is actually done.
(define generator->list
  (case-lambda
    ((gen)
     (let loop ((acc '()))
       (let ((v (gen)))
         (if (generator-end? v)
             (reverse acc)
             (loop (cons v acc))))))
    ((gen k)
     (let loop ((k k) (acc '()))
       (if (<= k 0)
           (reverse acc)
           (let ((v (gen)))
             (if (generator-end? v)
                 (reverse acc)
                 (loop (- k 1) (cons v acc)))))))))

(define (generator->vector gen)
  (list->vector (generator->list gen)))

;; ------------------------------------------------------------------------- ;;
;;  Combinators — all lazy, all stateful closures                             ;;
;; ------------------------------------------------------------------------- ;;

;; A generator over at most the next `k` values of `gen`. Answers a
;; *generator*, so it composes with `gdrop`, `gmap`, and `gfilter` — drain it
;; with `generator->list`. If `gen` ends early, the taken generator ends
;; there too.
(define (gtake gen k)
  (let ((taken 0))
    (lambda ()
      (if (>= taken k)
          generator-end
          (let ((v (gen)))
            (cond ((generator-end? v) v)
                  (else
                   (set! taken (+ taken 1))
                   v)))))))

;; A generator over the values after the first `k`. The skipping happens once,
;; on the first pull; every later call passes straight through.
(define (gdrop gen k)
  (if (<= k 0)
      gen
      (let ((skipped? #f))
        (lambda ()
          (if skipped?
              (gen)
              (let loop ((discarded 0))
                (let ((v (gen)))
                  (cond ((generator-end? v) v)
                        ((< discarded k) (loop (+ discarded 1)))
                        (else
                         (set! skipped? #t)
                         v)))))))))

;; The multi-generator workhorse: `(gmap f gen ...)` answers a generator over
;; `(f v1 v2 ...)`, pulling one value from each generator per step and
;; stopping at the first exhaustion — the SRFI 1 `map` rule, made lazy.
(define (gmap/bundled f gens)
  (lambda ()
    (let loop ((gens gens) (vals '()))
      (cond ((null? gens)
             (apply f (reverse vals)))
            (else
             (let ((v ((car gens))))
               (if (generator-end? v)
                   generator-end
                   (loop (cdr gens) (cons v vals)))))))))

(define (gmap f . gens)
  (if (null? gens)
      (error "gmap: at least one generator is required")
      (gmap/bundled f gens)))

;; Only the values the predicate accepts. On an infinite generator whose
;; values never pass, this loops forever — the step budget is the backstop,
;; exactly as for any runaway Lisp program.
(define (gfilter pred gen)
  (lambda ()
    (let loop ()
      (let ((v (gen)))
        (cond ((generator-end? v) v)
              ((pred v) v)
              (else (loop)))))))

;; ------------------------------------------------------------------------- ;;
;;  Consuming several generators at once                                      ;;
;; ------------------------------------------------------------------------- ;;

;; `(generator-for-each proc gen ...)` runs `proc` on every value the
;; generators produce, left to right, stopping at the first exhaustion.
;; Answers `(void)`.
(define (generator-for-each proc . gens)
  (let ((gen (apply gmap list gens)))
    (let loop ()
      (let ((v (gen)))
        (if (generator-end? v)
            (void)
            (begin (apply proc v) (loop)))))))

(define (generator-fold f acc gen)
  (let loop ((acc acc))
    (let ((v (gen)))
      (if (generator-end? v)
          acc
          (loop (f v acc))))))
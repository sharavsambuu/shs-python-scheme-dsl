;; generators.scm — generators and accumulators (S9 + S12).
;;
;; A *generator* is a procedure of zero arguments. Each call answers the next
;; value of a sequence; when the sequence is exhausted it answers the
;; **eof-object** — SRFI 158's protocol, since S12. The core's `(eof-object)`
;; is the exhaustion value, checked with `eof-object?`, exactly as `read`
;; signals an empty input. (S9 originally used a custom `generator-end` pair;
;; the object is still defined below and every library procedure still
;; accepts it, so pre-S12 code keeps running — but new code should not use
;; it.)
;;
;; Generators are closures and `set!` because this dialect's `call/cc` is
;; escape-only and re-entrant continuations do not exist here (docs/r7rs.md).
;; Two SRFI 158 constructors would need re-entry and therefore fail loudly:
;; `make-coroutine-generator` and `make-for-each-generator` — the documented
;; deviation, recorded in docs/srfi.md.
;;
;; The library is prelude: it ships in every environment, under both
;; profiles. The `(srfi 158)` library entry scopes these names for the
;; import/collision rules; its export list is the SRFI 158 surface audited
;; name by name against the final specification (docs/SRFI_TASKS.md, S12).

;; ------------------------------------------------------------------------- ;;
;;  The compatibility sentinel (S9's spelling — deprecated, still accepted)   ;;
;; ------------------------------------------------------------------------- ;;

;; A pair built once, at load time: no other value is `eq?` to it. Check with
;; `generator-end?`, never by structure. S12 aligned the protocol on the
;; eof-object; this object remains only so old code keeps running.
(define generator-end (list 'generator-end))

(define (generator-end? v) (eq? v generator-end))

;; The exhaustion test every library procedure uses internally: the SRFI 158
;; eof-object first, S9's sentinel second.
(define (%end? v) (or (eof-object? v) (generator-end? v)))

;; Pull one value from each generator; #f the moment any is exhausted.
;; (A list answers true in this dialect, so #f is a safe failure mark.)
(define (%pull-all gens)
  (if (null? gens)
      '()
      (let ((v ((car gens))))
        (if (%end? v)
            #f
            (let ((rest (%pull-all (cdr gens))))
              (and rest (cons v rest)))))))

;; ------------------------------------------------------------------------- ;;
;;  Constructors                                                              ;;
;; ------------------------------------------------------------------------- ;;

;; A generator over a list, left to right. The list is *not* copied: `rest`
;; walks it, so draining the generator costs nothing extra.
(define (list->generator lst)
  (let ((rest lst))
    (lambda ()
      (if (null? rest)
          (eof-object)
          (let ((v (car rest)))
            (set! rest (cdr rest))
            v)))))

;; The variadic spelling: `(generator 1 2 3)`.
(define (generator . values) (list->generator values))

;; The values, over and over, forever. Empty args would loop on nothing, so
;; it is an error — the spec leaves an empty circular generator undefined.
(define (circular-generator . values)
  (if (null? values)
      (error "circular-generator: needs at least one value")
      (let ((rest values) (base values))
        (lambda ()
          (when (null? rest) (set! rest base))
          (let ((v (car rest)))
            (set! rest (cdr rest))
            v)))))

;; A generator over a vector, left to right. Optional start and end bounds,
;; SRFI 158's shape.
(define vector->generator
  (case-lambda
    ((vec) (vector->generator vec 0 (vector-length vec)))
    ((vec start) (vector->generator vec start (vector-length vec)))
    ((vec start end)
     (lambda ()
       (if (>= start end)
           (eof-object)
           (let ((v (vector-ref vec start)))
             (set! start (+ start 1))
             v))))))

;; A vector walked backwards, last element first.
(define reverse-vector->generator
  (case-lambda
    ((vec) (reverse-vector->generator vec 0 (vector-length vec)))
    ((vec start) (reverse-vector->generator vec start (vector-length vec)))
    ((vec start end)
     (lambda ()
       (if (<= end start)
           (eof-object)
           (let ((v (vector-ref vec (- end 1))))
             (set! end (- end 1))
             v))))))

;; A generator over a string's characters.
(define string->generator
  (case-lambda
    ((str) (string->generator str 0 (string-length str)))
    ((str start) (string->generator str start (string-length str)))
    ((str start end)
     (lambda ()
       (if (>= start end)
           (eof-object)
           (let ((v (string-ref str start)))
             (set! start (+ start 1))
             v))))))

;; A generator over a bytevector's bytes.
(define bytevector->generator
  (case-lambda
    ((bvec) (bytevector->generator bvec 0 (bytevector-length bvec)))
    ((bvec start) (bytevector->generator bvec start (bytevector-length bvec)))
    ((bvec start end)
     (lambda ()
       (if (>= start end)
           (eof-object)
           (let ((v (bytevector-u8-ref bvec start)))
             (set! start (+ start 1))
             v))))))

;; The values of a list, over and over, forever — the laziness showcase: an
;; infinite repetition that allocates nothing per cycle. The empty list ends
;; immediately rather than looping forever. (S9's spelling; SRFI 158's
;; `circular-generator`, above, takes the values instead.)
(define (make-cycle-generator lst)
  (if (null? lst)
      (lambda () (eof-object))
      (let ((rest lst) (base lst))
        (lambda ()
          (when (null? rest) (set! rest base))
          (let ((v (car rest)))
            (set! rest (cdr rest))
            v)))))

;; An integer range. One argument is infinite: `(make-range-generator 0)` is
;; 0, 1, 2, ... — safe because consumers decide how much to take. With an end
;; (and an optional step) it is finite; a negative step counts down.
(define make-range-generator
  (case-lambda
    ((start) (make-range-generator start #f 1))
    ((start end) (make-range-generator start end 1))
    ((start end step)
     (let ((current start)
           (done? (cond ((not end) (lambda (v) #f))
                        ((>= step 0) (lambda (v) (>= v end)))
                        (else (lambda (v) (<= v end))))))
       (lambda ()
         (if (done? current)
             (eof-object)
             (let ((v current))
               (set! current (+ current step))
               v)))))))

;; Exactly `count` numbers, starting at `start` (default 0) by `step`
;; (default 1).
(define make-iota-generator
  (case-lambda
    ((count) (make-iota-generator count 0 1))
    ((count start) (make-iota-generator count start 1))
    ((count start step)
     (let ((left count) (current start))
       (lambda ()
         (if (<= left 0)
             (eof-object)
             (let ((v current))
               (set! left (- left 1))
               (set! current (+ current step))
               v)))))))

;; Unfold a seed into values, SRFI 1's `unfold` made lazy: while
;; `(stop? seed)` is false, yield `(mapper seed)` and step with
;; `(successor seed)`.
(define (make-unfold-generator stop? mapper successor seed)
  (let ((state seed) (done? #f))
    (lambda ()
      (if done?
          (eof-object)
          (if (stop? state)
              (begin (set! done? #t) (eof-object))
              (let ((v (mapper state)))
                (set! state (successor state))
                v))))))

;; --- the two constructors this dialect cannot honour ---------------------- ;;
;; Both need a body that suspends mid-computation and resumes later —
;; re-entrant continuations, which this interpreter deliberately does not
;; have (docs/r7rs.md, Tier 1). They fail loudly instead of pretending.

(define (make-coroutine-generator . rest)
  (error "make-coroutine-generator: not supported here — suspending a body needs re-entrant continuations, and this dialect's call/cc is escape-only (docs/r7rs.md); build a stateful closure generator instead"))

(define (make-for-each-generator . rest)
  (error "make-for-each-generator: not supported here — driving a for-each lazily needs re-entrant continuations, and this dialect's call/cc is escape-only (docs/r7rs.md)"))

;; ------------------------------------------------------------------------- ;;
;;  Combinators — all lazy, all stateful closures                             ;;
;; ------------------------------------------------------------------------- ;;

;; SRFI 1's `cons*`, generator edition: the values, then the last argument's
;; values. `(gcons* 1 2 gen)` answers 1, 2, then whatever `gen` has.
(define (gcons* . args)
  (lambda ()
    (cond ((null? args) (eof-object))
          ((null? (cdr args)) ((car args)))
          (else
           (let ((v (car args)))
             (set! args (cdr args))
             v)))))

;; Concatenation: each generator's values in turn. `(gappend)` is empty.
(define (gappend . gens)
  (lambda ()
    (let loop ((current gens))
      (cond ((null? current) (eof-object))
            (else
             (let ((v ((car current))))
               (if (%end? v)
                   (loop (cdr current))
                   v)))))))

;; `gflatten`: the elements of the lists `gen` produces, one at a time. An
;; empty inner list contributes nothing, and exhaustion is the eof-object.
(define (gflatten gen)
  (let ((state '()) (done? #f))
    (lambda ()
      (let loop ()
        (cond (done? (eof-object))
              ((null? state)
               (let ((next (gen)))
                 (if (%end? next)
                     (begin (set! done? #t) (eof-object))
                     (begin (set! state next) (loop)))))
              (else
               (let ((obj (car state)))
                 (set! state (cdr state))
                 obj)))))))

;; Groups of `k`. With `padding`, a final short group is padded up to `k`.
(define ggroup
  (case-lambda
    ((gen k) (simple-ggroup gen k))
    ((gen k padding)
     (let ((groups (simple-ggroup gen k)))
       (lambda ()
         (let ((group (groups)))
           (cond ((%end? group) group)
                 ((= (length group) k) group)
                 (else (append group (make-list (- k (length group)) padding))))))))))

(define (simple-ggroup gen k)
  (lambda ()
    (let loop ((item (gen)) (result '()) (count (- k 1)))
      (cond ((%end? item)
             (if (null? result) item (reverse result)))
            ((= count 0) (reverse (cons item result)))
            (else (loop (gen) (cons item result) (- count 1)))))))

;; A stable merge of sorted generators: each step answers the smaller head
;; (`<?` decides; ties go left). Variadic by pairwise merging. Lazy like every
;; generator operation (SRFI 158: "return a new generator without consuming
;; any elements from the source generator(s)") — the two heads are pulled on
;; the first call of the returned generator, never at construction.
(define gmerge
  (case-lambda
    ((<?) (error "gmerge: at least one generator is required"))
    ((<? gen) gen)
    ((<? genleft genright)
     (let ((left #f) (right #f) (armed? #f))
       (lambda ()
         (if (not armed?)
             (begin (set! left (genleft))
                    (set! right (genright))
                    (set! armed? #t)))
         (cond ((and (%end? left) (%end? right)) left)
               ((%end? left) (let ((obj right)) (set! right (genright)) obj))
               ((%end? right) (let ((obj left)) (set! left (genleft)) obj))
               ((<? right left) (let ((obj right)) (set! right (genright)) obj))
               (else (let ((obj left)) (set! left (genleft)) obj))))))
    ((<? . gens)
     (let loop ((rest gens) (merged '()))
       (cond ((null? rest) (apply gmerge <? (reverse merged)))
             ((null? (cdr rest)) (apply gmerge <? (reverse (cons (car rest) merged))))
             (else (loop (cddr rest)
                         (cons (gmerge <? (car rest) (cadr rest)) merged))))))))

;; The multi-generator workhorse: `(gmap f gen ...)` answers a generator over
;; `(f v1 v2 ...)`, pulling one value from each generator per step and
;; stopping at the first exhaustion — the SRFI 1 `map` rule, made lazy.
(define gmap
  (case-lambda
    ((proc) (error "gmap: at least one generator is required"))
    ((proc gen)
     (lambda ()
       (let ((item (gen)))
         (if (%end? item) item (proc item)))))
    ((proc . gens)
     (lambda ()
       (let ((items (%pull-all gens)))
         (if items (apply proc items) (eof-object)))))))

;; A fold-shaped generator: each step pulls one value from each generator,
;; calls `(apply proc (append items (list seed)))` for two values — the new
;; pipeline value and the new seed — and answers the value.
(define (gcombine proc seed . gens)
  (lambda ()
    (let ((items (%pull-all gens)))
      (if items
          (call-with-values
              (lambda () (apply proc (append items (list seed))))
            (lambda (value newseed)
              (set! seed newseed)
              value))
          (eof-object)))))

;; Only the values the predicate accepts. On an infinite generator whose
;; values never pass, this loops forever — the step budget is the backstop,
;; exactly as for any runaway Lisp program.
(define (gfilter pred gen)
  (lambda ()
    (let loop ()
      (let ((v (gen)))
        (cond ((%end? v) v)
              ((pred v) v)
              (else (loop)))))))

;; The complement of `gfilter`.
(define (gremove pred gen)
  (gfilter (lambda (v) (not (pred v))) gen))

;; A stateful filter: `(proc value state)` answers two values — keep? and the
;; new state. A running mean behind a rolling window, for free.
(define (gstate-filter proc seed gen)
  (lambda ()
    (let loop ()
      (let ((item (gen)))
        (if (%end? item)
            item
            (call-with-values (lambda () (proc item seed))
              (lambda (yes newstate)
                (set! seed newstate)
                (if yes item (loop)))))))))

;; A generator over at most the next `k` values of `gen`. If `gen` ends
;; early, the window is padded with `padding` (the eof-object by default, so
;; an unpadded take simply ends).
(define gtake
  (case-lambda
    ((gen k) (gtake gen k (eof-object)))
    ((gen k padding)
     (let ((taken 0))
       (lambda ()
         (if (>= taken k)
             (eof-object)
             (let ((v (gen)))
               (set! taken (+ taken 1))
               (if (%end? v) padding v))))))))

;; A generator over the values after the first `k`. The skipping happens once,
;; on the first pull; every later call passes straight through.
(define (gdrop gen k)
  (if (<= k 0)
      gen
      (let ((left k) (skipped? #f))
        (lambda ()
          (if skipped?
              (gen)
              (let loop ()
                (let ((v (gen)))
                  (cond ((%end? v) (begin (set! skipped? #t) v))
                        ((> left 1)
                         (set! left (- left 1))
                         (loop))
                        (else
                         (set! skipped? #t)
                         (gen))))))))))

;; Values while the predicate holds; the first failure ends the take —
;; permanently, even though `gen` could still answer.
(define (gtake-while pred gen)
  (let ((done? #f))
    (lambda ()
      (if done?
          (eof-object)
          (let ((v (gen)))
            (cond ((%end? v) v)
                  ((pred v) v)
                  (else (set! done? #t) (eof-object))))))))

;; Skip while the predicate holds — once; afterwards everything passes.
(define (gdrop-while pred gen)
  (let ((found #f))
    (lambda ()
      (let loop ()
        (let ((v (gen)))
          (cond (found v)
                ((and (not (%end? v)) (pred v)) (loop))
                (else (set! found #t) v)))))))

;; Delete every value `equal?` (or `==`) to `item`.
(define gdelete
  (case-lambda
    ((item gen) (gdelete item gen equal?))
    ((item gen ==)
     (lambda ()
       (let loop ()
         (let ((v (gen)))
           (cond ((%end? v) v)
                 ((== item v) (loop))
                 (else v))))))))

;; Collapse runs of duplicates, keeping the first of each.
(define gdelete-neighbor-dups
  (case-lambda
    ((gen) (gdelete-neighbor-dups gen equal?))
    ((gen ==)
     (let ((firsttime #t) (prev #f))
       (lambda ()
         (if firsttime
             (begin (set! firsttime #f)
                    (set! prev (gen))
                    prev)
             (let loop ()
               (let ((v (gen)))
                 (cond ((%end? v) v)
                       ((== prev v) (loop))
                       (else (set! prev v) v))))))))))

;; The values of `value-gen` at the indices `index-gen` counts out: a value
;; appears when its index equals the count so far. Either side exhausting
;; ends the take.
(define (gindex value-gen index-gen)
  (let ((done? #f) (count 0))
    (lambda ()
      (if done?
          (eof-object)
          (let loop ((value (value-gen)) (index (index-gen)))
            (cond ((or (%end? value) (%end? index))
                   (set! done? #t)
                   (eof-object))
                  ((= index count)
                   (set! count (+ count 1))
                   value)
                  (else
                   (set! count (+ count 1))
                   (loop (value-gen) index))))))))

;; The values of `value-gen` whose `truth-gen` neighbour is true.
(define (gselect value-gen truth-gen)
  (let ((done? #f))
    (lambda ()
      (if done?
          (eof-object)
          (let loop ((value (value-gen)) (truth (truth-gen)))
            (cond ((or (%end? value) (%end? truth))
                   (set! done? #t)
                   (eof-object))
                  (truth value)
                  (else (loop (value-gen) (truth-gen)))))))))

;; ------------------------------------------------------------------------- ;;
;;  Draining                                                                  ;;
;; ------------------------------------------------------------------------- ;;

;; All the values (or, with `k`, at most `k` of them).
(define generator->list
  (case-lambda
    ((gen) (reverse (generator->reverse-list gen)))
    ((gen k) (reverse (generator->reverse-list gen k)))))

;; The values, reversed — the fold-shaped drain the others build on.
(define generator->reverse-list
  (case-lambda
    ((gen) (generator->reverse-list gen #f))
    ((gen k)
     (let loop ((acc '()) (left (or k #f)))
       (if (and k (<= left 0))
           acc
           (let ((v (gen)))
             (if (%end? v)
                 acc
                 (loop (cons v acc) (and k (- left 1))))))))))

;; All the values (or the first `k`) as a vector.
(define generator->vector
  (case-lambda
    ((gen) (list->vector (generator->list gen)))
    ((gen k) (list->vector (generator->list gen k)))))

;; Fill a vector from `at`; answers how many values were written — stopping
;; at exhaustion *or* the end of the vector.
(define (generator->vector! vector at gen)
  (let loop ((value (gen)) (count 0) (pos at))
    (cond ((%end? value) count)
          ((>= pos (vector-length vector)) count)
          (else
           (vector-set! vector pos value)
           (loop (gen) (+ count 1) (+ pos 1))))))

;; The characters as a string (or the first `k` of them).
(define generator->string
  (case-lambda
    ((gen) (list->string (generator->list gen)))
    ((gen k) (list->string (generator->list gen k)))))

;; The left fold over the values, one generator or many: `(f v1 ... vn acc)`.
(define (generator-fold f seed . gens)
  (let loop ((acc seed))
    (let ((items (%pull-all gens)))
      (if items
          (loop (apply f (append items (list acc))))
          acc))))

;; `(f v1 ... vn)` collected into a list, left to right.
(define (generator-map->list f . gens)
  (let loop ((result '()))
    (let ((items (%pull-all gens)))
      (if items
          (loop (cons (apply f items) result))
          (reverse result)))))

;; Run `proc` on every value, left to right, stopping at the first
;; exhaustion. Answers `(void)`.
(define (generator-for-each proc . gens)
  (let loop ()
    (let ((items (%pull-all gens)))
      (if items
          (begin (apply proc items) (loop))
          (void)))))

;; The first value satisfying `pred`, or `#f`.
(define (generator-find pred gen)
  (let loop ()
    (let ((v (gen)))
      (cond ((%end? v) #f)
            ((pred v) v)
            (else (loop))))))

;; How many values satisfy `pred`.
(define (generator-count pred gen)
  (generator-fold (lambda (v n) (if (pred v) (+ 1 n) n)) 0 gen))

;; `(pred v)` of the first value that passes, else `#f`.
(define (generator-any pred gen)
  (let loop ()
    (let ((v (gen)))
      (cond ((%end? v) #f)
            ((pred v))
            (else (loop))))))

;; The last truthy `(pred v)`, or `#f` — `#t` when the generator is empty.
(define (generator-every pred gen)
  (let loop ((last #t))
    (let ((v (gen)))
      (if (%end? v)
          last
          (let ((r (pred v)))
            (if r (loop r) #f))))))

;; SRFI 1's `unfold` driven by a generator: the user hands us the unfold, so
;; no library dependency is baked in.
(define (generator-unfold g unfold . args)
  (apply unfold eof-object? (lambda (x) x) (lambda (x) (g)) (g) args))

;; ------------------------------------------------------------------------- ;;
;;  Accumulators — the sink half of SRFI 158                                  ;;
;; ------------------------------------------------------------------------- ;;

;; An accumulator is a procedure of one argument: pass it a value and it is
;; added to the state (the answer is unspecified); pass it the eof-object and
;; it answers the accumulated value.
(define (make-accumulator kons knil finalize)
  (let ((state knil))
    (lambda (obj)
      (if (eof-object? obj)
          (finalize state)
          (begin
            (set! state (kons obj state))
            (void))))))

(define (count-accumulator)
  (make-accumulator (lambda (obj state) (+ 1 state)) 0 (lambda (x) x)))

(define (list-accumulator)
  (make-accumulator cons '() reverse))

(define (reverse-list-accumulator)
  (make-accumulator cons '() (lambda (x) x)))

(define (vector-accumulator)
  (make-accumulator cons '() (lambda (x) (list->vector (reverse x)))))

(define (reverse-vector-accumulator)
  (make-accumulator cons '() list->vector))

;; Fill a pre-made vector from `at` on; answers the vector on eof.
(define (vector-accumulator! vec at)
  (lambda (obj)
    (if (eof-object? obj)
        vec
        (begin
          (vector-set! vec at obj)
          (set! at (+ at 1))
          (void)))))

(define (%list->bytevector lst)
  (let ((vec (make-bytevector (length lst) 0)))
    (let loop ((i 0) (rest lst))
      (if (null? rest)
          vec
          (begin
            (bytevector-u8-set! vec i (car rest))
            (loop (+ i 1) (cdr rest)))))))

(define (string-accumulator)
  (make-accumulator cons '() (lambda (lst) (list->string (reverse lst)))))

(define (bytevector-accumulator)
  (make-accumulator cons '() (lambda (lst) (%list->bytevector (reverse lst)))))

(define (bytevector-accumulator! bvec at)
  (lambda (obj)
    (if (eof-object? obj)
        bvec
        (begin
          (bytevector-u8-set! bvec at obj)
          (set! at (+ at 1))
          (void)))))

(define (sum-accumulator)
  (make-accumulator + 0 (lambda (x) x)))

(define (product-accumulator)
  (make-accumulator * 1 (lambda (x) x)))





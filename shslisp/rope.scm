;; rope.scm — Result, Kleisli composition, and the ROP style, in the DSL.
;;
;; ROP ("railway oriented programming") is a way of writing a fallible
;; computation as a *chain* instead of a nest of checks. Each step returns a
;; value that says which rail it is on, and the chain itself short-circuits: the
;; first refusal stops the train and every later step is simply not run. There
;; is no orchestrating `if/else` — the pipeline *is* the control flow.
;;
;; Two ingredients, and both are ordinary Lisp:
;;
;;   1. `Result` — a closed variant: `(ok value)` or `(err reason)`. The type is
;;      declared once with `define-variant`, which is what lets `match` name a
;;      case you forgot instead of quietly defaulting.
;;   2. Kleisli composition — `>=>` (the fish operator), `pipe-results`, and a
;;      `result-do` do-notation, all built on the single operation `result-bind`.
;;
;; The names line up with the pure-Python toolkit next door
;; (`python_tetris/fp/result.py`, `fp/kleisli.py`), so the two editions are
;; readable side by side. The laws those modules pin — left identity, right
;; identity, associativity — are pinned for this one too (tests/test_rop.py).
;;
;; A note on names: the Tetris domain installs its own rail tests, `success?`
;; and `failure?`, over its `Success`/`Failure` — named for the domain's own
;; constructors, so they never read as the constructors for this library's
;; `ok`/`err`. This library therefore spells its predicates `result-ok?` /
;; `result-err?`; `as-result` (in tetris/prelude.scm) lifts a domain result
;; onto these rails.

;; ------------------------------------------------------------------------- ;;
;;  The type                                                                   ;;
;; ------------------------------------------------------------------------- ;;

;; `define-variant` gives us, for free: the constructors `ok` and `err`, the
;; accessors `ok-value` and `err-reason`, and the predicate `result?`.
(define-variant result
  (ok value)
  (err reason))

(define (result-ok? r) (and (result? r) (eq? (tag-of r) 'ok)))
(define (result-err? r) (and (result? r) (eq? (tag-of r) 'err)))

;; ------------------------------------------------------------------------- ;;
;;  The functor and the monad                                                  ;;
;; ------------------------------------------------------------------------- ;;

;; `map` touches the value on the success rail and leaves a refusal alone.
(define (result-map r f)
  (if (result-ok? r) (ok (f (ok-value r))) r))

;; `map-err` is the mirror image: recover or re-describe a refusal.
(define (result-map-err r f)
  (if (result-err? r) (err (f (err-reason r))) r))

;; `map2` combines two successes; the first refusal wins.
(define (result-map2 ra rb f)
  (if (result-err? ra)
      ra
      (if (result-err? rb) rb (ok (f (ok-value ra) (ok-value rb))))))

;; `bind` is the one primitive: run *f* only on the success rail. Every other
;; operation in this file is built from it, which is why there is only one
;; place a short-circuit can be implemented (or got wrong).
(define (result-bind r f)
  (if (result-ok? r) (f (ok-value r)) r))

;; `bimap` maps both rails at once — the "handle it either way" operation.
(define (result-bimap r on-ok on-err)
  (if (result-ok? r) (ok (on-ok (ok-value r))) (err (on-err (err-reason r)))))

;; `fold` collapses a Result to a plain value: the caller must name both rails.
(define (result-fold r on-ok on-err)
  (if (result-ok? r) (on-ok (ok-value r)) (on-err (err-reason r))))

;; Lift a plain value onto the success rail (the monad's `return`).
(define (result-pure x) (ok x))

;; ------------------------------------------------------------------------- ;;
;;  Leaving the rails — reading the value back out                             ;;
;; ------------------------------------------------------------------------- ;;

(define (result-unwrap r)
  (if (result-ok? r) (ok-value r) (error "result-unwrap: called on err" (err-reason r))))

(define (result-unwrap-or r default)
  (if (result-ok? r) (ok-value r) default))

(define (result-unwrap-or-else r on-err)
  (if (result-ok? r) (ok-value r) (on-err (err-reason r))))

(define (result-expect r message)
  (if (result-ok? r) (ok-value r) (error message (err-reason r))))

;; The success rail as a 0- or 1-element list — handy for `apply`/`length`.
(define (result->list r) (if (result-ok? r) (list (ok-value r)) '()))

;; The declared, closed set of tags, as data.
(define (result-tags) (variant-tags 'result))

;; ------------------------------------------------------------------------- ;;
;;  Kleisli composition — the pipeline                                         ;;
;; ------------------------------------------------------------------------- ;;

;; A *Kleisli arrow* is a function A -> Result. `>=>` (the fish operator)
;; composes two of them into one, left to right, short-circuiting in between.
(define (>=> f g)
  (lambda (x) (result-bind (f x) g)))

;; `pipe-results` threads a starting value through any number of arrows. The
;; value is lifted with `ok` first, so the first arrow sees a plain value and
;; every later one sees the previous success — or nobody sees anything after the
;; first refusal.
(define (pipe-results-list x steps)
  (foldl (lambda (step acc) (result-bind acc step)) (ok x) steps))

(define (pipe-results x . steps) (pipe-results-list x steps))

;; ------------------------------------------------------------------------- ;;
;;  Collections of Results                                                     ;;
;; ------------------------------------------------------------------------- ;;

;; `sequence-results` turns a list of Results into a Result of a list: all-ok
;; gives every value, and the *first* refusal is the whole answer.
(define (sequence-results rs)
  (let loop ((rs rs) (acc '()))
    (cond ((null? rs) (ok (reverse acc)))
          ((result-err? (car rs)) (car rs))
          (else (loop (cdr rs) (cons (ok-value (car rs)) acc))))))

;; `traverse-results` maps a fallible function over a list and collects it.
(define (traverse-results f xs) (sequence-results (map f xs)))

;; Reading a *list* of Results when short-circuiting is not what you want.
(define (ok-values rs) (map ok-value (filter result-ok? rs)))
(define (err-reasons rs) (map err-reason (filter result-err? rs)))
(define (first-err rs) (find result-err? rs))
(define (count-errs rs) (count result-err? rs))

;; ------------------------------------------------------------------------- ;;
;;  Glue with the condition system                                             ;;
;; ------------------------------------------------------------------------- ;;

;; `attempt` runs a thunk and puts a *raised* value on the failure rail, so an
;; ordinary raising computation can join the pipeline. It is a procedure, not a
;; macro, so it cannot capture a name in the caller's expression.
(define (attempt thunk)
  (guard (e (#t (err e)))
    (ok (thunk))))

;; ------------------------------------------------------------------------- ;;
;;  Do-notation                                                                ;;
;; ------------------------------------------------------------------------- ;;

;; `(result-do (name <- step) ... final)` reads like imperative code but is
;; `result-bind` all the way down. `_` discards a step's value. Like every macro
;; here it is hygienic: the `name`s and the internal bindings are the caller's
;; and the template's respectively, and neither can capture the other.
(define-syntax result-do
  (syntax-rules (<-)
    ((_ (name <- expr) rest ...)
     (result-bind expr (lambda (name) (result-do rest ...))))
    ((_ expr) expr)
    ((_) (ok (void)))))

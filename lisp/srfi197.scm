;;; SRFI 197 — pipeline operators: chain, chain-and, chain-when,
;;; chain-lambda, nest, nest-reverse.
;;;
;;; This file is the (srfi 197) library's private implementation. Every macro
;;; does its work entirely at *expansion* time — the generated code references
;;; only core names (`apply`, `call-with-values`, `lambda`, `let`, `if`) — so
;;; the expansion is safe in any scope and no helper has to be embedded as a
;;; value.
;;;
;;; `chain` evaluates steps left to right, threading the pipeline value(s):
;;; a step's `_` placeholders are replaced by the previous step's values (in
;;; order, so multiple values fan out across multiple placeholders), and a
;;; trailing `_ ...` collects all remaining values into an `apply`. The
;;; expansion is a nest of `call-with-values`, so steps may return multiple
;;; values and the last step's values are the result.
;;;
;;; `nest`/`nest-reverse` substitute *lexically* and evaluate once at the end,
;;; which is what lets them build quoted data and contain special forms.

;; -- expansion-time helpers ------------------------------------------------ #

;; Parse `(initial [placeholder [ellipsis]] steps...)` — a symbol second
;; argument is a custom placeholder, a symbol third argument is a custom
;; ellipsis; both default to `_` and `...`.
(define (srfi197:parse args who)
  (if (null? args)
      (error "srfi 197:" who "needs an initial value"))
  (let ((initial (car args)) (rest (cdr args)))
    (cond
      ((null? rest)
       (values initial '_ '... '()))
      ((symbol? (car rest))
       (let ((ph (car rest)) (more (cdr rest)))
         (cond
           ((null? more)
            (values initial ph '... '()))
           ((symbol? (car more))
            (values initial ph (car more) (cdr more)))
           (else
            (values initial ph '... more)))))
      (else
       (values initial '_ '... rest)))))

;; Like srfi197:parse, but without an ellipsis (chain-and, chain-when): a
;; second symbol argument is the placeholder, and that is all.
(define (srfi197:parse-no-ellipsis args who)
  (if (null? args)
      (error "srfi 197:" who "needs an initial value"))
  (let ((initial (car args)) (rest (cdr args)))
    (cond
      ((null? rest)
       (values initial '_ '()))
      ((symbol? (car rest))
       (values initial (car rest) (cdr rest)))
      (else
       (values initial '_ rest)))))

(define (srfi197:check-steps steps who)
  (if (null? steps)
      #f
      (let ((step (car steps)))
        (if (not (and (pair? step) (not (null? step))))
            (error "srfi 197: each step must be a non-empty list, in" who)
            (srfi197:check-steps (cdr steps) who)))))

;; Count a step's placeholders and validate the ellipsis: it may only appear
;; at the very end of a step, immediately after a placeholder. Answers two
;; values: the placeholder count (including the one before the ellipsis) and
;; whether the step ends with the ellipsis.
(define (srfi197:analyze step ph ell)
  (let loop ((node step) (n 0) (prev-ph #f))
    (cond
      ((null? node) (values n #f))
      ((pair? node)
       (let ((elt (car node)))
         (cond
           ((eq? elt ell)
            (if (and (null? (cdr node)) prev-ph)
                (values n #t)
                (error "srfi 197: the ellipsis must immediately follow a placeholder, at the end of a step")))
           ((eq? elt ph)
            (loop (cdr node) (+ n 1) #t))
           (else
            (loop (cdr node) n #f)))))
      (else
       (error "srfi 197: a step must be a proper list")))))

;; For chain-and / chain-when: at most one placeholder, never an ellipsis.
;; Answers the placeholder count (0 or 1).
(define (srfi197:analyze-single step ph ell)
  (let loop ((node step) (n 0))
    (cond
      ((null? node) n)
      ((pair? node)
       (let ((elt (car node)))
         (cond
           ((eq? elt ell)
            (error "srfi 197: this form does not support the ellipsis"))
           ((eq? elt ph)
            (if (= n 1)
                (error "srfi 197: at most one placeholder per step here")
                (loop (cdr node) (+ n 1)))
            )
           (else
            (loop (cdr node) n)))))
      (else
       (error "srfi 197: a step must be a proper list")))))

;; Rewrite a step: each placeholder becomes the next var from `vars`; a
;; trailing `placeholder ellipsis` collapses into `(apply <head> ... rest-var)`.
(define (srfi197:rewrite step ph ell vars rest-var)
  (let loop ((node step) (acc '()) (vs vars))
    (cond
      ((null? node) acc)
      ((pair? node)
       (let ((elt (car node)) (more (cdr node)))
         (cond
           ((and (eq? elt ph) (pair? more) (eq? (car more) ell))
            (cons 'apply (append acc (list rest-var))))
           ((eq? elt ph)
            (loop more (append acc (list (car vs))) (cdr vs)))
           (else
            (loop more (append acc (list elt)) vs)))))
      (else
       (error "srfi 197: a step must be a proper list")))))

;; (v1 ... vk . restv) — a dotted formal chain ending in restv.
(define (srfi197:dotted-chain vs restv)
  (if (null? vs)
      restv
      (cons (car vs) (srfi197:dotted-chain (cdr vs) restv))))

;; The formal group for one step: a trailing `placeholder ellipsis` binds the
;; rest variable (plus one var per placeholder *before* it); k plain
;; placeholders bind (v1 ... vk); no placeholders bind one discarded variable
;; (the value is still evaluated). Answers three values: the group, the
;; per-placeholder replacement vars, and the rest variable (#f when there is
;; no ellipsis).
(define (srfi197:make-group n has-ell)
  (if (and (= n 0) (not has-ell))
      (values (list (gensym)) '() #f)
      (let build ((i 0) (group '()) (repls '()))
        (cond
          ((and has-ell (= i (- n 1)))
           ;; the final placeholder merges into the rest variable
           (let ((restv (gensym)))
             (values (srfi197:dotted-chain group restv) repls restv)))
          ((< i n)
           (let ((v (gensym)))
             (build (+ i 1) (append group (list v)) (append repls (list v)))))
          (else
           (values group repls #f))))))

;; -- chain ------------------------------------------------------------------ #

;; Bind group_i to expr_i (the initial value, then each rewritten step); the
;; body is the last rewritten step, so the last step's values are the result.
(define (srfi197:chain-build groups exprs)
  (if (null? groups)
      (car exprs)
      (list 'call-with-values
            (list 'lambda '() (car exprs))
            (list 'lambda
                  (car groups)
                  (srfi197:chain-build (cdr groups) (cdr exprs))))))

(define (srfi197:chain-expand initial ph ell steps)
  (let loop ((in steps) (groups '()) (exprs (list initial)))
    (if (null? in)
        (srfi197:chain-build groups exprs)
        (call-with-values
         (lambda () (srfi197:analyze (car in) ph ell))
         (lambda (n has-ell)
           (call-with-values
            (lambda () (srfi197:make-group n has-ell))
            (lambda (group repls rest-var)
              (loop (cdr in)
                    (append groups (list group))
                    (append exprs
                            (list (srfi197:rewrite (car in) ph ell
                                                   repls rest-var)))))))))))

(defmacro (chain . args)
  (call-with-values
   (lambda () (srfi197:parse args 'chain))
   (lambda (initial ph ell steps)
     (srfi197:check-steps steps 'chain)
     (srfi197:chain-expand initial ph ell steps))))

;; -- chain-and --------------------------------------------------------------- #

;; (let ((v1 e1)) (if v1 (let ((v2 e2)) (if v2 ... last)) #f)) — the pipeline
;; value is checked even when the step has no placeholder; the last step's
;; value is the result and is not checked.
(define (srfi197:chain-and-build vars exprs)
  (if (null? vars)
      (car exprs)
      (list 'let
            (list (list (car vars) (car exprs)))
            (list 'if
                  (car vars)
                  (srfi197:chain-and-build (cdr vars) (cdr exprs))
                  #f))))

(defmacro (chain-and . args)
  (call-with-values
   (lambda () (srfi197:parse-no-ellipsis args 'chain-and))
   (lambda (initial ph steps)
     (srfi197:check-steps steps 'chain-and)
     (if (null? steps)
         initial
         (let build ((in steps) (vars '()) (exprs (list initial)))
           (if (null? in)
               (srfi197:chain-and-build vars exprs)
               (let ((step (car in)))
                 (srfi197:analyze-single step ph '...)
                 (let ((v (gensym)))
                   (build (cdr in)
                          (append vars (list v))
                          (append exprs
                                  (list (srfi197:rewrite step ph '... (list v) #f))))))))))))

;; -- chain-when --------------------------------------------------------------- #

;; out starts as the initial value; each (guard step) wraps it in
;; (let ((cv out)) (if guard step' cv)) — a skipped step reuses the previous
;; value without evaluating the step.
(defmacro (chain-when . args)
  (call-with-values
   (lambda () (srfi197:parse-no-ellipsis args 'chain-when))
   (lambda (initial ph steps)
     (if (null? steps)
         initial
         (let loop ((in steps) (out initial))
           (if (null? in)
               out
               (let* ((elt (car in))
                      (parsed
                       (cond
                         ((and (pair? elt) (pair? (cdr elt)))
                          (cons (car elt) (car (cdr elt))))
                         ((pair? elt)
                          (cons #t (car elt)))
                         (else
                          (error "srfi 197: each chain-when step is (guard step) or (step)"))))
                      (v (gensym)))
                 (loop (cdr in)
                       (list 'let
                             (list (list v out))
                             (list 'if (car parsed)
                                   (srfi197:rewrite (cdr parsed) ph '... (list v) #f)
                                   v))))))))))


;; -- argument parsing for the forms without an initial value ----------------- #

;; (chain-lambda [ph [ell]] step ...) — steps are required. A leading symbol
;; is a custom placeholder; a second leading symbol is a custom ellipsis.
(define (srfi197:parse-arguments args who)
  (cond
    ((null? args)
     (error "srfi 197:" who "needs at least one step"))
    ((symbol? (car args))
     (let ((ph (car args)) (rest (cdr args)))
       (cond
         ((null? rest)
          (error "srfi 197:" who "needs at least one step"))
         ((symbol? (car rest))
          (values ph (car rest) (cdr rest)))
         (else
          (values ph '_ rest)))))
    (else
     (values '_ '... args))))

(define (srfi197:last-of xs who)
  (if (null? (cdr xs))
      (car xs)
      (srfi197:last-of (cdr xs) who)))

(define (srfi197:all-but-last xs who)
  (if (null? xs)
      (error "srfi 197:" who "needs a final value")
      (if (null? (cdr xs))
          '()
          (cons (car xs) (srfi197:all-but-last (cdr xs) who)))))

;; -- chain-lambda ------------------------------------------------------------ #

;; The first step's placeholders are the procedure's parameters; a trailing
;; `placeholder ellipsis` makes it variadic. The first step's value feeds the
;; remaining steps as a chain.
(define (srfi197:chain-lambda-expand ph ell steps)
  (let* ((first (car steps))
         (rest (cdr steps)))
    (call-with-values
     (lambda () (srfi197:analyze first ph ell))
     (lambda (n has-ell)
       (call-with-values
        (lambda () (srfi197:make-group n has-ell))
        (lambda (group repls rest-var)
          ;; n = 0 without an ellipsis means a zero-argument procedure, not a
          ;; discarded value: fix up the group the chain path built.
          (let* ((group (if (and (= n 0) (not has-ell)) '() group))
                 (body (srfi197:rewrite first ph ell repls rest-var)))
            (list 'lambda
                  group
                  (if (null? rest)
                      body
                      (srfi197:chain-expand body ph ell rest))))))))))

(defmacro (chain-lambda . args)
  (call-with-values
   (lambda () (srfi197:parse-arguments args 'chain-lambda))
   (lambda (ph ell steps)
     (srfi197:check-steps steps 'chain-lambda)
     (srfi197:chain-lambda-expand ph ell steps))))

;; -- nest / nest-reverse ------------------------------------------------------ #

;; Lexically replace the placeholder in a step (top level, exactly once) with
;; the accumulated form.
(define (srfi197:nest-subst step ph replacement)
  (let loop ((node step) (acc '()) (seen #f))
    (cond
      ((null? node)
       (if seen acc (error "srfi 197: nest: each step must contain the placeholder")))
      ((pair? node)
       (let ((elt (car node)))
         (cond
           ((eq? elt ph)
            (if seen
                (error "srfi 197: nest: only one placeholder per step")
                (loop (cdr node) (append acc (list replacement)) #t)))
           (else
            (loop (cdr node) (append acc (list elt)) seen)))))
      (else
       (error "srfi 197: nest: a step must be a proper list")))))

;; (nest [ph] step ... last): the placeholder in the last step is replaced by
;; last, then the next-to-last, and so on; the final form is evaluated once.
(define (srfi197:nest-expand ph steps last)
  (let loop ((in (reverse steps)) (acc last))
    (if (null? in)
        acc
        (loop (cdr in) (srfi197:nest-subst (car in) ph acc)))))

(defmacro (nest . args)
  (if (null? args)
      (error "srfi 197: nest needs a final value"))
  (if (symbol? (car args))
      ;; (nest placeholder step ... last) — or (nest placeholder last)
      (if (null? (cdr args))
          (error "srfi 197: nest needs a final value")
          (srfi197:nest-expand (car args)
                               (srfi197:all-but-last (cdr args) 'nest)
                               (srfi197:last-of (cdr args) 'nest)))
      ;; (nest step ... last)
      (if (null? (cdr args))
          (car args)
          (srfi197:nest-expand '_
                               (srfi197:all-but-last args 'nest)
                               (srfi197:last-of args 'nest)))))

;; (nest-reverse [ph] first step ...): the placeholder in the first step is
;; replaced by first, then forward through the remaining steps.
(define (srfi197:nest-reverse-expand first ph steps)
  (let loop ((in steps) (acc first))
    (if (null? in)
        acc
        (loop (cdr in) (srfi197:nest-subst (car in) ph acc)))))

(defmacro (nest-reverse . args)
  (cond
    ((null? args)
     (error "srfi 197: nest-reverse needs a first value"))
    ((null? (cdr args))
     (car args))
    ((symbol? (car (cdr args)))
     ;; (nest-reverse first placeholder step ...)
     (srfi197:nest-reverse-expand (car args)
                                  (car (cdr args))
                                  (cdr (cdr args))))
    (else
     ;; (nest-reverse first step ...)
     (srfi197:nest-reverse-expand (car args) '_ (cdr args)))))


;;; SRFI 89 — `define*` / `lambda*`: optional positional and named parameters.
;;;
;;; This file is the (srfi 89) library's private implementation, loaded into
;;; a scope whose parent is the interaction environment. `lambda*` expands to
;;; an ordinary `lambda` over a single rest parameter plus a runtime binder
;;; (SRFI 89's recommended shape), so `Closure`, `_bind`, `apply`, and
;;; `procedure-arity` are untouched. `define*` is a thin rewrite onto
;;; `lambda*`.
;;;
;;; A formal parameter list has up to three sections, in either order:
;;;
;;;   positional:  required `v`, then optional `(v default)`
;;;   named:       `(keyword v)` required, `(keyword v default)` optional
;;;   rest:        `. r` last
;;;
;;; All variables are distinct; all keywords are distinct. Defaults are
;;; evaluated left to right, at most once, in the scope of the parameters
;;; bound before them — which is why the expansion binds everything with one
;;; `let*` and puts each default behind an `if` instead of handing it to a
;;; runtime helper.

(define srfi89:required 'srfi89:required)

;; -- runtime helpers (run at call time) ------------------------------------ #

(define (srfi89:list-take xs n)
  (if (or (= n 0) (null? xs))
      '()
      (cons (car xs) (srfi89:list-take (cdr xs) (- n 1)))))

(define (srfi89:list-drop xs n)
  (if (or (= n 0) (null? xs))
      xs
      (srfi89:list-drop (cdr xs) (- n 1))))

;; Pull the keyword/value pairs out of the argument list (they may appear
;; anywhere), then split what is left into positionals and the rest tail.
;; Answers three values: the positional arguments, the tail, and an alist of
;; the supplied keywords.
(define (srfi89:split args name req opt kws has-rest)
  (let loop ((node args) (plain '()) (kwal '()))
    (cond
      ((null? node)
       (srfi89:finish (reverse plain) kwal name req opt has-rest))
      ((keyword? (car node))
       (if (null? (cdr node))
           (error "srfi 89: keyword without a value, calling" name)
           (let ((kw (car node)) (val (car (cdr node))))
             (if (not (memq kw kws))
                 (error "srfi 89: unknown keyword, calling" name kw)
                 (if (assq kw kwal)
                     (error "srfi 89: duplicate keyword, calling" name kw)
                     (loop (cdr (cdr node)) plain (cons (cons kw val) kwal)))))))
      (else
       (loop (cdr node) (cons (car node) plain) kwal)))))

(define (srfi89:finish plain kwal name req opt has-rest)
  (let ((n (length plain)))
    (if (< n req)
        (error "srfi 89: too few arguments, calling" name)
        (if (and (not has-rest) (> n (+ req opt)))
            (error "srfi 89: too many arguments, calling" name)
            (values (srfi89:list-take plain (+ req opt))
                    (srfi89:list-drop plain (+ req opt))
                    kwal)))))

(define (srfi89:asskw kwal kw)
  (cond ((null? kwal) #f)
        ((eq? (car (car kwal)) kw) (car kwal))
        (else (srfi89:asskw (cdr kwal) kw))))

(define (srfi89:missing-kw kw)
  (error "srfi 89: missing required keyword" kw))

(define (srfi89:ref xs i)
  ;; positional argument i; the split validated the count, so this is a guard
  (cond ((null? xs) (error "srfi 89: internal: missing positional argument"))
        ((= i 0) (car xs))
        (else (srfi89:ref (cdr xs) (- i 1)))))

;; -- expansion-time machinery ---------------------------------------------- #

;; Parse a formals list into three values: the positional specs
;; ((v default) ...), the named specs ((keyword v default) ...), and the rest
;; parameter (a symbol, or #f). Works on dotted Pair chains and on plain
;; lists; a `.` element (a form built programmatically) also ends the
;; positional section.
(define (srfi89:parse formals)
  (let loop ((node formals) (pos '()) (named '()))
    (cond
      ((null? node)
       (values pos named #f))
      ((symbol? node)
       (values pos named node))
      ((pair? node)
       (let ((elt (car node)) (more (cdr node)))
         (if (eq? elt '.)
             (values pos named (car more))
             (call-with-values
              (lambda () (srfi89:parse-elt elt pos named))
              (lambda (pos2 named2) (loop more pos2 named2))))))
      (else
       (error "srfi 89: bad formal parameter list")))))

(define (srfi89:parse-elt elt pos named)
  (cond
    ((symbol? elt)
     (values (append pos (list (list elt srfi89:required))) named))
    ((pair? elt)
     (let ((head (car elt)) (rest (cdr elt)))
       (cond
         ((keyword? head)
          ;; named: (keyword v) or (keyword v default)
          (let ((v (car rest)) (d (cdr rest)))
            (cond
              ((not (symbol? v))
               (error "srfi 89: a named parameter needs a variable after its keyword"))
              ((null? d)
               (values pos (append named (list (list head v srfi89:required)))))
              ((and (pair? d) (null? (cdr d)))
               (values pos (append named (list (list head v (car d))))))
              (else
               (error "srfi 89: bad named parameter: (keyword v) or (keyword v default)")))))
         ((symbol? head)
          ;; optional positional: (v default)
          (if (and (pair? rest) (null? (cdr rest)))
              (values (append pos (list (list head (car rest)))) named)
              (error "srfi 89: bad optional parameter: (v default) expected")))
         (else
          (error "srfi 89: bad formal parameter")))))
    (else
     (error "srfi 89: bad formal parameter"))))



(define (srfi89:all-required? pos)
  (cond ((null? pos) #t)
        ((eq? (car (cdr (car pos))) srfi89:required)
         (srfi89:all-required? (cdr pos)))
        (else #f)))

(define (srfi89:count-required pos)
  (cond ((null? pos) 0)
        ((eq? (car (cdr (car pos))) srfi89:required)
         (+ 1 (srfi89:count-required (cdr pos))))
        (else 0)))

(define (srfi89:distinct? xs)
  (cond ((null? xs) #t)
        ((memq (car xs) (cdr xs)) #f)
        (else (srfi89:distinct? (cdr xs)))))

(define (srfi89:check pos named)
  (let ((vars (append (map car pos)
                      (map (lambda (spec) (car (cdr spec))) named)))
        (kws (map car named)))
    (if (not (srfi89:distinct? vars))
        (error "srfi 89: duplicate parameter name"))
    (if (not (srfi89:distinct? kws))
        (error "srfi 89: duplicate keyword"))))

;; Generated code for each positional parameter: a required one reads slot i
;; (the split validated the count); an optional one evaluates its default —
;; once, in the let* scope of the parameters bound before it — only when the
;; slot is absent. The srfi89 helpers are embedded as *values* (the closures
;; themselves), not names: the expansion runs in the caller's scope, where
;; this library's private names are not visible.
(define (srfi89:pos-bindings pos posv i)
  (if (null? pos)
      '()
      (let* ((spec (car pos))
             (v (car spec))
             (d (car (cdr spec)))
             (binding
              (if (eq? d srfi89:required)
                  (list v (list srfi89:ref posv i))
                  (list v (list 'if (list '< (list 'length posv) (+ i 1))
                                d
                                (list 'list-ref posv i))))))
        (cons binding (srfi89:pos-bindings (cdr pos) posv (+ i 1))))))

;; Generated code for each named parameter: look the keyword up in the
;; supplied alist; absent means the default (or an error for a required
;; named parameter). The lookup is a generated `if`, so the default is
;; evaluated once and only when absent.
(define (srfi89:named-bindings named kwal)
  (if (null? named)
      '()
      (let* ((spec (car named))
             (kw (car spec))
             (v (car (cdr spec)))
             (d (car (cdr (cdr spec))))
             (cell (gensym))
             (else-expr
              (if (eq? d srfi89:required)
                  (list srfi89:missing-kw kw)
                  d))
             (binding
              (list v
                    (list 'let (list (list cell (list srfi89:asskw kwal kw)))
                          (list 'if cell (list 'cdr cell) else-expr)))))
        (cons binding (srfi89:named-bindings (cdr named) kwal)))))

;; The whole expansion: one ordinary `lambda` over a single rest parameter
;; (the bare-symbol formals list), a `call-with-values` split, then one
;; `let*` that binds every parameter in formals order — positionals, then
;; named, then the rest — so defaults see the parameters bound before them.
(define (srfi89:generate pos named rest body)
  (let* ((all (gensym))
         (posv (gensym))
         (tail (gensym))
         (kwal (gensym))
         (req (srfi89:count-required pos))
         (opt (- (length pos) req))
         (kws (map car named))
         (bindings
          (append
           (srfi89:pos-bindings pos posv 0)
           (srfi89:named-bindings named kwal)
           (if rest (list (list rest tail)) '()))))
    (list 'lambda
          all
          (list 'call-with-values
                (list 'lambda
                      '()
                      (list srfi89:split
                            all
                            (list 'quote 'lambda*)
                            req
                            opt
                            (cons 'list kws)
                            (if rest #t #f)))
                (cons 'lambda
                      (cons (list posv tail kwal)
                            (list (cons 'let* (cons bindings body)))))))))

(define (srfi89:expand formals body)
  (call-with-values
   (lambda () (srfi89:parse formals))
   (lambda (pos named rest)
     (srfi89:check pos named)
     (if (and (null? named) (srfi89:all-required? pos))
         ;; pure R7RS formals: no overhead, no semantic change
         (cons 'lambda (cons formals body))
         (srfi89:generate pos named rest body)))))

(defmacro (lambda* formals . body)
  (srfi89:expand formals body))

(defmacro (define* target . body)
  (if (pair? target)
      (list 'define (car target) (cons 'lambda* (cons (cdr target) body)))
      (cons 'define (cons target body))))

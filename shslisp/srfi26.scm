;;; SRFI 26 — `cut` and `cute`: specializing parameters without currying.
;;;
;;; This file is the (srfi 26) library's private implementation, loaded into
;;; a scope whose parent is the interaction environment. The macros are
;;; `defmacro`s (the raw tool) because they must scan a form and generate a
;;; fresh lambda parameter list; every generated name is a `gensym`, so a
;;; caller's variables are safe.
;;;
;;;   (cut cons (+ a 1) <>)    => (lambda (g1) (cons (+ a 1) g1))
;;;   (cute cons (+ a 1) <>)   => (let ((g2 (+ a 1))) (lambda (g1) (cons g2 g1)))
;;;
;;; `cut` re-evaluates its non-slot expressions on every call; `cute`
;;; evaluates them once, at construction. `partial` and `curry` remain
;;; project extensions — they are procedures, not syntax, and cannot leave a
;;; hole in the middle.

(define (cut:expand form style)
  (if (null? form) (error "cut/cute: no arguments"))
  (let loop ((rest form) (params '()) (pre-lets '()) (body '()) (seen-slot #f))
    (cond
      ((null? rest)
       (cut:finish params pre-lets body #f))
      (else
       (let ((elem (car rest)))
         (cond
           ((eq? elem '<>)
            (let ((p (gensym)))
              (loop (cdr rest) (append params (list p)) pre-lets
                    (append body (list p)) #t)))
           ((eq? elem '<...>)
            (if (not (null? (cdr rest)))
                (error "cut: <...> must be the last expression"))
            (if (not seen-slot)
                (error "cut: <...> must immediately follow a <>"))
            (cut:finish params pre-lets body #t))
           ((eq? style 'cute)
            (let ((t (gensym)))
              (loop (cdr rest) params
                    (append pre-lets (list (list t elem)))
                    (append body (list t)) seen-slot)))
           (else
            (loop (cdr rest) params pre-lets
                  (append body (list elem)) seen-slot))))))))

(define (cut:param-chain params rest-param)
  ;; (p1 p2 . rest) — a dotted parameter chain ending in rest-param
  (if (null? params)
      rest-param
      (cons (car params) (cut:param-chain (cdr params) rest-param))))

(define (cut:finish params pre-lets body rest?)
  (let ((rest-param (if rest? (gensym) #f))
        (lambda-form
         (lambda (param-list body-form)
           (list 'lambda param-list body-form))))
    (let ((param-list (if rest? (cut:param-chain params rest-param) params))
          (app-form (if rest?
                        (cons 'apply (append body (list rest-param)))
                        body)))
      (let ((lam (lambda-form param-list app-form)))
        (if (null? pre-lets)
            lam
            (list 'let pre-lets lam))))))

(defmacro (cut . form)
  (cut:expand form (quote cut)))

(defmacro (cute . form)
  (cut:expand form (quote cute)))

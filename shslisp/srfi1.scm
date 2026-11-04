;;; SRFI 1 — the list library.
;;;
;;; This file is the (srfi 1) library's private implementation: it is loaded
;;; into a scope whose parent is the interaction environment, so every name
;;; it does not define falls through to the core primitives (or the prelude).
;;; The library's export list — a checked constant in `lisp/library.py` — is
;;; the only public surface.
;;;
;;; Two families of names are deliberately NOT defined here, so the
;;; re-exported bindings are the *same objects* as (scheme base)'s:
;;; `member` and `assoc` (the base bindings take the optional comparator).
;;;
;;; Semantics that differ from the prelude's same-named helpers (fold, any,
;;; every, zip, iota, partition, span, count) live only in this scope: the
;;; game keeps using the prelude's, and the default DSL profile resolves the
;;; collisions explicitly (see docs/srfi.md).

(define (xcons d a) (cons a d))

(define (cons* first . rest)
  (if (null? rest)
      first
      (cons first (apply cons* rest))))

(define (list-tabulate n f)
  (let loop ((i 0) (acc '()))
    (if (= i n) (reverse acc) (loop (+ i 1) (cons (f i) acc)))))

(define (circular-list . xs)
  (if (null? xs) (error "circular-list: needs at least one element"))
  (let ((seed (cons 'circular-list-seed 'circular-list-seed)))
    (let ((chain (fold-right cons seed xs)))
      ;; walk to the cell whose tail is the seed, then close the cycle
      (let walk ((cell chain))
        (if (eq? (cdr cell) seed)
            (set-cdr! cell chain)
            (walk (cdr cell))))
      chain)))

(define (proper-list? x)
  (let loop ((slow x) (fast x))
    (cond ((null? fast) #t)
          ((not (pair? fast)) #f)
          (else
           (let ((f1 (cdr fast)))
             (cond ((null? f1) #t)
                   ((not (pair? f1)) #f)
                   ((eq? (cdr slow) (cdr f1)) #f)
                   (else (loop (cdr slow) (cdr f1)))))))))

(define (circular-list? x)
  (let loop ((slow x) (fast x))
    (cond ((not (pair? fast)) #f)
          ((not (pair? (cdr fast))) #f)
          (else
           (let ((hare (cdr (cdr fast))))
             (cond ((not (pair? hare)) #f)
                   ((eq? slow hare) #t)
                   (else (loop (cdr slow) hare))))))))

(define (dotted-list? x)
  (not (or (proper-list? x) (circular-list? x))))

(define (not-pair? x) (not (pair? x)))

(define (null-list? x)
  (cond ((pair? x) #f)
        ((null? x) #t)
        (else (error "null-list?: expected a list"))))

(define (third xs) (car (cdr (cdr xs))))
(define (fourth xs) (car (cdr (cdr (cdr xs)))))
(define (fifth xs) (car (cdr (cdr (cdr (cdr xs))))))
(define (sixth xs) (car (cdr (cdr (cdr (cdr (cdr xs)))))))
(define (seventh xs) (car (cdr (cdr (cdr (cdr (cdr (cdr xs))))))))
(define (eighth xs) (car (cdr (cdr (cdr (cdr (cdr (cdr (cdr xs)))))))))
(define (ninth xs) (car (cdr (cdr (cdr (cdr (cdr (cdr (cdr (cdr xs))))))))))
(define (tenth xs) (car (cdr (cdr (cdr (cdr (cdr (cdr (cdr (cdr (cdr xs)))))))))))

(define (last lst) (car (last-pair lst)))

(define (car+cdr x) (values (car x) (cdr x)))

;; SRFI 1 `iota` takes an optional start AND step: (iota count [start [step]]).
;; The prelude's two-argument iota stays for the game; this scope's is the
;; SRFI one, and the default DSL profile resolves the name in its favour.
(define (iota count . rest)
  (let ((start (if (null? rest) 0 (car rest)))
        (step (if (or (null? rest) (null? (cdr rest))) 1 (cadr rest))))
    (let loop ((i 0) (acc '()))
      (if (= i count)
          (reverse acc)
          (loop (+ i 1) (cons (+ start (* i step)) acc))))))


;;; --- take / drop / split ------------------------------------------------- ;;;

(define (take-right lst n)
  (let loop ((lead (drop lst n)) (tail lst))
    (if (null? lead) tail (loop (cdr lead) (cdr tail)))))

(define (drop-right lst n)
  (let loop ((lead (drop lst n)) (tail lst) (acc '()))
    (if (null? lead)
        (reverse acc)
        (loop (cdr lead) (cdr tail) (cons (car tail) acc)))))

(define (split-at lst n) (values (take lst n) (drop lst n)))
(define (split-at! lst n) (split-at lst n))

(define (take! lst n) (take lst n))
(define (drop-right! lst n) (drop-right lst n))

(define (take-while pred lst)
  (let loop ((i 0))
    (if (or (= i (length lst)) (not (pred (list-ref lst i))))
        (take lst i)
        (loop (+ i 1)))))

(define (drop-while pred lst) (drop lst (length (take-while pred lst))))

(define (take-while! pred lst) (take-while pred lst))
(define (drop-while! pred lst) (drop-while pred lst))

(define (take-while-right pred lst)
  (let search ((i (- (length lst) 1)))
    (cond ((< i 0) lst)
          ((pred (list-ref lst i)) (search (- i 1)))
          (else (take lst i)))))

(define (drop-while-right pred lst)
  (let search ((i (- (length lst) 1)))
    (cond ((< i 0) '())
          ((pred (list-ref lst i)) (search (- i 1)))
          (else (drop lst i)))))

(define (span pred lst)
  (values (take-while pred lst) (drop-while pred lst)))
(define (span! pred lst) (span pred lst))

(define (break pred lst)
  (span (lambda (x) (not (pred x))) lst))
(define (break! pred lst) (break pred lst))

(define (span-right pred lst)
  (values (take-while-right pred lst) (drop-while-right pred lst)))

(define (break-right pred lst)
  (span-right (lambda (x) (not (pred x))) lst))

(define (length+ x)
  (let loop ((slow x) (fast x) (n 0))
    (cond ((null? fast) n)
          ((not (pair? fast)) #f)
          (else
           (let ((f1 (cdr fast)))
             (cond ((null? f1) (+ n 1))
                   ((not (pair? f1)) #f)
                   (else
                    (let ((hare (cdr f1)))
                      (cond ((null? hare) (+ n 2))
                            ((not (pair? hare)) #f)
                            ((eq? slow hare) #f)
                            (else (loop (cdr slow) hare (+ n 2))))))))))))

;;; --- append / reverse ---------------------------------------------------- ;;;

(define (append! . lists) (apply append lists))
(define (reverse! lst) (reverse lst))
(define (concatenate lists) (apply append lists))
(define (concatenate! lists) (apply append lists))
(define (append-map f . lists) (apply append (apply map f lists)))
(define (append-map! f . lists) (apply append-map f lists))
(define (append-reverse rev-head tail)
  (append (reverse rev-head) tail))
(define (append-reverse! rev-head tail) (append-reverse rev-head tail))

(define (lists-equal-with elt= a b)
  (cond ((and (null? a) (null? b)) #t)
        ((or (null? a) (null? b)) #f)
        (else (and (elt= (car a) (car b))
                   (lists-equal-with elt= (cdr a) (cdr b))))))

;; `list=` is n-ary and compares ADJACENT lists, with an optional comparator
;; first: (list= [elt=] list1 ...).
(define (list= . args)
  (if (null? args)
      #t
      (let ((elt= (if (procedure? (car args)) (car args) equal?))
            (lists (if (procedure? (car args)) (cdr args) args)))
        (if (null? lists)
            #t
            (let check ((a (car lists)) (rest (cdr lists)))
              (if (null? rest)
                  #t
                  (and (lists-equal-with elt= a (car rest))
                       (check (car rest) (cdr rest)))))))))


;;; --- fold / unfold / reduce ---------------------------------------------- ;;;

;; Multi-list helpers, written before `map` is redefined so nothing here can
;; fall through to a shadowed binding.
(define (map1 f lst)
  (if (null? lst) '() (cons (f (car lst)) (map1 f (cdr lst)))))

(define (mapn f lists)
  (if (any-null? lists)
      '()
      (cons (apply f (map1 car lists)) (mapn f (map1 cdr lists)))))

(define (any-null? lists)
  (cond ((null? lists) #f)
        ((null? (car lists)) #t)
        (else (any-null? (cdr lists)))))

(define (fold f init . lists)
  (if (null? (cdr lists))
      (let loop ((acc init) (lst (car lists)))
        (if (null? lst) acc (loop (f (car lst) acc) (cdr lst))))
      (let loop ((acc init))
        (if (any-null? lists)
            acc
            (let ((args (append (map1 car lists) (list acc))))
              (set! lists (map1 cdr lists))
              (loop (apply f args)))))))

(define (fold-right f init . lists)
  (if (null? (cdr lists))
      (let foldr ((lst (car lists)))
        (if (null? lst) init (f (car lst) (foldr (cdr lst)))))
      (if (any-null? lists)
          init
          (apply f (append (map1 car lists)
                           (list (apply fold-right f init (map1 cdr lists))))))))

(define (pair-fold f init lst)
  (if (null? lst) init (f lst (pair-fold f init (cdr lst)))))

(define (pair-fold-right f init lst)
  (if (null? lst) init (f lst (pair-fold-right f init (cdr lst)))))

(define (pair-for-each f lst)
  (if (null? lst) 'done (begin (f lst) (pair-for-each f (cdr lst)))))

(define (reduce f ridentity lst)
  (if (null? lst) ridentity (fold f (car lst) (cdr lst))))

(define (reduce-right f ridentity lst)
  (cond ((null? lst) ridentity)
        ((null? (cdr lst)) (car lst))
        (else (f (car lst) (reduce-right f ridentity (cdr lst))))))

(define (unfold p f g seed . tail-gen)
  (let ((tail (if (null? tail-gen) (lambda () '()) (car tail-gen))))
    (let loop ((seed seed))
      (if (p seed) (tail) (cons (f seed) (loop (g seed)))))))

(define (unfold-right p f g seed . tail)
  (let ((tail (if (null? tail) '() (car tail))))
    (let loop ((seed seed) (acc tail))
      (if (p seed) acc (loop (g seed) (cons (f seed) acc))))))

;;; --- map / for-each / filtering ------------------------------------------ ;;;

;; SRFI 1 `map` and `for-each` are variadic and stop at the shortest list —
;; different from (scheme base)'s equal-length requirement. The default DSL
;; profile renames these to `srfi-1:map` / `srfi-1:for-each` so both
;; semantics are reachable; see docs/srfi.md.

(define (map f . lists)
  (if (null? lists) '() (mapn f lists)))

(define (for-each f . lists)
  (if (null? lists)
      'done
      (let loop ()
        (if (any-null? lists)
            'done
            (begin (apply f (map1 car lists))
                   (set! lists (map1 cdr lists))
                   (loop))))))

(define (map! f lst) (mapn f (list lst)))
(define (map-in-order f . lists) (apply map f lists))

(define (filter-map f . lists)
  (let loop ((results (apply map f lists)) (acc '()))
    (cond ((null? results) (reverse acc))
          ((not (car results)) (loop (cdr results) acc))
          (else (loop (cdr results) (cons (car results) acc))))))

(define (filter! f lst) (filter f lst))
(define (remove! pred lst) (remove pred lst))

(define (partition pred lst)
  (values (filter pred lst) (filter (lambda (x) (not (pred x))) lst)))
(define (partition! pred lst) (partition pred lst))

(define (remove pred lst)
  (filter (lambda (x) (not (pred x))) lst))

;;; --- searching ----------------------------------------------------------- ;;;

(define (find-tail pred lst)
  (cond ((null? lst) #f)
        ((pred (car lst)) lst)
        (else (find-tail pred (cdr lst)))))

(define (find pred lst)
  (cond ((find-tail pred lst) => car)
        (else #f)))

(define (find-right pred lst)
  (let loop ((result #f) (rest lst))
    (cond ((null? rest) result)
          ((pred (car rest)) (loop (car rest) (cdr rest)))
          (else (loop result (cdr rest))))))

(define (any pred . lists)
  (if (null? (cdr lists))
      (let loop ((lst (car lists)))
        (cond ((null? lst) #f)
              ((pred (car lst)))
              (else (loop (cdr lst)))))
      (let loop ()
        (if (any-null? lists)
            #f
            (let ((v (apply pred (map1 car lists))))
              (if v v (begin (set! lists (map1 cdr lists)) (loop))))))))

(define (every pred . lists)
  (if (null? (cdr lists))
      (let loop ((lst (car lists)) (last #t))
        (cond ((null? lst) last)
              ((pred (car lst)) => (lambda (v) (loop (cdr lst) v)))
              (else #f)))
      (let loop ((last #t))
        (if (any-null? lists)
            last
            (let ((v (apply pred (map1 car lists))))
              (if v (begin (set! lists (map1 cdr lists)) (loop v)) #f))))))

(define (list-index pred . lists)
  (if (null? (cdr lists))
      (let loop ((lst (car lists)) (i 0))
        (cond ((null? lst) #f)
              ((pred (car lst)) i)
              (else (loop (cdr lst) (+ i 1)))))
      (let loop ((i 0))
        (if (any-null? lists)
            #f
            (if (apply pred (map1 car lists))
                i
                (begin (set! lists (map1 cdr lists)) (loop (+ i 1))))))))

(define (count pred . lists)
  (if (null? (cdr lists))
      (let loop ((lst (car lists)) (n 0))
        (cond ((null? lst) n)
              ((pred (car lst)) (loop (cdr lst) (+ n 1)))
              (else (loop (cdr lst) n))))
      (let loop ((n 0))
        (if (any-null? lists)
            n
            (let ((hit (apply pred (map1 car lists))))
              (set! lists (map1 cdr lists))
              (loop (if hit (+ n 1) n)))))))

;;; --- deletion and association lists -------------------------------------- ;;;

(define (delete x lst . maybe-elt=)
  (let ((elt= (if (null? maybe-elt=) equal? (car maybe-elt=))))
    (filter (lambda (y) (not (elt= x y))) lst)))
(define (delete! x lst . maybe-elt=) (apply delete x lst maybe-elt=))

(define (delete-duplicates lst . maybe-elt=)
  (let ((elt= (if (null? maybe-elt=) equal? (car maybe-elt=))))
    (let loop ((rest lst) (acc '()))
      (cond ((null? rest) (reverse acc))
            ((member (car rest) acc elt=) (loop (cdr rest) acc))
            (else (loop (cdr rest) (cons (car rest) acc)))))))
(define (delete-duplicates! lst . maybe-elt=)
  (apply delete-duplicates lst maybe-elt=))

(define (alist-cons key datum alist) (cons (cons key datum) alist))

(define (alist-copy alist)
  (map (lambda (pair) (cons (car pair) (cdr pair))) alist))

(define (alist-delete key alist . maybe-elt=)
  (let ((elt= (if (null? maybe-elt=) equal? (car maybe-elt=))))
    (filter (lambda (pair) (not (elt= key (car pair)))) alist)))
(define (alist-delete! key alist . maybe-elt=)
  (apply alist-delete key alist maybe-elt=))

;;; --- set operations ------------------------------------------------------ ;;;

;; SRFI 1's lset procedures take the comparator as their FIRST argument.

(define (lset<= elt= . lists)
  (if (null? (cdr lists))
      #t
      (let check ((a (car lists)) (rest (cdr lists)))
        (if (null? rest)
            #t
            (and (lset-subset? elt= a (car rest))
                 (check (car rest) (cdr rest)))))))

(define (lset-subset? elt= a b)
  (let loop ((rest a))
    (cond ((null? rest) #t)
          ((member (car rest) b elt=) (loop (cdr rest)))
          (else #f))))

(define (lset= elt= . lists)
  (if (null? (cdr lists))
      #t
      (let check ((a (car lists)) (rest (cdr lists)))
        (if (null? rest)
            #t
            (and (lset-subset? elt= a (car rest))
                 (lset-subset? elt= (car rest) a)
                 (check (car rest) (cdr rest)))))))

(define (lset-adjoin elt= lst . xs)
  (lset-union2 elt= lst xs))

(define (lset-union elt= . lists)
  (fold (lambda (b acc) (lset-union2 elt= acc b)) '() lists))

(define (lset-union2 elt= a b)
  (append a (filter (lambda (x) (not (member x a elt=))) b)))

(define (lset-union! elt= . lists) (apply lset-union elt= lists))

(define (lset-intersection elt= . lists)
  (fold (lambda (b acc) (lset-intersection2 elt= acc b)) (car lists) (cdr lists)))

(define (lset-intersection2 elt= a b)
  (filter (lambda (x) (member x b elt=)) a))

(define (lset-intersection! elt= . lists) (apply lset-intersection elt= lists))

(define (lset-difference elt= . lists)
  (fold (lambda (b acc) (lset-difference2 elt= acc b)) (car lists) (cdr lists)))

(define (lset-difference2 elt= a b)
  (filter (lambda (x) (not (member x b elt=))) a))

(define (lset-difference! elt= . lists) (apply lset-difference elt= lists))

(define (lset-xor elt= . lists)
  (fold (lambda (b acc) (lset-xor2 elt= acc b)) (car lists) (cdr lists)))

(define (lset-xor2 elt= a b)
  (append (filter (lambda (x) (not (member x b elt=))) a)
          (filter (lambda (x) (not (member x a elt=))) b)))

(define (lset-xor! elt= . lists) (apply lset-xor elt= lists))

(define (lset-diff+intersection elt= . lists)
  (values (apply lset-difference elt= lists)
          (apply lset-intersection elt= lists)))

(define (lset-diff+intersection! elt= . lists)
  (apply lset-diff+intersection elt= lists))

;;; --- zip ----------------------------------------------------------------- ;;;

;; SRFI 1 `zip` is variadic and stops at the shortest list. The prelude's
;; two-list zip stays for the game; the default DSL profile resolves the
;; name in favour of this one (see docs/srfi.md).

(define (zip . lists) (apply map list lists))

(define (unzip1 lst) (map first lst))

(define (unzip2 lst)
  (values (map first lst) (map second lst)))

(define (unzip3 lst)
  (values (map first lst) (map second lst) (map third lst)))

(define (unzip4 lst)
  (values (map first lst) (map second lst) (map third lst) (map fourth lst)))

(define (unzip5 lst)
  (values (map first lst) (map second lst) (map third lst) (map fourth lst)
          (map fifth lst)))

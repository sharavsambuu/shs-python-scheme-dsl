;; prelude.scm — the standard library, written in the DSL itself.
;;
;; Everything here is ordinary Lisp you could have typed at the REPL — no
;; Python, no host hooks. That is the point: once a language has `lambda`,
;; `let`, `define`, and macros, this file is what "adding features" looks
;; like. Read it as the first worked example of the language, and as the
;; place to experiment: change a definition here and it is reloaded with
;; every environment.
;;
;; Naming note: a trailing `!` (as in the tetris prelude's `show!`) is a
;; convention, not syntax — "this function exists for its effect".

;; ------------------------------------------------------------------------- ;;
;;  Small combinators                                                          ;;
;; ------------------------------------------------------------------------- ;;

(define (identity x) x)
(define (inc x) (+ x 1))
(define (dec x) (- x 1))
(define (const x) (lambda (_) x))

;; `compose` is variadic and right-to-left: the last procedure runs first.
;; With no arguments it is `identity`, so folding it over a list of procedures
;; always has a neutral element, and `(compose f)` is just `f`.

(define (compose . fs)
  (cond ((null? fs) identity)
        ((null? (cdr fs)) (car fs))
        (else (let ((outer (car fs))
                    (inner (apply compose (cdr fs))))
                (lambda args (outer (apply inner args)))))))

;; `pipe` is the same pipeline read left-to-right, which is how a data flow is
;; usually written: `(pipe f g h)` is `(compose h g f)`.

(define (pipe . fs) (apply compose (reverse fs)))

;; `flip` calls a procedure with its arguments the other way round; for more
;; than two it reverses them, which is what that means for a variadic one.

(define (flip f) (lambda args (apply f (reverse args))))

(define (complement pred) (lambda args (not (apply pred args))))

;; Partial application: bind the first arguments now, take the rest later.
;; `partial` is variadic and needs no arity, so it works on any procedure.

(define (partial f . bound)
  (lambda args (apply f (append bound args))))

;; Currying *does* need an arity. A Lisp closure records its own
;; (`procedure-arity`); a host primitive does not, so pass it explicitly
;; there: `(curry + 3)`. Each call takes one argument.

(define (curry f . arity)
  (let ((n (if (null? arity) (procedure-arity f) (car arity))))
    (if (not n)
        (error "curry: cannot infer this procedure's arity; pass it, e.g. (curry + 3)" f)
        (let loop ((k n) (g f))
          (if (<= k 1) g (lambda (x) (loop (- k 1) (partial g x))))))))

;; ------------------------------------------------------------------------- ;;
;;  List access sugar                                                          ;;
;; ------------------------------------------------------------------------- ;;

(define (caar xs) (car (car xs)))
(define (cadr xs) (car (cdr xs)))
(define (caddr xs) (car (cdr (cdr xs))))
(define (second xs) (cadr xs))
(define (first xs) (car xs))
(define (rest xs) (cdr xs))

(define (last xs)
  (if (null? (cdr xs)) (car xs) (last (cdr xs))))

;; ------------------------------------------------------------------------- ;;
;;  Association lists — the language's record shape                            ;;
;; ------------------------------------------------------------------------- ;;

;; An alist is a list of two-element lists: ((key value) (key value) ...).
;; `assoc` (a primitive) finds the entry; these read it the friendly way.

(define (alist-ref alist key)
  (let ((entry (assoc key alist)))
    (if entry (cadr entry) #f)))

(define (alist-has? alist key)
  (if (assoc key alist) #t #f))

;; ------------------------------------------------------------------------- ;;
;;  Repetition (no `for` loop — a named let *is* the loop)                     ;;
;; ------------------------------------------------------------------------- ;;

(define (repeat n thunk)
  (let loop ((i 0))
    (if (>= i n)
        '()
        (begin (thunk) (loop (+ i 1))))))

(define (times f n) (repeat n f))

;; ------------------------------------------------------------------------- ;;
;;  Macros — the language rewriting itself                                     ;;
;; ------------------------------------------------------------------------- ;;

;; `while` is a macro, not a function: `(while test body)` must not evaluate
;; `body` before the test passes, and a function call cannot promise that.
;; Note the rest parameter `body` and the use of quasiquote.

(defmacro (while test . body)
  `(let loop ()
     (when ,test
       ,@body
       (loop))))

;; `++` is the smallest useful macro: it rewrites `(++ x)` into a `set!`,
;; which is why it can appear on the left of an assignment.

(defmacro (++ place)
  `(set! ,place (+ ,place 1)))

(defmacro (-- place)
  `(set! ,place (- ,place 1)))

;; ------------------------------------------------------------------------- ;;
;;  Hygienic macros — `define-syntax` + `syntax-rules`                         ;;
;; ------------------------------------------------------------------------- ;;
;;
;; `defmacro` above is the raw tool: its template can capture a caller's name
;; (which is why `while` binds `loop` and gets away with it only because no
;; caller is called `loop`). `syntax-rules` renames whatever its template
;; introduces, so `pop!` below can bind `v` and no caller can notice.

(define-syntax push!
  (syntax-rules ()
    ((_ place value) (set! place (cons value place)))))

(define-syntax pop!
  (syntax-rules ()
    ((_ place)
     (let ((v (car place)))
       (set! place (cdr place))
       v))))

;; `do` is the classic counted loop. It is *derived*: the expansion is a named
;; `let`, so `do` costs nothing the language did not already have.

(define-syntax do
  (syntax-rules ()
    ((_ ((var init step) ...) (test result ...) body ...)
     (let loop ((var init) ...)
       (if test
           (begin result ...)
           (begin body ... (loop step ...)))))))

(define-syntax dotimes
  (syntax-rules ()
    ((_ (var n) body ...)
     (do ((var 0 (+ var 1))) ((= var n)) body ...))))

;; `->` threads a value through a pipeline, each step receiving it as its
;; *first* argument; `->>` passes it last. Both are hygienic and expand into
;; ordinary calls, so they cost nothing at run time — they are only a way to
;; write nested calls in the order the data flows.
;;
;;   (-> x (f 1) g)      is  (g (f x 1))
;;   (->> x (f 1) g)     is  (g (f 1 x))

(define-syntax ->
  (syntax-rules ()
    ((_ x) x)
    ((_ x (f arg ...) more ...) (-> (f x arg ...) more ...))
    ((_ x f more ...) (-> (f x) more ...))))

(define-syntax ->>
  (syntax-rules ()
    ((_ x) x)
    ((_ x (f arg ...) more ...) (->> (f arg ... x) more ...))
    ((_ x f more ...) (->> (f x) more ...))))

;; ------------------------------------------------------------------------- ;;
;;  More list algorithms                                                       ;;
;; ------------------------------------------------------------------------- ;;

(define (cadddr xs) (car (cdr (cdr (cdr xs)))))
(define (last-pair xs) (if (null? (cdr xs)) xs (last-pair (cdr xs))))
(define (list-head xs n) (take xs n))

;; ``take`` and ``drop`` are primitives (``lisp/builtins.py``): they slice the
;; proper list in one pass. The recursive ``(cons (car xs) (take (cdr xs) ...))``
;; spelling copies the tail at every cons, so it is quadratic on a long list.

(define (even? n) (= (modulo n 2) 0))
(define (odd? n) (= (modulo n 2) 1))
(define (zero? n) (= n 0))
(define (positive? n) (> n 0))
(define (negative? n) (< n 0))

(define (any pred xs)
  (if (null? xs) #f (if (pred (car xs)) #t (any pred (cdr xs)))))

(define (every pred xs)
  (if (null? xs) #t (if (pred (car xs)) (every pred (cdr xs)) #f)))

(define (count pred xs)
  (foldl (lambda (x n) (if (pred x) (+ n 1) n)) 0 xs))

(define (find pred xs)
  (cond ((null? xs) #f)
        ((pred (car xs)) (car xs))
        (else (find pred (cdr xs)))))

(define (find-index pred xs)
  (let loop ((xs xs) (i 0))
    (cond ((null? xs) #f)
          ((pred (car xs)) i)
          (else (loop (cdr xs) (+ i 1))))))

(define (delete x xs) (filter (lambda (y) (not (equal? x y))) xs))
(define (remove pred xs) (filter (lambda (y) (not (pred y))) xs))

(define (zip a b)
  (if (or (null? a) (null? b))
      '()
      (cons (list (car a) (car b)) (zip (cdr a) (cdr b)))))

(define (append-map f xs) (apply append (map f xs)))
(define (sum xs) (foldl + 0 xs))
(define (iota n . start) (map (lambda (i) (+ (if (null? start) 0 (car start)) i)) (range n)))
(define fold foldl)
(define reduce foldl)

;; An alist is the language's record; this is its "update a field" (a new list).

(define (alist-set alist key value)
  (cons (list key value)
        (filter (lambda (entry) (not (equal? (car entry) key))) alist)))

;; ------------------------------------------------------------------------- ;;
;;  A little more string and table sugar                                       ;;
;; ------------------------------------------------------------------------- ;;

(define (string-prefix? s prefix)
  (let ((n (string-length prefix)))
    (and (>= (string-length s) n) (string=? (substring s 0 n) prefix))))

(define (string-suffix? s suffix)
  (let ((n (string-length suffix)) (m (string-length s)))
    (and (>= m n) (string=? (substring s (- m n) m) suffix))))

(define (string-index s ch)
  (let loop ((i 0))
    (cond ((>= i (string-length s)) #f)
          ((char=? (string-ref s i) ch) i)
          (else (loop (+ i 1))))))

(define (hash-table-for-each proc table)
  (for-each
    (lambda (key) (proc key (hash-table-ref table key)))
    (hash-table-keys table)))

;; ------------------------------------------------------------------------- ;;
;;  Linear traversals                                                          ;;
;; ------------------------------------------------------------------------- ;;
;;
;; A proper list is a host list, and `cdr` copies the tail — so a traversal
;; written as structural recursion (`(loop (cdr xs))`) costs O(n^2) on a long
;; list: fine for a board, wrong for a log. The helpers below walk with the
;; primitive traversals (`map`, `filter`, `foldl`, `for-each`), which loop in
;; the host without copying, and so stay linear. Reach for that pattern when
;; you add one.

(define (take-while pred xs)
  (let ((out '()) (done #f))
    (for-each
      (lambda (x)
        (when (not done)
          (if (pred x) (push! out x) (set! done #t))))
      xs)
    (reverse out)))

(define (drop-while pred xs)
  (let ((out '()) (dropping #t))
    (for-each
      (lambda (x)
        (if (and dropping (pred x))
            #t
            (begin (set! dropping #f) (push! out x))))
      xs)
    (reverse out)))

(define (span pred xs) (list (take-while pred xs) (drop-while pred xs)))

(define (partition pred xs)
  (let ((yes '()) (no '()))
    (for-each (lambda (x) (if (pred x) (push! yes x) (push! no x))) xs)
    (list (reverse yes) (reverse no))))

;; `distinct` keeps the first occurrence of each value, using `equal?` — a hash
;; table is keyed structurally, so a list or a tagged value works as a key.

(define (distinct xs)
  (let ((seen (make-hash-table)) (out '()))
    (for-each
      (lambda (x)
        (unless (hash-table-has-key? seen x)
          (hash-table-set! seen x #t)
          (push! out x)))
      xs)
    (reverse out)))

;; `map-index` also passes the position. `list-ref` is O(1) on a proper list,
;; so walking `(range n)` is linear — unlike walking `(cdr xs)`.

(define (map-index f xs)
  (let ((n (length xs)))
    (map (lambda (i) (f i (list-ref xs i))) (range n))))

(define (enumerate xs) (map-index (lambda (i x) (list i x)) xs))

;; `filter-map` maps and drops the `#f` results: the usual way to keep what a
;; mapping produced and skip what it could not.

(define (filter-map f xs)
  (filter (lambda (value) (not (eq? value #f))) (map f xs)))

(define (flat-map f xs) (append-map f xs))

(define (flatten x)
  (cond ((null? x) '())
        ((list? x) (append-map flatten x))
        (else (list x))))

(define (product xs) (foldl * 1 xs))

;; `iterate` is x, f(x), f(f(x)), ... — the first n values, starting at x.

(define (iterate f x n)
  (let loop ((i 0) (value x) (out '()))
    (if (>= i n)
        (reverse out)
        (loop (+ i 1) (f value) (cons value out)))))

;; ------------------------------------------------------------------------- ;;
;;  Sorting and grouping by a key                                               ;;
;; ------------------------------------------------------------------------- ;;
;;
;; `sort` takes a less-than predicate on the *elements*; with a key you want
;; that predicate on `(key element)`. These are that, plus the two searches and
;; the grouping that usually go with it.

(define (sort-by key less xs)
  (sort xs (lambda (a b) (less (key a) (key b)))))

(define (max-by key less xs)
  (if (null? xs)
      (error "max-by: empty list")
      (foldl (lambda (x best) (if (less (key best) (key x)) x best))
             (car xs)
             (cdr xs))))

(define (min-by key less xs)
  (if (null? xs)
      (error "min-by: empty list")
      (foldl (lambda (x best) (if (less (key x) (key best)) x best))
             (car xs)
             (cdr xs))))

;; `group-by` returns an alist of `(key (elements ...))` — the entry's value is
;; the list of elements — in first-seen order, so `alist-ref` reads it and the
;; order is the input's, not a hash table's.

(define (group-by key xs)
  (let ((groups (make-hash-table)) (order '()))
    (for-each
      (lambda (x)
        (let ((k (key x)))
          (unless (hash-table-has-key? groups k)
            (push! order k)
            (hash-table-set! groups k '()))
          (hash-table-set! groups k (cons x (hash-table-ref groups k)))))
      xs)
    (map (lambda (k) (list k (reverse (hash-table-ref groups k))))
         (reverse order))))

;; ------------------------------------------------------------------------- ;;
;;  Memoisation                                                                ;;
;; ------------------------------------------------------------------------- ;;

;; The cache is keyed by the whole argument list, and hashing is structural, so
;; a procedure of several arguments (or of lists) is memoised by value.

(define (memoize f)
  (let ((cache (make-hash-table)))
    (lambda args
      (if (hash-table-has-key? cache args)
          (hash-table-ref cache args)
          (let ((value (apply f args)))
            (hash-table-set! cache args value)
            value)))))


;; ------------------------------------------------------------------------- ;;
;;  Delayed evaluation — promises                                             ;;
;; ------------------------------------------------------------------------- ;;

;; A promise is a two-slot vector: slot 0 is whether it has been forced, slot 1
;; is the thunk before forcing and the value after. Written in Lisp on vectors
;; — the language's one mutable cell — it needs no new host type, and `force`
;; is idempotent *by construction*, which is a promise's whole contract.
;;
;; `force` on anything that is not a promise returns it unchanged, so a lazy
;; pipeline can force a possibly-eager stage without first checking.

(define (make-promise thunk)
  (if (procedure? thunk)
      (vector #f thunk)     ; a thunk: not yet forced
      (vector #t thunk)))   ; already a value: forced from the start

(define (promise? p) (and (vector? p) (= (vector-length p) 2)))

(define (force p)
  (if (promise? p)
      (if (vector-ref p 0)
          (vector-ref p 1)
          (let ((value ((vector-ref p 1))))
            (vector-set! p 1 value)
            (vector-set! p 0 #t)
            value))
      p))

(define-syntax delay
  (syntax-rules ()
    ((_ expr) (make-promise (lambda () expr)))))

;; `delay-force` is `delay` whose body forces, so a chain of
;; `(delay-force (later ...))` does not build a thunk tower.
(define-syntax delay-force
  (syntax-rules ()
    ((_ expr) (make-promise (lambda () (force expr))))))

;; ------------------------------------------------------------------------- ;;
;;  Parameters — dynamically scoped cells                                     ;;
;; ------------------------------------------------------------------------- ;;

;; A parameter is a procedure: call it with no arguments to read the current
;; value, or with one to set it — returning the *old* value, which is exactly
;; what `parameterize` needs in order to restore. The cell is a one-slot vector.

(define (make-parameter init)
  (let ((cell (vector init)))
    (lambda args
      (if (null? args)
          (vector-ref cell 0)
          (let ((old (vector-ref cell 0)))
            (vector-set! cell 0 (car args))
            old)))))

;; `parameterize` sets each parameter, runs the body, then restores the old
;; values in `dynamic-wind`'s *after* thunk — so restoration happens on a normal
;; return, on a `raise`, and when a captured continuation exits the extent. Each
;; parameter expression and each value expression is evaluated exactly once.

(define-syntax parameterize
  (syntax-rules ()
    ((_ ((param value) ...) body ...)
     (let ((ps (list param ...))
           (new (list value ...)))
       (let ((old (map (lambda (p v) (p v)) ps new)))
         (dynamic-wind
           (lambda () #t)
           (lambda () (begin body ...))
           (lambda () (for-each (lambda (p o) (p o)) ps old))))))))

;; ------------------------------------------------------------------------- ;;
;;  The current ports, and the file conveniences that rebind them             ;;
;; ------------------------------------------------------------------------- ;;

;; A "current port" is a parameter (above), so `parameterize` is what redirects
;; I/O — and the redirection is undone on every exit from the extent, a `raise`
;; included. `display`, `write`, `newline`, and `print` are host primitives,
;; but they write to `(current-output-port)`, so rebinding the parameter is all
;; it takes to redirect them.

(define current-input-port  (make-parameter (standard-input-port)))
(define current-output-port (make-parameter (standard-output-port)))
(define current-error-port  (make-parameter (standard-error-port)))

(define (with-output-to-file path thunk)
  (let ((port (open-output-file path)))
    (dynamic-wind
      (lambda () #t)
      (lambda () (parameterize ((current-output-port port)) (thunk)))
      (lambda () (close-port port)))))

(define (call-with-output-file path proc)
  (let ((port (open-output-file path)))
    (dynamic-wind
      (lambda () #t)
      (lambda () (proc port))
      (lambda () (close-port port)))))

(define (with-input-from-file path thunk)
  (let ((port (open-input-file path)))
    (dynamic-wind
      (lambda () #t)
      (lambda () (parameterize ((current-input-port port)) (thunk)))
      (lambda () (close-port port)))))

(define (call-with-input-file path proc)
  (let ((port (open-input-file path)))
    (dynamic-wind
      (lambda () #t)
      (lambda () (proc port))
      (lambda () (close-port port)))))

;; structured.scm — the `with-parallel` macro over a Python nursery.
;;
;; Loaded by nursery.py. The macro turns a block of tasks into one nursery
;; call; the Python side does the threads, the join-all, and the error
;; propagation. Structured concurrency is a *discipline*: every task spawned
;; inside the block is joined before the block exits — success or failure —
;; so no task outlives the code that started it.
;;
;; The rule that makes sharing an environment across the nursery's threads
;; safe: tasks are PURE. They read their closures, they compute, they return
;; a value — no `define`, no `set!`, no mutation of anything the other tasks
;; can see. (That is the same contract futures.md-style nurseries ask for.)

;; --- the macro -----------------------------------------------------------------
;; `(with-parallel task1 task2 ...)` answers the list of every task's value,
;; in task order — or propagates the first task's error, after joining all.

(define-syntax with-parallel
  (syntax-rules ()
    ((with-parallel task ...)
     (nursery-run (list (lambda () task) ...)))))

;; --- the workload ---------------------------------------------------------------
;; Four "services", each spending most of its time WAITING (I/O, in real
;; life; `spin-ms` here). Waiting is what threads are for: while one task
;; sleeps, another runs. CPU-bound tasks would NOT speed up this way —
;; CPython's GIL serializes them (see docs/capabilities.md, "the walls");
;; for real CPU parallelism see 05-parallel-map and 06-core-saturation.

(define (io-service name ms)
  (spin-ms ms)
  (list name 'io-complete 'took-ms ms))

(define tasks
  (list (lambda () (io-service "auth"     900))
        (lambda () (io-service "billing" 1200))
        (lambda () (io-service "search"  700))
        (lambda () (io-service "notify"  500))))

;; driven by nursery.py, which times both. NOTE: the sequential baseline is
;; timed by the host as four separate evaluations, not one big `(map ...)`
;; run — the interpreter charges a step budget per evaluation, and a single
;; program that computes all four services back-to-back would trip it. The
;; nursery's threads are immune: each task is applied in its own thread of
;; evaluation. (A real property of this interpreter, and a fair one — the
;; baseline it forbids is exactly the shape a scheduler exists to replace.)
(define (parallel-results) (nursery-run tasks))

;; --- the failure case ------------------------------------------------------------
;; One poisoned task. The nursery still joins ALL tasks — no task is left
;; running — and then the error propagates. Here it is caught two ways:
;; Python-side (try/except in nursery.py) and Scheme-side (guard, below).

(define (parallel-fail)
  (nursery-run
   (cons (lambda () (error "billing: card declined"))
         tasks)))

(define (guarded-fail)
  (guard (e ((error-object? e) (list 'nursery-caught (error-object-message e))))
    (parallel-fail)))

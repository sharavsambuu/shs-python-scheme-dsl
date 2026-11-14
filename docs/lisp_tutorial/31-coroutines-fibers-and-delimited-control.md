# 31. Coroutines, fibers, and delimited control

> **What this chapter teaches.** How to suspend and resume computations with delimited continuations (`(srfi 226)`), yield values from coroutine generators (`(srfi 158)` and `(srfi 190)`), and coordinate cooperative fibers with mutexes and condition variables (`(srfi 18)`).
> **Before this:** [20 Generators: SRFI 158](19-generators.md) and [30 Testing and debugging: SRFI 64](30-testing-and-debugging-srfi-64.md) · **Time:** 15 minutes
> **After this you can:** write `coroutine-generator` producers with `yield`, use `call-with-continuation-prompt` and `abort-current-continuation`, and run baton-scheduled `(srfi 18)` fibers.

`shslisp` executes Scheme in a Python host without C stack switching or OS-level preemption. To support coroutines and fibers cleanly, `shslisp` models suspension with **baton-scheduled cooperative fibers** (`CooperativeFiber`) built on Python threads that pass a single execution baton back and forth: only one fiber (or the caller) runs at a time, giving deterministic handoffs without shared-state data races.

Four SRFIs work together on top of this runtime:

1. **`(srfi 226)` — Delimited continuations & prompts:** `make-continuation-prompt-tag`, `call-with-continuation-prompt`, `abort-current-continuation`, `call-with-composable-continuation`, and `call-with-continuation-barrier`.
2. **`(srfi 158)` — Coroutine generators:** `make-coroutine-generator` and `make-for-each-generator` turn imperative loops or `for-each` traversals into lazy generators.
3. **`(srfi 190)` — Coroutine generators syntax:** `coroutine-generator`, `define-coroutine-generator`, and `yield` give concise generator syntax on top of `make-coroutine-generator`.
4. **`(srfi 18)` — Cooperative threads, mutexes, and condition variables:** `make-thread`, `thread-start!`, `thread-yield!`, `thread-sleep!`, `thread-join!`, `thread-terminate!`, `make-mutex`, `mutex-lock!`, `mutex-unlock!`, `make-condition-variable`, `condition-variable-signal!`, and `condition-variable-broadcast!`.

## Try it

```scheme
(import (scheme base)
        (srfi 158)
        (srfi 190)
        (srfi 226)
        (srfi 18))

;; 1. SRFI 226: delimited prompt + one-shot composable continuation
(define tag (make-continuation-prompt-tag 'demo))
(define saved #f)
(define step1
  (call-with-continuation-prompt
   (lambda ()
     (+ 10
        (call-with-composable-continuation
         (lambda (k)
           (set! saved k)
           (abort-current-continuation tag 'paused))
         tag)))
   tag
   (lambda (msg) msg)))
(display step1)
(newline)
(display (call-with-continuation-prompt (lambda () (saved 5)) tag))
(newline)

;; 2. SRFI 190: coroutine-generator with yield
(define-coroutine-generator (countdown n)
  (let loop ((i n))
    (when (> i 0)
      (yield i)
      (loop (- i 1)))))

(display (generator->list (countdown 3)))
(newline)

;; 3. SRFI 18: cooperative threads + mutex
(define m (make-mutex))
(define log '())
(define t1
  (make-thread
   (lambda ()
     (mutex-lock! m)
     (set! log (cons 'worker log))
     (mutex-unlock! m))))
(thread-start! t1)
(thread-join! t1)
(display log)
(newline)
```

Expected output:

```text
paused
15
(3 2 1)
(worker)
```

## Delimited continuations: `(srfi 226)`

A **prompt** marks a boundary on the dynamic call chain with `call-with-continuation-prompt`. Inside it:

- `abort-current-continuation` unwinds directly back to the matching prompt tag and invokes its abort handler (or returns the aborted values to the default handler).
- `call-with-composable-continuation` captures the slice of computation between the current point and the matching prompt tag as a **one-shot** procedure `k` backed by a `CooperativeFiber`. Save `k` and abort to the prompt (`abort-current-continuation`), then resume it once from outside with `(k v)`.
- `call-with-continuation-barrier` prevents aborts and composable captures from crossing the barrier.

Note that because `shslisp` implements delimited capture via one-shot baton-scheduled fibers, use `(k v)` once per capture (for coroutines, generators, and suspend/resume workflows) rather than multi-shot backtracking.

## Coroutine generators: `(srfi 158)` and `(srfi 190)`

`(srfi 158)` adds two fiber-backed constructors alongside `generator` and `list->generator`:

- `(make-coroutine-generator proc)` calls `(proc yield)` inside a cooperative fiber; each `(yield v)` suspends the producer until the consumer calls the generator.
- `(make-for-each-generator for-each-fn collection)` turns any `for-each`-style iterator (such as `vector-for-each` or `string-for-each`) into a lazy generator.

`(srfi 190)` wraps `make-coroutine-generator` with `yield` as a syntax parameter:

```scheme
(define-coroutine-generator (squares n)
  (do ((i 1 (+ i 1)))
      ((> i n))
    (yield (* i i))))
```

If `yield` is called outside a `coroutine-generator`, it raises an error.

## Cooperative fibers & synchronization: `(srfi 18)`

`(srfi 18)` provides SRFI-18's thread, mutex, and condition-variable API, scheduled cooperatively via the shared baton:

- Threads start suspended (`make-thread`) and begin running when `thread-start!` is called.
- `thread-yield!` hands the baton to other runnable threads; `thread-sleep!` yields for a timeout.
- `thread-join!` waits for a thread to finish and returns its result (or re-raises an uncaught thread exception).
- `make-mutex`, `mutex-lock!`, `mutex-unlock!`, `make-condition-variable`, `condition-variable-signal!`, and `condition-variable-broadcast!` coordinate access between fibers without deadlocking the single-baton scheduler.

## Exercises

1. Write a `coroutine-generator` that yields the Fibonacci sequence up to a limit `n`, and collect its values with `generator->list`.
2. Wrap a computation in `call-with-continuation-prompt` with a custom abort handler, and use `abort-current-continuation` to bail out early with a default value.
3. Spawn two `(srfi 18)` threads that alternate appending `'a` and `'b` to a shared list protected by a mutex, yielding between turns with `thread-yield!`.

## The shape you copy

```scheme
(import (scheme base) (srfi 158) (srfi 190))

(define-coroutine-generator (range-step start stop step)
  (let loop ((x start))
    (when (< x stop)
      (yield x)
      (loop (+ x step)))))
```

---

Previous: [30 Testing and debugging: SRFI 64](30-testing-and-debugging-srfi-64.md) · Next: [Appendix A — Reference](appendix-a-reference.md)

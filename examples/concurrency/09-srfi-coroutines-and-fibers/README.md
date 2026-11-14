# 09 · SRFI coroutines & fibers — `(srfi 226)`, `(srfi 158)`/`(srfi 190)`, and `(srfi 18)`

```sh
python -m shslisp run examples/concurrency/09-srfi-coroutines-and-fibers/srfi_coroutines_and_fibers.scm
```

While `01` and `02` build generators and a round-robin scheduler by hand in
pure Scheme, `shslisp` v0.3.0+ ships a baton-scheduled `CooperativeFiber`
engine and four standard SRFIs on top of it:

1. **`(srfi 190)`** — `define-coroutine-generator` and `yield` write lazy
   producers directly as imperative/recursive Scheme (`fibonacci-up-to`).
2. **`(srfi 158)`** — `make-for-each-generator` and `make-coroutine-generator`
   turn any `for-each`-shaped traversal into a lazy generator.
3. **`(srfi 226)`** — `call-with-continuation-prompt`,
   `abort-current-continuation`, and one-shot
   `call-with-composable-continuation` suspend and resume mid-expression.
4. **`(srfi 18)`** — `make-thread`, `thread-start!`, `thread-yield!`,
   `thread-join!`, `make-mutex`, and `make-condition-variable` coordinate
   cooperative producer/consumer fibers deterministically without OS-level
   data races.

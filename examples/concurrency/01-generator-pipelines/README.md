# 01 · generator pipelines — independent activities joined by lazy flow

```sh
python -m lisp run examples/concurrency/01-generator-pipelines/log_pipeline.scm
```

Two pipelines over web-server logs, built entirely from the S9 generator
library that ships in every environment:

1. a **finite** one: entries → `gfilter` (5xx only) → `gmap` (paths) →
   tally and average — each stage is a closure holding its own position;
2. an **infinite** one: `make-range-generator 0` never ends, yet the
   pipeline terminates because the consumer decides how much to take
   (`gtake`). Pull-based flow control, for free.

## What to notice

- Values flow **one at a time**; no stage after the source ever allocates a
  list of the whole input. Producer and consumer run at their own paces.
- The measured outputs are real: avg 5xx latency 6200 ms = (9001+5000+6000+4800)/4;
  207 failures ≈ 20000/97.
- A generator is **single-use** — the example documents the bug it avoided
  (folding the same generator twice measures a drained stream: count 0).
- The interpreter's per-evaluation step budget is the backstop for runaway
  infinite pipelines; 20000 events was chosen to stay inside it.

This is concurrency's gentle single-core foundation; the multi-core
relaxations live in `05-parallel-map` and `06-core-saturation`.

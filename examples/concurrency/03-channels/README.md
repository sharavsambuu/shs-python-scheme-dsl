# 03 · channels — competing consumers on a shared channel

```sh
python examples/concurrency/03-channels/channels.py
```

Two worker threads pull orders from one shared work channel, process them
(each in its **own** `make_env()`), and push results to a results channel
that the main thread drains. The Scheme side defines the worker behavior;
the Python side owns the threads and the queues.

## What to notice

- The transcript interleaves: worker-a and worker-b pick up orders
  milliseconds apart, genuinely at the same time.
- The work here is `spin-ms` (standing in for I/O) — **waiting** is what
  threads are good at. CPU-bound work in Python threads gains nothing
  (the GIL; measured honestly in `04`), so real cores live in 05/06.
- One lock exists in this file — `PRINT_LOCK`, to keep transcript lines
  from interleaving. Zero locks protect the *work*: each worker's state is
  its own env; the channel is the only shared thing.
- Poison pills (`'done`) shut workers down; the join proves no orphans.

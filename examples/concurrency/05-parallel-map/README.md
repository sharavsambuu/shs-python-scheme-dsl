# 05 · parallel map — CPU-bound Scheme work on many cores

```sh
python examples/concurrency/05-parallel-map/parallel_map.py
```

The reusable multi-core pattern: a `multiprocessing` pool where every
worker process builds **its own** `make_env()` once (in the pool
initializer) and then answers `parallel-map`-shaped requests. The workload
counts primes in eight ranges with a trial-division `prime?` written in
Scheme — deliberately naive, honestly CPU-bound.

## Measured on a 24-core machine

```
sequential:  13.718s  (one core)
pool:         2.803s  (8 processes on 24 cores)
speedup:      4.89x
```

## The rules that make it work

- **Env-per-process.** Envs are cheap and self-contained; there is no
  shared state to break. This is the multiprocessing reading of the
  example set's design rule.
- **Source crosses the seam, closures don't.** The Scheme function ships
  to workers as a string and is evaluated in each worker's env.
- **Plain data crosses back.** Numbers pickle cleanly; schemes, closures,
  and envs do not. Design the task boundary around data.
- Threads would not do this: the GIL serializes CPU-bound Python (04
  measured it at 0.85x). Processes each carry their own interpreter and
  their own GIL — that is where the cores come from.

The demonstrable sibling — same shape, scaled to every core, with a
picture — is `06-core-saturation`.

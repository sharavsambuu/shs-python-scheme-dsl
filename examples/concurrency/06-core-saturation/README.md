# 06 · core saturation — one Mandelbrot row per core

```sh
python examples/concurrency/06-core-saturation/cores.py
```

The demonstrable multi-core spectacle. A pool of worker processes — one per
CPU core — renders the Mandelbrot set row by row, with live per-row
progress, then re-renders it on one core and prints the speedup. The math
(`mandelbrot-row`, escape-time iteration over a palette string) is Scheme;
Python only distributes rows and assembles the picture.

## Measured on a 24-core machine

```
one core:    7.838s
24 cores:    0.869s   (48 rows, ~2 per worker)
speedup:     9.02x
```

(Amdahl, honestly: 48 rows over 24 workers ≈ two rows each, and rows differ
in cost — the center rows do the full 50 iterations.)

## What to watch

- The **progress lines arrive in a burst** — dozens of pids each finishing
  rows within the same second. That is your CPU, all of it, busy.
- Every character of the ASCII picture was computed by the Scheme
  interpreter; the speedup is real parallelism, not less work.
- Strings are the ideal cross-process cargo: built in Scheme, pickled
  between processes, assembled in Python.

The reusable pattern (same env-per-worker shape, plain data crossing) is
`05-parallel-map`.

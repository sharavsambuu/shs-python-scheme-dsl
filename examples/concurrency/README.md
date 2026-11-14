# examples/concurrency — eight concurrent shapes for one embedded Scheme

Each folder is a self-contained, runnable example. Every one follows the
same design rule, which is also this repository's concurrency contract:

> **Concurrency machinery lives Python-side, coordination lives Scheme-side,
> and every task gets its own `make_env()`.** The evaluator is a mutable
> tree-walker with no internal locking — never share one live environment
> across OS threads. Sharing is for *values*, not for environments.

Run any example from the repository root:

```sh
python -m shslisp run examples/concurrency/01-generator-pipelines/log_pipeline.scm   # pure Scheme
python examples/concurrency/03-channels/channels.py                              # host examples
```

| # | Folder | Shape | Mechanism | Cores |
|---|--------|-------|-----------|-------|
| 01 | `01-generator-pipelines` | lazy producer→filter→map→consume | S9 generators (in the prelude) | 1 |
| 02 | `02-fibers` | cooperative fibers + round-robin scheduler | generator protocol, pure Scheme | 1 |
| 03 | `03-channels` | competing consumers over a shared channel | Python threads + `queue.Queue` | threads (I/O) |
| 04 | `04-structured-concurrency` | `with-parallel` nursery: join-all, first-error-wins | macro over a Python nursery | threads (I/O) |
| 05 | `05-parallel-map` | parallel map over CPU-bound Scheme work | `multiprocessing`, env-per-worker | **real cores** |
| 06 | `06-core-saturation` | Mandelbrot rendered by every core at once | `multiprocessing` pool + progress | **all cores** |
| 07 | `07-actors` | actors: mailboxes, typed messages, request/reply | threads, one env per actor | threads |
| 08 | `08-supervision` | supervision: let it crash, restart, give up | 07 + try/except as the crash signal | threads |
| 09 | `09-srfi-coroutines-and-fibers` | `yield` generators, delimited prompts, cooperative threads + mutex/cv | `(srfi 190)`, `(srfi 226)`, `(srfi 18)` (`CooperativeFiber`) | 1 (baton) |

## How to read the set

01→02 are single-core foundations: *independent activities joined by lazy
flow* (01) and *a scheduler interleaving parked continuations* (02). 03→04
add real OS threads for **waiting** work. 05→06 are the multi-core pair:
the GIL makes CPU-bound threads useless (04's README tells that story with
a measured 0.85x), so **real cores mean real processes** — 05 is the
reusable pattern, 06 is the demonstrable spectacle. 07→08 are the capstone:
the actor pattern, which fits this architecture almost eerily well because
the design rule above *is* the actor model's first two rules.

## The two walls (stated once, honored everywhere)

1. **R7RS `call/cc` is escape-only**, while suspendable control flow uses
   `shslisp`'s baton-scheduled `CooperativeFiber` runtime via `(srfi 226)`
   (delimited prompts & one-shot composable continuations), `(srfi 158)`/`(srfi 190)`
   (`make-coroutine-generator`, `yield`), and `(srfi 18)` (cooperative threads,
   mutexes, and condition variables) — see `09-srfi-coroutines-and-fibers`.
2. **No shared-memory OS threads over one env** — `(srfi 18)` fibers are
   baton-scheduled (one fiber runs at a time); for true parallel OS threads or
   processes, actors and nurseries (`03`–`08`) give each worker its own `make_env()`.

Everything here is buildable without touching the interpreter: the examples
differ only in the primitives their hosts install and the macros their
Scheme files define.

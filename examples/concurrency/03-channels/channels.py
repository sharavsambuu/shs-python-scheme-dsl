"""channels.py — competing consumers over a real thread-shared channel.

Run with:  python examples/concurrency/03-channels/channels.py

The design rule this example set follows: the concurrency machinery lives
Python-side, the coordination lives Scheme-side, and every task gets its own
environment (never share one live env across threads — docs/capabilities.md).

What it shows:
1. a `queue.Queue` surfaced to Scheme as (ch-put!)/(ch-get!);
2. TWO worker threads, each with its own `make_env`, competing over ONE work
   channel (the classic fan-out pattern — work is pulled, never pushed);
3. a results channel flowing back the other way;
4. an interleaved transcript proving the workers really ran at the same time.

The Scheme code is the *policy* (how to consume, what to compute); the Python
code is the *mechanism* (threads, queues, where values cross the seam).
"""

import queue
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # the repo root

from shslisp import install_primitives, make_env, run
from shslisp.types import intern

# --- the channel registry ------------------------------------------------------
# An integer names a channel; the registry is the only shared mutable thing,
# and the Queue class is the only object two threads ever touch.

CHANNELS: list[queue.Queue] = []

START = time.perf_counter()
PRINT_LOCK = threading.Lock()


def make_channel() -> int:
    CHANNELS.append(queue.Queue())
    return len(CHANNELS) - 1


def ch_put(ch: int, value) -> None:
    CHANNELS[ch].put(value)


def ch_get(ch: int):
    return CHANNELS[ch].get()  # blocks — that is the point


def log(who: str, msg: str) -> None:
    with PRINT_LOCK:
        print(f"[{time.perf_counter() - START:6.3f}s] {who}: {msg}")


# --- the Scheme side ------------------------------------------------------------
# Each worker thread runs this program in its OWN environment. The channel
# numbers are baked in by the spawner. (process task) is the payload — some
# arbitrary CPU work; here, a character checksum, just to be honest about it.

WORKER_SOURCE = """
(define WORK-CH    {work})
(define RESULTS-CH {results})

(define (process task)
  (fold + 0 (map char->integer (string->list task))))

(define (consume name)
  (let ((task (ch-get! WORK-CH)))
    (cond ((eq? task 'done)
           (log "work channel drained, signing off"))
          (else
           (log (string-append "picked up \\"" task "\\""))
           (spin-ms 40)   ; the payload takes real time to compute
           (ch-put! RESULTS-CH (list name (process task)))
           (consume name)))))
"""

WORK_CH = 0  # set by main(); read by spawn_worker when formatting the source
RESULTS_CH = 1


def main() -> None:
    global WORK_CH, RESULTS_CH
    work = make_channel()
    results = make_channel()
    WORK_CH, RESULTS_CH = work, results

    def spawn_worker(name: str) -> threading.Thread:
        def life() -> None:
            env = make_env(install_tetris=False)  # a host example: no game
            install_primitives(env, [
                ("ch-put!", ch_put),
                ("ch-get!", lambda ch: ch_get(ch)),
                ("spin-ms", lambda ms: time.sleep(ms / 1000)),
                ("log", lambda msg: log(name, msg)),
            ])
            source = WORKER_SOURCE.format(work=work, results=results)
            run(source + f'\n(consume "{name}")', env)

        thread = threading.Thread(target=life, name=name)
        thread.start()
        return thread

    print("== two workers, one work channel, one results channel ==")
    print("(main) spawning workers; tasks: 8 orders of work\n")
    workers = [spawn_worker("worker-a"), spawn_worker("worker-b")]

    # feed the work channel — tasks are plain strings, the one value type that
    # crosses the seam with zero ceremony
    for task in ["order-01", "order-02", "order-03", "order-04",
                 "order-05", "order-06", "order-07", "order-08"]:
        ch_put(work, task)
    for _ in workers:
        ch_put(work, intern("done"))  # the poison pill is a Scheme symbol

    # collect the results on this thread (the main thread blocks on the queue)
    total = 0
    for _ in range(8):
        who, checksum = ch_get(results)
        total += checksum
    for t in workers:
        t.join()

    print(f"\n(main) all workers joined; total checksum = {total}")
    print("(main) the transcript above interleaves: two threads, "
          "one shared channel, no locks in the Scheme code")


if __name__ == "__main__":
    main()

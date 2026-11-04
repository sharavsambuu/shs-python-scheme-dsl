"""actors.py — the actor pattern: private state, a mailbox, no locks.

Run with:  python examples/concurrency/07-actors/actors.py

An actor is a small heap of state with an address. Nobody touches the state
directly; you send messages to the address, and the actor processes them one
at a time, in its own environment, on its own thread. The state cannot race
because nothing but the actor can reach it — which is exactly the discipline
this interpreter's "one env per thread" rule wants anyway. The actor pattern
is not a workaround for the walls; it is the shape of the space between them.

What each actor is, concretely:
- a mailbox: a Python queue, registered under a name;
- a behavior: `(define (handle state msg) ...)` in actors' own source;
- a loop: `actor-loop` from actors.scm — six lines, tail-recursive, eternal;
- a thread: `make_env()` + the behavior, one per actor.

Demonstrated here:
1. a counter actor — messages mutate ITS state, nobody else's;
2. request/reply — the reply-to pattern: the answer is itself a message;
3. a ping-pong conversation between two actors, five rounds, interleaved;
4. stopping: the one message every actor understands.

Scheme-side messages are plain data — lists built with `list`, taken apart
with `car`/`cadr` — so `variant-match` (SRFI 241) or plain `cond` both work
for dispatch. No locks appear anywhere in this file.
"""

import queue
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # the repo root

from shslisp import load_file, make_env, run, to_string
from shslisp.types import intern

# --- the actor runtime ---------------------------------------------------------

ACTORS: dict[str, queue.Queue] = {}
LOCK = threading.Lock()
PRINT_LOCK = threading.Lock()   # keeps concurrent logs from interleaving


def msg(*parts):
    """Build a Scheme message from Python: strings become symbols.

    A Scheme `(eq? msg 'add)` compares against an interned Symbol, so a
    Python str "add" would never match — the one seam sharp edge worth
    knowing about. `msg("add", 10)` is the Scheme list `(add 10)`.
    """
    return [intern(p) if isinstance(p, str) else p for p in parts]


def log(actor: str, text: str) -> None:
    with PRINT_LOCK:
        print(f"  [{actor:<8}] {text}")


def spawn(name: str, behavior: str) -> threading.Thread:
    """Register `name`, then run its behavior loop on a fresh env + thread."""
    mailbox: queue.Queue = queue.Queue()
    with LOCK:
        ACTORS[name] = mailbox

    def life() -> None:
        env = make_env(install_tetris=False)   # one env per actor, always
        load_file(env, Path(__file__).with_name("actors.scm"))
        from shslisp import install_primitives

        install_primitives(env, [
            ("recv!", mailbox.get),            # blocks: an actor parks here
            ("send!",
             lambda to, msg: ACTORS[to].put(msg)),
            ("log", lambda text: log(name, to_string(text))),
        ])
        run(behavior, env)                     # defines `handle`
        run("(actor-loop 0)", env)             # ...and lives in it

    thread = threading.Thread(target=life, name=f"actor:{name}", daemon=True)
    thread.start()
    return thread


# --- the behaviors (each one defines `handle`) -----------------------------------

COUNTER = """
(define (handle state msg)
  (cond ((and (pair? msg) (eq? (car msg) 'add))
         (let ((next (+ state (cadr msg))))
           (log (string-append "counter: " (number->string state)
                               " + " (number->string (cadr msg))
                               " -> " (number->string next)))
           next))
        ((and (pair? msg) (eq? (car msg) 'get))
         (send! (cadr msg) (list 'state state))
         (log (string-append "replied with state " (number->string state)))
         state)
        (else state)))
"""

PINGER = """
(define (handle state msg)
  (cond ((eq? msg 'begin)
         (send! 'ponger (list 'ping 1))
         state)
        ((and (pair? msg) (eq? (car msg) 'pong))
         (let ((n (cadr msg)))
           (log (string-append "round " (number->string n) ": pong received"))
           (if (< n 5)
               (begin (send! 'ponger (list 'ping (+ n 1))) state)
               (begin (send! 'main (list 'done n)) state))))
        (else state)))
"""

PONGER = """
(define (handle state msg)
  (if (and (pair? msg) (eq? (car msg) 'ping))
      (let ((n (cadr msg)))
        (log (string-append "round " (number->string n) ": ping received"))
        (send! 'pinger (list 'pong n))
        (+ state 1))
      state))
"""

# --- the scenario ------------------------------------------------------------------


def main() -> None:
    print("== three actors, one mailbox each, zero locks ==")
    inbox: queue.Queue = queue.Queue()
    ACTORS["main"] = inbox

    threads = [
        spawn("counter", COUNTER),
        spawn("pinger", PINGER),
        spawn("ponger", PONGER),
    ]
    time.sleep(1.0)  # let the envs finish loading (each builds a full make_env)

    print("\n-- 1: messages mutate the counter's state, and only its state --")
    for amount in (10, 32, 100):
        ACTORS["counter"].put(msg("add", amount))

    print("\n-- 2: request/reply — the answer is itself a message --")
    ACTORS["counter"].put(msg("get", "main"))
    reply = inbox.get(timeout=5)
    print(f"  [main    ] got reply: {to_string(reply)}")

    print("\n-- 3: ping-pong, five rounds, two actors talking --")
    ACTORS["pinger"].put(intern("begin"))   # a bare symbol, not a list
    done = inbox.get(timeout=5)
    print(f"  [main    ] pinger reports: {to_string(done)} rounds completed")

    print("\n-- 4: stopping --")
    for name in ("counter", "pinger", "ponger"):
        ACTORS[name].put(intern("stop"))    # ditto — the one message every
    for t in threads:                       # actor understands
        t.join(timeout=5)
    print("  [main    ] all actor threads joined; the registry outlives them")


if __name__ == "__main__":
    main()

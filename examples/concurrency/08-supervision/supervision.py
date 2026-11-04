"""supervision.py — actors + the supervisor pattern: let it crash.

Run with:  python examples/concurrency/08-supervision/supervision.py

Erlang's one big idea, on this little stage: an actor that hits an error
does NOT try to patch itself up mid-flight — it crashes, its supervisor
notices, and the actor comes back fresh: same behavior, clean state. The
error handling and the business logic never touch each other.

This is 07-actors's spawn machinery with one addition: `life()` wraps the
actor loop in try/except. A LispError escaping the loop IS the crash signal
— no new vocabulary needed. The interpreter's own error objects (message,
irritants) are what crosses the boundary, so the supervisor's decision is
data-driven, and the whole thing composes with `guard` if a behavior wants
to handle a *specific* failure itself.

Watch the transcript for the story: state builds to 142, the poison pill
crashes the actor, the supervisor restarts it — and the count is 0 again,
because state was never meant to survive a crash. Then it climbs, crashes,
climbs... until the restart budget is spent and the supervisor gives up.
"""

import queue
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # the repo root

from shslisp import LispError, load_file, make_env, run
from shslisp.types import intern

ACTORS: dict[str, queue.Queue] = {}
LOCK = threading.Lock()
PRINT_LOCK = threading.Lock()
START = time.perf_counter()


def log(who: str, text: str) -> None:
    with PRINT_LOCK:
        print(f"[{time.perf_counter() - START:6.2f}s] {who}: {text}")


def msg(*parts):
    """Scheme message from Python — strings become symbols (see 07-actors)."""
    return [intern(p) if isinstance(p, str) else p for p in parts]


# --- the Scheme side ------------------------------------------------------------
# The behavior: a counter with a poison-pill phobia. Messages:
#   (add n)      -> state + n          (get reply) -> sends state back
#   (poison)     -> raises, uncatchably
# Note what is NOT here: any try/catch. Crashing is the behavior's whole
# error strategy; the supervisor owns the recovery.

BEHAVIOR = """
(define (handle state m)
  (cond ((and (pair? m) (eq? (car m) 'add))
         (let ((next (+ state (cadr m))))
           (log (string-append "count -> " (number->string next)))
           next))
        ((and (pair? m) (eq? (car m) 'get))
         (send! (cadr m) (list 'count state))
         state)
        ((and (pair? m) (eq? (car m) 'poison))
         (error "counter: poisoned state detected"))
        (else state)))

(define (actor-loop state)
  (let ((m (recv!)))
    (if (eq? m 'stop)
        (begin (log "clean stop") state)
        (actor-loop (handle state m)))))
"""

MAX_RESTARTS = 3


def supervise(name: str, behavior: str) -> threading.Thread:
    """Spawn a supervised actor. Crash -> log -> restart with FRESH state."""
    mailbox: queue.Queue = queue.Queue()
    with LOCK:
        ACTORS[name] = mailbox
    restarts = 0

    def life() -> None:
        nonlocal restarts
        attempt = restarts
        while True:
            env = make_env(install_tetris=False)  # fresh env = fresh state
            load_file(env, Path(__file__).with_name("actor_loop.scm"))
            from shslisp import install_primitives

            install_primitives(env, [
                ("recv!", mailbox.get),
                ("send!", lambda to, m: ACTORS[to].put(m)),
                ("log", lambda text: log(name, text)),
            ])
            try:
                run(behavior + "\n(actor-loop 0)", env)
                log(f"supervisor", f"{name} stopped cleanly")
                return
            except LispError as exc:
                # THE decision point. Crash is data: message, then policy.
                if restarts >= MAX_RESTARTS:
                    log("supervisor", f"{name} used all {MAX_RESTARTS} "
                                      f"restarts — giving up, actor declared dead")
                    log("supervisor", f"last words: {exc}")
                    return
                restarts += 1
                log("supervisor", f"{name} crashed ({exc}) — "
                                  f"restarting {restarts}/{MAX_RESTARTS}, state reset")

    thread = threading.Thread(target=life, name=name, daemon=True)
    thread.start()
    return thread


def main() -> None:
    counter = supervise("counter", BEHAVIOR)
    time.sleep(1.0)  # env load

    log("main", "story: climb, crash, restart (state resets), repeat x3, give up")
    for amount in (42, 100):
        ACTORS["counter"].put(msg("add", amount))
    ACTORS["counter"].put(msg("poison"))
    time.sleep(0.4)
    for amount in (10, 32):
        ACTORS["counter"].put(msg("add", amount))
    ACTORS["counter"].put(msg("poison"))
    time.sleep(0.4)
    for amount in (5, 7, 11):
        ACTORS["counter"].put(msg("add", amount))
    ACTORS["counter"].put(msg("poison"))
    time.sleep(0.4)
    # the fourth life drains this mail, then its poison is the last straw:
    ACTORS["counter"].put(msg("add", 999))
    ACTORS["counter"].put(msg("poison"))

    counter.join(timeout=15)
    log("main", "the supervisor outlived its actor; the mailbox just holds mail")


if __name__ == "__main__":
    main()

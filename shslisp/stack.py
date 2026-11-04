"""A host stack deep enough for the language's own recursion.

The evaluator is a tree-walker. A *tail* call loops (the trampoline), but a
non-tail call nests, and every level of that nesting is a handful of Python
frames. :data:`shslisp.evaluator.DEPTH_LIMIT` therefore promises one million
nested calls, and the host must have room for them.

On CPython 3.11+ that room is free — Python-to-Python calls no longer consume C
stack — so a deep recursion works on any thread. This module is the belt to
those braces: a program run through :func:`run_with_deep_stack` gets a worker
thread with a large stack *reserved* up front, so the same ceiling holds even
on a host where frames still cost C stack. The reservation is virtual memory;
only the frames that actually nest touch it, so a shallow program pays nothing.

Two entry points deliberately stay on the main thread:

* the pygame edge, because SDL requires its window and event loop there;
* the REPL, because Ctrl-C must be able to cancel the line being read or
  evaluated.

Both rely on CPython ≥3.11 (which this project requires) for the ceiling.
"""
from __future__ import annotations

import threading
from typing import Any, Callable

#: Bytes reserved for a program's thread. Large enough that the evaluator's own
#: ceiling is reached first, so a runaway recursion ends in a
#: ``LispRecursionError`` rather than a dead host.
STACK_BYTES = 512 * 1024 * 1024

#: Marks the threads this module started, so a nested entry point does not
#: spawn another one.
_local = threading.local()


def on_deep_stack() -> bool:
    """True when the current thread is one :func:`run_with_deep_stack` started."""
    return bool(getattr(_local, "deep", False))


def run_with_deep_stack(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Call ``fn(*args, **kwargs)`` with room for a million nested calls.

    The call runs on a fresh thread with :data:`STACK_BYTES` reserved and its
    result (or exception) is handed back, so a caller cannot tell the
    difference beyond a deeper stack.

    It is idempotent: called from a thread that already has the deep stack, it
    simply calls through. That is what lets nested entry points (a script that
    runs another script) pay for the thread only once.
    """
    if on_deep_stack():
        return fn(*args, **kwargs)

    outcome: dict[str, Any] = {}

    def target() -> None:
        _local.deep = True
        try:
            outcome["value"] = fn(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 — re-raised on the caller
            outcome["error"] = exc

    # ``stack_size`` is a process-wide setting for *new* threads, so put it
    # back afterwards: another thread created later should not inherit ours.
    previous = threading.stack_size()
    try:
        threading.stack_size(STACK_BYTES)
    except (ValueError, RuntimeError):  # pragma: no cover — exotic host
        pass
    try:
        worker = threading.Thread(
            target=target, name="lisp-program", daemon=True
        )
        worker.start()
    finally:
        try:
            threading.stack_size(previous)
        except (ValueError, RuntimeError):  # pragma: no cover
            pass

    worker.join()
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("value")

"""``(srfi 226)`` — Control Features (delimited prompts, barriers, and fibers).

Provides a clean, pure-Python cooperative fiber engine alongside SRFI-226
prompt tags, ``call-with-continuation-prompt``, ``abort-current-continuation``,
``call-with-composable-continuation``, ``call-with-continuation-barrier``,
and ``continuation-prompt-available?``.

Each prompt that suspends via ``call-with-composable-continuation`` runs on a
lock-step baton-scheduled Python ``threading.Thread`` (one runnable fiber at a
time), so normal Scheme evaluation pays zero overhead, no C extensions are
needed, and suspension works cleanly through arbitrary ``map``/``for-each``/
``apply`` nesting.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable

from .errors import LispError, LispTypeError
from .evaluator import apply_procedure
from .types import EOF, Primitive, Symbol


@dataclass(eq=False)
class PromptTag:
    """Distinct identity for a delimited continuation prompt."""

    name: str | None = None

    def __repr__(self) -> str:
        return f"#<continuation-prompt-tag {self.name or 'anon'}>"


_DEFAULT_PROMPT_TAG = PromptTag("default")
_local = threading.local()


def _prompt_stack() -> list[tuple[PromptTag, int]]:
    stack = getattr(_local, "prompt_stack", None)
    if stack is None:
        stack = []
        _local.prompt_stack = stack
    return stack


def _barrier_depth() -> int:
    return getattr(_local, "barrier_depth", 0)


def _set_barrier_depth(val: int) -> None:
    _local.barrier_depth = val


class PromptAbort(Exception):
    """Unwinds the stack to the nearest matching ``call-with-continuation-prompt``."""

    def __init__(self, tag: PromptTag, values: list[Any]) -> None:
        self.tag = tag
        self.values = values
        super().__init__(f"abort to prompt {tag}")


class FiberClosed(BaseException):
    """Internal signal to unwind a discarded fiber thread cleanly."""


class CooperativeFiber:
    """Baton-scheduled one-shot fiber for coroutines, generators, and prompts."""

    def __init__(self, target: Callable[[CooperativeFiber], Any]) -> None:
        self._cond = threading.Condition()
        self._state = "init"  # init | running | yielded | done | error
        self._resume_val: Any = None
        self._yield_kind: str = ""
        self._yield_payload: Any = None
        self._closed = False
        self._target = target
        self._thread = threading.Thread(
            target=self._run_target,
            name="shslisp-fiber",
            daemon=True,
        )
        self._thread.start()

    def _run_target(self) -> None:
        with self._cond:
            while self._state == "init" and not self._closed:
                self._cond.wait()
            if self._closed:
                return
        try:
            res = self._target(self)
        except FiberClosed:
            return
        except BaseException as exc:  # noqa: BLE001 — forwarded to caller
            with self._cond:
                self._yield_kind = "error"
                self._yield_payload = exc
                self._state = "error"
                self._cond.notify_all()
            return
        with self._cond:
            self._yield_kind = "done"
            self._yield_payload = res
            self._state = "done"
            self._cond.notify_all()

    def step(self, value: Any = None) -> tuple[str, Any]:
        """Pass the baton into the fiber and wait until it yields or finishes."""
        with self._cond:
            if self._state in ("done", "error"):
                return self._yield_kind, self._yield_payload
            self._resume_val = value
            self._state = "running"
            self._cond.notify_all()
            while self._state == "running":
                self._cond.wait()
            return self._yield_kind, self._yield_payload

    def suspend(self, kind: str, payload: Any) -> Any:
        """Yield from inside the fiber back to its caller, returning the next resume value."""
        with self._cond:
            self._yield_kind = kind
            self._yield_payload = payload
            self._state = "yielded"
            self._cond.notify_all()
            while self._state == "yielded" and not self._closed:
                self._cond.wait()
            if self._closed:
                raise FiberClosed()
            return self._resume_val

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()


def _require_prompt_tag(val: Any, who: str) -> PromptTag:
    if not isinstance(val, PromptTag):
        raise LispTypeError(f"{who}: expected continuation-prompt-tag, got {type(val).__name__}")
    return val


def _make_prompt_tag(*args: Any) -> PromptTag:
    if len(args) > 1:
        raise LispTypeError("make-continuation-prompt-tag: expected 0 or 1 arguments")
    name = str(args[0]) if args and isinstance(args[0], Symbol) else (str(args[0]) if args else None)
    return PromptTag(name=name)


def _prompt_tag_p(v: Any) -> bool:
    return isinstance(v, PromptTag)


def _default_prompt_tag() -> PromptTag:
    return _DEFAULT_PROMPT_TAG


def _prompt_available_p(*args: Any) -> bool:
    tag = _require_prompt_tag(args[0], "continuation-prompt-available?") if args else _DEFAULT_PROMPT_TAG
    b_depth = _barrier_depth()
    for t, depth in reversed(_prompt_stack()):
        if depth < b_depth:
            break
        if t is tag:
            return True
    return False


def _default_handler(*vals: Any) -> Any:
    if len(vals) == 1:
        return apply_procedure(vals[0], [])
    raise LispError("default-prompt-handler: expected 1 thunk argument")


def _drive_prompt(fiber: CooperativeFiber, tag: PromptTag, handler: Any, initial_val: Any = None, is_resume: bool = False) -> Any:
    """Run or resume *fiber* under a delimited prompt for *tag*."""
    stack = _prompt_stack()
    b_depth = _barrier_depth()
    entry = (tag, b_depth)
    stack.append(entry)
    try:
        kind, payload = fiber.step(initial_val)
    finally:
        if stack and stack[-1] is entry:
            stack.pop()
        elif entry in stack:
            stack.remove(entry)

    if kind == "done":
        return payload
    if kind == "abort":
        abort_tag, vals = payload
        if abort_tag is tag:
            return apply_procedure(handler, vals)
        raise PromptAbort(abort_tag, vals)
    if kind == "error":
        exc = payload
        if isinstance(exc, PromptAbort):
            if exc.tag is tag:
                return apply_procedure(handler, exc.values)
            raise exc
        raise exc
    raise LispError(f"call-with-continuation-prompt: unexpected fiber state {kind}")


def _call_with_continuation_prompt(thunk: Any, *rest: Any) -> Any:
    if len(rest) > 2:
        raise LispTypeError("call-with-continuation-prompt: expected 1 to 3 arguments")
    tag = _require_prompt_tag(rest[0], "call-with-continuation-prompt") if len(rest) >= 1 else _DEFAULT_PROMPT_TAG
    handler = rest[1] if len(rest) >= 2 else Primitive("default-prompt-handler", _default_handler)

    def _run_in_fiber(fiber: CooperativeFiber) -> Any:
        prev_fiber = getattr(_local, "active_fiber", None)
        _local.active_fiber = fiber
        _local.prompt_stack = [(tag, 0)]
        _local.barrier_depth = 0
        try:
            return apply_procedure(thunk, [])
        finally:
            _local.active_fiber = prev_fiber

    fiber = CooperativeFiber(_run_in_fiber)
    return _drive_prompt(fiber, tag, handler)


def _abort_current_continuation(tag_obj: Any, *vals: Any) -> Any:
    tag = _require_prompt_tag(tag_obj, "abort-current-continuation")
    # Verify prompt is available above any active barrier.
    if not _prompt_available_p(tag):
        raise LispError(f"abort-current-continuation: no prompt available for {tag}")
    fiber = getattr(_local, "active_fiber", None)
    if fiber is not None and getattr(_local, "in_composable_receiver", False):
        # Suspend the fiber so a captured composable continuation can still resume it.
        return fiber.suspend("abort", (tag, list(vals)))
    raise PromptAbort(tag, list(vals))


def _call_with_composable_continuation(proc: Any, *rest: Any) -> Any:
    if len(rest) > 1:
        raise LispTypeError("call-with-composable-continuation: expected 1 or 2 arguments")
    tag = _require_prompt_tag(rest[0], "call-with-composable-continuation") if rest else _DEFAULT_PROMPT_TAG
    if not _prompt_available_p(tag):
        raise LispError(f"call-with-composable-continuation: no prompt available for {tag}")
    fiber = getattr(_local, "active_fiber", None)
    if fiber is None:
        raise LispError("call-with-composable-continuation: must run inside call-with-continuation-prompt")

    def _k(*args: Any) -> Any:
        val = args[0] if len(args) == 1 else (None if not args else list(args))
        kind, payload = fiber.step(val)
        if kind == "done":
            return payload
        if kind == "abort":
            abort_tag, vals = payload
            raise PromptAbort(abort_tag, vals)
        if kind == "error":
            raise payload
        raise LispError(f"composable-continuation: unexpected fiber state {kind}")

    k_prim = Primitive("composable-continuation", _k)
    prev_flag = getattr(_local, "in_composable_receiver", False)
    _local.in_composable_receiver = True
    try:
        return apply_procedure(proc, [k_prim])
    finally:
        _local.in_composable_receiver = prev_flag


def _call_with_continuation_barrier(thunk: Any) -> Any:
    prev = _barrier_depth()
    _set_barrier_depth(len(_prompt_stack()))
    try:
        return apply_procedure(thunk, [])
    finally:
        _set_barrier_depth(prev)


def make_coroutine_generator(proc: Any) -> Primitive:
    """SRFI-158 ``make-coroutine-generator`` backed by a :class:`CooperativeFiber`."""
    done = False

    def _run_gen(fiber: CooperativeFiber) -> Any:
        def _yield(val: Any = None) -> Any:
            return fiber.suspend("yield", val)

        yield_prim = Primitive("yield", _yield)
        prev_yield = getattr(_local, "coro_yield", None)
        _local.coro_yield = yield_prim
        try:
            apply_procedure(proc, [yield_prim])
        finally:
            _local.coro_yield = prev_yield
        return EOF

    fiber = CooperativeFiber(_run_gen)

    def _next() -> Any:
        nonlocal done
        if done:
            return EOF
        kind, payload = fiber.step(None)
        if kind == "yield":
            return payload
        if kind == "done":
            done = True
            return EOF
        if kind == "error":
            done = True
            raise payload
        done = True
        return EOF

    return Primitive("coroutine-generator", _next)


def coro_yield(val: Any = None) -> Any:
    """Invoke the active thread-local coroutine's ``yield`` (SRFI 190)."""
    y = getattr(_local, "coro_yield", None)
    if y is None:
        raise LispError("yield: called outside coroutine-generator")
    return apply_procedure(y, [val])


def install(scope: Any) -> None:
    """Bind the ``(srfi 226)`` control-features vocabulary into *scope*."""
    bindings = [
        ("make-continuation-prompt-tag", _make_prompt_tag),
        ("continuation-prompt-tag?", _prompt_tag_p),
        ("default-continuation-prompt-tag", _default_prompt_tag),
        ("continuation-prompt-available?", _prompt_available_p),
        ("call-with-continuation-prompt", _call_with_continuation_prompt),
        ("abort-current-continuation", _abort_current_continuation),
        ("call-with-composable-continuation", _call_with_composable_continuation),
        ("call-with-continuation-barrier", _call_with_continuation_barrier),
    ]
    for name, fn in bindings:
        scope.define(name, Primitive(name, fn))

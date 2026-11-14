"""``(srfi 18)`` — Multithreading support (cooperative fibers, mutexes, condvars).

Implements the SRFI-18 API using a deterministic cooperative baton scheduler:
at most one Scheme fiber executes at any instant, so shared Scheme globals
never suffer data races while ``thread-yield!``, ``thread-join!``, mutexes,
and condition variables work cleanly through arbitrary Scheme recursion.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from .errors import LispError, LispTypeError
from .evaluator import apply_procedure
from .types import Primitive, Symbol


class _ThreadTerminated(BaseException):
    """Internal signal to unwind a terminated SRFI-18 fiber."""


class SchemeThread:
    """A cooperative SRFI-18 fiber."""

    def __init__(self, thunk: Any, name: Any = None) -> None:
        self.thunk = thunk
        self.name = name
        self.state = "new"  # new | runnable | blocked | terminated
        self.result: Any = None
        self.error: BaseException | None = None
        self.ident: int | None = None
        self.terminated_flag = False
        self.join_waiters: deque[SchemeThread] = deque()


class SchemeMutex:
    """SRFI-18 mutex."""

    def __init__(self, name: Any = None) -> None:
        self.name = name
        self.owner: SchemeThread | None = None
        self.waiters: deque[SchemeThread] = deque()


class SchemeCondVar:
    """SRFI-18 condition variable."""

    def __init__(self, name: Any = None) -> None:
        self.name = name
        self.waiters: deque[SchemeThread] = deque()


class _CooperativeScheduler:
    """Lock-step baton scheduler ensuring single-threaded Scheme execution."""

    def __init__(self) -> None:
        self.cond = threading.Condition()
        self.active_ident: int | None = None
        self.ready: deque[SchemeThread] = deque()
        self.threads_by_ident: dict[int, SchemeThread] = {}

    def ensure_current(self) -> SchemeThread:
        ident = threading.get_ident()
        t = self.threads_by_ident.get(ident)
        if t is None:
            t = SchemeThread(None, name="primordial")
            t.state = "runnable"
            t.ident = ident
            self.threads_by_ident[ident] = t
        if self.active_ident is None:
            self.active_ident = ident
        return t

    def _handoff_locked(self, cur: SchemeThread, requeue_cur: bool) -> None:
        if requeue_cur and not cur.terminated_flag:
            cur.state = "runnable"
            self.ready.append(cur)
        while self.ready:
            nxt = self.ready.popleft()
            if nxt.state != "terminated" and nxt.ident is not None:
                self.active_ident = nxt.ident
                self.cond.notify_all()
                break
        else:
            # No other runnable fiber: keep baton if cur is still alive.
            if requeue_cur and not cur.terminated_flag:
                self.active_ident = cur.ident
                return
            self.active_ident = None
            self.cond.notify_all()
            return

        while self.active_ident != cur.ident and not cur.terminated_flag:
            self.cond.wait()
        if cur.terminated_flag:
            raise _ThreadTerminated()

    def start(self, t: SchemeThread) -> SchemeThread:
        if t.state != "new":
            raise LispError("thread-start!: thread already started")
        t.state = "runnable"
        started_evt = threading.Event()

        def _runner() -> None:
            ident = threading.get_ident()
            with self.cond:
                t.ident = ident
                self.threads_by_ident[ident] = t
                started_evt.set()
                while self.active_ident != ident and not t.terminated_flag:
                    self.cond.wait()
            if not t.terminated_flag:
                try:
                    t.result = apply_procedure(t.thunk, [])
                except _ThreadTerminated:
                    pass
                except BaseException as exc:  # noqa: BLE001 — stored for thread-join!
                    t.error = exc
            with self.cond:
                t.state = "terminated"
                while t.join_waiters:
                    w = t.join_waiters.popleft()
                    if w.state != "terminated":
                        w.state = "runnable"
                        self.ready.append(w)
                if self.ready:
                    nxt = self.ready.popleft()
                    self.active_ident = nxt.ident
                else:
                    self.active_ident = None
                self.cond.notify_all()

        py_thread = threading.Thread(target=_runner, name="shslisp-srfi18", daemon=True)
        py_thread.start()
        started_evt.wait()
        with self.cond:
            self.ensure_current()
            self.ready.append(t)
        return t

    def yield_current(self) -> None:
        with self.cond:
            cur = self.ensure_current()
            if not self.ready:
                return
            self._handoff_locked(cur, requeue_cur=True)

    def join(self, t: SchemeThread) -> Any:
        with self.cond:
            cur = self.ensure_current()
            if t is cur:
                raise LispError("thread-join!: thread cannot join itself")
            while t.state != "terminated":
                cur.state = "blocked"
                t.join_waiters.append(cur)
                self._handoff_locked(cur, requeue_cur=False)
        if t.error is not None:
            raise t.error
        return t.result

    def mutex_lock(self, m: SchemeMutex) -> bool:
        with self.cond:
            cur = self.ensure_current()
            while m.owner is not None:
                cur.state = "blocked"
                m.waiters.append(cur)
                self._handoff_locked(cur, requeue_cur=False)
            m.owner = cur
            return True

    def mutex_unlock(self, m: SchemeMutex, cv: SchemeCondVar | None = None) -> bool:
        with self.cond:
            cur = self.ensure_current()
            if m.owner is cur:
                m.owner = None
            if m.waiters:
                nxt = m.waiters.popleft()
                if nxt.state != "terminated":
                    nxt.state = "runnable"
                    self.ready.append(nxt)
            if cv is not None:
                cur.state = "blocked"
                cv.waiters.append(cur)
                self._handoff_locked(cur, requeue_cur=False)
            return True

    def condvar_signal(self, cv: SchemeCondVar) -> bool:
        with self.cond:
            self.ensure_current()
            if cv.waiters:
                w = cv.waiters.popleft()
                if w.state != "terminated":
                    w.state = "runnable"
                    self.ready.append(w)
            return True

    def condvar_broadcast(self, cv: SchemeCondVar) -> bool:
        with self.cond:
            self.ensure_current()
            while cv.waiters:
                w = cv.waiters.popleft()
                if w.state != "terminated":
                    w.state = "runnable"
                    self.ready.append(w)
            return True


_SCHED = _CooperativeScheduler()


def _make_thread(thunk: Any, *rest: Any) -> SchemeThread:
    if len(rest) > 1:
        raise LispTypeError("make-thread: expected 1 or 2 arguments")
    name = rest[0] if rest else None
    if isinstance(name, Symbol):
        name = str(name)
    return SchemeThread(thunk, name=name)


def _thread_p(v: Any) -> bool:
    return isinstance(v, SchemeThread)


def _thread_name(t: Any) -> Any:
    if not isinstance(t, SchemeThread):
        raise LispTypeError("thread-name: expected thread")
    return t.name


def _current_thread() -> SchemeThread:
    with _SCHED.cond:
        return _SCHED.ensure_current()


def _thread_start(t: Any) -> SchemeThread:
    if not isinstance(t, SchemeThread):
        raise LispTypeError("thread-start!: expected thread")
    return _SCHED.start(t)


def _thread_yield() -> bool:
    _SCHED.yield_current()
    return True


def _thread_sleep(secs: Any) -> bool:
    _SCHED.yield_current()
    time.sleep(max(0.0, float(secs)))
    return True


def _thread_terminate(t: Any) -> bool:
    if not isinstance(t, SchemeThread):
        raise LispTypeError("thread-terminate!: expected thread")
    with _SCHED.cond:
        t.terminated_flag = True
        t.state = "terminated"
        _SCHED.cond.notify_all()
    return True


def _thread_join(t: Any) -> Any:
    if not isinstance(t, SchemeThread):
        raise LispTypeError("thread-join!: expected thread")
    return _SCHED.join(t)


def _make_mutex(*rest: Any) -> SchemeMutex:
    name = rest[0] if rest else None
    if isinstance(name, Symbol):
        name = str(name)
    return SchemeMutex(name=name)


def _mutex_p(v: Any) -> bool:
    return isinstance(v, SchemeMutex)


def _mutex_lock(m: Any) -> bool:
    if not isinstance(m, SchemeMutex):
        raise LispTypeError("mutex-lock!: expected mutex")
    return _SCHED.mutex_lock(m)


def _mutex_unlock(m: Any, *rest: Any) -> bool:
    if not isinstance(m, SchemeMutex):
        raise LispTypeError("mutex-unlock!: expected mutex")
    cv = rest[0] if rest else None
    if cv is not None and not isinstance(cv, SchemeCondVar):
        raise LispTypeError("mutex-unlock!: expected condition-variable")
    return _SCHED.mutex_unlock(m, cv)


def _make_condvar(*rest: Any) -> SchemeCondVar:
    name = rest[0] if rest else None
    if isinstance(name, Symbol):
        name = str(name)
    return SchemeCondVar(name=name)


def _condvar_p(v: Any) -> bool:
    return isinstance(v, SchemeCondVar)


def _condvar_signal(cv: Any) -> bool:
    if not isinstance(cv, SchemeCondVar):
        raise LispTypeError("condition-variable-signal!: expected condition-variable")
    return _SCHED.condvar_signal(cv)


def _condvar_broadcast(cv: Any) -> bool:
    if not isinstance(cv, SchemeCondVar):
        raise LispTypeError("condition-variable-broadcast!: expected condition-variable")
    return _SCHED.condvar_broadcast(cv)


def install(scope: Any) -> None:
    """Bind the ``(srfi 18)`` cooperative-fiber vocabulary into *scope*."""
    bindings = [
        ("current-thread", _current_thread),
        ("thread?", _thread_p),
        ("make-thread", _make_thread),
        ("thread-name", _thread_name),
        ("thread-start!", _thread_start),
        ("thread-yield!", _thread_yield),
        ("thread-sleep!", _thread_sleep),
        ("thread-terminate!", _thread_terminate),
        ("thread-join!", _thread_join),
        ("mutex?", _mutex_p),
        ("make-mutex", _make_mutex),
        ("mutex-lock!", _mutex_lock),
        ("mutex-unlock!", _mutex_unlock),
        ("condition-variable?", _condvar_p),
        ("make-condition-variable", _make_condvar),
        ("condition-variable-signal!", _condvar_signal),
        ("condition-variable-broadcast!", _condvar_broadcast),
    ]
    for name, fn in bindings:
        scope.define(name, Primitive(name, fn))

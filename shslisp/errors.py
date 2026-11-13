"""Lisp runtime errors — one base class, purpose-named subclasses.

Nothing in the language raises a bare ``Exception``. A program error surfaces
as a :class:`LispError` subclass so a REPL, a script, or a test can tell "the
program is wrong" (catch it, print it, keep going) apart from "the host is
wrong" (let it crash).
"""
from __future__ import annotations


from dataclasses import dataclass


@dataclass(frozen=True)
class SourceLocation:
    """A 1-based line/column position in a source text (H9).

    Attached to errors and returned alongside forms by the ``*_located``
    readers. ``file`` is the host's name for the text (``<string>`` by
    default). Column counts Unicode code points, not bytes.
    """

    file: str = "<string>"
    line: int = 1
    col: int = 1

    def __str__(self) -> str:  # pragma: no cover - exercised via str()
        return f"{self.file}:{self.line}:{self.col}"


class LispError(Exception):
    """Base class for every error a Lisp program can raise."""

    source: SourceLocation | None = None

    def __init__(self, message: str = "", source: SourceLocation | None = None) -> None:
        super().__init__(message)
        self.source = source
        if source is not None and message:
            super().__init__(f"{source}: {message}")

    def __str__(self) -> str:
        """The message, prefixed with ``file:line:col`` when a source is known.

        The evaluator may attach the innermost span AFTER construction (the
        error is raised deep in the trampoline), so the prefix is computed at
        render time. A message that already carries the prefix is untouched —
        the text a caller matched before stays a substring.
        """
        message = super().__str__()
        source = self.source
        if source is not None:
            prefix = f"{source}: "
            if not message.startswith(prefix):
                return prefix + message
        return message


class LispSyntaxError(LispError):
    """The reader could not turn text into forms (unbalanced parens, a
    runaway string, a stray ``)``)."""


class LispNameError(LispError):
    """A symbol was referenced before it was bound."""


class LispTypeError(LispError):
    """A procedure was handed a value of the wrong type."""


class LispArityError(LispError):
    """A procedure was handed the wrong number of arguments."""

    def __init__(self, name: str, expected: str, got: int) -> None:
        super().__init__(f"{name}: expected {expected} argument(s), got {got}")
        self.name = name
        self.expected = expected
        self.got = got


class LispRecursionError(LispError):
    """A non-tail recursion outran the interpreter's stack budget.

    Tail calls cost no host stack, so this is only ever reached by *non-tail*
    recursion (``(+ 1 (f (- n 1)))``) deeper than :data:`shslisp.evaluator.DEPTH_LIMIT`.
    Raising a :class:`LispError` here — rather than letting Python's own
    ``RecursionError`` escape — keeps the abstraction whole: a Lisp program
    only ever sees Lisp errors.
    """


class FileError(LispError):
    """A host filesystem operation failed (R7RS ``file-error?``)."""


class ReadError(LispError):
    """A datum could not be read from a port (R7RS ``read-error?``)."""


class LispBudgetError(LispError):
    """A program outran the interpreter's step budget.

    The companion to :class:`LispRecursionError` for the case the stack
    budget cannot see: tail calls are flat, so an infinite tail loop costs no
    depth — but it still spends a real step of Python work each round. Each
    root evaluation counts its trampoline steps against
    :data:`shslisp.evaluator.STEPS_BUDGET` (the MAX_PUMP backstop a self-hosted
    runtime owes itself), and past that a clean Lisp error ends the walk
    instead of a hang.
    """


class LispRaise(LispError):
    """A value in flight, put there by ``(raise obj)``.

    The condition system's carrier: it is a :class:`LispError` so an unhandled
    ``raise`` still travels the ordinary error rail, but a ``guard`` or
    ``with-exception-handler`` can tell it apart and hand ``.value`` to the
    handler.
    """

    def __init__(self, value: object, continuable: bool = False) -> None:
        super().__init__(_describe(value))
        self.value = value
        #: ``(raise-continuable ...)`` marks its value: a handler that returns
        #: lets the program continue with the handler's result, instead of
        #: re-raising. ``(raise ...)`` is never continuable.
        self.continuable = continuable


def _describe(value: object) -> str:
    """A one-line message for a raised value (its ``message`` if it has one)."""
    message = getattr(value, "message", None)
    if isinstance(message, str):
        return message
    return str(value)


class ContinuationJump(Exception):
    """Internal control flow: a continuation was invoked.

    Deliberately *not* a :class:`LispError`, so the condition system (which
    catches Lisp errors) never intercepts an escape in progress; it unwinds
    straight to the ``call/cc`` that created it.
    """

    def __init__(self, token: object, value: object) -> None:
        super().__init__("continuation invoked")
        self.token = token
        self.value = value

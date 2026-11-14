"""``(srfi 28)`` — basic format strings (S18), core-backed on the printer.

CLI scripts spent whole ``(display ...)`` chains assembling one line of
telemetry. ``format`` is the one-call spelling, and it delegates to the
language's own printer, so ``~a`` and ``~s`` render exactly what ``display``
and ``write`` would — no second formatting dialect to keep in sync.

``docs/SRFI_TASKS.md`` (S18) is the plan this implements. The library entry in
:mod:`shslisp.library` scopes the name; the primitive is core-*backed*
(installed into the library's own scope on first import), so the strict
``r7rs`` profile leaves it import-only.

**Scope**: ``format`` with the four directives the ledger claims — ``~a``
(display), ``~s`` (write), ``~%`` (newline), ``~~`` (a literal tilde).

**Destination** is SRFI 28's: ``#f`` answers the string, ``#t`` writes to
``(current-output-port)``, and a port writes to that port. The return value on
the two port paths is unspecified (``#<void>`` in practice) — callers use
``#f`` when they need the text.

**Documented deviations** (``docs/srfi.md`` carries the list):

* ``~%`` and ``~~`` are SRFI 48's directives, not SRFI 28's (which specifies
  only ``~a`` and ``~s``). Both are additive — no SRFI 28 program can observe
  them unless it writes them — and the ledger asked for them.
* A directive with no argument, an unknown directive, or leftover arguments
  is a loud :class:`LispError`: a format string that silently dropped a value
  is the class of bug this library exists to remove.
"""

from __future__ import annotations

from typing import Any

from .env import Environment
from .errors import LispError, LispTypeError
from .evaluator import apply_procedure
from .printer import to_string
from .types import NIL, Port, Primitive, intern

__all__ = ["install"]

#: The print directives: ``~a``/``~s`` each consume one argument.
_VALUE_DIRECTIVES = {"a": False, "s": True}


# --------------------------------------------------------------------------- #
#  Ports                                                                       #
# --------------------------------------------------------------------------- #

def _current_output_port(env: Environment) -> Any:
    """``(current-output-port)`` from the enclosing environment, if bound.

    The prelude's parameter is a closure over a cell, so calling it answers the
    port the program has parameterized — the same object ``display`` uses.
    """
    found = env.find(intern("current-output-port"))
    if found is None:  # pragma: no cover - the prelude always binds it
        raise LispError("format: no current output port is bound")
    return apply_procedure(env.lookup(intern("current-output-port")), [])


def _write_to(port: Any, text: str, who: str) -> None:
    if not isinstance(port, Port):
        raise LispTypeError(f"{who}: expected an output port, got {port!r}")
    if not port.writable:
        raise LispTypeError(f"{who}: not an output port")
    if port.closed:
        raise LispTypeError(f"{who}: port is closed")
    port.stream.write(text)


# --------------------------------------------------------------------------- #
#  format                                                                      #
# --------------------------------------------------------------------------- #

def _render(template: str, args: list, who: str) -> str:
    out: list = []
    index = 0
    position = 0
    length = len(template)
    while position < length:
        char = template[position]
        if char != "~":
            out.append(char)
            position += 1
            continue
        position += 1
        if position >= length:
            raise LispError(f"{who}: format string ends with a bare '~'")
        directive = template[position]
        position += 1
        if directive == "~":
            out.append("~")
        elif directive == "%":
            out.append("\n")
        elif directive in _VALUE_DIRECTIVES:
            if index >= len(args):
                raise LispError(
                    f"{who}: no argument left for '~{directive}' at position {position - 2}"
                )
            out.append(to_string(args[index], write=_VALUE_DIRECTIVES[directive]))
            index += 1
        else:
            raise LispError(f"{who}: unknown directive '~{directive}'")
    if index < len(args):
        raise LispError(
            f"{who}: {len(args) - index} argument(s) left over after the format string"
        )
    return "".join(out)


def _format_value(destination: Any, template: Any, args: list) -> Any:
    if not isinstance(template, str):
        raise LispTypeError(f"format: expected a format string, got {template!r}")
    return _render(str(template), args, "format")


# --------------------------------------------------------------------------- #
#  Installing                                                                  #
# --------------------------------------------------------------------------- #

def install(env: Environment) -> None:
    """Bind the ``(srfi 28)`` surface into *env* (the library's private scope).

    The procedure closes over *env* so ``#t`` (write to the current output
    port) resolves the prelude's parameter in the environment the library was
    installed into — the same object ``display`` writes through.
    """

    def format_fn(destination: Any, template: Any, *args: Any) -> Any:
        text = _format_value(destination, template, list(args))
        if destination is False:
            return text
        if destination is True:
            _write_to(_current_output_port(env), text, "format")
            return NIL
        _write_to(destination, text, "format")
        return NIL

    env.define(intern("format"), Primitive("format", format_fn))

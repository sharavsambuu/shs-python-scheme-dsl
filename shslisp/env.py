"""Lexical environments — the chain of scopes a symbol is looked up through.

One dictionary plus a parent pointer. Everything a Lisp needs to know about
scope falls out of that: a closure captures the environment object it was
made in, so it keeps seeing that scope's bindings even after the ``define``
that created them returned (the classic test of lexical, not dynamic, scope).
"""
from __future__ import annotations

import re
from typing import Any, Optional

from .errors import LispNameError
from .types import ForwardReference, Symbol

#: A hygiene alias ends in ``#h<counter>``. An error that leaks one is telling
#: the programmer about a name they never wrote, so the messages below put the
#: original spelling back.
_ALIAS_SUFFIX = re.compile(r"#h\d+$")


def _original(name: Symbol) -> str:
    """``later#h1`` → ``later``: an alias reported as the name it stands for."""
    return _ALIAS_SUFFIX.sub("", str(name))


class Environment:
    """A frame of bindings with an optional parent.

    ``loader`` is the module loader this scope was created in (:class:`shslisp.loader.Loader`).
    It is inherited from the parent, so any scope can ask ``(load ...)`` and get
    the same cache; the value is host state, not a binding a program can read.
    """

    __slots__ = ("vars", "parent", "loader", "libraries", "feature_extra", "core_names")

    def __init__(
        self,
        parent: Optional["Environment"] = None,
        vars: Optional[dict[Symbol, Any]] = None,
        loader: Any = None,
    ) -> None:
        self.vars: dict[Symbol, Any] = dict(vars) if vars else {}
        self.parent = parent
        self.loader = loader if loader is not None or parent is None else parent.loader
        #: The library registry this scope was created in
        #: (:mod:`shslisp.library`), inherited from the parent like ``loader``.
        #: ``None`` only for a root scope nobody installed a registry into.
        self.libraries = None if parent is None else parent.libraries
        #: The profile's additional feature identifiers (``dsl-profile`` and the
        #: SRFI names), set on the root by :func:`shslisp.runtime.make_env` and
        #: inherited from the parent like ``loader`` — this is what keeps
        #: ``cond-expand`` and ``(features)`` answering the same question.
        self.feature_extra = () if parent is None else parent.feature_extra
        #: The names the core floor itself defined
        #: (:func:`shslisp.builtins.install_core`), set on the root and inherited
        #: like ``loader`` — the library system refuses to let an import
        #: silently replace any of them (see :func:`shslisp.library.apply_imports`).
        self.core_names = frozenset() if parent is None else parent.core_names


    def define(self, name: Symbol, value: Any) -> None:
        """Bind *name* in **this** frame (shadowing any outer binding)."""
        self.vars[name] = value

    def find(self, name: Symbol) -> Optional["Environment"]:
        """The nearest frame that binds *name*, or ``None``."""
        env: Optional[Environment] = self
        while env is not None:
            if name in env.vars:
                return env
            env = env.parent
        return None

    def lookup(self, name: Symbol) -> Any:
        """The value bound to *name*, or raise :class:`LispNameError`.

        A hygiene alias for an identifier that was unbound where its macro was
        defined is bound to a :class:`ForwardReference`; resolving it *here*,
        in the definition site's root scope, is what keeps a use-site frame
        from capturing it while still letting a later top-level ``define``
        answer.
        """
        env = self.find(name)
        if env is None:
            raise LispNameError(f"unbound symbol: {_original(name)}")
        value = env.vars[name]
        seen: Optional[set] = None
        while isinstance(value, ForwardReference):
            seen = seen if seen is not None else set()
            if value.name in seen:
                raise LispNameError(f"unbound symbol: {_original(value.name)}")
            seen.add(value.name)
            found = value.env.find(value.name)
            if found is None:
                raise LispNameError(f"unbound symbol: {_original(value.name)}")
            value = found.vars[value.name]
        return value

    def set(self, name: Symbol, value: Any) -> None:
        """Assign through to the frame that already binds *name*."""
        env = self.find(name)
        if env is None:
            raise LispNameError(f"cannot set! unbound symbol: {_original(name)}")
        env.vars[name] = value

    def is_bound(self, name: Symbol) -> bool:
        return self.find(name) is not None

"""Lexical environments — the chain of scopes a symbol is looked up through.

One dictionary plus a parent pointer. Everything a Lisp needs to know about
scope falls out of that: a closure captures the environment object it was
made in, so it keeps seeing that scope's bindings even after the ``define``
that created them returned (the classic test of lexical, not dynamic, scope).
"""
from __future__ import annotations

from typing import Any, Optional

from .errors import LispNameError
from .types import Symbol


class Environment:
    """A frame of bindings with an optional parent.

    ``loader`` is the module loader this scope was created in (:class:`lisp.loader.Loader`).
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
        #: (:mod:`lisp.library`), inherited from the parent like ``loader``.
        #: ``None`` only for a root scope nobody installed a registry into.
        self.libraries = None if parent is None else parent.libraries
        #: The profile's additional feature identifiers (``dsl-profile`` and the
        #: SRFI names), set on the root by :func:`lisp.runtime.make_env` and
        #: inherited from the parent like ``loader`` — this is what keeps
        #: ``cond-expand`` and ``(features)`` answering the same question.
        self.feature_extra = () if parent is None else parent.feature_extra
        #: The names the core floor itself defined
        #: (:func:`lisp.builtins.install_core`), set on the root and inherited
        #: like ``loader`` — the library system refuses to let an import
        #: silently replace any of them (see :func:`lisp.library.apply_imports`).
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
        """The value bound to *name*, or raise :class:`LispNameError`."""
        env = self.find(name)
        if env is None:
            raise LispNameError(f"unbound symbol: {name}")
        return env.vars[name]

    def set(self, name: Symbol, value: Any) -> None:
        """Assign through to the frame that already binds *name*."""
        env = self.find(name)
        if env is None:
            raise LispNameError(f"cannot set! unbound symbol: {name}")
        env.vars[name] = value

    def is_bound(self, name: Symbol) -> bool:
        return self.find(name) is not None

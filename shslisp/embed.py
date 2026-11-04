"""Embedding the language in a Python program — the host-facing seam.

This module is what a *different* project imports. It knows nothing about any
particular domain; it is the mechanism by which a host says "here are my
functions, let Lisp call them", in the shape this repository insists on
(``docs/PRACTICES.md`` §9): **a declared list, resolved once, no dynamic
lookup**. The Tetris edition next door is one caller of this API, not a special
case of it.

A host project does three things:

.. code-block:: python

    from shslisp import make_env, install_primitives

    def cart_total(cart): ...
    def cart_add(cart, sku, qty): ...

    env = make_env()                       # a general Scheme, no game needed
    install_primitives(env, [              # the whole crossing, in one list
        ("cart-total", cart_total),
        ("cart-add!", cart_add),
    ])

    from shslisp import run
    run("(cart-total (cart-add! (make-cart) \"abc\" 2))", env)

Three rules make that safe to reason about:

1. **Declared, not discovered.** ``install_primitives`` takes an explicit list;
   nothing is found by ``getattr(module, type(x).__name__)`` at call time. A
   reviewer reads one diff and sees every name the host exposes.
2. **Total and loud.** A duplicate name, a non-callable, or a malformed entry
   raises at install time, naming the offender — never a silent shadow.
3. **Composable.** An *extension* is any callable ``env -> env`` (or an object
   with an ``install(env)`` method), so a host ships its vocabulary as a value
   and passes it to :func:`shslisp.runtime.make_env` via ``extensions=[...]``.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping, Union

from .env import Environment
from .errors import LispError
from .types import Primitive, intern

__all__ = [
    "PrimitiveTable",
    "install_primitives",
    "install_extension",
    "load_lisp",
]

#: What :func:`install_primitives` accepts: a mapping of ``name -> callable``,
#: or an iterable of ``(name, callable)`` pairs. The list form is preferred for
#: review (it spells its own order); the mapping form is a convenience.
PrimitiveTable = Union[
    Mapping[str, Callable[..., Any]],
    Iterable[tuple[str, Callable[..., Any]]],
]


def install_primitives(
    env: Environment,
    primitives: PrimitiveTable,
    *,
    source: str = "the host",
) -> Environment:
    """Bind every declared primitive into *env*; return *env*.

    *source* names the declaring file or project, so a failure says *where* the
    bad entry is — the same courtesy the interpreter pays its own builtins.
    """
    items = (
        primitives.items() if isinstance(primitives, Mapping) else primitives
    )
    seen: set[str] = set()
    for entry in items:
        try:
            name, fn = entry
        except (TypeError, ValueError):
            raise LispError(
                f"{source}: every primitive must be a (name, callable) pair, "
                f"got {entry!r}"
            ) from None
        if not isinstance(name, str):
            raise LispError(f"{source}: primitive name {name!r} is not a string")
        if name in seen:
            raise LispError(f"{source}: duplicate primitive {name!r}")
        if not callable(fn):
            raise LispError(
                f"{source}: {name!r} is not callable "
                f"({type(fn).__name__})"
            )
        seen.add(name)
        env.define(intern(name), Primitive(name, fn))
    return env


def install_extension(env: Environment, extension: Any) -> Environment:
    """Run one extension against *env* and return the environment.

    An extension is either a plain callable (``lambda env: ...``) or an object
    that exposes ``install(env)`` — so a host can pass a module, a class
    instance, or a function and all three read the same at the call site. An
    extension may return a new environment (rare) or nothing (usual).
    """
    run = getattr(extension, "install", extension)
    if not callable(run):
        raise LispError(
            f"extension {extension!r} is neither callable nor has .install(env)"
        )
    result = run(env)
    return result if isinstance(result, Environment) else env


def load_lisp(env: Environment, path: Any) -> Any:
    """Load a ``.scm`` file through *env*'s loader; return its last value.

    Thin convenience so an embedder never has to import :mod:`shslisp.runtime`
    just to run a file. Falls back to a plain read-and-evaluate when the
    environment has no loader attached.
    """
    from .runtime import load_file

    return load_file(env, path)

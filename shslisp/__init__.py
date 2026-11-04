"""``shslisp`` — a small Scheme-flavored Lisp you can embed in any Python program.

The language is the first-class thing here; a domain (the Tetris game, or one
of your own) is a library on top of it. Read the modules in this order:

* :mod:`shslisp.reader` — text becomes data (and ``'x`` becomes ``(quote x)``);
* :mod:`shslisp.types` — what the values *are*;
* :mod:`shslisp.evaluator` — data becomes behaviour, via a tail-calling loop;
* :mod:`shslisp.stack` — the host stack that loop's non-tail recursion needs;
* :mod:`shslisp.loader` — ``(load …)``: how a program is split across files;
* :mod:`shslisp.builtins` — the primitives;
* :mod:`shslisp.syntax` — ``define-syntax``/``syntax-rules`` (hygienic macros);
* :mod:`shslisp.prelude` (``prelude.scm``) — the standard library, in Lisp;
* :mod:`shslisp.rope` (``rope.scm``) — Result, Kleisli, and ROP, in Lisp.

To put your own Python functions in front of a program — the whole point of a
DSL host — read :mod:`shslisp.embed`::

    from shslisp import install_primitives, make_env, run

    env = make_env()                       # a general Scheme, no game needed
    install_primitives(env, [("double", lambda n: n * 2)])
    run("(double 21)", env)                # -> 42

Then ``tetris/`` for the game edition, and ``python -m shslisp repl`` to use it.
"""
from __future__ import annotations

import sys

# The floor is a semantics guarantee, not a packaging nicety: the evaluator
# sizes the host recursion limit for a million nested Lisp calls, which only
# holds where Python-to-Python calls do not consume C stack (CPython 3.11+).
# pip refuses to install on an older interpreter; this catches a tree that
# was vendored in instead, loudly, before a deep recursion can segfault it.
if sys.version_info < (3, 11):
    raise ImportError(
        "shslisp requires Python 3.11 or newer (the evaluator's recursion "
        f"ceiling relies on 3.11+ stackless calls); this is "
        f"{sys.version.split()[0]}"
    )

from .embed import install_extension, install_primitives, load_lisp
from .env import Environment
from .errors import (
    LispArityError,
    LispError,
    LispNameError,
    LispRecursionError,
    LispSyntaxError,
    LispTypeError,
)
from .evaluator import apply_procedure, equal, evaluate, evaluate_program
from .loader import Loader
from .printer import to_string
from .reader import read_all, read_one
from .runtime import load_file, make_env, run
from .stack import STACK_BYTES, on_deep_stack, run_with_deep_stack
from .types import (
    NIL,
    Char,
    Closure,
    ErrorObject,
    HashTable,
    Macro,
    Pair,
    Primitive,
    Symbol,
    SyntaxRules,
    Tagged,
    Values,
    Vector,
    intern,
    is_tagged,
    is_true,
    make_tagged,
)

__all__ = [
    "Environment",
    "Loader",
    "NIL",
    "Char",
    "Closure",
    "ErrorObject",
    "HashTable",
    "Macro",
    "Pair",
    "Primitive",
    "Symbol",
    "SyntaxRules",
    "Tagged",
    "Values",
    "Vector",
    "intern",
    "is_tagged",
    "is_true",
    "make_tagged",
    "apply_procedure",
    "equal",
    "evaluate",
    "evaluate_program",
    "to_string",
    "read_all",
    "read_one",
    "install_primitives",
    "install_extension",
    "load_lisp",
    "load_file",
    "make_env",
    "run",
    "STACK_BYTES",
    "on_deep_stack",
    "run_with_deep_stack",
    "LispError",
    "LispSyntaxError",
    "LispNameError",
    "LispTypeError",
    "LispArityError",
    "LispRecursionError",
]

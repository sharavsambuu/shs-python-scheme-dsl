"""Assembling a ready-to-run environment.

Two layers are the *language*, and they always come:

1. **core** — the primitives (:mod:`lisp.builtins`);
2. **prelude** — the standard library and the ROP library, written in Lisp
   itself (``lisp/prelude.scm``, ``lisp/rope.scm``).

Everything after that is an **extension**, and each can be left out:

3. whatever the host passes in ``extensions=[...]`` (see :mod:`lisp.embed`);
4. the Tetris edition, when this project is present — wired by the game's own
   :func:`tetris.env.install`, not by anything here.

That is the whole generality story: ``make_env()`` is a perfectly good
general-purpose Scheme, and the game is one extension of it. A foreign project
that vendor-copies ``lisp/`` gets the first two layers and nothing else, because
``install_tetris`` defaults to ``None`` — *auto* — meaning "include the game
only if the ``tetris`` package is importable."

Every environment also gets a :class:`~lisp.loader.Loader`, so a program can be
split across files from the very first form it reads. ``make_env`` only decides
*where* a bare module name is looked up; the rules of resolution, load-once, and
cycle detection live in the loader.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, TextIO

from .builtins import install_core
from .embed import install_extension
from .env import Environment
from .errors import LispError
from .evaluator import evaluate_program
from .features import feature_symbols
from .library import install as install_libraries
from .loader import Loader
from .reader import read_all
from .types import intern, make_list, Primitive

__all__ = ["load_file", "make_env", "run", "PRELUDE", "ROPE_PRELUDE"]

#: The standard library, in Lisp.
PRELUDE = Path(__file__).with_name("prelude.scm")

#: The ROP library (Result, Kleisli, do-notation), also written in Lisp.
ROPE_PRELUDE = Path(__file__).with_name("rope.scm")

#: An extension is any callable ``env -> env`` or object with ``install(env)``.
Extension = Any

#: The game package, named once. Present only in this repository's tree; a
#: foreign project that vendor-copies ``lisp/`` simply never has it. We probe
#: for the *edition* (``tetris.env``) rather than the bare package name, so an
#: unrelated module that happens to be called ``tetris`` is not mistaken for it.
_GAME_PACKAGE = "tetris.env"


def _game_available() -> bool:
    """Is the Tetris edition importable from here? (Auto mode's whole test.)"""
    try:
        return importlib.util.find_spec(_GAME_PACKAGE) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        # No importable `tetris` package, or a broken parent on the path.
        return False


def load_file(env: Environment, path: Any) -> Any:
    """Read and evaluate every form in *path*; return the last value.

    When *env* carries a loader (every environment from :func:`make_env` does)
    the file is loaded through it: it joins the load-once cache, and its own
    ``(load ...)`` calls resolve relative to *it*.
    """
    if env.loader is not None:
        return env.loader.load_one(path)
    source = Path(path).read_text(encoding="utf-8")
    return evaluate_program(read_all(source), env)


def make_env(
    out: Optional[TextIO] = None,
    prelude: bool = True,
    search_paths: Iterable[Any] = (),
    loader: Optional[Loader] = None,
    extensions: Iterable[Extension] = (),
    install_tetris: Optional[bool] = None,
    profile: Optional[str] = "dsl",
) -> Environment:
    """Build a global environment: core, prelude, then the requested extensions.

    *search_paths* are tried **before** the working directory, so an embedder
    can put its own library first. *extensions* are run after the prelude, in
    order; each is a callable ``env -> env`` or an object with ``install(env)``
    (see :func:`lisp.embed.install_extension`).

    *install_tetris* selects the Tetris edition — ``True`` to require it,
    ``False`` to omit it, and the default ``None`` for *auto*: include it when
    the ``tetris`` package can be imported. Auto is what makes ``make_env()``
    just work both in this repository (the game is installed) and in a foreign
    project that copied ``lisp/`` (it is not).

    *profile* selects which SRFI layer is pre-imported: ``"dsl"`` (the
    default) installs every mandatory SRFI with the collision resolutions
    applied (:mod:`lisp.profile`), ``"r7rs"`` installs only the strict subset
    the conformance harness runs, and ``None`` skips the profile entirely for
    tests that need the bare core + prelude. Orthogonal to *install_tetris*:
    no profile installs game bindings.
    """
    env = Environment()
    install_core(env, out=out if out is not None else sys.stdout)
    loader = (loader if loader is not None else Loader()).attach(env)
    loader.add_search_paths([*search_paths, Path.cwd()])
    if prelude:
        loader.load_one(PRELUDE)
        loader.load_one(ROPE_PRELUDE)

    # The library system — registered after the prelude, because every
    # ``(scheme ...)`` export resolves against *env* itself: the bindings an
    # import binds are the very objects the environment already has.
    install_libraries(env)

    # The SRFI layer, pre-imported by the profile. Additive: the profile binds
    # no name the core already binds, so no existing meaning changes.
    if profile is not None:
        from .profile import PROFILE_FEATURES, install as install_profile

        install_profile(env, profile)
        extra = PROFILE_FEATURES.get(profile, ())
        env.feature_extra = tuple(extra)
        env.define(
            intern("features"),
            Primitive(
                "features", lambda extra=extra: make_list(feature_symbols(extra))
            ),
        )

    if install_tetris is None:
        install_tetris = _game_available()
    if install_tetris:
        # The host edition's own installer — this module knows the *name*, the
        # edition knows the vocabulary. Deferred so the language imports no
        # host package until a caller actually asks for one.
        try:
            from tetris.env import install as install_game
        except ImportError as exc:
            raise LispError(
                "no host edition is installed: the 'tetris.env' package is "
                "not importable. make_env(install_tetris=True) requires the "
                "host project; use install_tetris=False to forbid it, or "
                "leave the default (auto) to include a host when present"
            ) from exc
        install_game(env)

    for extension in extensions:
        install_extension(env, extension)
    return env


def run(source: str, env: Optional[Environment] = None) -> Any:
    """Evaluate a program string; the last value is returned."""
    return evaluate_program(read_all(source), env if env is not None else make_env())

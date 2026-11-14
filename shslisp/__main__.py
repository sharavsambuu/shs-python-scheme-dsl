"""``shs`` — the command line for this Scheme.

    shs                              # the REPL (the default)
    shs -e "(+ 1 2)"                 # evaluate an expression, print the value
    shs run program.scm [args ...]   # run a script; args become
                                     # ``*command-line-args*``
    shs program.scm [args ...]       # the same, gosh-style: the file *is* the
                                     # command when it exists
    shs --profile r7rs               # strict R7RS-small: no SRFIs preloaded
    shs --plugin mypkg --plugin mypkg:extra -e "(host-verb)"
    shs --version

``shs`` is deliberately gosh-shaped: no arguments is an interactive session,
``run`` executes a file, ``-e`` evaluates an expression, and a script may
begin with a shebang line (``#!/usr/bin/env shs``) and be run as an
executable directly.

Profiles (``--profile``): ``dsl`` — the default — pre-imports the mandatory
SRFI layer (SRFIs 1, 26, 88, 89, 197, 241) with the documented collision
resolutions; ``r7rs`` pre-imports only the strict R7RS-small conformance
subset; ``none`` skips the profile entirely.

Plugins (``--plugin``, repeatable, or the ``SHS_PLUGINS`` environment
variable, ``os.pathsep``-separated): each spec is ``module[:attr]`` — an
importable Python module and the attribute (default ``install``) called with
the environment, exactly the extension shape :mod:`shslisp.embed` documents.
The same plugin list reaches ``run``, ``-e`` and ``repl``; a spec that does
not import, or an attribute that is not callable, is a loud error naming the
spec, never a silent skip.

This module is composition only. Everything interesting lives in the ``shslisp``
package, and a host project embeds the language directly (``shslisp.embed``)
without ever coming near this file. Additional script directories can be put
on the load path with the ``SHS_PATH`` environment variable
(``os.pathsep``-separated, like ``PATH``).
"""
from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path
from typing import Any, Iterable, List, Optional, TextIO

from .errors import LispError
from .evaluator import evaluate_program
from .printer import to_string
from .reader import read_all
from .repl import run_repl
from .runtime import load_file, make_env
from .stack import run_with_deep_stack
from .types import intern, make_list

#: Program name and one-line identity, used by argparse and error messages.
PROGRAM = "shs"

#: Fallback version when the distribution metadata is absent (a source tree
#: run in place rather than installed).
_FALLBACK_VERSION = "0.2.3"


def _version() -> str:
    """The installed version, or the fallback for an in-place source tree."""
    try:
        from importlib.metadata import version, PackageNotFoundError

        return version("shslisp")
    except PackageNotFoundError:
        return _FALLBACK_VERSION
    except Exception:  # noqa: BLE001 — any metadata trouble is the same answer
        return _FALLBACK_VERSION


# --------------------------------------------------------------------------- #
#  Environments                                                                #
# --------------------------------------------------------------------------- #

def _profile_value(name: str) -> Optional[str]:
    """``none`` means *skip the profile*; anything else is a profile name."""
    return None if name == "none" else name


def _search_paths() -> List[Path]:
    """Extra load path from ``SHS_PATH``, ``os.pathsep``-separated (``:`` on
    Unix, ``;`` on Windows — the same convention as ``PATH`` itself).

    The working directory is added by :func:`shslisp.runtime.make_env` itself;
    a user or host adds more directories here without touching any code.
    """
    return [
        Path(part)
        for part in os.environ.get("SHS_PATH", "").split(os.pathsep)
        if part
    ]


# --------------------------------------------------------------------------- #
#  Plugins (R-01)                                                             #
# --------------------------------------------------------------------------- #

def _plugin_specs(cli_specs: Optional[Iterable[str]] = None) -> List[str]:
    """Every plugin spec, in install order: ``SHS_PLUGINS`` then ``--plugin``.

    ``SHS_PLUGINS`` is ``os.pathsep``-separated like ``PATH`` (``:`` on Unix,
    ``;`` on Windows), so a host can export its vocabulary once and have every
    ``shs`` invocation — ``run``, ``-e`` and ``repl`` — see it.
    """
    specs = [
        part.strip()
        for part in os.environ.get("SHS_PLUGINS", "").split(os.pathsep)
        if part.strip()
    ]
    specs.extend(spec.strip() for spec in (cli_specs or ()) if spec.strip())
    # One install per spec: a host that exports SHS_PLUGINS and also passes
    # --plugin would otherwise run an installer twice, and `install_primitives`
    # refuses a duplicate name. First mention wins, order preserved.
    seen: set[str] = set()
    unique: List[str] = []
    for spec in specs:
        if spec not in seen:
            seen.add(spec)
            unique.append(spec)
    return unique


def _resolve_plugin(spec: str) -> Any:
    """Import one ``MOD[:ATTR]`` spec and answer its install callable.

    ``ATTR`` defaults to ``install`` — the :mod:`shslisp.embed` extension
    shape. Every failure names *spec*, because "which plugin broke" is the
    only thing the user needs to know at that point.
    """
    module_name, sep, attr = spec.partition(":")
    module_name = module_name.strip()
    attr = attr.strip() if sep else "install"
    if not module_name:
        raise LispError(
            f"plugin {spec!r}: expected MOD[:ATTR], got an empty module name"
        )
    if not attr:
        raise LispError(
            f"plugin {spec!r}: expected MOD[:ATTR], got an empty attribute"
        )
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001 — every import failure is one answer
        raise LispError(
            f"plugin {spec!r}: cannot import module {module_name!r}: {exc}"
        ) from None
    target = getattr(module, attr, None)
    # `install_extension` accepts a callable or an object with `.install(env)`;
    # resolve the same shape here so the error can name the spec.
    runner = getattr(target, "install", target)
    if not callable(runner):
        raise LispError(
            f"plugin {spec!r}: module {module_name!r} has no callable {attr!r} "
            f"(a plugin is a callable, an object with install(env), or a module "
            f"exporting install(env))"
        )
    return target


def load_plugins(specs: Iterable[str]) -> List[Any]:
    """Resolve plugin specs to install callables for ``make_env(extensions=...)``.

    Resolution is eager: a bad spec fails before any Scheme is read, so a
    typo in ``SHS_PLUGINS`` can never produce a half-configured session.
    """
    return [_resolve_plugin(spec) for spec in specs]


# --------------------------------------------------------------------------- #
#  Running a file                                                              #
# --------------------------------------------------------------------------- #

def run_script(
    path: str,
    out: Optional[TextIO] = None,
    tetris: bool = False,
    profile: str = "dsl",
    script_args: Optional[List[str]] = None,
    extensions: Iterable[Any] = (),
):
    """Evaluate a file form by form; return the last value.

    Unlike the REPL, a script does not echo every intermediate value — it
    prints only what it explicitly ``display``s. The final value is returned
    so the CLI can decide whether to show it.

    Loading goes through the environment's loader, so the entry file is just
    module zero: ``(load ...)`` inside it resolves relative to the file, and
    loading it twice is a no-op. A leading shebang line is accepted.

    The program runs on a stack with room for the interpreter's full recursion
    ceiling (see :mod:`shslisp.stack`): a script is not interactive, so it is the
    one place where reserving a big stack costs nothing.

    *script_args* — when given — become the Scheme list bound to
    ``*command-line-args*`` inside the script.

    *extensions* are already-resolved host plugins (see
    :func:`load_plugins`); they are installed after the prelude, in order, by
    :func:`shslisp.runtime.make_env`.

    *tetris* defaults to ``False`` — *opt-in*: a host edition (a package
    with an ``install(env)`` vocabulary installer) is installed only on
    request, so a plain `shs run` is a general-purpose Scheme. Pass
    ``True`` for the in-repo game edition.
    """
    return run_with_deep_stack(
        _run_script, path, out, tetris, profile, script_args, extensions
    )


def _run_script(
    path: str,
    out: Optional[TextIO],
    tetris: bool,
    profile: str,
    script_args: Optional[List[str]],
    extensions: Iterable[Any] = (),
):
    env = make_env(
        out=out,
        install_tetris=tetris,
        profile=_profile_value(profile),
        search_paths=_search_paths(),
        extensions=extensions,
    )
    if script_args is not None:
        env.define(intern("*command-line-args*"), make_list(list(script_args)))
    return load_file(env, path), env


# --------------------------------------------------------------------------- #
#  Evaluating -e expressions                                                   #
# --------------------------------------------------------------------------- #

def _eval_expressions(
    expressions: List[str],
    profile: str,
    extensions: Iterable[Any] = (),
) -> int:
    """Evaluate each ``-e`` expression in one environment; print each value.

    One environment for all expressions, in order — so a definition in an
    earlier ``-e`` is visible to a later one, the way a shell's ``-c`` chain
    behaves. A value is printed unless it is ``()`` — the language's
    "nothing", not worth an echo.

    *extensions* are the resolved ``--plugin`` / ``SHS_PLUGINS`` installers
    (R-01), installed by :func:`shslisp.runtime.make_env` before the first
    expression is read.
    """
    try:
        env = make_env(
            out=sys.stdout,
            profile=_profile_value(profile),
            search_paths=_search_paths(),
            extensions=extensions,
        )
        for source in expressions:
            result = evaluate_program(read_all(source), env)
            if result is not None and to_string(result) != "()":
                sys.stdout.write(to_string(result) + "\n")
        return 0
    except BrokenPipeError:
        raise  # main's handler exits quietly; see it for the reasoning
    except (LispError, OSError) as exc:
        sys.stderr.write(f"{PROGRAM}: {exc}\n")
        return 1


# --------------------------------------------------------------------------- #
#  Argument parsing                                                            #
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description=(
            "A small Scheme-flavored Lisp, installable and embeddable. "
            "With no command, an interactive REPL."
        ),
        epilog=(
            "script arguments after `run FILE' are available to the script "
            "as the list *command-line-args*"
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"{PROGRAM} {_version()}",
    )
    parser.add_argument(
        "-e", "--eval",
        dest="expr",
        action="append",
        default=None,
        metavar="EXPR",
        help="evaluate EXPR and print each non-empty value (repeatable)",
    )
    parser.add_argument(
        "--profile",
        choices=("dsl", "r7rs", "none"),
        default="dsl",
        help="which SRFI layer to pre-import (default: dsl)",
    )
    parser.add_argument(
        "--plugin",
        dest="plugins",
        action="append",
        default=[],
        metavar="MOD[:ATTR]",
        help=(
            "load a host plugin: import MOD and call its ATTR (default: "
            "install) with the environment; repeatable"
        ),
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("repl", help="interactive prompt (the default)")

    run = sub.add_parser("run", help="evaluate a .scm file")
    run.add_argument("file", help="path to a .scm script")
    run.add_argument(
        "args",
        nargs="*",
        help="script arguments, bound to *command-line-args*",
    )
    return parser


# --------------------------------------------------------------------------- #
#  Entry point                                                                 #
# --------------------------------------------------------------------------- #

def main(argv: Optional[List[str]] = None) -> int:
    try:
        return _dispatch(argv)
    except BrokenPipeError:
        # A downstream reader (`shs run ... | head`) closed the pipe. Exit
        # quietly the way well-behaved filters do, and point stdout at the
        # void so the interpreter's final flush does not re-report the error.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return 0


#: The subcommands. Anything else that names an existing file is taken as a
#: script to run — the gosh convention ``gosh program.scm``.
_KNOWN_COMMANDS = ("repl", "run")

#: Options that consume the next token as their value. The gosh-style scan
#: must step over that value: ``shs --plugin pkg prog.scm`` names a *plugin*,
#: not a script called ``pkg`` (R-01).
_VALUE_OPTIONS = ("-e", "--eval", "--profile", "--plugin")


def _script_index(argv: List[str]) -> Optional[int]:
    """Index of the first bare token that names an existing file, if any.

    Options (with their values) are skipped; the first remaining token is the
    one that decides — a known subcommand means the user already spelled the
    command, a file means ``run`` should be made explicit, anything else is
    not a script.
    """
    skip_value = False
    for index, token in enumerate(argv):
        if skip_value:
            skip_value = False
            continue
        if token.startswith("-"):
            # ``--plugin=pkg`` / ``-e(+ 1 2)`` carry their value in the same
            # token; the bare spellings take the next one.
            skip_value = token in _VALUE_OPTIONS
            continue
        if token in _KNOWN_COMMANDS:
            return None
        return index if os.path.isfile(token) else None
    return None


def _dispatch(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # gosh-style: ``shs program.scm args...`` runs the script. The first
    # argument that is neither an option nor a known command, but does name
    # an existing file, is a script — make ``run`` explicit for it.
    script = _script_index(argv)
    if script is not None:
        argv.insert(script, "run")
    args = build_parser().parse_args(argv)

    try:
        extensions = load_plugins(_plugin_specs(args.plugins))
    except LispError as exc:
        sys.stderr.write(f"{PROGRAM}: {exc}\n")
        return 1

    if args.expr is not None:
        return _eval_expressions(args.expr, args.profile, extensions=extensions)

    command = args.command or "repl"

    if command == "repl":
        return run_repl(
            search_paths=_search_paths(),
            profile=_profile_value(args.profile),
            extensions=extensions,
        )

    if command == "run":
        try:
            result, _env = run_script(
                args.file,
                out=sys.stdout,
                profile=args.profile,
                script_args=args.args,
                extensions=extensions,
            )
        except BrokenPipeError:
            raise  # main's handler exits quietly; see it for the reasoning
        except (LispError, OSError) as exc:
            sys.stderr.write(f"{PROGRAM}: {exc}\n")
            return 1
        if result is not None and to_string(result) != "()":
            sys.stdout.write(to_string(result) + "\n")
        return 0

    build_parser().error(f"unknown command {command!r}")  # pragma: no cover
    return 2  # unreachable; argparse exits first


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


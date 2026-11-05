"""``shs`` — the command line for this Scheme.

    shs                              # the REPL (the default)
    shs -e "(+ 1 2)"                 # evaluate an expression, print the value
    shs run program.scm [args ...]   # run a script; args become
                                     # ``*command-line-args*``
    shs program.scm [args ...]       # the same, gosh-style: the file *is* the
                                     # command when it exists
    shs --profile r7rs               # strict R7RS-small: no SRFIs preloaded
    shs --version

``shs`` is deliberately gosh-shaped: no arguments is an interactive session,
``run`` executes a file, ``-e`` evaluates an expression, and a script may
begin with a shebang line (``#!/usr/bin/env shs``) and be run as an
executable directly.

Profiles (``--profile``): ``dsl`` — the default — pre-imports the mandatory
SRFI layer (SRFIs 1, 26, 88, 89, 197, 241) with the documented collision
resolutions; ``r7rs`` pre-imports only the strict R7RS-small conformance
subset; ``none`` skips the profile entirely.

This module is composition only. Everything interesting lives in the ``shslisp``
package, and a host project embeds the language directly (``shslisp.embed``)
without ever coming near this file. Additional script directories can be put
on the load path with the ``SHS_PATH`` environment variable
(``os.pathsep``-separated, like ``PATH``).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional, TextIO

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
_FALLBACK_VERSION = "0.2.1"


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
#  Running a file                                                              #
# --------------------------------------------------------------------------- #

def run_script(
    path: str,
    out: Optional[TextIO] = None,
    tetris: Optional[bool] = None,
    profile: str = "dsl",
    script_args: Optional[List[str]] = None,
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

    *tetris* defaults to ``None`` — *auto*: a host edition (a package with an
    ``install(env)`` vocabulary installer) is installed when importable, so a
    script written for a host sees the host and the same call is a plain
    Scheme elsewhere.
    """
    return run_with_deep_stack(_run_script, path, out, tetris, profile, script_args)


def _run_script(
    path: str,
    out: Optional[TextIO],
    tetris: Optional[bool],
    profile: str,
    script_args: Optional[List[str]],
):
    env = make_env(
        out=out,
        install_tetris=tetris,
        profile=_profile_value(profile),
        search_paths=_search_paths(),
    )
    if script_args is not None:
        env.define(intern("*command-line-args*"), make_list(list(script_args)))
    return load_file(env, path), env


# --------------------------------------------------------------------------- #
#  Evaluating -e expressions                                                   #
# --------------------------------------------------------------------------- #

def _eval_expressions(expressions: List[str], profile: str) -> int:
    """Evaluate each ``-e`` expression in one environment; print each value.

    One environment for all expressions, in order — so a definition in an
    earlier ``-e`` is visible to a later one, the way a shell's ``-c`` chain
    behaves. A value is printed unless it is ``()`` — the language's
    "nothing", not worth an echo.
    """
    try:
        env = make_env(
            out=sys.stdout,
            profile=_profile_value(profile),
            search_paths=_search_paths(),
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


def _dispatch(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # gosh-style: ``shs program.scm args...`` runs the script. The first
    # argument that is neither an option nor a known command, but does name
    # an existing file, is a script — make ``run`` explicit for it.
    for index, token in enumerate(argv):
        if token.startswith("-"):
            continue
        if token not in _KNOWN_COMMANDS and os.path.isfile(token):
            argv.insert(index, "run")
        break
    args = build_parser().parse_args(argv)

    if args.expr is not None:
        return _eval_expressions(args.expr, args.profile)

    command = args.command or "repl"

    if command == "repl":
        return run_repl(
            search_paths=_search_paths(),
            profile=_profile_value(args.profile),
        )

    if command == "run":
        try:
            result, _env = run_script(
                args.file,
                out=sys.stdout,
                profile=args.profile,
                script_args=args.args,
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


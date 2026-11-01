"""The embedding seam: :mod:`lisp.embed` and ``make_env``'s extension points.

This file is the *contract* a foreign host project relies on, so it is tested
from the host's side: build a plain Scheme, hand it a declared table of Python
functions, and call them from Lisp. None of it mentions the game.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from lisp import install_extension, install_primitives, make_env, run
from lisp.errors import LispError
from lisp.runtime import make_env as runtime_make_env
from lisp.types import intern

ROOT = Path(__file__).resolve().parent.parent


def _names(env) -> set:
    return {str(name) for name in env.vars}


# --------------------------------------------------------------------------- #
#  install_primitives — the declared crossing                                   #
# --------------------------------------------------------------------------- #

def test_a_host_function_becomes_a_callable_primitive() -> None:
    env = make_env(install_tetris=False)
    install_primitives(env, [("double", lambda n: n * 2)], source="test")
    assert run("(double 21)", env) == 42


def test_several_primitives_can_call_each_other() -> None:
    env = make_env(install_tetris=False)
    install_primitives(
        env,
        [
            ("unit", lambda: 1),
            ("plus", lambda a, b: a + b),
        ],
        source="test",
    )
    assert run("(plus (unit) 41)", env) == 42


def test_a_mapping_is_accepted_like_a_list() -> None:
    env = make_env(install_tetris=False)
    install_primitives(env, {"triple": lambda n: n * 3}, source="test")
    assert run("(triple 14)", env) == 42


def test_a_duplicate_name_is_refused_and_names_its_source() -> None:
    env = make_env(install_tetris=False)
    with pytest.raises(LispError, match="myproject.py: duplicate primitive 'twice'"):
        install_primitives(
            env,
            [("twice", lambda: 1), ("twice", lambda: 2)],
            source="myproject.py",
        )


def test_a_non_callable_is_refused_at_install_time() -> None:
    env = make_env(install_tetris=False)
    with pytest.raises(LispError, match="not callable"):
        install_primitives(env, [("oops", 42)], source="test")


def test_a_malformed_entry_is_refused_at_install_time() -> None:
    env = make_env(install_tetris=False)
    with pytest.raises(LispError, match="must be a \\(name, callable\\) pair"):
        install_primitives(env, [("only-a-name",)], source="test")  # type: ignore[list-item]


def test_a_non_string_name_is_refused() -> None:
    env = make_env(install_tetris=False)
    with pytest.raises(LispError, match="is not a string"):
        install_primitives(env, [(42, lambda: 1)], source="test")  # type: ignore[list-item]


def test_installing_returns_the_same_environment() -> None:
    env = make_env(install_tetris=False)
    assert install_primitives(env, [("noop", lambda: None)]) is env


# --------------------------------------------------------------------------- #
#  Extensions — a host ships its vocabulary as a value                          #
# --------------------------------------------------------------------------- #

def test_a_plain_callable_is_an_extension() -> None:
    def extension(env):
        install_primitives(env, [("forty-two", lambda: 42)])

    env = make_env(install_tetris=False, extensions=[extension])
    assert run("(forty-two)", env) == 42


def test_an_object_with_install_is_an_extension() -> None:
    class Host:
        def install(self, env):
            return install_primitives(env, [("host-name", lambda: "hi")])

    env = make_env(install_tetris=False, extensions=[Host()])
    assert run("(host-name)", env) == "hi"


def test_install_extension_tolerates_a_missing_return() -> None:
    env = make_env(install_tetris=False)
    assert install_extension(env, lambda e: None) is env


def test_install_extension_refuses_a_non_extension() -> None:
    env = make_env(install_tetris=False)
    with pytest.raises(LispError, match="neither callable"):
        install_extension(env, object())


def test_extensions_run_after_the_prelude_so_they_can_use_it() -> None:
    def extension(env):
        # `map` comes from the prelude, written in Lisp; if the order were
        # wrong this would be an unbound symbol at definition time only if the
        # extension *called* it, so we call it here on purpose.
        assert run("(map (lambda (x) x) (list 1 2 3))", env) == [1, 2, 3]

    make_env(install_tetris=False, extensions=[extension])


# --------------------------------------------------------------------------- #
#  make_env(install_tetris=...) — auto, on, off                                 #
# --------------------------------------------------------------------------- #

#: A name that only the game declares; its presence is the game being installed.
GAME_NAME = "board-of"


def test_off_is_a_plain_scheme() -> None:
    env = make_env(install_tetris=False)
    assert GAME_NAME not in _names(env)
    assert run("(+ 1 2)", env) == 3


def test_on_requires_a_host_that_is_there() -> None:
    # Forcing the edition is a *contract*: either the host is installed, or
    # the caller gets a clear error naming the missing package and the way out
    # — never a raw ImportError from the middle of the import machinery.
    with pytest.raises(LispError, match="tetris"):
        make_env(install_tetris=True)


def test_auto_is_a_plain_scheme_without_the_game(monkeypatch) -> None:
    # The foreign-project case: `tetris` cannot be imported, so `make_env()`
    # must quietly be a general Scheme rather than failing.
    monkeypatch.setattr("lisp.runtime._game_available", lambda: False)
    env = make_env()
    assert GAME_NAME not in _names(env)
    assert run("(* 6 7)", env) == 42


# --------------------------------------------------------------------------- #
#  The packaging claim: `import lisp` does not drag the game in                 #
# --------------------------------------------------------------------------- #

def test_importing_the_language_does_not_import_the_game() -> None:
    code = (
        "import sys, lisp; "
        "assert 'tetris' not in sys.modules, 'lisp imported the game'; "
        "print('clean')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "clean"


def test_the_packaging_publishes_the_language_and_its_lisp_data() -> None:
    # The project installs on its own, and the standard library ships as data.
    # The claim is pinned here because the build backend is not always present.
    import tomllib

    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["tool"]["setuptools"]["packages"] == ["lisp"]
    assert data["tool"]["setuptools"]["package-data"]["lisp"] == ["*.scm"]
    assert (ROOT / "lisp" / "prelude.scm").is_file()
    assert (ROOT / "lisp" / "rope.scm").is_file()
    scripts = data["project"]["scripts"]
    assert any(target == "lisp.__main__:main" for target in scripts.values())

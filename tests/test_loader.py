"""The module system: ``(load ...)`` — resolution, load-once, and cycles.

These tests use real files in ``tmp_path`` rather than mocks, because the whole
point of the feature is what happens on disk: a relative spec must resolve
against the *calling* file, and a module must be evaluated exactly once.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lisp.env import Environment
from lisp.errors import LispArityError, LispError, LispTypeError
from lisp.evaluator import evaluate
from lisp.loader import Loader
from lisp.printer import to_string
from lisp.reader import read_all
from lisp.runtime import load_file, make_env
from lisp.types import intern


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def run_source(env: Environment, source: str):
    result = None
    for form in read_all(source):
        result = evaluate(form, env)
    return result


def value(env: Environment, source: str) -> str:
    return to_string(run_source(env, source), write=False)


# --------------------------------------------------------------------------- #
#  Resolution                                                                  #
# --------------------------------------------------------------------------- #

def test_a_sibling_is_resolved_relative_to_the_calling_file(tmp_path: Path) -> None:
    write(tmp_path / "modules" / "a.scm", '(define (double x) (* 2 x))\n(load "sibling")\n')
    write(tmp_path / "modules" / "sibling.scm", "(define *sib* 41)\n")
    env = make_env(install_tetris=False)

    load_file(env, tmp_path / "modules" / "a.scm")

    assert value(env, "(double 21)") == "42"
    assert value(env, "*sib*") == "41"


def test_the_suffix_is_optional(tmp_path: Path) -> None:
    write(tmp_path / "helper.scm", "(define *answer* 42)\n")
    env = make_env(install_tetris=False, search_paths=[tmp_path])

    value(env, '(load "helper")')

    assert value(env, "*answer*") == "42"


def test_a_search_path_entry_is_used_when_the_caller_is_elsewhere(
    tmp_path: Path,
) -> None:
    # The module is *not* next to the entry file, so only the search path can
    # find it.
    library = tmp_path / "library"
    write(library / "thing.scm", "(define *found* #t)\n")
    entry = write(tmp_path / "entry.scm", '(load "thing")\n')
    env = make_env(install_tetris=False, search_paths=[library])

    load_file(env, entry)

    assert value(env, "*found*") == "#t"


def test_a_nested_chain_resolves_each_step_from_its_own_file(
    tmp_path: Path,
) -> None:
    # entry -> a/a.scm -> b/b.scm -> c.scm, where each step is relative.
    write(tmp_path / "a" / "a.scm", '(load "../b/b")\n')
    write(tmp_path / "a" / "c.scm", "(define *deep* 7)\n")
    write(tmp_path / "b" / "b.scm", '(load "../a/c")\n')
    env = make_env(install_tetris=False)

    load_file(env, tmp_path / "a" / "a.scm")

    assert value(env, "*deep*") == "7"


def test_load_accepts_several_modules_in_order(tmp_path: Path) -> None:
    write(tmp_path / "one.scm", '(set! *order* (string-append *order* "1"))\n')
    write(tmp_path / "two.scm", '(set! *order* (string-append *order* "2"))\n')
    env = make_env(install_tetris=False, search_paths=[tmp_path])

    run_source(env, '(define *order* "")')
    value(env, '(load "one" "two")')

    assert value(env, "*order*") == "12"


# --------------------------------------------------------------------------- #
#  Load once                                                                   #
# --------------------------------------------------------------------------- #

def test_a_module_is_evaluated_once_however_often_it_is_loaded(
    tmp_path: Path,
) -> None:
    write(tmp_path / "inc.scm", "(set! *loads* (+ *loads* 1))\n")
    env = make_env(install_tetris=False, search_paths=[tmp_path])

    run_source(env, "(define *loads* 0)")
    value(env, '(load "inc")')
    value(env, '(load "inc")')
    value(env, '(load "./inc.scm")')  # the same file, another spelling

    assert value(env, "*loads*") == "1"


def test_a_repeat_load_returns_the_first_result(tmp_path: Path) -> None:
    write(tmp_path / "answer.scm", "(+ 40 2)\n")
    env = make_env(install_tetris=False, search_paths=[tmp_path])

    assert value(env, '(load "answer")') == "42"
    assert value(env, '(load "answer")') == "42"


def test_loaded_predicate_and_module_list(tmp_path: Path) -> None:
    write(tmp_path / "thing.scm", "(define *thing* #t)\n")
    env = make_env(install_tetris=False, search_paths=[tmp_path])

    assert value(env, '(loaded? "thing")') == "#f"
    value(env, '(load "thing")')
    assert value(env, '(loaded? "thing")') == "#t"
    assert value(env, '(loaded? "nope")') == "#f"
    modules = value(env, "(loaded-modules)")
    assert "thing.scm" in modules


def test_search_path_is_readable_from_lisp(tmp_path: Path) -> None:
    env = make_env(install_tetris=False, search_paths=[tmp_path])
    assert str(tmp_path) in value(env, "(search-path)")


# --------------------------------------------------------------------------- #
#  Errors                                                                      #
# --------------------------------------------------------------------------- #

def test_a_cycle_is_reported_with_the_chain(tmp_path: Path) -> None:
    write(tmp_path / "a.scm", '(load "b")\n')
    write(tmp_path / "b.scm", '(load "a")\n')
    env = make_env(install_tetris=False, search_paths=[tmp_path])

    with pytest.raises(LispError) as caught:
        value(env, '(load "a")')

    message = str(caught.value)
    assert "circular" in message
    assert "a.scm -> b.scm -> a.scm" in message


def test_a_missing_module_names_where_it_looked(tmp_path: Path) -> None:
    env = make_env(install_tetris=False, search_paths=[tmp_path])

    with pytest.raises(LispError) as caught:
        value(env, '(load "nope")')

    message = str(caught.value)
    assert "no such module" in message
    assert str(tmp_path) in message


def test_load_needs_a_path_string() -> None:
    env = make_env(install_tetris=False)
    with pytest.raises(LispTypeError):
        value(env, "(load 42)")


def test_load_with_no_arguments_is_an_arity_error() -> None:
    env = make_env(install_tetris=False)
    with pytest.raises(LispArityError):
        value(env, "(load)")


def test_a_loader_belongs_to_one_environment() -> None:
    loader = Loader()
    env = Environment()
    assert loader.attach(env) is loader
    assert loader.attach(env) is loader
    with pytest.raises(LispError):
        loader.attach(Environment())


# --------------------------------------------------------------------------- #
#  The host and the program share one cache                                    #
# --------------------------------------------------------------------------- #

def test_host_loading_and_lisp_loading_are_the_same_module(tmp_path: Path) -> None:
    module = write(tmp_path / "once.scm", "(set! *once* (+ *once* 1))\n")
    env = make_env(install_tetris=False, search_paths=[tmp_path])
    env.define(intern("*once*"), 0)

    load_file(env, module)  # the host
    value(env, '(load "once")')  # the program

    assert env.lookup(intern("*once*")) == 1

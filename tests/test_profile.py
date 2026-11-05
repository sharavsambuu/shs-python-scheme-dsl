"""The DSL profile: the SRFI layer is the language people actually use.

``make_env()`` (the default profile) pre-imports every mandatory SRFI with the
collision resolutions applied; ``profile="r7rs"`` is the strict subset the
conformance harness runs; ``profile=None`` skips the profile for tests that
need the bare core + prelude. The profile is additive — it binds no name the
core already binds.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from shslisp.errors import LispNameError
from shslisp.evaluator import evaluate_program
from shslisp.reader import read_all
from shslisp.runtime import make_env
from shslisp.types import intern

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
EXERCISES = ROOT / "docs" / "lisp_tutorial" / "exercises"


def run(env, source: str):
    return evaluate_program(read_all(source), env)


@pytest.fixture
def dsl():
    """The default DSL profile, no game."""
    return make_env(install_tetris=False, profile="dsl")


def test_the_default_env_has_the_srfi_layer_without_a_preamble(dsl) -> None:
    # Every mandatory name, no (import ...) preamble: cut, define*, chain,
    # match, and the SRFI 1 names.
    assert run(dsl, "((cut + 1 <>) 2)") == 3
    assert run(dsl, "(chain 1)") == 1
    assert run(dsl, "(match 5 [,x x])") == 5
    assert run(dsl, "((lambda* (a (b 2)) (list a b)) 1)") == [1, 2]
    assert run(dsl, "(filter odd? '(1 2 3))") == [1, 3]
    assert run(dsl, "(keyword->string 'host:)") == "host"
    assert run(dsl, "(fold-right cons '() '(1 2 3))") == [1, 2, 3]


def test_the_default_env_resolves_the_map_and_for_each_split(dsl) -> None:
    # The base map/for-each keep the R7RS (scheme base) meaning; the SRFI 1
    # ones are renamed. The shared names are the same binding objects.
    assert run(dsl, "(srfi-1:map + '(1 2) '(10 20))") == [11, 22]
    assert run(dsl, "(procedure? srfi-1:map)") is True
    # member/assoc are the same objects, extended with the optional comparator
    assert run(dsl, "(member 2 '(1 2 3))") == [2, 3]
    assert run(dsl, "(member 2 '(1 2 3) =)") == [2, 3]
    # (eq? car srfi-1:car) — the shared set is one binding, not two aliases:
    # the profile's import resolved against *env* itself.
    from shslisp.library import get_library

    lib_env = get_library(dsl, ("srfi", "1")).instantiate()
    assert lib_env.find(intern("member")) is dsl.find(intern("member"))
    assert lib_env.find(intern("filter")) is dsl.find(intern("filter"))


def test_the_strict_env_has_no_srfi_layer() -> None:
    env = make_env(install_tetris=False, profile="r7rs")
    with pytest.raises(LispNameError):
        run(env, "(cut + 1 <>)")
    with pytest.raises(LispNameError):
        run(env, "(chain 1)")
    with pytest.raises(LispNameError):
        run(env, "(define* (f a) a)")
    with pytest.raises(LispNameError):
        run(env, "(srfi-1:map + '() '())")
    # match is the global SRFI 241 special form: it is there in any profile
    assert run(env, "(match 5 [,x x])") == 5


def test_the_profile_is_idempotent(dsl) -> None:
    # importing the same library twice — or applying the profile twice — is
    # not a duplicate-binding error
    run(dsl, "(import (srfi 1))")
    run(dsl, "(import (srfi 1))")
    env = make_env(install_tetris=False, profile="dsl")
    from shslisp.profile import install as install_profile

    install_profile(env, "dsl")
    install_profile(env, "dsl")
    assert run(env, "(filter odd? '(1 2))") == [1]


def test_install_tetris_false_never_installs_game_bindings(dsl) -> None:
    with pytest.raises(LispNameError):
        run(dsl, "(new-game)")
    with pytest.raises(LispNameError):
        run(dsl, "(move-left)")


def test_the_profile_features_are_introspectable(dsl) -> None:
    names = run(dsl, "(features)")
    spelled = [str(n) for n in names]
    assert spelled[-10:] == [
        "dsl-profile", "srfi-1", "srfi-26", "srfi-88", "srfi-89", "srfi-197", "srfi-241",
        "srfi-19", "srfi-158", "srfi-160",
    ]
    assert "srfi-204" not in spelled


def test_cond_expand_answers_the_same_question_as_features(dsl) -> None:
    """`cond-expand` sees the profile's identifiers, like `(features)` does."""
    assert run(dsl, "(cond-expand (dsl-profile 'dsl) (else 'strict))") == intern("dsl")
    assert run(dsl, "(cond-expand (srfi-1 'yes) (else 'no))") == intern("yes")
    assert run(dsl, "(cond-expand ((library (srfi 1)) 'yes) (else 'no))") == intern("yes")


def test_cond_expand_sees_no_profile_features_under_the_strict_profile() -> None:
    env = make_env(install_tetris=False, profile="r7rs")
    assert run(env, "(cond-expand (dsl-profile 'dsl) (else 'strict))") == intern("strict")


# --------------------------------------------------------------------------- #
#  The profile lint: every shipped .scm file loads under the default profile #
# --------------------------------------------------------------------------- #

def _shipped_lisp() -> list:
    """Every shipped .scm file, as (path, game) pairs.

    The examples and the exercises are language-only: each must load in a
    plain default-profile environment with no host installed.
    """
    pairs: list = []
    for path in sorted((ROOT / "examples").glob("*.scm")):
        pairs.append((path, False))
    for path in sorted(EXERCISES.glob("*.scm")):
        pairs.append((path, False))
    return pairs


def test_every_shipped_lisp_file_loads_under_the_default_profile() -> None:
    from shslisp.profile import lint

    pairs = _shipped_lisp()
    assert len(pairs) >= 6  # the examples, the exercises
    failures = lint(pairs)
    assert not failures, "\n".join(failures)


def test_the_lint_rejects_a_legacy_file(tmp_path: Path) -> None:
    # A file that does not load under the default profile turns the lint red:
    # an undefined name fails in every environment.
    from shslisp.profile import lint

    legacy = tmp_path / "legacy.scm"
    legacy.write_text("(this-word-does-not-exist 1)\n", encoding="utf-8")
    failures = lint([(legacy, False)])
    assert len(failures) == 1
    assert "legacy.scm" in failures[0]


def test_the_lint_rejects_a_missing_import(tmp_path: Path) -> None:
    from shslisp.profile import lint

    legacy = tmp_path / "typo.scm"
    legacy.write_text("(srfi-1:zip + '(1) '(2))\n", encoding="utf-8")
    failures = lint([(legacy, False)])
    assert len(failures) == 1
    assert "typo.scm" in failures[0]


def test_the_strict_env_leaves_the_trading_srfis_import_only() -> None:
    # docs/srfi.md: the strict r7rs profile leaves (srfi 19) and (srfi 160)
    # import-only, like every other SRFI — their primitives install into the
    # libraries' own scopes on first import, never into the core floor.
    env = make_env(install_tetris=False, profile="r7rs")
    names = (
        "current-time", "time-resolution", "make-date", "date->string",
        "string->date", "make-f64vector", "f64vector", "f64vector-map", "time-utc",
    )
    assert all(env.find(intern(name)) is None for name in names)
    run(env, "(import (srfi 19) (srfi 160 base) (srfi 160 f64))")
    assert all(env.find(intern(name)) is not None for name in names)
    assert run(env, '(date->string (make-date 0 0 0 12 1 1 2026 0) "~4")') == (
        "2026-01-01T12:00:00Z"
    )


def test_the_two_160_libraries_share_one_primitive_set() -> None:
    # Both export lists name make-f64vector: one private scope, one object —
    # importing both in a single form is a re-export, not a collision.
    env = make_env(install_tetris=False)
    run(env, "(import (srfi 160 base) (srfi 160 f64))")
    from shslisp.library import get_library

    base = get_library(env, ("srfi", "160", "base")).instantiate()
    f64 = get_library(env, ("srfi", "160", "f64")).instantiate()
    assert base.find(intern("make-f64vector")) is f64.find(intern("make-f64vector"))


def test_the_bare_core_also_leaves_the_trading_srfis_import_only() -> None:
    # profile=None is the bare core + prelude: no profile pre-imports at all,
    # so the trading libraries must behave exactly as they do under r7rs.
    env = make_env(install_tetris=False, profile=None)
    names = (
        "current-time", "make-date", "date->string", "string->date",
        "make-f64vector", "f64vector", "f64vector-map", "time-utc",
    )
    assert all(env.find(intern(name)) is None for name in names)
    run(env, "(import (srfi 19) (srfi 160 f64))")
    assert all(env.find(intern(name)) is not None for name in names)
    assert run(env, "(f64vector->list (f64vector 1.0 2.0))") == [1.0, 2.0]


def test_importing_one_trading_library_does_not_bind_the_other() -> None:
    # (srfi 19) and (srfi 160) own separate private scopes: importing one
    # must not smuggle the other's names into the strict environment.
    env = make_env(install_tetris=False, profile="r7rs")
    run(env, "(import (srfi 19))")
    assert env.find(intern("date->string")) is not None
    assert env.find(intern("f64vector")) is None
    run(env, "(import (srfi 160 base))")
    assert env.find(intern("f64vector")) is not None
    assert env.find(intern("f64vector-map")) is None
    run(env, "(import (srfi 160 f64))")
    assert env.find(intern("f64vector-map")) is not None


def test_every_binding_shared_by_the_two_160_libraries_is_the_same_object() -> None:
    env = make_env(install_tetris=False)
    run(env, "(import (srfi 160 base) (srfi 160 f64))")
    from shslisp.library import get_library

    base = get_library(env, ("srfi", "160", "base")).instantiate()
    f64 = get_library(env, ("srfi", "160", "f64")).instantiate()
    for name in (
        "make-f64vector", "f64vector", "f64vector?", "f64?",
        "f64vector-ref", "f64vector-length", "f64vector-set!",
        "f64vector->list", "list->f64vector",
    ):
        assert base.lookup(intern(name)) is f64.lookup(intern(name)), name


def test_the_default_profile_preimports_the_library_objects_themselves() -> None:
    # The DSL profile's pre-import is the same import: the objects the
    # libraries expose and the objects in the environment have one identity.
    dsl = make_env(install_tetris=False, profile="dsl")
    from shslisp.library import get_library

    lib19 = get_library(dsl, ("srfi", "19")).instantiate()
    lib160 = get_library(dsl, ("srfi", "160", "f64")).instantiate()
    for name in ("current-time", "date->string", "string->date"):
        assert dsl.lookup(intern(name)) is lib19.lookup(intern(name)), name
    for name in ("make-f64vector", "f64vector-map", "f64?"):
        assert dsl.lookup(intern(name)) is lib160.lookup(intern(name)), name

"""The R7RS library system: ``define-library``, ``import``, and import sets.

These are the A13 tests: the R7RS library examples, the four import-set
modifiers, collision handling, and the guarantee that the existing ``(load
...)`` code keeps working beside it. A library that is declared but not
implemented (the SRFI stubs before S1-S6) must fail loudly, not bind nothing.
"""
from __future__ import annotations

import pytest

from shslisp.errors import LispError, LispNameError
from shslisp.evaluator import evaluate_program
from shslisp.reader import read_all
from shslisp.runtime import make_env


def run(env, source: str):
    return evaluate_program(read_all(source), env)


# --------------------------------------------------------------------------- #
#  Import sets                                                                #
# --------------------------------------------------------------------------- #

def test_import_only(env) -> None:
    run(env, "(import (only (scheme base) car cdr cons))")
    assert run(env, "(cons 1 2)") is not None
    run(env, "(import (scheme base))")  # a second import is not a collision


def test_import_except(env) -> None:
    assert run(env, "(eval '(car '(1 2)) (environment '(except (scheme base) map)))") == 1
    with pytest.raises(LispNameError):
        run(env, "(eval '(map + '(1 2)) (environment '(except (scheme base) map)))")


def test_import_prefix(env) -> None:
    run(env, "(import (prefix (only (scheme base) car cdr) base:))")
    assert run(env, "(base:car '(1 2))") == 1
    assert run(env, "(base:cdr '(1 2))") == [2]


def test_import_rename(env) -> None:
    fresh = "(environment '(rename (only (scheme base) car) (car first)))"
    assert run(env, f"(eval '(first '(1 2)) {fresh})") == 1
    with pytest.raises(LispNameError):
        run(env, f"(eval 'car {fresh})")


def test_import_collision_names_the_name(env) -> None:
    run(env, """
    (define-library (one) (export clash) (import (scheme base))
      (begin (define (clash) 1)))
    (define-library (two) (export clash) (import (scheme base))
      (begin (define (clash) 2)))
    """)
    with pytest.raises(LispError, match="collision on clash"):
        run(env, "(import (only (one) clash) (only (two) clash))")


def test_import_shared_names_are_not_collisions(env) -> None:
    # Two sets that bind a name to the *same* binding are fine — that is the
    # whole point of re-exporting base names through a library.
    run(env, "(import (scheme base) (only (scheme cxr) caaar cadddr))")
    assert run(env, "(caaar '(((9)) x))") == 9


def test_import_of_an_unknown_library_fails_clearly(env) -> None:
    with pytest.raises(LispError, match="no such library"):
        run(env, "(import (no such library))")


def test_import_of_a_declared_but_missing_srfi_says_so(env) -> None:
    # All the planned SRFIs landed with S1-S6 and import; the only stub left
    # is the withdrawn SRFI 204, which fails loudly naming SRFI 241.
    run(env, "(import (srfi 1))")
    run(env, "(import (srfi 26))")
    run(env, "(import (srfi 88))")
    run(env, "(import (srfi 89))")
    run(env, "(import (srfi 197))")
    run(env, "(import (srfi 241))")
    with pytest.raises(LispError, match="SRFI 241"):
        run(env, "(import (srfi 204))")


# --------------------------------------------------------------------------- #
#  define-library                                                             #
# --------------------------------------------------------------------------- #

def test_define_library_exports_only_what_it_names(env) -> None:
    run(env, """
    (define-library (demo)
      (export seven hidden-ref)
      (import (scheme base))
      (begin (define seven 7) (define hidden 8) (define (hidden-ref) hidden)))
    """)
    run(env, "(import (demo))")
    assert run(env, "seven") == 7
    assert run(env, "(hidden-ref)") == 8
    with pytest.raises(LispNameError):
        run(env, "hidden")  # defined but not exported


def test_define_library_export_renaming(env) -> None:
    run(env, """
    (define-library (demo)
      (export (rename hidden public-ref))
      (import (scheme base))
      (begin (define hidden 9)))
    """)
    run(env, "(import (demo))")
    assert run(env, "public-ref") == 9
    with pytest.raises(LispNameError):
        run(env, "hidden")


def test_define_library_include(env, tmp_path) -> None:
    (tmp_path / "helper.scm").write_text("(define from-include 42)\n", encoding="utf-8")
    env.loader.add_search_paths([tmp_path])
    run(env, f"""
    (define-library (demo)
      (export from-include)
      (import (scheme base))
      (include "{tmp_path / 'helper.scm'}"))
    """)
    run(env, "(import (demo))")
    assert run(env, "from-include") == 42


def test_define_library_include_library_declarations(env, tmp_path) -> None:
    (tmp_path / "decls.scm").write_text(
        "(export from-decls)\n(begin (define from-decls 5))\n", encoding="utf-8"
    )
    env.loader.add_search_paths([tmp_path])
    run(env, f"""
    (define-library (demo)
      (import (scheme base))
      (include-library-declarations "{tmp_path / 'decls.scm'}"))
    """)
    run(env, "(import (demo))")
    assert run(env, "from-decls") == 5


def test_define_library_cond_expand_body(env) -> None:
    run(env, """
    (define-library (demo)
      (export picked)
      (import (scheme base))
      (cond-expand (lisppy (begin (define picked 'lisp)))
                   (else (begin (define picked 'other)))))
    """)
    run(env, "(import (demo))")
    assert run(env, "picked") == "lisp"


def test_define_library_cycles_are_errors(env) -> None:
    run(env, """
    (define-library (a) (import (scheme base)) (export a-ref))
    (define-library (b) (import (scheme base) (only (a) a-ref)) (export b-ref))
    """)
    # b importing a is fine; a self-import is a cycle.
    assert run(env, "(cond-expand ((library (b)) 'b-declared) (else 'no))") == "b-declared"
    run(env, "(define-library (c) (import (only (c) nope)) (export x))")
    with pytest.raises(LispError, match="circular"):
        run(env, "(import (c))")


def test_define_library_unknown_declaration_is_an_error(env) -> None:
    run(env, "(define-library (demo-bad) (nonsense 1))")
    with pytest.raises(LispError, match="unknown declaration"):
        run(env, "(import (demo-bad))")


# --------------------------------------------------------------------------- #
#  cond-expand and environment, backed by the registry                        #
# --------------------------------------------------------------------------- #

def test_cond_expand_library_sees_a_user_defined_library(env) -> None:
    run(env, "(define-library (demo) (export x))")
    assert run(env, "(cond-expand ((library (demo)) 1) (else 2))") == 1
    assert run(env, "(cond-expand ((library (no such)) 1) (else 2))") == 2


def test_environment_is_backed_by_real_libraries(env) -> None:
    assert run(env, "(eval '(+ 1 2) (environment '(scheme base)))") == 3
    run(env, "(eval '(define env-local 5) (environment '(scheme base)))")
    with pytest.raises(LispNameError):
        run(env, "env-local")  # definitions through it stay local


def test_environment_accepts_import_sets(env) -> None:
    assert run(env, "(eval '(car '(1 2)) (environment '(only (scheme base) car)))") == 1


def test_importing_scheme_base_does_not_install_tetris() -> None:
    env = make_env(install_tetris=False)
    run(env, "(import (scheme base) (scheme write))")
    with pytest.raises(LispNameError):
        run(env, "new-game")


def test_a_defined_library_is_invisible_to_a_fresh_env() -> None:
    env = make_env(install_tetris=False)
    run(env, "(define-library (demo) (export x))")
    fresh = make_env(install_tetris=False)
    with pytest.raises(LispError, match="no such library"):
        run(fresh, "(import (demo))")


# --------------------------------------------------------------------------- #
#  load keeps working beside import                                           #
# --------------------------------------------------------------------------- #

def test_load_still_works_beside_the_library_system(env, tmp_path) -> None:
    (tmp_path / "plain.scm").write_text("(define plain 3)\n", encoding="utf-8")
    env.loader.add_search_paths([tmp_path])
    run(env, '(load "plain")')
    assert run(env, "plain") == 3


def test_sld_files_load_like_lisp_files(env, tmp_path) -> None:
    (tmp_path / "mod.sld").write_text("(define sld-value 11)\n", encoding="utf-8")
    env.loader.add_search_paths([tmp_path])
    run(env, '(load "mod.sld")')
    assert run(env, "sld-value") == 11

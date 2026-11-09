"""H7: syntax-rules in a library cannot reach library-private helpers.

Documents and pins the option-(a) decision on docs/HARDENING_TASKS.md H7:
keep the limitation (no syntax-case / custom ellipsis this round) and teach
the workaround — export helpers and build the form with defmacro, or keep
macros at top level. A syntax-rules macro exported from a define-library
expands in the importing program, but its hygiene aliases live in the
library's own scope, which that program cannot see, so a template naming a
library-private helper (or even a library import such as +) fails with
LispNameError naming the identifier the template wrote, not its alias.
"""
from __future__ import annotations

import pytest

from shslisp.errors import LispError
from shslisp.runtime import make_env, run


def test_top_level_syntax_rules_can_name_its_helper() -> None:
    # At top level the same shape works — the alias resolves in the root.
    env = make_env()
    assert run(
        "(define (private-helper x) (* x 2)) "
        "(define-syntax use-helper (syntax-rules () ((_ a) (private-helper a)))) "
        "(use-helper 21)",
        env,
    ) == 42


def test_library_syntax_rules_cannot_reach_private_helper() -> None:
    # The deliberate limitation: exported syntax-rules fails loudly.
    env = make_env()
    with pytest.raises(LispError, match="private-helper"):
        run(
            """
            (define-library (h-helpers)
              (export use-helper)
              (import (scheme base))
              (begin (define (private-helper x) (* x 2))
                     (define-syntax use-helper (syntax-rules () ((_ a) (private-helper a))))))
            (import (h-helpers))
            (use-helper 21)
            """,
            env,
        )


def test_library_syntax_rules_cannot_reach_library_import() -> None:
    # Even (import (scheme base)) bindings are invisible to the exported
    # syntax-rules template when it aliases them (doc: "export them, or
    # build with defmacro").
    env = make_env()
    with pytest.raises(LispError):
        run(
            """
            (define-library (h-imported)
              (export use-helper)
              (import (scheme base))
              (begin (define-syntax use-helper (syntax-rules () ((_ a) (+ a a))))))
            (import (h-imported))
            (use-helper 21)
            """,
            env,
        )


def test_library_defmacro_workaround() -> None:
    # Workaround (a): export helpers + defmacro reaches them.
    env = make_env()
    assert run(
        """
        (define-library (h-defmacro)
          (export use-helper private-helper)
          (import (scheme base))
          (begin (define (private-helper x) (* x 2))
                 (defmacro (use-helper a) (list 'private-helper a))))
        (import (h-defmacro))
        (use-helper 21)
        """,
        env,
    ) == 42

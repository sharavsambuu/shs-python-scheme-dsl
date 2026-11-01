"""The two environments the language ships in: the DSL profile (the default)
and the strict R7RS profile the conformance harness runs.

A profile is a list of import sets, applied to an environment by the library
system (:func:`lisp.library.apply_imports`) — the A13 registry does the
binding, and the collision rule inside one call is what keeps the profile
honest. The DSL profile pre-imports every mandatory SRFI with the collision
resolutions spelled out: the SRFI 1 ``map``/``for-each`` are renamed (they
differ from ``(scheme base)`` on unequal lengths), and ``match`` needs no
resolution because it is the global SRFI 241 form while the project matcher is
already named ``variant-match``.

The profile is *additive*: it binds no name that ``(scheme base)`` already
binds, so ``make_env(profile="dsl")`` changes no existing meaning.
"""

#: The DSL profile: every mandatory import, as import-set specs.
DSL_PROFILE = [
    "(scheme base)",
    "(scheme write)",
    "(rename (srfi 1) (map srfi-1:map) (for-each srfi-1:for-each))",
    "(srfi 26)",
    "(srfi 88)",
    "(srfi 89)",
    "(srfi 197)",
    "(srfi 241)",
]

#: The strict R7RS profile: the conformance target. The core and the prelude
#: are the whole language; the SRFIs exist as libraries but are not
#: pre-imported.
R7RS_PROFILE: list = []

#: The feature identifiers each profile adds to ``(features)``.
PROFILE_FEATURES = {
    "dsl": [
        "dsl-profile",
        "srfi-1",
        "srfi-26",
        "srfi-88",
        "srfi-89",
        "srfi-197",
        "srfi-241",
    ],
    "r7rs": [],
}


def install(env, profile: str = "dsl") -> None:
    """Apply *profile*'s import sets to *env*; the library system binds."""
    specs = DSL_PROFILE if profile == "dsl" else R7RS_PROFILE
    if not specs:
        return
    from .library import apply_imports
    from .reader import read_all

    apply_imports(env, [read_all(spec)[0] for spec in specs], who="profile")


def lint(paths) -> list:
    """Every shipped ``.scm`` file must load under the default profile.

    *paths* is a list of ``(path, game)`` pairs: a file under ``tetris/`` (the
    game's own prelude) is loaded into a game environment, everything else
    into a language-only one. The CLI's script tree is on the search path,
    mirroring ``run_script``. Returns the failures; an empty list means the
    lint is green.
    """
    from pathlib import Path

    from .errors import LispNameError
    from .runtime import load_file, make_env

    scripts = Path(__file__).resolve().parent.parent / "scripts"
    search_paths = [scripts] if scripts.is_dir() else []
    failures: list = []
    for path, game in paths:
        try:
            env = make_env(install_tetris=game, search_paths=search_paths)
            load_file(env, path)  # through the loader: (load ...) resolves
        except LispNameError as exc:
            # A missing *name* may be a game word: some shipped files use the
            # game's vocabulary, and `run_script` auto-installs it. Retry in a
            # game environment before calling it a failure.
            if game:
                failures.append(f"{path}: {exc}")
                continue
            try:
                env = make_env(install_tetris=True, search_paths=search_paths)
                load_file(env, path)
            except Exception as game_exc:  # noqa: BLE001
                failures.append(f"{path}: {game_exc}")
        except Exception as exc:  # noqa: BLE001 - the lint reports anything
            failures.append(f"{path}: {exc}")
    return failures

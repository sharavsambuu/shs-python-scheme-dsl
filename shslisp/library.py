"""The R7RS library system: ``define-library``, ``import``, and the registry.

A library is three things and nothing more:

* **a name** — ``(scheme base)``, ``(srfi 1)`` — the tuple of its parts;
* **exports** — the names it makes public, checked against the manifest
  (:mod:`shslisp.manifest`) for the built-in ``(scheme ...)`` libraries;
* **a private environment** — the scope its definitions live in. A library's
  exports are resolved *through* that scope, so two libraries that re-export
  the same binding hand back the *same object*: importing ``(srfi 1)`` next to
  ``(scheme base)`` does not quietly make ``car`` mean something else.

The registry belongs to an environment tree, exactly the way the loader does:
:func:`shslisp.runtime.make_env` installs it, child scopes inherit it, and a
``define-library`` evaluated anywhere in the tree registers into it. Two
consequences fall out of that: importing the same library twice is not a
duplicate-binding error (the second import rebinds the same values), and a
library defined in one environment is invisible to a fresh one — a program's
imports cannot leak across a :func:`make_env` boundary.

Import sets are R7RS §5.4: a plain library name, or ``(only ...)``,
``(except ...)``, ``(prefix ...)``, ``(rename ...)`` over one. Within one
``import`` form, two sets that bind the same local name to *different*
bindings are an error that names the collision; the same binding twice is
fine. An import that names a library which does not exist fails with "no such
library", and one that names a library which is declared but not implemented
fails with "not implemented yet" — never a silent no-op.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from .env import Environment
from .errors import LispError, LispSyntaxError, LispTypeError
from .types import NIL, Keyword, Symbol, intern

__all__ = [
    "Library",
    "SyntaxBinding",
    "install",
    "eval_import",
    "eval_define_library",
    "environment_from_specs",
    "library_available",
    "apply_imports",
    "get_library",
    "register_library",
]


# --------------------------------------------------------------------------- #
#  Syntactic exports                                                          #
# --------------------------------------------------------------------------- #

class SyntaxBinding:
    """A syntactic export: recognized by the evaluator, not a first-class value.

    ``(scheme base)`` exports ``begin``, ``define``, ``lambda`` — special
    forms the evaluator matches before any lookup, so there is nothing to
    bind. The sentinel exists so the *collision rule* can still see them: two
    import sets both carrying ``begin`` agree; a syntax name and a procedure
    of the same spelling do not.
    """

    __slots__ = ("name",)
    _cache: dict[str, "SyntaxBinding"] = {}

    def __new__(cls, name: str) -> "SyntaxBinding":
        sentinel = cls._cache.get(name)
        if sentinel is None:
            sentinel = super().__new__(cls)
            sentinel.name = name
            cls._cache[name] = sentinel
        return sentinel

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, SyntaxBinding) and other.name == self.name

    def __hash__(self) -> int:
        return hash(("lisp-syntax", self.name))

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"#<syntax {self.name}>"


# --------------------------------------------------------------------------- #
#  Libraries                                                                  #
# --------------------------------------------------------------------------- #

class Library:
    """One library: a name, its exports, and (lazily) a private environment.

    * Built-in ``(scheme ...)`` libraries are built from a *builder* — a
      callable that populates the private scope — and an explicit export list
      generated from the manifest.
    * ``define-library`` libraries are built from their declaration forms,
      processed in order the first time the library is imported.
    * A *missing* library is declared (so ``(library ...)``, ``environment``,
      and ``import`` all know it exists) but not implemented: importing it
      fails with "not implemented yet" rather than "unknown library".
    """

    def __init__(
        self,
        name: tuple[str, ...],
        *,
        exports: Optional[frozenset[str]] = None,
        builder: Optional[Callable[[], Environment]] = None,
        decls: Optional[list] = None,
        base_dir: Optional[Path] = None,
        missing: Optional[str] = None,
        owner: Optional[Environment] = None,
        note: str = "",
    ) -> None:
        self.name = tuple(name)
        self.exports = exports
        self.missing = missing
        self.note = note
        self._builder = builder
        self._decls = decls
        self._base_dir = base_dir
        self._owner = owner
        self._env: Optional[Environment] = None
        self._instantiating = False

    def instantiate(self) -> Environment:
        """The library's private environment, built on first need."""
        if self._env is not None:
            return self._env
        if self.missing is not None:
            raise LispError(_missing_message(self))
        if self._instantiating:
            raise LispError(
                "define-library: circular import involving "
                f"({' '.join(self.name)})"
            )
        self._instantiating = True
        try:
            if self._builder is not None:
                self._env = self._builder()
            else:
                env = Environment()
                # The private scope shares the owner's registry, so its own
                # ``(import ...)`` declarations can resolve libraries.
                env.libraries = self._owner.libraries if self._owner else None
                # ``self._env`` is set only *after* the declarations run: a
                # library importing itself sees the in-progress marker, not a
                # half-built environment.
                self._process_decls(self._decls or [], env)
                self._env = env
        finally:
            self._instantiating = False
        return self._env

    def export_binding(self, name: Symbol, who: str = "import") -> Any:
        """The value (or syntax sentinel) an import of *name* must bind."""
        if self.missing is not None:
            raise LispError(_missing_message(self, who))
        env = self.instantiate()
        # A renamed export binds its *internal* name: (export (rename frm to))
        # makes `to` resolve to whatever `frm` is bound to.
        internal = intern(getattr(self, "renames", {}).get(str(name), str(name)))
        frame = env.find(internal)
        if frame is not None:
            return frame.vars[internal]
        from .evaluator import _SPECIAL_FORMS

        # ``syntax-rules`` is parsed structurally by ``define-syntax``/``let-syntax``
        # rather than being an expression form, so it has no special-form entry —
        # it is still recognised syntax, and an export of it is still real.
        if name in _SPECIAL_FORMS or str(name) == "syntax-rules":
            return SyntaxBinding(str(name))
        raise LispError(
            f"{who}: library ({' '.join(self.name)}) exports {name}, "
            "but it is not bound"
        )

    # -- define-library bodies ------------------------------------------------ #

    def _process_decls(self, decls: list, lib_env: Environment) -> None:
        from .evaluator import evaluate_program

        exported: set[str] = set(self.exports or ())
        renames: dict[str, str] = dict(getattr(self, "renames", {}))
        index = 0
        while index < len(decls):
            decl = decls[index]
            index += 1
            if not (isinstance(decl, list) and decl and isinstance(decl[0], Symbol)):
                raise LispSyntaxError(
                    f"define-library: ({' '.join(self.name)}) has a bad declaration"
                )
            head = str(decl[0])
            if head == "export":
                for spec in decl[1:]:
                    # An export spec is a name, or (rename name export-name).
                    if isinstance(spec, list) and len(spec) == 3 and isinstance(spec[0], Symbol) and str(spec[0]) == "rename":
                        frm, to = spec[1], spec[2]
                        if not (isinstance(frm, Symbol) and isinstance(to, Symbol)):
                            raise LispSyntaxError("export: rename names must be symbols")
                        exported.add(str(to))
                        # The map is export-name -> internal name: `to` resolves
                        # to whatever `frm` is bound to in the private scope.
                        renames[str(to)] = str(frm)
                    elif isinstance(spec, Symbol):
                        exported.add(str(spec))
                    else:
                        raise LispSyntaxError("export: names must be symbols")
            elif head == "import":
                apply_imports(lib_env, decl[1:], who="import")
            elif head == "begin":
                evaluate_program(decl[1:], lib_env)
            elif head == "include":
                for spec in decl[1:]:
                    _include_into(lib_env, self._base_dir, spec, fold_case=False)
            elif head == "include-ci":
                for spec in decl[1:]:
                    _include_into(lib_env, self._base_dir, spec, fold_case=True)
            elif head == "include-library-declarations":
                for spec in decl[1:]:
                    path = _resolve_against(self._base_dir, spec)
                    from .reader import read_all

                    decls[index:index] = read_all(path.read_text(encoding="utf-8"))
            elif head == "cond-expand":
                for clause in decl[1:]:
                    if not (isinstance(clause, list) and clause):
                        raise LispSyntaxError("cond-expand: bad clause")
                    requirement = clause[0]
                    if isinstance(requirement, Symbol) and str(requirement) == "else":
                        decls[index:index] = list(clause[1:])
                        break
                    if _requirement(requirement):
                        decls[index:index] = list(clause[1:])
                        break
            else:
                raise LispSyntaxError(
                    f"define-library: unknown declaration ({head} ...)"
                )
        self.exports = frozenset(exported)
        self.renames = renames

    # -- introspection -------------------------------------------------------- #

    def export_names(self) -> list[str]:
        return sorted(self.exports or ())

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        state = "missing" if self.missing else "library"
        return f"#<{state} ({' '.join(self.name)})>"


def _missing_message(library: Library, who: str = "") -> str:
    prefix = f"{who}: " if who else ""
    return (
        f"{prefix}({' '.join(library.name)}) is not implemented yet"
        + (f" — {library.missing}" if library.missing else "")
    )


def _requirement(value: Any) -> bool:
    """A ``cond-expand`` requirement *inside a library body*.

    Same grammar as the top-level form, but ``(library ...)`` cannot be
    answered here — a library body's ``cond-expand`` runs while the registry
    is being built, so only feature identifiers and ``and``/``or``/``not``
    are honoured; a ``(library ...)`` requirement is an error.
    """
    from .evaluator import _feature_requirement

    if (
        isinstance(value, list)
        and value
        and isinstance(value[0], Symbol)
        and str(value[0]) == "library"
    ):
        raise LispSyntaxError(
            "define-library: (library ...) in a body cond-expand would ask "
            "the registry while it is being built"
        )
    return _feature_requirement(value)


# --------------------------------------------------------------------------- #
#  Include (library bodies)                                                   #
# --------------------------------------------------------------------------- #

def _resolve_against(base_dir: Optional[Path], spec: Any) -> Path:
    """The file *spec* names, relative to the library's own directory."""
    if not isinstance(spec, str) or isinstance(spec, Symbol):
        raise LispSyntaxError("include: expected a file-name string")
    raw = Path(str(spec))
    if raw.is_absolute():
        candidates = [raw]
    else:
        if base_dir is None:
            raise LispError(
                f"include: no source directory to resolve {str(spec)!r} against"
            )
        names = (
            [raw]
            if raw.suffix
            else [raw.with_name(raw.name + ".scm"), raw.with_name(raw.name + ".lisp"), raw]
        )
        candidates = [base_dir / name for name in names]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise LispError(f"include: no such file {str(spec)!r}")


def _include_into(
    lib_env: Environment, base_dir: Optional[Path], spec: Any, fold_case: bool
) -> None:
    from .evaluator import evaluate_program
    from .reader import read_all

    path = _resolve_against(base_dir, spec)
    source = path.read_text(encoding="utf-8")
    if fold_case:
        source = "#!fold-case\n" + source
    evaluate_program(read_all(source), lib_env)


# --------------------------------------------------------------------------- #
#  The registry (one per environment tree, like the loader)                    #
# --------------------------------------------------------------------------- #

def registry_of(env: Environment) -> dict[tuple[str, ...], Library]:
    """The environment tree's registry — created empty if there is none."""
    if env.libraries is None:
        env.libraries = {}
    return env.libraries


def register_library(env: Environment, library: Library) -> None:
    registry_of(env)[library.name] = library


def get_library(
    env: Environment, parts: tuple[str, ...], who: str = "import"
) -> Optional[Library]:
    """The library named by *parts*, or ``None`` when it is not in the registry."""
    return registry_of(env).get(parts)


def library_available(env: Environment, value: Any) -> bool:
    """Is the library named by *value* implemented here?

    ``cond-expand``'s ``(library ...)`` test. A declared-but-missing library
    answers ``#f`` — it exists in the registry but cannot be imported.
    """
    from .libraries import library_name

    try:
        parts = library_name(value)
    except TypeError:
        return False
    library = registry_of(env).get(parts)
    return library is not None and library.missing is None


def library_name_of(value: Any, who: str) -> tuple[str, ...]:
    """Validate an unevaluated library-name form; return its parts."""
    from .libraries import library_name

    if not isinstance(value, list) or not value:
        raise LispTypeError(f"{who}: each import specifier is a library name list")
    try:
        return library_name(value)
    except TypeError:
        raise LispTypeError(f"{who}: each import specifier is a library name list") from None


# --------------------------------------------------------------------------- #
#  Import sets                                                                #
# --------------------------------------------------------------------------- #

def _resolve_set(spec: Any, env: Environment, who: str) -> dict[Symbol, Any]:
    """One import set as a mapping of local names to bindings (or sentinels)."""
    if not isinstance(spec, list) or not spec:
        raise LispSyntaxError(f"{who}: each import set is a list")
    head = spec[0]
    if isinstance(head, Symbol) and str(head) in ("only", "except", "prefix", "rename"):
        modifier = str(head)
        if len(spec) < 2:
            raise LispSyntaxError(f"{who}: ({modifier} ...) needs an import set")
        inner = _resolve_set(spec[1], env, who)
        if modifier == "only":
            out: dict[Symbol, Any] = {}
            for name in spec[2:]:
                if not isinstance(name, Symbol):
                    raise LispSyntaxError(f"{who}: only: names must be symbols")
                if name not in inner:
                    raise LispError(
                        f"{who}: only: {name} is not exported by the library"
                    )
                out[name] = inner[name]
            return out
        if modifier == "except":
            dropped = {n for n in spec[2:] if isinstance(n, Symbol)}
            return {n: b for n, b in inner.items() if n not in dropped}
        if modifier == "prefix":
            # The prefix may be a keyword (`base:`) — SRFI 88's trailing-colon
            # identifiers read as keywords, and a keyword's name is exactly
            # the prefix text. A plain symbol works too.
            if len(spec) != 3 or not isinstance(spec[2], (Symbol, Keyword)):
                raise LispSyntaxError(f"{who}: prefix: expected (prefix set prefix)")
            # A keyword prefix (`base:`) is written back with its colon, so
            # `(prefix (only (scheme base) car) base:)` binds `base:car`.
            prefix = str(spec[2]) + (":" if isinstance(spec[2], Keyword) else "")
            return {intern(prefix + str(n)): b for n, b in inner.items()}
        # rename
        out = dict(inner)
        for pair in spec[2:]:
            if not (isinstance(pair, list) and len(pair) == 2):
                raise LispSyntaxError(f"{who}: rename: each entry is (from to)")
            frm, to = pair
            if not (isinstance(frm, Symbol) and isinstance(to, Symbol)):
                raise LispSyntaxError(f"{who}: rename: names must be symbols")
            if frm not in inner:
                raise LispError(
                    f"{who}: rename: {frm} is not exported by the library"
                )
            del out[frm]
            out[to] = inner[frm]
        return out
    parts = library_name_of(spec, who)
    library = get_library(env, parts)
    if library is None:
        shown = " ".join(parts)
        raise LispError(f"{who}: no such library ({shown})")
    if library.missing is not None:
        raise LispError(_missing_message(library, who))
    # Instantiate *first*: a define-library library's export list is only
    # known once its declarations have been processed.
    library.instantiate()
    exports = library.exports or frozenset()
    return {intern(name): library.export_binding(intern(name), who) for name in exports}


def _same_binding(a: Any, b: Any) -> bool:
    """Do two import sets agree on what a local name means?"""
    if isinstance(a, SyntaxBinding) or isinstance(b, SyntaxBinding):
        return a == b
    return a is b


def _describe_set(spec: Any) -> str:
    from .printer import to_string

    return to_string(spec, write=True)


def _renamed_targets(spec: Any, out: set) -> None:
    """The ``to`` names of every ``rename`` modifier inside an import set."""
    if not (isinstance(spec, list) and spec and isinstance(spec[0], Symbol)):
        return
    head = str(spec[0])
    if head == "rename":
        for pair in spec[2:]:
            if isinstance(pair, list) and len(pair) == 2 and isinstance(pair[1], Symbol):
                out.add(pair[1])
    if head in ("only", "except", "prefix", "rename") and len(spec) >= 2:
        _renamed_targets(spec[1], out)


def apply_imports(env: Environment, sets: list, who: str = "import") -> None:
    """Apply import *sets* to *env*, refusing cross-set collisions by name.

    A plain library import keeps R7RS shadowing semantics: importing
    ``(srfi 1)`` binds its ``for-each`` over the base one, by design. The one
    guarded case is a **rename whose target is a core primitive** — the
    profile obeys the additive rule at the floor (it renames ``map``/
    ``for-each`` *away* from the core names), so a user ``(rename ...
    (fold car))`` is almost certainly a mistake and raises instead of
    silently putting a different procedure where ``car`` was. Rebinding a
    name to the very object it already has is always fine.
    """
    renamed: set[Symbol] = set()
    for spec in sets:
        _renamed_targets(spec, renamed)
    mapping: dict[Symbol, Any] = {}
    sources: dict[Symbol, str] = {}
    for spec in sets:
        for name, binding in _resolve_set(spec, env, who).items():
            if name in mapping and not _same_binding(mapping[name], binding):
                second = _describe_set(spec)
                raise LispError(
                    f"{who}: name collision on {name} between {sources[name]} "
                    f"and {second} — the two sets bind {name} to different "
                    f"bindings; fix: split the sets into separate (import ...) "
                    f"forms (the later one shadows), or trim one set with "
                    f"(except {second} {name}), or keep both with "
                    f"(rename {second} ({name} <new-name>))"
                )
            mapping[name] = binding
            sources[name] = _describe_set(spec)
    for name, binding in mapping.items():
        if isinstance(binding, SyntaxBinding):
            continue
        core_names = getattr(env, "core_names", ()) or ()
        if name in renamed and name in core_names:
            current = env.lookup(name)
            if not _same_binding(current, binding):
                raise LispError(
                    f"{who}: name collision on {name}: renaming onto a core "
                    f"primitive is refused — pick another local name"
                )
        env.define(name, binding)


# --------------------------------------------------------------------------- #
#  The special forms                                                          #
# --------------------------------------------------------------------------- #

def eval_import(expr: list, env: Environment) -> Any:
    """``(import set ...)`` — bind the sets' names into *env*."""
    if len(expr) < 2:
        raise LispSyntaxError("import: needs at least one import set")
    apply_imports(env, list(expr[1:]), who="import")
    return NIL


def eval_define_library(expr: list, env: Environment) -> Any:
    """``(define-library (name parts...) declaration ...)`` — register it.

    The declarations are *not* processed here: a library is built the first
    time something imports it, which is what makes mutual reference between
    libraries an error you can see instead of a load-order accident.
    """
    if len(expr) < 2 or not isinstance(expr[1], list) or not expr[1]:
        raise LispSyntaxError(
            "define-library: expected (define-library (name parts...) decl...)"
        )
    parts = tuple(str(part) for part in expr[1])
    base_dir = env.loader.current_dir() if env.loader is not None else None
    register_library(
        env, Library(parts, decls=list(expr[2:]), base_dir=base_dir, owner=env)
    )
    return NIL


def environment_from_specs(
    base: Environment, specs: tuple, who: str = "environment"
) -> Environment:
    """``(environment import-spec ...)`` — a *restricted* fresh environment.

    The environment is a root scope holding only what the import sets bind:
    a name the libraries do not export is unbound here, which is what R7RS's
    restricted import means. The registry and loader are shared with *base*
    so a definition evaluated in it can still resolve libraries and files.
    """
    child = Environment()
    child.libraries = base.libraries
    child.loader = base.loader
    sets = []
    for spec in specs:
        if isinstance(spec, Symbol):
            raise LispTypeError(
                f"{who}: each import specifier is a library name list, "
                f"not the bare symbol {spec}"
            )
        library_name_of(spec, who)
        sets.append(spec)
    apply_imports(child, sets, who=who)
    return child


# --------------------------------------------------------------------------- #
#  Installing the built-in libraries                                          #
# --------------------------------------------------------------------------- #

def _core_backed_builder(env: Environment, installers: tuple) -> Callable[[], Environment]:
    """A builder for a core-*backed* library: its Python primitives are
    installed into one private child scope the first time an import needs
    them — never into the core floor. The strict ``r7rs`` profile therefore
    sees these names only through ``(import ...)``, like every other SRFI,
    while the default profile's pre-import binds the very same objects.
    Libraries sharing a builder share the scope, so ``(srfi 160 base)`` and
    ``(srfi 160 f64)`` hand back the *same* primitive objects — the collision
    rule compares bindings by identity (see ``_same_binding``)."""
    cache: list = []

    def build() -> Environment:
        if not cache:
            scope = Environment(parent=env)
            for installer in installers:
                installer(scope)
            cache.append(scope)
        return cache[0]

    return build


def install(env: Environment) -> None:
    """Register the built-in ``(scheme ...)`` libraries and the SRFI stubs.

    Must run *after* the core and prelude are loaded: every ``(scheme ...)``
    export resolves against *env* itself, so the bindings an import binds are
    the very objects the environment already has — ``car`` in an importing
    scope *is* the environment's ``car``, not a copy.
    """
    from .manifest import KNOWN_MISSING, MANIFEST

    registry = registry_of(env)
    for display_name, manifest_lib in MANIFEST.items():
        parts = tuple(display_name.strip("()").split())
        names = (*manifest_lib.procedures, *manifest_lib.syntax)
        if not names:
            continue
        if all(name in KNOWN_MISSING for name in names):
            # Every name this library would export is deliberately absent —
            # it is a *missing* library, and importing it says why.
            registry[parts] = Library(parts, missing=manifest_lib.note or "unsupported")
            continue
        exports = frozenset(name for name in names if name not in KNOWN_MISSING)
        registry[parts] = Library(
            parts, exports=exports, builder=lambda: env, missing=None
        )
    for parts, reason in _MISSING_LIBRARIES.items():
        registry.setdefault(parts, Library(parts, missing=reason))
    registry[("srfi", "1")] = lisp_file_library(
        env,
        ("srfi", "1"),
        Path(__file__).with_name("srfi1.scm"),
        _SRFI1_EXPORTS,
        note="The list library.",
    )
    registry[("srfi", "26")] = lisp_file_library(
        env,
        ("srfi", "26"),
        Path(__file__).with_name("srfi26.scm"),
        ("cut", "cute"),
        note="Specializing parameters without currying.",
    )
    # SRFI 88: keyword objects. The reader, printer, equality and the three
    # primitives are core (builtins.py); the library just scopes the names.
    registry[("srfi", "88")] = Library(
        ("srfi", "88"),
        exports=frozenset({"keyword?", "keyword->string", "string->keyword"}),
        builder=lambda: env,
        note="Keyword objects.",
    )
    registry[("srfi", "89")] = lisp_file_library(
        env,
        ("srfi", "89"),
        Path(__file__).with_name("srfi89.scm"),
        ("define*", "lambda*"),
        note="Optional positional and named parameters.",
    )
    registry[("srfi", "197")] = lisp_file_library(
        env,
        ("srfi", "197"),
        Path(__file__).with_name("srfi197.scm"),
        ("chain", "chain-and", "chain-when", "chain-lambda", "nest", "nest-reverse"),
        note="Pipeline operators.",
    )
    registry[("srfi", "241")] = Library(
        ("srfi", "241"),
        exports=frozenset({"match"}),
        builder=lambda: env,
        note="Pattern matcher.",
    )
    # The trading-layer libraries (S10, S11) are core-*backed*, not
    # core-*bound*: their primitives install into a private scope on first
    # import (see `_core_backed_builder`), so the strict r7rs profile leaves
    # them import-only — the docs' promise — while the default profile's
    # pre-import binds the same objects.
    def _install_srfi19(scope: Environment) -> None:
        from .srfi19 import install as installer

        installer(scope)

    def _install_srfi160(scope: Environment) -> None:
        from .srfi160 import install as installer

        installer(scope)

    registry[("srfi", "19")] = Library(
        ("srfi", "19"),
        exports=frozenset(_SRFI19_EXPORTS),
        builder=_core_backed_builder(env, (_install_srfi19,)),
        note="Time and date (S10): core-backed Python primitives.",
    )
    registry[("srfi", "158")] = Library(
        ("srfi", "158"),
        exports=frozenset(_SRFI158_EXPORTS),
        builder=lambda: env,
        note="Generators and accumulators (S12): the prelude's audited surface.",
    )
    srfi160_builder = _core_backed_builder(env, (_install_srfi160,))
    registry[("srfi", "160", "base")] = Library(
        ("srfi", "160", "base"),
        exports=frozenset(_SRFI160_BASE_EXPORTS),
        builder=srfi160_builder,
        note="Homogeneous numeric vectors (S11): the SRFI-4 eight + @?, x12 types.",
    )
    registry[("srfi", "160", "f64")] = Library(
        ("srfi", "160", "f64"),
        exports=frozenset(_SRFI160_F64_EXPORTS),
        builder=srfi160_builder,
        note="The f64vector operation set (S11), the numpy bridge.",
    )
    # The S14/S15/S17/S18 libraries are core-backed the same way: their
    # primitives install into a private scope on first import, so the strict
    # r7rs profile leaves them import-only. `(srfi 64)` is pure Lisp: its
    # assertion forms are macros, which a Python module cannot define.
    def _install_srfi125(scope: Environment) -> None:
        from .srfi125 import install as installer

        installer(scope)

    def _install_srfi132(scope: Environment) -> None:
        from .srfi132 import install as installer

        installer(scope)

    def _install_srfi180(scope: Environment) -> None:
        from .srfi180 import install as installer

        installer(scope)

    def _install_srfi28(scope: Environment) -> None:
        from .srfi28 import install as installer

        installer(scope)

    def _install_srfi152(scope: Environment) -> None:
        from .srfi152 import install as installer

        installer(scope)

    registry[("srfi", "28")] = Library(
        ("srfi", "28"),
        exports=frozenset(_SRFI28_EXPORTS),
        builder=_core_backed_builder(env, (_install_srfi28,)),
        note="Basic format strings (S18): ~a, ~s, ~%, ~~.",
    )
    registry[("srfi", "64")] = lisp_file_library(
        env,
        ("srfi", "64"),
        Path(__file__).with_name("srfi64.scm"),
        _SRFI64_EXPORTS,
        note="A Scheme API for test suites (S16): assertion macros + a runner.",
    )
    registry[("srfi", "125")] = Library(
        ("srfi", "125"),
        exports=frozenset(_SRFI125_EXPORTS),
        builder=_core_backed_builder(env, (_install_srfi125,)),
        note="Hash tables (S14): the core's equal?-keyed tables, SRFI spellings.",
    )
    registry[("srfi", "132")] = Library(
        ("srfi", "132"),
        exports=frozenset(_SRFI132_EXPORTS),
        builder=_core_backed_builder(env, (_install_srfi132,)),
        note="Sort libraries (S15): Python Timsort over the caller's comparator.",
    )
    registry[("srfi", "152")] = Library(
        ("srfi", "152"),
        exports=frozenset(_SRFI152_EXPORTS),
        builder=_core_backed_builder(env, (_install_srfi152,)),
        note="String utilities (S18): split/join/contains/trim/affixes.",
    )
    registry[("srfi", "180")] = Library(
        ("srfi", "180"),
        exports=frozenset(_SRFI180_EXPORTS),
        builder=_core_backed_builder(env, (_install_srfi180,)),
        note="JSON (S17): json-read / json-write over the stdlib json module.",
    )


#: A library implemented in Lisp: a private scope whose parent is the owning
#: environment (so every name the file does not define falls through to the
#: core primitives), with the file loaded into it once per registry.
def lisp_file_library(
    env: Environment, name: tuple[str, ...], path: Path, exports: tuple[str, ...],
    note: str = "",
) -> Library:
    def build() -> Environment:
        from .evaluator import evaluate_program
        from .reader import read_all

        lib_env = Environment(parent=env)
        evaluate_program(read_all(path.read_text(encoding="utf-8")), lib_env)
        return lib_env

    return Library(name, exports=frozenset(exports), builder=build, note=note)


#: Declared but not implemented: importing fails with "not implemented yet",
#: and ``(library ...)``, ``(features)`` and ``cond-expand`` all answer
#: consistently. S2-S6 replace these with real libraries.
_MISSING_LIBRARIES: dict[tuple[str, ...], str] = {
    ("srfi", "204"): "SRFI 204 is withdrawn; the match library is SRFI 241",
}

#: The SRFI 1 export list — the library's public surface, checked by a test
#: against both the SRFI 1 procedure index and the library's own environment.
#: Names shared with ``(scheme base)`` (``member``, ``assoc``, ``map``,
#: ``for-each``, ``filter``) are the *same bindings*, re-exported, except
#: ``map``/``for-each``, whose SRFI 1 semantics differ and are renamed in the
#: default profile.
_SRFI1_EXPORTS = (
    "alist-cons alist-copy alist-delete alist-delete! any append! append-map"
    " append-map! append-reverse append-reverse! assoc assq assv break break!"
    " car cdr car+cdr circular-list circular-list? concatenate concatenate!"
    " cons* count delete delete! delete-duplicates delete-duplicates!"
    " dotted-list? drop drop-right drop-right! drop-while drop-while! eighth"
    " every fifth filter filter! filter-map find find-right find-tail first"
    " fold fold-right fourth iota last last-pair length+ lset<= lset= lset-adjoin"
    " lset-diff+intersection lset-diff+intersection! lset-difference"
    " lset-difference! lset-intersection lset-intersection! lset-union"
    " lset-union! lset-xor lset-xor! list-index list-ref list-tabulate list="
    " map map! map-in-order for-each member memq memv ninth not-pair?"
    " null-list? pair-fold pair-fold-right pair-for-each partition partition!"
    " proper-list? reduce reduce-right remove remove! reverse! second seventh"
    " set-car! set-cdr! sixth span span-right span! split-at split-at! take take!"
    " take-right take-while take-while-right take-while! tenth third unfold"
    " unfold-right unzip1 unzip2 unzip3 unzip4 unzip5 xcons zip"
).split()

#: The (srfi 19) surface (S10) — the workhorse subset the ledger scoped, each
#: name a core-bound primitive in shslisp/srfi19.py. Documented deviations:
#: no TAI/thread clocks (the constants exist, the clocks refuse), no leap
#: seconds, no monotonic<->UTC conversions, no zone names, no date-zone-name/
#: date-dst? (the reference surface does not require them).
_SRFI19_EXPORTS = (
    "time-tai time-utc time-monotonic time-thread time-process time-duration"
    " current-time time-resolution"
    " make-time time? time-type time-second time-nanosecond"
    " set-time-type! set-time-second! set-time-nanosecond! copy-time"
    " time=? time<? time<=? time>? time>=?"
    " time-difference time-difference! add-duration add-duration!"
    " subtract-duration subtract-duration!"
    " current-date make-date date? date-nanosecond date-second date-minute"
    " date-hour date-day date-month date-year date-zone-offset"
    " date-year-day date-week-day date-week-number"
    " current-julian-day current-modified-julian-day"
    " date->julian-day date->modified-julian-day date->time-utc"
    " julian-day->date julian-day->time-utc"
    " modified-julian-day->date modified-julian-day->time-utc"
    " time-utc->date time-utc->julian-day time-utc->modified-julian-day"
    " date->string string->date"
).split()

#: The (srfi 158) surface (S12) — the final SRFI 158 export list, audited
#: name by name. The names are bound by the prelude (shslisp/generators.scm);
#: make-coroutine-generator/make-for-each-generator are bound but fail loudly
#: (they need re-entrant continuations). `max`/`min` accumulators are *not*
#: in the final SRFI's export list, so they are not claimed either.
_SRFI158_EXPORTS = (
    "generator circular-generator make-iota-generator make-range-generator"
    " make-coroutine-generator list->generator vector->generator"
    " reverse-vector->generator string->generator bytevector->generator"
    " make-for-each-generator make-unfold-generator"
    " gcons* gappend gcombine gfilter gremove gtake gdrop gtake-while"
    " gdrop-while gflatten ggroup gmerge gmap gstate-filter gdelete"
    " gdelete-neighbor-dups gindex gselect"
    " generator->list generator->reverse-list generator->vector"
    " generator->vector! generator->string"
    " generator-fold generator-map->list generator-for-each generator-find"
    " generator-count generator-any generator-every generator-unfold"
    " make-accumulator count-accumulator list-accumulator"
    " reverse-list-accumulator vector-accumulator reverse-vector-accumulator"
    " vector-accumulator! string-accumulator bytevector-accumulator"
    " bytevector-accumulator! sum-accumulator product-accumulator"
).split()

#: (srfi 160 base) — the eight SRFI-4 procedures plus the @? predicate, for
#: all twelve types. The names are core-bound primitives in srfi160.py.
_SRFI160_BASE_EXPORTS = (
    "make-u8vector make-s8vector make-u16vector make-s16vector"
    " make-u32vector make-s32vector make-u64vector make-s64vector"
    " make-f32vector make-f64vector make-c64vector make-c128vector"
    " u8vector s8vector u16vector s16vector u32vector s32vector u64vector"
    " s64vector f32vector f64vector c64vector c128vector"
    " u8vector? s8vector? u16vector? s16vector? u32vector? s32vector?"
    " u64vector? s64vector? f32vector? f64vector? c64vector? c128vector?"
    " u8vector-length s8vector-length u16vector-length s16vector-length"
    " u32vector-length s32vector-length u64vector-length s64vector-length"
    " f32vector-length f64vector-length c64vector-length c128vector-length"
    " u8vector-ref s8vector-ref u16vector-ref s16vector-ref u32vector-ref"
    " s32vector-ref u64vector-ref s64vector-ref f32vector-ref f64vector-ref"
    " c64vector-ref c128vector-ref"
    " u8vector-set! s8vector-set! u16vector-set! s16vector-set!"
    " u32vector-set! s32vector-set! u64vector-set! s64vector-set!"
    " f32vector-set! f64vector-set! c64vector-set! c128vector-set!"
    " u8vector->list s8vector->list u16vector->list s16vector->list"
    " u32vector->list s32vector->list u64vector->list s64vector->list"
    " f32vector->list f64vector->list c64vector->list c128vector->list"
    " list->u8vector list->s8vector list->u16vector list->s16vector"
    " list->u32vector list->s32vector list->u64vector list->s64vector"
    " list->f32vector list->f64vector list->c64vector list->c128vector"
    " u8? s8? u16? s16? u32? s32? u64? s64? f32? f64? c64? c128?"
).split()

#: (srfi 160 f64) — the SRFI-133-shaped operation set plus
#: make-f64vector-generator and write-f64vector. `f64vector-comparator` is
#: deliberately absent: it needs SRFI 128, which is not scheduled; the
#: omission is documented, not shimmed.
_SRFI160_F64_EXPORTS = (
    "make-f64vector f64vector f64vector-unfold f64vector-unfold-right"
    " f64vector-copy f64vector-reverse-copy f64vector-append"
    " f64vector-concatenate f64vector-append-subvectors"
    " f64? f64vector? f64vector-empty? f64vector="
    " f64vector-ref f64vector-length"
    " f64vector-take f64vector-take-right f64vector-drop f64vector-drop-right"
    " f64vector-segment f64vector-fold f64vector-fold-right f64vector-map"
    " f64vector-map! f64vector-for-each f64vector-count f64vector-cumulate"
    " f64vector-take-while f64vector-take-while-right f64vector-drop-while"
    " f64vector-drop-while-right f64vector-index f64vector-index-right"
    " f64vector-skip f64vector-skip-right f64vector-any f64vector-every"
    " f64vector-partition f64vector-filter f64vector-remove"
    " f64vector-set! f64vector-swap! f64vector-fill! f64vector-reverse!"
    " f64vector-copy! f64vector-reverse-copy! f64vector-unfold!"
    " f64vector-unfold-right!"
    " f64vector->list list->f64vector reverse-f64vector->list"
    " reverse-list->f64vector f64vector->vector vector->f64vector"
    " make-f64vector-generator write-f64vector"
).split()

#: The (srfi 125) surface (S14) — the ledger's twelve names. The core already
#: binds ten of them (`make-hash-table`, `hash-table?`, `hash-table-ref`,
#: `hash-table-ref/default`, `hash-table-set!`, `hash-table-delete!`,
#: `hash-table-keys`, `hash-table-values`, `hash-table->alist`, and the two
#: spellings below come from `shslisp/srfi125.py`); the exported bindings are
#: the same objects the core has, not copies.
_SRFI125_EXPORTS = (
    "make-hash-table hash-table? hash-table-ref hash-table-ref/default"
    " hash-table-set! hash-table-delete! hash-table-contains? hash-table-size"
    " hash-table-keys hash-table-values hash-table->alist alist->hash-table"
).split()

#: The (srfi 132) surface (S15) — the sort half of the SRFI the ledger scoped.
#: The mutation operators and the merge/median/selection families are not
#: claimed (docs/srfi.md records the omission).
_SRFI132_EXPORTS = (
    "list-sorted? list-sort list-stable-sort"
    " vector-sorted? vector-sort vector-stable-sort"
).split()

#: The (srfi 64) surface (S16). The assertion names are syntax (macros);
#: `test-runner-current`/`test-runner-simple`/`test-begin`/`test-end` are
#: procedures. Bound by `shslisp/srfi64.scm`.
_SRFI64_EXPORTS = (
    "test-begin test-end test-group test-assert test-equal test-eqv test-eq"
    " test-error test-runner-current test-runner-simple"
).split()

#: The (srfi 28) surface (S18): the one procedure the ledger claims.
_SRFI28_EXPORTS = ("format",)

#: The (srfi 152) surface (S18) — the ledger's seven names. `string-trim` is
#: both-ends here (the locked S18 test; see docs/srfi.md).
_SRFI152_EXPORTS = (
    "string-split string-join string-contains"
    " string-trim string-trim-both string-prefix? string-suffix?"
).split()

#: The (srfi 180) surface (S17): the two primitives the ledger claims.
_SRFI180_EXPORTS = ("json-read", "json-write")

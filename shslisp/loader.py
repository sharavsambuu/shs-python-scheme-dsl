"""The module system: ``(load "path")``.

A language that cannot read a file is a language where every program is one
file. This module is the smallest thing that fixes that, and it is deliberately
three rules:

* **Resolution** — a relative path is tried against the *loading* file's own
  directory first, then each search path; the ``.scm`` suffix is optional —
  a bare name tries ``.scm``, then ``.lisp`` for older modules, then the
  path as written.
  So a library can say ``(load "hud")`` next to itself, and a script can say
  ``(load "domains/planning/one-ply")`` from anywhere.
* **Load once** — a module is read and evaluated at most once per
  environment, however many times it is loaded. The second ``(load ...)``
  returns the first result and defines nothing again. The cache is keyed by
  the *resolved absolute path*, so ``domains/x.scm`` and ``./domains/x.scm``
  are one module, not two.
* **Cycles are errors** — ``a -> b -> a`` raises, naming the chain, instead of
  recursing until the interpreter's stack dies.

The loader belongs to exactly one environment. An
:class:`~shslisp.env.Environment` remembers it, which is why the host's
:func:`shslisp.runtime.load_file` and a program's ``(load ...)`` share one cache
and one resolution rule: loading a script is just loading a module by another
name.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, List, Optional

from .env import Environment
from .errors import LispArityError, LispError, LispTypeError
from .evaluator import evaluate_program
from .reader import read_all
from .types import NIL, Primitive, intern

__all__ = ["SUFFIX", "Loader"]

#: Added to a spec that has no suffix of its own.
SUFFIX = ".scm"


def _unique(paths: Iterable[Path]) -> List[Path]:
    """Drop duplicates while keeping order (the search order is meaningful)."""
    seen: set[Path] = set()
    out: List[Path] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            out.append(path)
    return out


class Loader:
    """Resolve, evaluate once, and remember every module it was asked to load."""

    def __init__(self, search_paths: Iterable[Any] = ()) -> None:
        self.search_paths: List[Path] = _unique(
            Path(p).expanduser().resolve() for p in search_paths
        )
        self.env: Optional[Environment] = None
        #: Files currently being evaluated, outermost first — used both for
        #: relative resolution and for cycle detection.
        self._stack: List[Path] = []
        #: Resolved path → the value of that module's last form.
        self._loaded: dict[Path, Any] = {}

    # -- installation -------------------------------------------------------- #

    def install(self, env: Environment) -> "Loader":
        """Bind this loader to *env* and define the module primitives there."""
        self.env = env
        env.loader = self
        env.define(intern("load"), Primitive("load", self.load))
        env.define(intern("loaded?"), Primitive("loaded?", self.loaded))
        env.define(
            intern("loaded-modules"), Primitive("loaded-modules", self.modules)
        )
        env.define(intern("search-path"), Primitive("search-path", self.paths))
        return self

    def attach(self, env: Environment) -> "Loader":
        """Install into *env*; a loader belongs to exactly one environment."""
        if self.env is None:
            return self.install(env)
        if self.env is env:
            return self
        raise LispError("load: a loader belongs to exactly one environment")

    def add_search_paths(self, paths: Iterable[Any]) -> "Loader":
        """Append directories to the search path (order is preserved)."""
        self.search_paths = _unique(
            [*self.search_paths, *(Path(p).expanduser().resolve() for p in paths)]
        )
        return self

    # -- the program-facing hook -------------------------------------------- #

    def load(self, *specs: Any) -> Any:
        """``(load "a" "b")`` — evaluate each module; return the last value."""
        if not specs:
            raise LispArityError("load", "at least 1", 0)
        value: Any = NIL
        for spec in specs:
            value = self.load_one(spec)
        return value

    def load_one(self, spec: Any) -> Any:
        """Resolve *spec*, then evaluate it unless it is already loaded."""
        path = self.resolve(spec)
        if path in self._loaded:
            return self._loaded[path]
        if path in self._stack:
            raise LispError(f"load: circular dependency: {self._chain(path)}")
        if self.env is None:
            raise LispError("load: this loader is not installed in an environment")
        self._stack.append(path)
        try:
            source = path.read_text(encoding="utf-8")
            value = evaluate_program(read_all(source), self.env)
        finally:
            self._stack.pop()
        # A file with no forms evaluates to nothing; ``()`` is the language's
        # "nothing", so that is what a caller should see.
        self._loaded[path] = NIL if value is None else value
        return self._loaded[path]

    def include_file(self, spec: Any, fold_case: bool = False) -> Any:
        """``(include "file")`` — read *spec* and evaluate it in this env.

        Unlike ``load``, this is textual inclusion: the file is read and
        evaluated every time, and a cycle is still an error. ``include-ci``
        prepends ``#!fold-case`` so its identifiers fold.
        """
        path = self.resolve(spec)
        if path in self._stack:
            raise LispError(f"include: circular dependency: {self._chain(path)}")
        if self.env is None:
            raise LispError("include: this loader is not installed in an environment")
        self._stack.append(path)
        try:
            source = path.read_text(encoding="utf-8")
            if fold_case:
                source = "#!fold-case\n" + source
            return evaluate_program(read_all(source), self.env)
        finally:
            self._stack.pop()

    # -- introspection ------------------------------------------------------- #

    def loaded(self, spec: Any) -> bool:
        """``(loaded? "domains/x")`` — has this module already been evaluated?"""
        try:
            return self.resolve(spec) in self._loaded
        except LispError:
            return False

    def modules(self) -> Any:
        """``(loaded-modules)`` — resolved paths, in load order."""
        return [str(path) for path in self._loaded] or NIL

    def paths(self) -> Any:
        """``(search-path)`` — the directories a bare spec is tried against."""
        return [str(path) for path in self.search_paths] or NIL

    # -- resolution ---------------------------------------------------------- #

    def bases(self) -> List[Path]:
        """Where a relative spec is looked up: the caller's dir, then the path."""
        here = [self._stack[-1].parent] if self._stack else []
        return _unique([*here, *self.search_paths])

    def current_dir(self) -> Optional[Path]:
        """The directory of the file being read right now (``None`` if at a REPL)."""
        return self._stack[-1].parent if self._stack else None

    def resolve(self, spec: Any) -> Path:
        """The file *spec* names, or an error listing every place we looked."""
        if not isinstance(spec, (str, Path)):
            raise LispTypeError(
                f"load: expected a path string, got {type(spec).__name__}"
            )
        raw = Path(str(spec))
        names = [raw] if raw.suffix else [raw.with_name(raw.name + SUFFIX), raw.with_name(raw.name + ".lisp"), raw]
        if raw.is_absolute():
            candidates = names
        else:
            candidates = [base / name for base in self.bases() for name in names]
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        raise LispError(f"load: no such module {spec!r}; searched {self._where()}")

    def _where(self) -> str:
        bases = self.bases()
        return ", ".join(str(base) for base in bases) if bases else "(no search path)"

    def _chain(self, path: Path) -> str:
        """``b.scm -> c.scm -> b.scm`` — the cycle, from its first repeat."""
        try:
            start = self._stack.index(path)
        except ValueError:  # pragma: no cover - only called for a stacked path
            start = 0
        names = [*self._stack[start:], path]
        return " -> ".join(p.name for p in names)

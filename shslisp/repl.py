"""A read-eval-print loop, and the file runner the CLI leans on.

The REPL is deliberately thin. It only has to solve one problem a plain
``eval`` does not: knowing when a form is *finished*. It reads lines until the
parentheses balance, then evaluates — so a ``define`` can be typed across as
many lines as it takes, which is what makes a Lisp REPL worth having.

It is also hostile-input safe: a form typed with mistakes — an unterminated
string, a stray ``)``, a character literal the reader rejects — comes back as
an ``error:`` line, and the loop goes on. A crash is a bug the error classes
in :mod:`shslisp.errors` exist to prevent.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterable, List, Optional, TextIO

from .env import Environment
from .errors import ContinuationJump, LispError, LispSyntaxError
from .evaluator import evaluate
from .printer import to_string
from .reader import read_all, tokenize
from .runtime import load_file, make_env

BANNER = "shs — a small Scheme-flavored Lisp.  (,help  ,quit)"

HELP = """\
,help          show this help
,load PATH     load a module (relative to it, then the search path; once only)
,quit          leave              (also: ,q  or  quit)

Everything else is Lisp.  Try:
  (+ 1 2)
  (define (fact n) (if (= n 0) 1 (* n (fact (- n 1)))))
  (fact 20)
  (fold + 0 '(1 2 3 4))            ; SRFI 1 — the list library
  (map (cut * 2 <>) '(1 2 3))      ; SRFI 26 — specialized calls
  (chain 5 (* _ 2) (+ _ 1))        ; SRFI 197 — threading pipelines

  (load "my-library")              ; .scm files on the search path
"""


#: Reader errors that *more input* can repair — the form is still open and the
#: REPL should ask for another line. Everything else the tokenizer raises is
#: terminal: the buffer is handed to the reader, whose error the loop prints
#: and survives.
_CONTINUABLE_READ_ERRORS = ("unterminated", "nothing follows #\\")


def _complete(source: str) -> bool:
    """True when *source* holds whole forms the reader can accept.

    Paren balance is the frame; the tokenizer's own errors refine it. An
    unterminated string, ``|symbol|``, or block comment — or a ``#\\`` still
    waiting for its character — keeps the form open, exactly like an
    unbalanced ``(``. A terminal reader error (``#\\zzz``, a bad ``\\x``
    escape) can never be repaired by more input, so the buffer is declared
    complete and handed to the reader, whose message comes back as an
    ``error:`` line instead of a traceback.
    """
    depth = 0
    try:
        for token in tokenize(source):
            if token == "(":
                depth += 1
            elif token == ")":
                depth -= 1
    except LispSyntaxError as exc:
        return not str(exc).startswith(_CONTINUABLE_READ_ERRORS)
    return depth <= 0


class Repl:
    """Line-oriented REPL over a single persistent environment."""

    def __init__(
        self,
        env: Optional[Environment] = None,
        out: Optional[TextIO] = None,
        prompt: str = "lisp> ",
        banner: bool = True,
        history_file: Optional[str] = None,
    ) -> None:
        self.out = out if out is not None else sys.stdout
        self.env = env if env is not None else make_env(out=self.out)
        self.prompt = prompt
        self.banner = banner
        self.history_file = history_file
        self._history: list[str] = []
        self._load_history()
        self._install_readline_history()

    def _load_history(self) -> None:
        p = self.history_file
        if p is None:
            try:
                p = str(Path.home() / ".shs_history")
            except Exception:
                return
            self.history_file = p
        try:
            path = Path(p)
            if path.is_file():
                self._history = path.read_text(encoding="utf-8").splitlines()[-500:]
        except Exception:
            pass

    def _save_history(self) -> None:
        if self.history_file is None:
            return
        try:
            Path(self.history_file).write_text(
                "\n".join(self._history[-500:]) + ("\n" if self._history else ""),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _install_readline_history(self) -> None:
        try:
            import readline  # type: ignore
        except Exception:
            return
        try:
            history_file = self.history_file
            if history_file and Path(history_file).is_file():
                readline.read_history_file(history_file)
            # No custom completer — readline history is the win here; keep
            # it optional so non-interactive embedding is unaffected.
        except Exception:
            pass

    def _remember(self, line: str) -> None:
        if line.strip() and line not in self._history[-1:]:
            self._history.append(line)

    def eval_source(self, source: str) -> List[str]:
        """Evaluate every form in *source*; return each value as text."""
        return [
            to_string(evaluate(form, self.env), write=False)
            for form in read_all(source)
        ]

    def _echo(self, source: str) -> None:
        """Evaluate every form in *source*; print each value — or the error."""
        try:
            for text in self.eval_source(source):
                self.out.write(text + "\n")
        except LispError as exc:
            self.out.write(f"error: {exc}\n")
        except ContinuationJump:
            # A continuation captured in an earlier form has no call/cc left
            # to return to; the jump ends here as an error, not a dead REPL.
            self.out.write("error: continuation invoked outside its extent\n")
        except KeyboardInterrupt:  # pragma: no cover - interactive only
            self.out.write("\n")

    def _drain(self, buffer: str) -> None:
        """EOF with an unfinished form: report it instead of dropping it."""
        if buffer.strip():
            self._echo(buffer)

    def run(self, in_stream: Optional[TextIO] = None) -> int:
        in_stream = in_stream if in_stream is not None else sys.stdin
        if self.banner:
            self.out.write(BANNER + "\n")
        buffer = ""
        while True:
            try:
                self.out.write(self.prompt if not buffer else "  ... ")
                self.out.flush()
                line = in_stream.readline()
            except KeyboardInterrupt:  # pragma: no cover - interactive only
                # Ctrl+C at the prompt starts a fresh form, it does not kill
                # the session.
                self.out.write("\n")
                buffer = ""
                continue
            if not line:  # EOF
                self.out.write("\n")
                self._drain(buffer)
                return 0
            if not buffer:
                stripped = line.strip()
                if stripped.startswith(","):
                    if self._command(stripped):
                        return 0
                    continue
                if stripped in ("quit", "exit"):
                    return 0
            self._remember(line)
            buffer += line
            if not _complete(buffer):
                continue
            source, buffer = buffer, ""
            self._echo(source)
            self._save_history()

    def _command(self, line: str) -> bool:
        """Run a ``,command``; return True to leave the REPL."""
        parts = line[1:].split(None, 1)
        name = parts[0] if parts else ""
        arg = parts[1].strip() if len(parts) > 1 else ""
        if name in ("q", "quit", "exit"):
            return True
        if name in ("h", "help", "?"):
            self.out.write(HELP)
        elif name == "load":
            if not arg:
                self.out.write("usage: ,load PATH\n")
            else:
                try:
                    load_file(self.env, arg)
                    self.out.write(f"loaded {arg}\n")
                except (LispError, OSError) as exc:
                    self.out.write(f"error: {exc}\n")
        else:
            self.out.write(f"unknown command ,{name}  (try ,help)\n")
        return False


def run_repl(
    install_tetris: bool = False,
    out: Optional[TextIO] = None,
    in_stream: Optional[TextIO] = None,
    search_paths: Iterable[Any] = (),
    profile: Optional[str] = "dsl",
) -> int:
    """Build an environment and hand it to a :class:`Repl`.

    *install_tetris* defaults to ``False`` — opt-in (H6) — so the REPL is a
    plain Scheme unless explicitly given a host edition.
    *search_paths* let a host put its own library directory in front of the
    working directory. *profile* selects the pre-imported SRFI layer (see
    :func:`shslisp.runtime.make_env`).
    """
    env = make_env(
        install_tetris=install_tetris,
        out=out,
        search_paths=search_paths,
        profile=profile,
    )
    return Repl(env=env, out=out).run(in_stream=in_stream)

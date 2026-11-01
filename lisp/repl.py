"""A read-eval-print loop, and the file runner the CLI leans on.

The REPL is deliberately thin. It only has to solve one problem a plain
``eval`` does not: knowing when a form is *finished*. It reads lines until the
parentheses balance, then evaluates — so a ``define`` can be typed across as
many lines as it takes, which is what makes a Lisp REPL worth having.
"""
from __future__ import annotations

import sys
from typing import Any, Iterable, List, Optional, TextIO

from .env import Environment
from .errors import LispError
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
  (chain 5 (_ * 2) (_ + 1))        ; SRFI 197 — threading pipelines

  (load "my-library")              ; .scm files on the search path
"""


def _balanced(source: str) -> bool:
    """True when every ``(`` has a partner — comments and strings excluded."""
    depth = 0
    for token in tokenize(source):
        if token == "(":
            depth += 1
        elif token == ")":
            depth -= 1
    return depth <= 0


class Repl:
    """Line-oriented REPL over a single persistent environment."""

    def __init__(
        self,
        env: Optional[Environment] = None,
        out: Optional[TextIO] = None,
        prompt: str = "lisp> ",
        banner: bool = True,
    ) -> None:
        self.out = out if out is not None else sys.stdout
        self.env = env if env is not None else make_env(out=self.out)
        self.prompt = prompt
        self.banner = banner

    def eval_source(self, source: str) -> List[str]:
        """Evaluate every form in *source*; return each value as text."""
        return [
            to_string(evaluate(form, self.env), write=False)
            for form in read_all(source)
        ]

    def run(self, in_stream: Optional[TextIO] = None) -> int:
        in_stream = in_stream if in_stream is not None else sys.stdin
        if self.banner:
            self.out.write(BANNER + "\n")
        buffer = ""
        while True:
            self.out.write(self.prompt if not buffer else "  ... ")
            self.out.flush()
            line = in_stream.readline()
            if not line:  # EOF
                self.out.write("\n")
                return 0
            if not buffer:
                stripped = line.strip()
                if stripped.startswith(","):
                    if self._command(stripped):
                        return 0
                    continue
                if stripped in ("quit", "exit"):
                    return 0
            buffer += line
            if not _balanced(buffer):
                continue
            source, buffer = buffer, ""
            try:
                for text in self.eval_source(source):
                    self.out.write(text + "\n")
            except LispError as exc:
                self.out.write(f"error: {exc}\n")
            except KeyboardInterrupt:  # pragma: no cover - interactive only
                self.out.write("\n")
                buffer = ""

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
    install_tetris: Optional[bool] = None,
    out: Optional[TextIO] = None,
    in_stream: Optional[TextIO] = None,
    search_paths: Iterable[Any] = (),
    profile: Optional[str] = "dsl",
) -> int:
    """Build an environment and hand it to a :class:`Repl`.

    *install_tetris* defaults to ``None`` — *auto* — so the REPL carries the
    game when a host edition is installed and is a plain Scheme anywhere else.
    *search_paths* let a host put its own library directory in front of the
    working directory. *profile* selects the pre-imported SRFI layer (see
    :func:`lisp.runtime.make_env`).
    """
    env = make_env(
        install_tetris=install_tetris,
        out=out,
        search_paths=search_paths,
        profile=profile,
    )
    return Repl(env=env, out=out).run(in_stream=in_stream)

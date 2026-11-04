"""The REPL under hostile input.

A REPL's whole job is to survive its user: every form typed with a mistake in
it must come back as an ``error:`` line with the loop still standing. These
tests drive :class:`lisp.repl.Repl` with the inputs that once crashed it — an
unterminated string escaping the balance check, a terminal reader error
reaching the loop unguarded, a continuation invoked after its ``call/cc`` was
gone — and pin the recoveries: multi-line strings complete, bad input is
reported, and the prompt returns.
"""
from __future__ import annotations

import io

from lisp.repl import Repl, _complete
from lisp.runtime import make_env


def drive(*lines: str) -> tuple[int, str]:
    """Run a session over the given lines; answer with (exit code, output)."""
    out = io.StringIO()
    repl = Repl(env=make_env(out=out), out=out, banner=False)
    rc = repl.run(in_stream=io.StringIO("".join(line + "\n" for line in lines)))
    return rc, out.getvalue()


# --------------------------------------------------------------------------- #
#  The completion check                                                        #
# --------------------------------------------------------------------------- #

def test_incomplete_forms_ask_for_another_line() -> None:
    assert not _complete("(+ 1")            # open paren
    assert not _complete('"abc')            # open string
    assert not _complete("|quo")            # open |quoted symbol|
    assert not _complete("#| comment")      # open block comment
    assert not _complete("#\\")             # a char literal waiting for its char


def test_complete_forms_evaluate() -> None:
    assert _complete("(+ 1 2)")
    assert _complete('"abc"')
    assert _complete("")                    # nothing pending


def test_a_stray_close_paren_is_complete_so_the_reader_can_report_it() -> None:
    # depth <= 0 is "complete": the error belongs to the reader's message.
    assert _complete(")")


def test_a_terminal_reader_error_is_complete_so_the_reader_can_report_it() -> None:
    # No amount of further typing repairs #\zzz; waiting would hang the prompt.
    assert _complete("(list #\\zzz)")


# --------------------------------------------------------------------------- #
#  Sessions that must survive                                                  #
# --------------------------------------------------------------------------- #

def test_a_multi_line_string_completes() -> None:
    rc, out = drive('(string-append "ab', 'cd")', "(+ 1 2)")
    assert rc == 0
    assert "ab\ncd" in out
    assert "3" in out


def test_an_unterminated_string_at_eof_is_reported_not_dropped() -> None:
    rc, out = drive('(display "hello')
    assert rc == 0
    assert "error: unterminated string literal" in out


def test_an_unbalanced_form_at_eof_is_reported_not_dropped() -> None:
    rc, out = drive("(+ 1")
    assert rc == 0
    assert "error:" in out


def test_a_stray_paren_is_an_error_and_the_loop_goes_on() -> None:
    rc, out = drive(")", "(+ 3 4)")
    assert rc == 0
    assert "error: unexpected )" in out
    assert "7" in out


def test_a_terminal_reader_error_is_an_error_and_the_loop_goes_on() -> None:
    rc, out = drive("(list #\\zzz)", "(+ 1 2)")
    assert rc == 0
    assert "error: unknown character name" in out
    assert "3" in out


def test_a_char_literal_on_one_line_still_reads_normally() -> None:
    rc, out = drive("(char? #\\a)")
    assert rc == 0
    assert "#t" in out
    assert "error:" not in out


def test_a_char_literal_may_not_swallow_the_line_break() -> None:
    # ``#\`` followed by Enter used to read the newline as the character.
    rc, out = drive("(list #\\", "a)")
    assert rc == 0
    assert "error:" in out


def test_a_stale_continuation_is_an_error_and_the_loop_goes_on() -> None:
    rc, out = drive(
        "(define k #f)",
        "(call/cc (lambda (c) (set! k c) 1))",
        "(k 99)",
        "(+ 1 2)",
    )
    assert rc == 0
    assert "1" in out                                    # the normal return
    assert "error: continuation invoked outside its extent" in out
    assert "3" in out                                    # still standing


def test_a_bad_number_literal_is_an_error_and_the_loop_goes_on() -> None:
    rc, out = drive("1/0", "(+ 1 2)")
    assert rc == 0
    assert "error: bad number literal: 1/0" in out
    assert "3" in out


def test_a_failed_load_is_an_error_and_the_loop_goes_on() -> None:
    rc, out = drive(",load no-such-library.scm", "(+ 1 2)")
    assert rc == 0
    assert "error:" in out
    assert "3" in out


def test_ctrl_c_at_the_prompt_starts_a_fresh_form() -> None:
    out = io.StringIO()
    repl = Repl(env=make_env(out=out), out=out, banner=False)

    class Jumpy(io.StringIO):
        """A stream whose first readline is a Ctrl+C, like a console's."""

        raised = False

        def readline(self) -> str:
            if not self.raised:
                self.raised = True
                raise KeyboardInterrupt
            return super().readline()

    rc = repl.run(in_stream=Jumpy("(+ 1 2)\n"))
    assert rc == 0
    assert "3" in out.getvalue()

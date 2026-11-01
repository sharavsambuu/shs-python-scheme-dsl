"""Ports and the host hooks: string and file I/O, the current ports, the clock.

The lesson these pin down is that the *mechanism* (read/write on a port object)
lives in Python, while the *policy* (which port is current, and how it is
rebound) lives in the prelude — so redirecting `display` is `parameterize`, not
a special case of the printer.
"""
from __future__ import annotations

import pytest

from lisp import run
from lisp.errors import LispError, LispTypeError


# --------------------------------------------------------------------------- #
#  String ports                                                                 #
# --------------------------------------------------------------------------- #

def test_an_output_string_port_collects_what_is_written(ev) -> None:
    ev("(define p (open-output-string))")
    ev('(display "hi " p)')
    ev("(write 3.5 p)")
    assert ev("(get-output-string p)") == "hi 3.5"


def test_write_string_and_write_char_take_a_port(ev) -> None:
    ev("(define p (open-output-string))")
    ev('(write-string "abc" p)')
    ev("(write-char #\\! p)")
    assert ev("(get-output-string p)") == "abc!"


def test_an_input_string_port_reads_characters(ev) -> None:
    ev('(define p (open-input-string "abc"))')
    assert ev("(char=? (read-char p) #\\a)") is True
    assert ev("(char=? (read-char p) #\\b)") is True
    assert ev("(char=? (peek-char p) #\\c)") is True  # peek does not consume
    assert ev("(char=? (read-char p) #\\c)") is True
    assert ev("(eof-object? (read-char p))") is True


def test_read_line_strips_the_terminator_and_then_eofs(ev) -> None:
    ev('(define p (open-input-string "one\\ntwo\\n"))')
    assert ev("(read-line p)") == "one"
    assert ev("(read-line p)") == "two"
    assert ev("(eof-object? (read-line p))") is True


def test_ports_predicates_distinguish_direction(ev) -> None:
    ev("(define out (open-output-string))")
    ev('(define in (open-input-string ""))')
    assert ev("(port? out)") is True
    assert ev("(output-port? out)") is True
    assert ev("(input-port? out)") is False
    assert ev("(input-port? in)") is True
    assert ev("(port? 3)") is False


def test_a_port_prints_as_an_opaque_handle(ev) -> None:
    ev("(define p (open-output-string))")
    assert ev("(write-to-string p)") == "#<output-port <string>>"


def test_writing_to_an_input_port_is_refused(ev) -> None:
    ev('(define p (open-input-string ""))')
    with pytest.raises(LispTypeError, match="not an output port"):
        ev('(write-string "x" p)')


def test_using_a_closed_port_is_refused(ev) -> None:
    ev("(define p (open-output-string))")
    ev("(close-port p)")
    with pytest.raises(LispTypeError, match="is closed"):
        ev('(write-string "x" p)')


# --------------------------------------------------------------------------- #
#  The current-port parameters and redirection                                  #
# --------------------------------------------------------------------------- #

def test_parameterize_redirects_display(ev) -> None:
    ev("(define scratch (open-output-string))")
    ev('(parameterize ((current-output-port scratch)) (display "redirected"))')
    assert ev("(get-output-string scratch)") == "redirected"


def test_display_defaults_back_to_the_standard_port(buffered_env) -> None:
    # No explicit port and no parameterize: `display` writes to the standard
    # output port, which the fixture has pointed at its buffer.
    env, buffer = buffered_env
    run('(display "to-stdout")', env)
    run("(newline)", env)
    assert buffer.getvalue() == "to-stdout\n"


# --------------------------------------------------------------------------- #
#  File I/O                                                                     #
# --------------------------------------------------------------------------- #

def test_with_output_to_file_writes_and_closes(ev, tmp_path) -> None:
    path = tmp_path / "note.txt"
    ev(f'(with-output-to-file "{path}" (lambda () (display "hello") (newline)))')
    assert path.read_text() == "hello\n"


def test_call_with_output_file_exposes_the_port(ev, tmp_path) -> None:
    path = tmp_path / "two.txt"
    ev(f'(call-with-output-file "{path}" (lambda (p) (write-string "x" p)))')
    assert path.read_text() == "x"


def test_with_input_from_file_reads_lines(ev, tmp_path) -> None:
    path = tmp_path / "read.txt"
    path.write_text("alpha\nbeta\n")
    ev(f"(define seen '())")
    ev(
        f'(with-input-from-file "{path}"'
        " (lambda () (set! seen (list (read-line) (read-line)))))"
    )
    assert ev("seen") == ["alpha", "beta"]


def test_call_with_input_file_exposes_the_port(ev, tmp_path) -> None:
    path = tmp_path / "one.txt"
    path.write_text("Q")
    ev(f'(define c (call-with-input-file "{path}" (lambda (p) (read-char p))))')
    assert ev("(char=? c #\\Q)") is True


def test_opening_a_missing_file_names_the_failure(ev, tmp_path) -> None:
    missing = tmp_path / "nope.txt"
    with pytest.raises(LispError, match="open-input-file"):
        ev(f'(open-input-file "{missing}")')


def test_a_file_port_closes_on_an_exception(ev, tmp_path) -> None:
    path = tmp_path / "boom.txt"
    ev(
        f'(define nope (guard (e (#t (string-append "caught "'
        f' (error-object-message e))))'
        f' (call-with-output-file "{path}" (lambda (p) (error "boom")))))'
    )
    assert ev("nope").startswith("caught ")
    # The port was closed by the after-thunk even though the body raised, so the
    # file exists and is complete.
    assert path.exists()


# --------------------------------------------------------------------------- #
#  The environment and the clock                                                #
# --------------------------------------------------------------------------- #

def test_command_line_is_a_list_of_strings(ev) -> None:
    argv = ev("(command-line)")
    assert isinstance(argv, list) and argv
    assert all(isinstance(item, str) for item in argv)


def test_environment_variables_are_readable(ev, monkeypatch) -> None:
    monkeypatch.setenv("LISPPY_TEST_VAR", "42")
    assert ev('(get-environment-variable "LISPPY_TEST_VAR")') == "42"
    assert ev('(get-environment-variable "LISPPY_ABSENT_VAR")') is False
    entries = ev("(get-environment-variables)")
    assert ["LISPPY_TEST_VAR", "42"] in entries


def test_the_clock_answers_in_seconds_and_jiffies(ev) -> None:
    assert isinstance(ev("(current-second)"), float)
    assert isinstance(ev("(current-jiffy)"), int)
    assert ev("(jiffies-per-second)") == 1_000_000_000


def test_exit_leaves_the_host_with_a_status(ev) -> None:
    with pytest.raises(SystemExit) as exit_info:
        ev("(exit 3)")
    assert exit_info.value.code == 3

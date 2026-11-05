"""The SRFI 19 time and date library — the trading layer's clock and calendar (S10).

``(srfi 19)`` is core-backed: Python primitives over the stdlib's clock and
proleptic Gregorian calendar, registered in ``shslisp/builtins.py`` and
scoped by the library entry in ``shslisp/library.py``. What is pinned here:

* **the types** — ``time-utc``/``time-monotonic``/``time-process``/``time-duration``
  and the immutable ``date``, with SRFI 19's accessors;
* **the conversions** — ``time-utc->date``/``date->time-utc``, the Julian Day
  family (pinned against the known value for 2000-01-01T12:00Z), and the
  ``date->string``/``string->date`` round trip through the ``~`` directives;
* **the deviations, loudly** — no TAI or thread clocks, no leap seconds, and
  comparisons that refuse mixed types.

The plan this implements is S10 in ``docs/SRFI_TASKS.md``; the matrix row is
in ``docs/srfi.md``.
"""
from __future__ import annotations

import pytest

from shslisp.errors import LispError, LispTypeError
from shslisp.evaluator import evaluate_program
from shslisp.reader import read_all
from shslisp.runtime import make_env
from shslisp.types import intern


def run(env, source: str):
    return evaluate_program(read_all(source), env)


@pytest.fixture
def env():
    return make_env(install_tetris=False)


@pytest.fixture
def ev(env):
    return lambda source: run(env, source)


# --------------------------------------------------------------------------- #
#  The types and their accessors                                              #
# --------------------------------------------------------------------------- #


def test_a_time_is_a_time_and_the_accessors_answer(ev) -> None:
    assert ev("(time? (current-time 'time-utc))") is True
    assert ev("(time? 5)") is False
    assert ev("(time-type (make-time 'time-utc 250000000 1725000000))") == "time-utc"
    assert ev("(time-second (make-time 'time-utc 250000000 1725000000))") == 1725000000
    assert ev("(time-nanosecond (make-time 'time-utc 250000000 1725000000))") == 250000000
    assert ev("(time-second (copy-time (make-time 'time-utc 0 10)))") == 10


def test_current_time_answers_utc_by_default_and_monotonic_on_request(ev) -> None:
    assert ev("(time-type (current-time))") == "time-utc"
    assert ev("(time-type (current-time 'time-monotonic))") == "time-monotonic"
    assert ev("(time-type (current-time 'time-process))") == "time-process"
    # The wall clock is measured from the epoch, and the nanosecond field is
    # always the normalized 0..999999999 fraction.
    assert ev("(>= (time-second (current-time 'time-utc)) 0)") is True
    assert ev(
        "(let ((ns (time-nanosecond (current-time 'time-utc))))"
        "  (and (>= ns 0) (< ns 1000000000)))"
    ) is True


def test_time_resolution_is_a_positive_nanosecond_count(ev) -> None:
    resolution = ev("(time-resolution)")
    assert isinstance(resolution, int) and resolution >= 1


def test_set_time_bang_mutates_in_place(ev) -> None:
    ev("(define t (make-time 'time-utc 100 10))")
    ev("(set-time-second! t 42)")
    ev("(set-time-nanosecond! t 200)")
    ev("(set-time-type! t 'time-monotonic)")
    assert ev("(list (time-type t) (time-second t) (time-nanosecond t))") == [
        "time-monotonic", 42, 200,
    ]


# --------------------------------------------------------------------------- #
#  Comparisons and duration arithmetic                                        #
# --------------------------------------------------------------------------- #


def test_time_comparisons_are_fieldwise(ev) -> None:
    assert ev("(time=? (make-time 'time-utc 0 10) (make-time 'time-utc 0 10))") is True
    assert ev("(time<? (make-time 'time-utc 0 10) (make-time 'time-utc 500000000 10))") is True
    assert ev("(time<=? (make-time 'time-utc 0 10) (make-time 'time-utc 0 10))") is True
    assert ev("(time>? (make-time 'time-utc 0 11) (make-time 'time-utc 0 10))") is True
    assert ev("(time>=? (make-time 'time-utc 0 10) (make-time 'time-utc 0 11))") is False


def test_comparisons_refuse_mixed_types(ev) -> None:
    with pytest.raises(LispTypeError, match="share a type"):
        ev("(time=? (make-time 'time-utc 0 1) (make-time 'time-monotonic 0 1))")


def test_duration_arithmetic_composes_and_normalizes(ev) -> None:
    # 10.5 s minus 3 s is 7.5 s:
    ev("(define d (time-difference (make-time 'time-utc 500000000 10)"
    "                              (make-time 'time-utc 0 3)))")
    assert ev("(time-type d)") == "time-duration"
    assert ev("(time-second d)") == 7
    assert ev("(time-nanosecond d)") == 500000000
    # ...and 3 s minus 10.5 s is -7.5 s. The nanosecond field keeps the
    # spec's 0..999999999 invariant, so the sign lives on floored seconds:
    ev("(define n (time-difference (make-time 'time-utc 0 3)"
    "                              (make-time 'time-utc 500000000 10)))")
    assert ev("(time-second n)") == -8
    assert ev("(time-nanosecond n)") == 500000000
    # add/subtract keep the base's type and carry:
    assert ev(
        "(list (time-second (add-duration (make-time 'time-utc 0 100)"
        "                                  (make-time 'time-duration 500000000 1)))"
        "     (time-nanosecond (add-duration (make-time 'time-utc 0 100)"
        "                                    (make-time 'time-duration 500000000 1))))"
    ) == [101, 500000000]
    assert ev(
        "(time-second (subtract-duration (make-time 'time-utc 0 100)"
        "                                (make-time 'time-duration 0 3)))"
    ) == 97


def test_add_duration_refuses_a_non_duration(ev) -> None:
    with pytest.raises(LispTypeError, match="time-duration"):
        ev("(add-duration (make-time 'time-utc 0 1) (make-time 'time-utc 0 2))")


# --------------------------------------------------------------------------- #
#  Dates and the conversions                                                  #
# --------------------------------------------------------------------------- #


def test_make_date_and_the_accessors(ev) -> None:
    ev("(define d (make-date 123456789 17 42 21 5 11 2026 7200))")
    assert ev("(date-nanosecond d)") == 123456789
    assert ev("(date-second d)") == 17
    assert ev("(date-minute d)") == 42
    assert ev("(date-hour d)") == 21
    assert ev("(date-day d)") == 5
    assert ev("(date-month d)") == 11
    assert ev("(date-year d)") == 2026
    assert ev("(date-zone-offset d)") == 7200
    # 2026-11-05 is a Thursday (week-day 4, Sunday=0), day 309 of the year:
    assert ev("(date-week-day d)") == 4
    assert ev("(date-year-day d)") == 309


def test_make_date_refuses_an_unreal_day_and_a_leap_second(ev) -> None:
    with pytest.raises(LispTypeError, match="not a real day"):
        ev("(make-date 0 0 0 0 31 2 2026 0)")
    with pytest.raises(LispTypeError, match="second"):
        ev("(make-date 0 60 0 0 1 1 2026 0)")


def test_time_date_round_trip_at_zone_zero(ev) -> None:
    ev("(define d (make-date 123 17 42 21 5 11 2026 0))")
    assert ev("(equal? (time-utc->date (date->time-utc d) 0) d)") is True


def test_time_utc_to_date_honours_the_zone_offset(ev) -> None:
    # The same instant at +02:00 reads two hours later on the calendar.
    ev("(define t (make-time 'time-utc 0 1000000))")
    assert ev(
        "(= (date-hour (time-utc->date t 7200))"
        "  (modulo (+ (date-hour (time-utc->date t 0)) 2) 24))"
    ) is True


def test_julian_day_is_pinned_against_the_known_value(ev) -> None:
    # 2000-01-01T12:00:00Z is Julian Day 2451545.0 — the textbook value.
    assert ev("(date->julian-day (make-date 0 0 0 12 1 1 2000 0))") == 2451545.0
    assert ev("(date->julian-day (make-date 0 0 0 12 2 1 2000 0))") == 2451546.0
    # Modified Julian Day is Julian Day minus 2400000.5:
    assert ev(
        "(- (date->julian-day (make-date 0 0 0 12 1 1 2000 0))"
        "   (date->modified-julian-day (make-date 0 0 0 12 1 1 2000 0)))"
    ) == 2400000.5


def test_julian_day_round_trip(ev) -> None:
    ev("(define d (make-date 0 0 0 12 1 1 2000 0))")
    assert ev("(equal? (julian-day->date (date->julian-day d) 0) d)") is True
    assert ev("(equal? (modified-julian-day->date (date->modified-julian-day d) 0) d)") is True


# --------------------------------------------------------------------------- #
#  date->string / string->date                                                #
# --------------------------------------------------------------------------- #


def test_date_string_round_trip_through_the_iso_directives(ev) -> None:
    ev("(define d (make-date 0 17 42 21 5 11 2026 7200))")
    assert ev('(date->string d "~4")') == "2026-11-05T21:42:17+0200"
    assert ev(
        '(equal? (string->date (date->string d "~4") "~Y-~m-~dT~H:~M:~S~z") d)'
    ) is True


def test_date_string_directives(ev) -> None:
    ev("(define d (make-date 0 7 5 9 14 7 2000 -14400))")
    assert ev('(date->string d "~a ~b ~d ~H:~M:~S~z ~Y")') == "Fri Jul 14 09:05:07-0400 2000"
    assert ev('(date->string d "~D")') == "07/14/00"
    assert ev('(date->string d "~T")') == "09:05:07"
    assert ev('(date->string d "~1")') == "2000-07-14"
    assert ev('(date->string d "~p ~I")') == "AM 09"
    assert ev('(date->string d "~~")') == "~"
    # ~w answers the week-day digit as *text* inside the format string:
    assert ev('(date->string d "~w")') == "5"


def test_string_to_date_the_required_converters(ev) -> None:
    assert ev('(date-year (string->date "5 Nov 2026" "~d ~b ~Y"))') == 2026
    assert ev('(date-month (string->date "5 November 2026" "~d ~B ~Y"))') == 11
    assert ev('(date-day (string->date " 5" "~e"))') == 5
    assert ev('(date-hour (string->date " 9" "~k"))') == 9
    assert ev('(date-minute (string->date "42" "~M"))') == 42
    assert ev('(date-zone-offset (string->date "-0400" "~z"))') == -14400
    assert ev('(date-zone-offset (string->date "+0200" "~z"))') == 7200
    # Unset fields default to the documented defaults (1900-01-01, UTC):
    assert ev('(date-zone-offset (string->date "2026" "~Y"))') == 0
    assert ev('(date-month (string->date "2026" "~Y"))') == 1
    assert ev('(date-year (string->date "26" "~y"))') > 2000


def test_unknown_directives_fail_loudly(ev) -> None:
    with pytest.raises(LispError, match="not a supported directive"):
        ev('(date->string (current-date 0) "~V")')
    with pytest.raises(LispError, match="not a supported converter"):
        ev('(string->date "x" "~N")')


# --------------------------------------------------------------------------- #
#  The deviations, loudly, and the wiring                                     #
# --------------------------------------------------------------------------- #


def test_there_is_no_tai_clock_and_it_says_so(ev) -> None:
    with pytest.raises(LispError, match="time-tai"):
        ev("(current-time 'time-tai)")


def test_there_is_no_thread_clock(ev) -> None:
    with pytest.raises(LispError, match="time-thread"):
        ev("(current-time 'time-thread)")


def test_the_constants_exist_as_symbols(ev) -> None:
    assert ev("(symbol? time-tai)") is True
    assert ev("(eq? time-utc 'time-utc)") is True


def test_the_library_imports_and_binds(env) -> None:
    run(env, "(import (srfi 19))")
    assert env.find(intern("date->string")) is not None
    assert env.find(intern("string->date")) is not None


def test_the_default_profile_preimports_srfi_19() -> None:
    dsl = make_env(install_tetris=False)
    assert run(dsl, "(time? (current-time))") is True
    assert run(dsl, "(procedure? string->date)") is True


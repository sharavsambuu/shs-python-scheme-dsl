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


# --------------------------------------------------------------------------- #
#  The audit pass (S13): loud validation, and weeks that match the reference   #
# --------------------------------------------------------------------------- #

def test_string_to_date_validates_the_time_of_day_and_the_whole_input(ev) -> None:
    with pytest.raises(LispError, match="hour out of range"):
        ev('(string->date "99" "~H")')
    with pytest.raises(LispError, match="minute out of range"):
        ev('(string->date "99" "~M")')
    with pytest.raises(LispError, match="second out of range"):
        ev('(string->date "99" "~S")')
    # the whole input must match the template: trailing garbage is an error
    with pytest.raises(LispError, match="trailing character"):
        ev('(string->date "2026junk" "~Y")')
    # the readers are width-capped like the reference's, so concatenated
    # templates parse field by field
    d = ev('(string->date "20261105" "~Y~m~d")')
    assert (d.year, d.month, d.day) == (2026, 11, 5)


def test_time_resolution_validates_its_type_argument(ev) -> None:
    with pytest.raises(LispTypeError, match="not a time type"):
        ev("(time-resolution 'garbage)")
    with pytest.raises(LispTypeError, match="expected a symbol"):
        ev("(time-resolution 42)")
    assert isinstance(ev("(time-resolution 'time-utc)"), int)
    assert isinstance(ev("(time-resolution)"), int)


def test_the_julian_day_converters_demand_a_time_utc(ev) -> None:
    with pytest.raises(LispTypeError, match="expected a time-utc"):
        ev("(time-utc->julian-day (make-time 'time-duration 0 1))")
    with pytest.raises(LispTypeError, match="expected a time-utc"):
        ev("(time-utc->modified-julian-day (make-time 'time-monotonic 0 5))")


def test_week_numbers_match_the_srfi_19_reference(ev) -> None:
    # The reference's formula: quotient(year-day - days-before-first-week, 7),
    # the partial first week sharing week 0. 2026-01-01 is a Thursday.
    assert ev("(date-week-number (make-date 0 0 0 12 1 1 2026 0) 0)") == 0
    assert ev("(date-week-number (make-date 0 0 0 12 4 1 2026 0) 0)") == 0
    assert ev("(date-week-number (make-date 0 0 0 12 11 1 2026 0) 0)") == 1
    # ~U / ~W are zero-padded, and a partial first week bumps the numbering
    assert ev('(date->string (make-date 0 0 0 12 1 1 2026 0) "~U")') == "01"
    assert ev('(date->string (make-date 0 0 0 12 11 1 2026 0) "~U")') == "02"
    assert ev('(date->string (make-date 0 0 0 12 4 1 2026 0) "~W")') == "01"
    # a year starting on the week's own first day has no partial week:
    # 2023-01-01 was a Sunday
    assert ev('(date->string (make-date 0 0 0 12 1 1 2023 0) "~U")') == "00"


# --------------------------------------------------------------------------- #
#  Regression coverage beyond the S13 pins: template shapes, day boundaries,   #
#  zone spellings, week numbers across years, and every clock type             #
# --------------------------------------------------------------------------- #


def test_string_to_date_parses_every_supported_template_shape(ev) -> None:
    # Concatenated numeric fields: each reader stops at its width cap.
    d = ev('(string->date "20261105214217" "~Y~m~d~H~M~S")')
    assert (d.year, d.month, d.day, d.hour, d.minute, d.second) == (
        2026, 11, 5, 21, 42, 17,
    )
    # The same fields with literals between them.
    d = ev('(string->date "2026 11 05 21 42 17" "~Y ~m ~d ~H ~M ~S")')
    assert (d.year, d.month, d.day, d.hour, d.minute, d.second) == (
        2026, 11, 5, 21, 42, 17,
    )
    # The month-name and weekday converters, abbreviated and long.
    d = ev('(string->date "05 Nov 2026" "~d ~b ~Y")')
    assert (d.year, d.month, d.day) == (2026, 11, 5)
    d = ev('(string->date "Thursday, 05 November 2026" "~A, ~d ~B ~Y")')
    assert (d.year, d.month, d.day) == (2026, 11, 5)
    # ~e and ~k consume the reference's space padding.
    d = ev('(string->date " 5  9" "~e ~k")')
    assert (d.day, d.hour) == (5, 9)


def test_string_to_date_validates_real_days_and_time_of_day_boundaries(ev) -> None:
    for text, template, message in (
        ("2026-13-01", "~Y-~m-~d", "real day"),
        ("2026-00-01", "~Y-~m-~d", "real day"),
        ("2026-02-30", "~Y-~m-~d", "real day"),
        ("0000-01-01", "~Y-~m-~d", "real day"),
        ("24", "~H", "hour out of range"),
        ("60", "~M", "minute out of range"),
        ("60", "~S", "second out of range"),
    ):
        with pytest.raises(LispError, match=message):
            ev(f'(string->date "{text}" "{template}")')
    # The boundaries themselves are legal, including a leap day.
    d = ev('(string->date "2026-12-31 23:59:59" "~Y-~m-~d ~H:~M:~S")')
    assert (d.day, d.hour, d.minute, d.second) == (31, 23, 59, 59)
    d = ev('(string->date "2024-02-29" "~Y-~m-~d")')
    assert (d.year, d.month, d.day) == (2024, 2, 29)


def test_string_to_date_reads_every_supported_zone_spelling(ev) -> None:
    for text, expected in (
        ("+0200", 7200), ("-0400", -14400),
        ("+02:00", 7200), ("-01:30", -5400),
        ("Z", 0), ("z", 0), ("UTC", 0), ("GMT", 0),
    ):
        assert ev(f'(date-zone-offset (string->date "{text}" "~z"))') == expected


def test_string_to_date_rejects_missing_literals_digits_and_trailing_input(ev) -> None:
    with pytest.raises(LispError, match="trailing character"):
        ev('(string->date "+0200junk" "~z")')
    with pytest.raises(LispError, match="expected 'T'"):
        ev('(string->date "2026-01-01x" "~Y-~m-~dT")')
    with pytest.raises(LispError, match="expected digits"):
        ev('(string->date "x" "~d")')


def test_date_week_numbers_across_years_start_days_and_leap_day(ev) -> None:
    # The SRFI 19 reference formula: quotient(year-day - partial-first-week, 7).
    # Values computed from the reference's tm:days-before-first-week /
    # tm:week-day pair, over several years and start days.
    week_cases = (
        ((2023, 1, 1), 0, 0),
        ((2024, 1, 1), 0, 0),   # Monday: start=0 leaves a partial week
        ((2024, 1, 1), 1, 0),
        ((2025, 1, 1), 3, 0),
        ((2026, 1, 1), 4, 0),
        ((2027, 1, 1), 5, 0),
        ((2024, 2, 29), 0, 7),  # leap day
        ((2024, 12, 31), 0, 51),
        ((2024, 12, 31), 2, 52),
        ((2026, 1, 11), 0, 1),
        ((2026, 1, 11), 2, 0),
    )
    for (year, month, day), start, week in week_cases:
        date_src = f"(make-date 0 0 0 12 {day} {month} {year} 0)"
        assert ev(f"(date-week-number {date_src} {start})") == week
    # ~U is the Sunday-start week number, padded to two digits and bumped by
    # one when the year opens with a partial week (the reference's rule).
    u_cases = (
        ((2023, 1, 1), "00"), ((2024, 1, 1), "01"),
        ((2025, 1, 1), "01"), ((2026, 1, 1), "01"),
        ((2027, 1, 1), "01"), ((2024, 2, 29), "08"),
        ((2024, 12, 31), "52"), ((2026, 1, 11), "02"),
    )
    for (year, month, day), utext in u_cases:
        date_src = f"(make-date 0 0 0 12 {day} {month} {year} 0)"
        assert ev(f'(date->string {date_src} "~U")') == utext
    # ~W is the Monday-start sibling with its own padding/bump.
    w_cases = (
        ((2024, 1, 1), "00"), ((2023, 1, 1), "01"),
        ((2025, 1, 1), "01"), ((2024, 12, 31), "52"),
    )
    for (year, month, day), wtext in w_cases:
        date_src = f"(make-date 0 0 0 12 {day} {month} {year} 0)"
        assert ev(f'(date->string {date_src} "~W")') == wtext
    # The start day is a 0..6 field, checked like any other index.
    for start in (-1, 7):
        with pytest.raises(LispTypeError, match="must be 0..6"):
            ev(f"(date-week-number (make-date 0 0 0 12 1 1 2026 0) {start})")


def test_time_resolution_and_julian_converters_check_their_types(ev) -> None:
    # Every clock type is accepted; a duration is not a clock.
    for type_name in (
        "time-utc", "time-monotonic", "time-process", "time-tai", "time-thread",
    ):
        assert isinstance(ev(f"(time-resolution '{type_name})"), int)
    with pytest.raises(LispTypeError, match="not a clock"):
        ev("(time-resolution 'time-duration)")
    with pytest.raises(LispTypeError, match="not a clock"):
        ev("(current-time 'time-duration)")
    # The Julian converters accept time-utc, and refuse every other time type.
    assert ev("(time-utc->julian-day (make-time 'time-utc 0 0))") == 2440587.5
    assert ev(
        "(time-utc->modified-julian-day (make-time 'time-utc 0 0))"
    ) == 40587.0
    for type_name in ("time-duration", "time-monotonic", "time-process", "time-tai"):
        with pytest.raises(LispTypeError, match="expected a time-utc"):
            ev(f"(time-utc->julian-day (make-time '{type_name} 0 1))")
        with pytest.raises(LispTypeError, match="expected a time-utc"):
            ev(f"(time-utc->modified-julian-day (make-time '{type_name} 0 1))")
    # A boolean is not a real Julian Day, even though Python bool is an int.
    with pytest.raises(LispTypeError, match="real Julian Day"):
        ev("(julian-day->time-utc #t)")



# --------------------------------------------------------------------------- #
#  The second audit pass: Julian overflow leaks, strict names, ~z shape, and   #
#  the reference's default date->string format.                               #
# --------------------------------------------------------------------------- #


def test_julian_day_converters_reject_non_finite_values_loudly(ev) -> None:
    for source in (
        "(julian-day->time-utc +inf.0)",
        "(julian-day->time-utc -inf.0)",
        "(julian-day->time-utc +nan.0)",
        "(julian-day->date +inf.0 0)",
        "(modified-julian-day->date -inf.0 0)",
    ):
        with pytest.raises(LispTypeError, match="finite Julian Day"):
            ev(source)
    # A finite value too large for float arithmetic is still a Lisp error.
    with pytest.raises(LispTypeError, match="out of range"):
        ev("(julian-day->time-utc 1e308)")
    with pytest.raises(LispTypeError, match="date out of range"):
        ev("(julian-day->date 1e300 0)")
    with pytest.raises(LispTypeError, match="date out of range"):
        ev("(modified-julian-day->date -1e300 0)")


def test_date_conversions_never_leak_host_overflow(ev) -> None:
    # Huge seconds and huge zone offsets reach datetime's limits; the
    # boundary must translate that into a Lisp type error, not OverflowError.
    for source in (
        "(time-utc->date (make-time 'time-utc 0 (expt 10 30)))",
        "(time-utc->date (make-time 'time-utc 0 0) (expt 10 30))",
        "(current-date (expt 10 30))",
        "(julian-day->date 1e300 0)",
    ):
        with pytest.raises(LispTypeError, match="date out of range"):
            ev(source)
    with pytest.raises(LispTypeError, match="julian day out of range"):
        ev("(time-utc->julian-day (make-time 'time-utc 0 (expt 10 400)))")


def test_date_string_defaults_to_the_reference_locale_format(ev) -> None:
    # SRFI 19's date->string defaults to ~c ("~a ~b ~d ~H:~M:~S~z ~Y").
    assert ev("(date->string (make-date 0 7 5 9 14 7 2000 -14400))") == (
        "Fri Jul 14 09:05:07-0400 2000"
    )
    assert ev("(date->string (make-date 0 0 0 12 1 1 2026 0))") == (
        "Thu Jan 01 12:00:00Z 2026"
    )
    # And ~z prints Z at offset zero, like the reference; it still parses.
    assert ev('(date->string (make-date 0 0 0 12 1 1 2026 0) "~z")') == "Z"
    assert ev('(date->string (make-date 0 0 0 12 1 1 2026 0) "~4")') == (
        "2026-01-01T12:00:00Z"
    )
    assert ev(
        '(date-zone-offset (string->date "2026-01-01T12:00:00Z"'
        ' "~Y-~m-~dT~H:~M:~S~z"))'
    ) == 0


def test_string_to_date_distinguishes_abbreviated_and_long_names(ev) -> None:
    assert ev('(date-month (string->date "5 Nov 2026" "~d ~b ~Y"))') == 11
    assert ev('(date-month (string->date "5 November 2026" "~d ~B ~Y"))') == 11
    # Exact names, case-insensitively; not prefixes, and not the wrong width.
    assert ev('(date-month (string->date "5 nov 2026" "~d ~b ~Y"))') == 11
    for text, template, message in (
        ("5 November 2026", "~d ~b ~Y", "abbreviated month"),
        ("5 Nov 2026", "~d ~B ~Y", "long month"),
        ("Thu", "~A", "unknown weekday"),
        ("Thursday", "~a", "unknown weekday"),
        ("Thurs", "~A", "unknown weekday"),
        ("", "~a", "expected a weekday"),
    ):
        with pytest.raises(LispError, match=message):
            ev(f'(string->date "{text}" "{template}")')


def test_string_to_date_zone_offsets_are_exactly_hhmm_or_hh_colon_mm(ev) -> None:
    for text, expected in (
        ("+0200", 7200), ("-0400", -14400),
        ("+02:00", 7200), ("-01:30", -5400), ("+00:00", 0),
    ):
        assert ev(f'(date-zone-offset (string->date "{text}" "~z"))') == expected
    # Three digits, a dangling colon, one digit, and overlong offsets are
    # all refused — the reference reads exactly four digits (or HH:MM).
    for text, message in (
        ("+020", "zone minute"),
        ("+02:0", "zone minute"),
        ("+0200:", "trailing character"),
        ("+02000", "trailing character"),
        ("+2", "zone hour"),
        ("+2400", "out of range"),
        ("+0260", "out of range"),
    ):
        with pytest.raises(LispError, match=message):
            ev(f'(date-zone-offset (string->date "{text}" "~z"))')


def test_date_string_year_is_four_digits(ev) -> None:
    # Table 1: ~Y is the year in four digits, zero-padded like the reference's
    # tm:padding — not Python's bare str(year).
    for year, text in ((1, "0001"), (42, "0042"), (999, "0999"), (2026, "2026")):
        assert ev(f'(date->string (make-date 0 0 0 0 1 1 {year} 0) "~Y")') == text

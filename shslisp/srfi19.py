"""``(srfi 19)`` — time and date, core-backed on the Python stdlib (S10).

The Gregorian machinery is exactly what ``datetime`` is for, so this library
is Python primitives registered in the core floor — the ``(srfi 88)`` way —
and the ``(srfi 19)`` library entry in :mod:`shslisp.library` only scopes the
names for the import/collision rules. ``docs/SRFI_TASKS.md`` (S10) is the
plan this implements.

**Deviations, decided up front and documented in** ``docs/srfi.md``:

* **No TAI.** ``time-tai`` exists as a constant symbol, but ``current-time``
  refuses it loudly — there is no leap-second table here, and pretending UTC
  seconds are TAI seconds would be a silent lie.
* **No ``time-thread``.** No thread clocks exist in this interpreter.
* **No leap seconds.** ``date-second`` is 0..59; a Python ``datetime`` cannot
  represent second 60.
* **No ``time-monotonic`` ↔ UTC conversions.** The monotonic clock is a
  stopwatch with an arbitrary origin — differences only.
* **Integer zone offsets only.** Offsets are SRFI 19's seconds **east** of
  UTC; there is no zone-name vocabulary in the core (a host publishes named
  zones through the seam if a strategy needs one).
* **C-locale English names** for ``date->string``/``string->date``, and the
  directive set is a documented subset of SRFI 19's tables.
"""

from __future__ import annotations

import math
import time as _time
from datetime import date as _date
from typing import Any

from .env import Environment
from .errors import LispArityError, LispError, LispTypeError
from .types import NIL, Primitive, Srfi19Date, Srfi19Time, Symbol, intern

__all__ = ["install", "format_date"]

#: The Julian Day of the Unix epoch (1970-01-01T00:00:00Z).
_JD_OF_EPOCH = 2440587.5

#: The Modified Julian Day offset: MJD = JD - 2400000.5.
_MJD_OFFSET = 2400000.5

#: The ordinal of 1970-01-01 in Python's proleptic Gregorian calendar.
_EPOCH_ORDINAL = _date(1970, 1, 1).toordinal()

#: The time-type symbols the spec names. ``time-duration`` is a duration, not
#: a clock; ``time-tai``/``time-thread`` exist as constants but no clock
#: answers them (the deviations above).
_TIME_TYPES = (
    "time-utc", "time-monotonic", "time-process",
    "time-tai", "time-thread", "time-duration",
)

#: C-locale names for the converters (the documented locale deviation).
_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
_WEEKDAYS = (
    "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
)


# --------------------------------------------------------------------------- #
#  Argument gates                                                              #
# --------------------------------------------------------------------------- #

def _expect_time(value: Any, who: str) -> Srfi19Time:
    if not isinstance(value, Srfi19Time):
        raise LispTypeError(f"{who}: expected a time, got {value!r}")
    return value


def _expect_date(value: Any, who: str) -> Srfi19Date:
    if not isinstance(value, Srfi19Date):
        raise LispTypeError(f"{who}: expected a date, got {value!r}")
    return value


def _expect_int(value: Any, who: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LispTypeError(f"{who}: expected an exact integer, got {value!r}")
    return value


def _expect_symbol(value: Any, who: str) -> str:
    if isinstance(value, Symbol):
        return str(value)
    raise LispTypeError(f"{who}: expected a symbol, got {value!r}")


def _expect_type_name(value: Any, who: str) -> str:
    name = _expect_symbol(value, who)
    if name not in _TIME_TYPES:
        raise LispTypeError(
            f"{who}: {name} is not a time type — expected one of "
            + ", ".join(_TIME_TYPES)
        )
    return name


# --------------------------------------------------------------------------- #
#  Epoch arithmetic — pure ordinal math, no OS calendar calls, any year        #
# --------------------------------------------------------------------------- #

def _sec_to_fields(second: int) -> tuple:
    """Epoch seconds -> ``(year, month, day, hour, minute, second)`` in UTC."""
    days, rem = divmod(second, 86400)
    day = _date.fromordinal(_EPOCH_ORDINAL + days)
    hour, rem = divmod(rem, 3600)
    minute, sec = divmod(rem, 60)
    return day.year, day.month, day.day, hour, minute, sec


def _fields_to_sec(year: int, month: int, day: int, hour: int, minute: int, sec: int) -> int:
    days = _date(year, month, day).toordinal() - _EPOCH_ORDINAL
    return days * 86400 + hour * 3600 + minute * 60 + sec


def _datetime_now_local():
    # A tiny indirection so the module imports no datetime.datetime name at
    # the top level — the local clock is only touched through the primitives.
    from datetime import datetime as _datetime

    return _datetime.now().astimezone()


def _local_offset() -> int:
    """The host zone's offset right now, in seconds east of UTC."""
    offset = _datetime_now_local().utcoffset()
    return int(offset.total_seconds()) if offset is not None else 0


def _time_from_ns(ns: int, type_name: str) -> Srfi19Time:
    second, nanosecond = divmod(ns, 1_000_000_000)
    return Srfi19Time(type_name, second, nanosecond)


def _normalize(total_ns: int) -> tuple:
    """Whole seconds and a 0..999,999,999 fraction; the sign lives on seconds."""
    return divmod(total_ns, 1_000_000_000)


def _utc_sec_to_date(second: int, nanosecond: int, zone_offset: int) -> Srfi19Date:
    year, month, day, hour, minute, sec = _sec_to_fields(second + zone_offset)
    return Srfi19Date(nanosecond, sec, minute, hour, day, month, year, zone_offset)


def _time_to_jd(t: Srfi19Time) -> float:
    return _JD_OF_EPOCH + (t.second + t.nanosecond / 1e9) / 86400.0


def _jd_to_time_utc(jd: float) -> Srfi19Time:
    total = (float(jd) - _JD_OF_EPOCH) * 86400.0
    second = math.floor(total)
    nanosecond = int(round((total - second) * 1e9))
    if nanosecond >= 1_000_000_000:
        second, nanosecond = second + 1, nanosecond - 1_000_000_000
    return Srfi19Time("time-utc", second, nanosecond)


# --------------------------------------------------------------------------- #
#  Current time and clock resolution                                           #
# --------------------------------------------------------------------------- #

def _current_time(*args: Any) -> Srfi19Time:
    if len(args) > 1:
        raise LispArityError("current-time", "at most 1", len(args))
    type_name = _expect_type_name(args[0], "current-time") if args else "time-utc"
    if type_name == "time-utc":
        return _time_from_ns(_time.time_ns(), type_name)
    if type_name == "time-monotonic":
        return _time_from_ns(_time.monotonic_ns(), type_name)
    if type_name == "time-process":
        return _time_from_ns(_time.process_time_ns(), type_name)
    if type_name in ("time-tai", "time-thread"):
        raise LispError(
            f"current-time: no {type_name} clock exists here — a documented "
            "(srfi 19) deviation (no TAI without a leap-second table, no "
            "thread clocks in this interpreter)"
        )
    raise LispTypeError(f"current-time: {type_name} is not a clock")


def _time_resolution(*args: Any) -> int:
    if len(args) > 1:
        raise LispArityError("time-resolution", "at most 1", len(args))
    # The wall clock's resolution, in nanoseconds — the host's own figure.
    info = _time.get_clock_info("time")
    return max(1, int(round(info.resolution * 1e9)))


# --------------------------------------------------------------------------- #
#  Time object, accessors, comparisons, arithmetic                             #
# --------------------------------------------------------------------------- #

def _make_time(type_name: Any, nanosecond: Any, second: Any) -> Srfi19Time:
    name = _expect_type_name(type_name, "make-time")
    ns = _expect_int(nanosecond, "make-time")
    sec = _expect_int(second, "make-time")
    if not 0 <= ns <= 999_999_999:
        raise LispTypeError(f"make-time: nanosecond must be 0..999999999, got {ns}")
    return Srfi19Time(name, sec, ns)


def _comparison(name: str, op: Any) -> Any:
    def fn(a: Any, b: Any) -> bool:
        ta, tb = _expect_time(a, name), _expect_time(b, name)
        if ta.type != tb.type:
            raise LispTypeError(
                f"{name}: the times must share a type ({ta.type} vs {tb.type})"
            )
        return op((ta.second, ta.nanosecond), (tb.second, tb.nanosecond))

    return fn


def _difference(mutate: bool) -> Any:
    def fn(t1: Any, t2: Any) -> Any:
        a, b = _expect_time(t1, "time-difference"), _expect_time(t2, "time-difference")
        if a.type != b.type:
            raise LispTypeError(
                f"time-difference: the times must share a type ({a.type} vs {b.type})"
            )
        second, nanosecond = _normalize(
            (a.second - b.second) * 1_000_000_000 + a.nanosecond - b.nanosecond
        )
        if mutate:
            a.type, a.second, a.nanosecond = "time-duration", second, nanosecond
            return a
        return Srfi19Time("time-duration", second, nanosecond)

    return fn


def _duration_arith(name: str, mutate: bool, sign: int) -> Any:
    def fn(t: Any, duration: Any) -> Any:
        base, dur = _expect_time(t, name), _expect_time(duration, name)
        if dur.type != "time-duration":
            raise LispTypeError(f"{name}: expected a time-duration, got a {dur.type}")
        total = (
            (base.second + sign * dur.second) * 1_000_000_000
            + base.nanosecond
            + sign * dur.nanosecond
        )
        second, nanosecond = _normalize(total)
        if mutate:
            base.second, base.nanosecond = second, nanosecond
            return base
        return Srfi19Time(base.type, second, nanosecond)

    return fn


def _copy_time(t: Any) -> Srfi19Time:
    checked = _expect_time(t, "copy-time")
    return Srfi19Time(checked.type, checked.second, checked.nanosecond)


# --------------------------------------------------------------------------- #
#  Dates                                                                       #
# --------------------------------------------------------------------------- #

def _current_date(*args: Any) -> Srfi19Date:
    if len(args) > 1:
        raise LispArityError("current-date", "at most 1", len(args))
    offset = _expect_int(args[0], "current-date") if args else _local_offset()
    second, nanosecond = divmod(_time.time_ns(), 1_000_000_000)
    return _utc_sec_to_date(second, nanosecond, offset)


def _make_date(*args: Any) -> Srfi19Date:
    if len(args) != 8:
        raise LispArityError("make-date", 8, len(args))
    ns = _expect_int(args[0], "make-date")
    sec = _expect_int(args[1], "make-date")
    minute = _expect_int(args[2], "make-date")
    hour = _expect_int(args[3], "make-date")
    day = _expect_int(args[4], "make-date")
    month = _expect_int(args[5], "make-date")
    year = _expect_int(args[6], "make-date")
    offset = _expect_int(args[7], "make-date")
    for value, low, high, what in (
        (ns, 0, 999_999_999, "nanosecond"), (sec, 0, 59, "second"),
        (minute, 0, 59, "minute"), (hour, 0, 23, "hour"),
        (day, 1, 31, "day"), (month, 1, 12, "month"),
    ):
        if not low <= value <= high:
            raise LispTypeError(f"make-date: {what} out of range: {value}")
    try:
        _date(year, month, day)
    except ValueError as exc:
        raise LispTypeError(
            f"make-date: not a real day: {year}-{month}-{day} ({exc})"
        ) from None
    return Srfi19Date(ns, sec, minute, hour, day, month, year, offset)


def _date_year_day(d: Srfi19Date) -> int:
    return _date(d.year, d.month, d.day).timetuple().tm_yday


def _date_week_day(d: Srfi19Date) -> int:
    # Python's weekday() is Monday=0; SRFI 19 wants Sunday=0.
    return (_date(d.year, d.month, d.day).weekday() + 1) % 7


def _date_week_number(*args: Any) -> int:
    if len(args) != 2:
        raise LispArityError("date-week-number", 2, len(args))
    d = _expect_date(args[0], "date-week-number")
    start = _expect_int(args[1], "date-week-number")
    if not 0 <= start <= 6:
        raise LispTypeError(
            f"date-week-number: day-of-week-starting-week must be 0..6, got {start}"
        )
    offset = (_date_week_day(d) - start) % 7
    return ((_date_year_day(d) - 1) + 7 - offset) // 7


def _date_to_time_utc(d: Srfi19Date) -> Srfi19Time:
    second = (
        _fields_to_sec(d.year, d.month, d.day, d.hour, d.minute, d.second)
        - d.zone_offset
    )
    return Srfi19Time("time-utc", second, d.nanosecond)


def _time_utc_to_date(*args: Any) -> Srfi19Date:
    if len(args) > 2:
        raise LispArityError("time-utc->date", "at most 2", len(args))
    t = _expect_time(args[0], "time-utc->date")
    if t.type != "time-utc":
        raise LispTypeError(f"time-utc->date: expected a time-utc, got a {t.type}")
    offset = _expect_int(args[1], "time-utc->date") if len(args) > 1 else _local_offset()
    return _utc_sec_to_date(t.second, t.nanosecond, offset)


# --------------------------------------------------------------------------- #
#  Julian Day / Modified Julian Day converters                                 #
# --------------------------------------------------------------------------- #

def _julian(name: str, from_time: bool, modified: bool) -> Any:
    def fn(value: Any) -> Any:
        if from_time:
            t = _expect_time(value, name)
        else:
            t = _date_to_time_utc(_expect_date(value, name))
        jd = _time_to_jd(t)
        return jd - _MJD_OFFSET if modified else jd

    return fn


def _jd_to(name: str, to_date: bool, modified: bool) -> Any:
    def fn(*args: Any) -> Any:
        if len(args) > 2:
            raise LispArityError(name, "at most 2", len(args))
        jd = args[0]
        if isinstance(jd, bool) or not isinstance(jd, (int, float)):
            raise LispTypeError(f"{name}: expected a real Julian Day, got {jd!r}")
        t = _jd_to_time_utc(float(jd) + (_MJD_OFFSET if modified else 0.0))
        if to_date:
            offset = _expect_int(args[1], name) if len(args) > 1 else _local_offset()
            return _utc_sec_to_date(t.second, t.nanosecond, offset)
        return t

    return fn


# --------------------------------------------------------------------------- #
#  date->string / string->date                                                 #
# --------------------------------------------------------------------------- #

def _week_day_abbrev(d: Srfi19Date) -> str:
    return _WEEKDAYS[_date_week_day(d)][:3]


def _month_abbrev(d: Srfi19Date) -> str:
    return _MONTHS[d.month - 1][:3]


def _zone_text(d: Srfi19Date) -> str:
    sign = "+" if d.zone_offset >= 0 else "-"
    total = abs(d.zone_offset)
    return f"{sign}{total // 3600:02d}{total % 3600 // 60:02d}"


def _h12(d: Srfi19Date) -> int:
    return d.hour % 12 or 12


def _directives(d: Srfi19Date) -> dict:
    """The supported ``date->string`` directives, as formatters."""
    return {
        "~": "~",
        "a": _week_day_abbrev(d),
        "A": _WEEKDAYS[_date_week_day(d)],
        "b": _month_abbrev(d),
        "B": _MONTHS[d.month - 1],
        "c": "~a ~b ~d ~H:~M:~S~z ~Y",
        "d": f"{d.day:02d}",
        "D": "~m/~d/~y",
        "e": f"{d.day:2d}",
        "h": _month_abbrev(d),
        "H": f"{d.hour:02d}",
        "I": f"{_h12(d):02d}",
        "j": f"{_date_year_day(d):03d}",
        "k": f"{d.hour:2d}",
        "l": f"{_h12(d):2d}",
        "m": f"{d.month:02d}",
        "M": f"{d.minute:02d}",
        "n": "\n",
        "N": f"{d.nanosecond:09d}",
        "p": "AM" if d.hour < 12 else "PM",
        "r": "~I:~M:~S ~p",
        "S": f"{d.second:02d}",
        "T": "~H:~M:~S",
        "U": str(_date_week_number(d, 0)),
        "w": str(_date_week_day(d)),
        "W": str(_date_week_number(d, 1)),
        "x": "~m/~d/~y",
        "X": "~H:~M:~S",
        "y": f"{d.year % 100:02d}",
        "Y": str(d.year),
        "z": _zone_text(d),
        "1": "~Y-~m-~d",
        "2": "~H:~M:~S~z",
        "3": "~H:~M:~S",
        "4": "~Y-~m-~dT~H:~M:~S~z",
        "5": "~Y-~m-~dT~H:~M:~S",
    }


def format_date(d: Srfi19Date, fmt: str) -> str:
    """Expand *fmt* over *d* — the ``date->string`` engine, exposed for tests."""
    directives = _directives(d)
    out: list = []
    i, n = 0, len(fmt)
    while i < n:
        if fmt[i] != "~":
            out.append(fmt[i])
            i += 1
            continue
        if i + 1 >= n:
            raise LispError("date->string: a trailing ~ has no directive")
        spec = fmt[i + 1]
        if spec not in directives:
            raise LispError(
                f"date->string: ~{spec} is not a supported directive — "
                "docs/srfi.md records the supported subset"
            )
        replacement = directives[spec]
        # A nested template (`~c`, `~T`, `~1`...) recurses; the literal `~~`
        # replacement is one tilde and must not.
        out.append(
            format_date(d, replacement)
            if len(replacement) > 1 and replacement.startswith("~")
            else replacement
        )
        i += 2
    return "".join(out)


def _date_to_string(*args: Any) -> str:
    if len(args) > 2:
        raise LispArityError("date->string", "at most 2", len(args))
    d = _expect_date(args[0], "date->string")
    if len(args) > 1:
        if not isinstance(args[1], str):
            raise LispTypeError("date->string: expected a format string")
        return format_date(d, args[1])
    return format_date(d, "~4")


_WEEKDAY_WORDS = tuple(word.lower() for word in _WEEKDAYS)
_MONTH_WORDS = tuple(word.lower() for word in _MONTHS)


def _parse_zone(text: str, pos: int) -> tuple:
    """``~z``: ``+HHMM``/``-HHMM``/``+HH:MM``/``Z``/``UTC``/``GMT``."""
    upper = text[pos:].upper()
    for word in ("UTC", "GMT", "UT"):
        if upper.startswith(word):
            return 0, pos + len(word)
    if pos < len(text) and text[pos] in "Zz":
        return 0, pos + 1
    if pos >= len(text) or text[pos] not in "+-":
        raise LispError("string->date: ~z expected a zone offset")
    sign = 1 if text[pos] == "+" else -1
    pos += 1
    digits = ""
    while pos < len(text) and (text[pos].isdigit() or text[pos] == ":"):
        digits += text[pos]
        pos += 1
    digits = digits.replace(":", "")
    if len(digits) < 3:
        raise LispError(f"string->date: ~z could not read a zone offset near {digits!r}")
    hours, minutes = int(digits[:-2]), int(digits[-2:])
    return sign * (hours * 3600 + minutes * 60), pos


def _string_to_date(*args: Any) -> Srfi19Date:
    if len(args) != 2:
        raise LispArityError("string->date", 2, len(args))
    text, template = args
    if not isinstance(text, str) or not isinstance(template, str):
        raise LispTypeError("string->date: expected two strings")
    # The unset fields' defaults are a documented deviation: 1900-01-01, UTC.
    fields = {
        "nanosecond": 0, "second": 0, "minute": 0, "hour": 0,
        "day": 1, "month": 1, "year": 1900, "zone_offset": 0,
    }
    pos, tpos, tlen = 0, 0, len(text)

    def skip_while(predicate: Any) -> None:
        nonlocal pos
        while pos < tlen and predicate(text[pos]):
            pos += 1

    def read_int() -> int:
        nonlocal pos
        start = pos
        skip_while(str.isdigit)
        if start == pos:
            raise LispError(f"string->date: expected digits at position {pos}")
        return int(text[start:pos])

    while tpos < len(template):
        ch = template[tpos]
        if ch != "~":
            if pos < tlen and text[pos] == ch:
                pos += 1
            else:
                raise LispError(
                    f"string->date: expected {ch!r} at position {pos} of the input"
                )
            tpos += 1
            continue
        if tpos + 1 >= len(template):
            raise LispError("string->date: a trailing ~ has no directive")
        spec = template[tpos + 1]
        tpos += 2
        if spec == "~":
            if pos < tlen and text[pos] == "~":
                pos += 1
            else:
                raise LispError("string->date: expected ~ in the input")
        elif spec in ("a", "A"):
            skip_while(str.isalpha)  # the weekday name sets nothing
        elif spec in ("b", "B", "h"):
            start = pos
            skip_while(str.isalpha)
            word = text[start:pos].lower()
            if not word:
                raise LispError("string->date: expected a month name")
            for index, name in enumerate(_MONTH_WORDS):
                if name.startswith(word):
                    fields["month"] = index + 1
                    break
            else:
                raise LispError(f"string->date: unknown month name {word!r}")
        elif spec in ("d", "e"):
            skip_while(str.isspace)
            fields["day"] = read_int()
        elif spec in ("H", "k"):
            skip_while(str.isspace)
            fields["hour"] = read_int()
        elif spec == "m":
            fields["month"] = read_int()
        elif spec == "M":
            fields["minute"] = read_int()
        elif spec == "S":
            fields["second"] = read_int()
        elif spec == "y":
            value = read_int()
            current = _datetime_now_local().year
            year = current // 100 * 100 + value
            if year > current + 50:
                year -= 100
            elif year < current - 50:
                year += 100
            fields["year"] = year
        elif spec == "Y":
            fields["year"] = read_int()
        elif spec == "z":
            offset, pos = _parse_zone(text, pos)
            fields["zone_offset"] = offset
        else:
            raise LispError(
                f"string->date: ~{spec} is not a supported converter — "
                "docs/srfi.md records the supported subset"
            )
    # Validate the assembled day loudly.
    try:
        _date(fields["year"], fields["month"], fields["day"])
    except ValueError as exc:
        raise LispError(f"string->date: the fields do not name a real day ({exc})") from None
    return Srfi19Date(**fields)


# --------------------------------------------------------------------------- #
#  Registration                                                                #
# --------------------------------------------------------------------------- #

def install(env: Environment) -> None:
    """Bind the ``(srfi 19)`` names into the core floor."""

    def define(name: str, fn: Any) -> None:
        env.define(intern(name), Primitive(name, fn))

    # The time-type constants are the symbols themselves — bound directly,
    # not wrapped: `(current-time time-utc)` evaluates `time-utc` to the symbol.
    for type_name in _TIME_TYPES:
        symbol = intern(type_name)
        env.define(symbol, symbol)

    define("current-time", _current_time)
    define("time-resolution", _time_resolution)
    define("make-time", _make_time)
    define("time?", lambda x: isinstance(x, Srfi19Time))
    define("time-type", lambda t: intern(_expect_time(t, "time-type").type))
    define("time-second", lambda t: _expect_time(t, "time-second").second)
    define("time-nanosecond", lambda t: _expect_time(t, "time-nanosecond").nanosecond)

    def _set_time_type(t: Any, type_name: Any) -> Any:
        _expect_time(t, "set-time-type!").type = _expect_type_name(
            type_name, "set-time-type!"
        )
        return NIL

    def _set_time_second(t: Any, second: Any) -> Any:
        _expect_time(t, "set-time-second!").second = _expect_int(
            second, "set-time-second!"
        )
        return NIL

    def _set_time_nanosecond(t: Any, ns: Any) -> Any:
        value = _expect_int(ns, "set-time-nanosecond!")
        if not 0 <= value <= 999_999_999:
            raise LispTypeError(
                f"set-time-nanosecond!: nanosecond must be 0..999999999, got {value}"
            )
        _expect_time(t, "set-time-nanosecond!").nanosecond = value
        return NIL

    define("set-time-type!", _set_time_type)
    define("set-time-second!", _set_time_second)
    define("set-time-nanosecond!", _set_time_nanosecond)
    define("copy-time", _copy_time)

    define("time=?", _comparison("time=?", lambda a, b: a == b))
    define("time<?", _comparison("time<?", lambda a, b: a < b))
    define("time>?", _comparison("time>?", lambda a, b: a > b))
    define("time<=?", _comparison("time<=?", lambda a, b: a <= b))
    define("time>=?", _comparison("time>=?", lambda a, b: a >= b))

    define("time-difference", _difference(mutate=False))
    define("time-difference!", _difference(mutate=True))
    define("add-duration", _duration_arith("add-duration", mutate=False, sign=1))
    define("add-duration!", _duration_arith("add-duration!", mutate=True, sign=1))
    define("subtract-duration", _duration_arith("subtract-duration", mutate=False, sign=-1))
    define("subtract-duration!", _duration_arith("subtract-duration!", mutate=True, sign=-1))

    define("current-date", _current_date)
    define("make-date", _make_date)
    define("date?", lambda x: isinstance(x, Srfi19Date))
    for field in ("nanosecond", "second", "minute", "hour", "day", "month", "year", "zone_offset"):
        name = f"date-{field.replace('_', '-')}"
        define(name, (lambda f, n: lambda d: getattr(_expect_date(d, n), f))(field, name))
    define("date-year-day", lambda d: _date_year_day(_expect_date(d, "date-year-day")))
    define("date-week-day", lambda d: _date_week_day(_expect_date(d, "date-week-day")))
    define("date-week-number", _date_week_number)

    define("current-julian-day", lambda: _time_to_jd(_current_time()))
    define("current-modified-julian-day", lambda: _time_to_jd(_current_time()) - _MJD_OFFSET)

    define("date->time-utc", lambda d: _date_to_time_utc(_expect_date(d, "date->time-utc")))
    define("time-utc->date", _time_utc_to_date)

    define("date->julian-day", _julian("date->julian-day", from_time=False, modified=False))
    define("date->modified-julian-day", _julian("date->modified-julian-day", from_time=False, modified=True))
    define("time-utc->julian-day", _julian("time-utc->julian-day", from_time=True, modified=False))
    define("time-utc->modified-julian-day", _julian("time-utc->modified-julian-day", from_time=True, modified=True))
    define("julian-day->date", _jd_to("julian-day->date", to_date=True, modified=False))
    define("modified-julian-day->date", _jd_to("modified-julian-day->date", to_date=True, modified=True))
    define("julian-day->time-utc", _jd_to("julian-day->time-utc", to_date=False, modified=False))
    define("modified-julian-day->time-utc", _jd_to("modified-julian-day->time-utc", to_date=False, modified=True))

    define("date->string", _date_to_string)
    define("string->date", _string_to_date)

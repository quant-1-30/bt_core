#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015-2023 Daniel Rodriguez
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################

import datetime
import math
import time as _time
import pytz
import pandas as pd
from datetime import timedelta

MAX_MONTH_RANGE = 23
MAX_WEEK_RANGE = 5


ZERO = datetime.timedelta(0)

STDOFFSET = datetime.timedelta(seconds=-_time.timezone)
if _time.daylight:
    DSTOFFSET = datetime.timedelta(seconds=-_time.altzone)
else:
    DSTOFFSET = STDOFFSET

DSTDIFF = DSTOFFSET - STDOFFSET

# To avoid rounding errors taking dates to next day
TIME_MAX = datetime.time(23, 59, 59, 999990)

# To avoid rounding errors taking dates to next day
TIME_MIN = datetime.time.min


def tzparse(tz):
    # If no object has been provided by the user and a timezone can be
    # found via contractdtails, then try to get it from pytz, which may or
    # may not be available.
    tzstr = isinstance(tz, str)
    if tz is None or not tzstr:
        return Localizer(tz)

    try:
        import pytz  # keep the import very local
    except ImportError:
        return Localizer(tz)    # nothing can be done

    tzs = tz
    if tzs == 'CST':  # usual alias
        tzs = 'CST6CDT'

    try:
        tz = pytz.timezone(tzs)
    except pytz.UnknownTimeZoneError:
        return Localizer(tz)    # nothing can be done

    return tz


def Localizer(tz):
    import types

    def localize(self, dt):
        return dt.replace(tzinfo=self)

    if tz is not None and not hasattr(tz, 'localize'):
        # patch the tz instance with a bound method
        tz.localize = types.MethodType(localize, tz)

    return tz


# A UTC class, same as the one in the Python Docs
class _UTC(datetime.tzinfo):
    """UTC"""

    def utcoffset(self, dt):
        return ZERO

    def tzname(self, dt):
        return "UTC"

    def dst(self, dt):
        return ZERO

    def localize(self, dt):
        return dt.replace(tzinfo=self)


class _LocalTimezone(datetime.tzinfo):

    def utcoffset(self, dt):
        if self._isdst(dt):
            return DSTOFFSET
        else:
            return STDOFFSET

    def dst(self, dt):
        if self._isdst(dt):
            return DSTDIFF
        else:
            return ZERO

    def tzname(self, dt):
        return _time.tzname[self._isdst(dt)]

    def _isdst(self, dt):
        tt = (dt.year, dt.month, dt.day,
              dt.hour, dt.minute, dt.second,
              dt.weekday(), 0, 0)
        try:
            stamp = _time.mktime(tt)
        except (ValueError, OverflowError):
            return False  # Too far in the future, not relevant

        tt = _time.localtime(stamp)
        return tt.tm_isdst > 0

    def localize(self, dt):
        return dt.replace(tzinfo=self)


UTC = _UTC()
TZLocal = _LocalTimezone()


HOURS_PER_DAY = 24.0
MINUTES_PER_HOUR = 60.0
SECONDS_PER_MINUTE = 60.0
MUSECONDS_PER_SECOND = 1e6
MINUTES_PER_DAY = MINUTES_PER_HOUR * HOURS_PER_DAY
SECONDS_PER_DAY = SECONDS_PER_MINUTE * MINUTES_PER_DAY
MUSECONDS_PER_DAY = MUSECONDS_PER_SECOND * SECONDS_PER_DAY


#def num2date(x, tz=None, naive=True):
#    # Same as matplotlib except if tz is None a naive datetime object
#    # will be returned.
#    """
#    *x* is a float value which gives the number of days
#    (fraction part represents hours, minutes, seconds) since
#    0001-01-01 00:00:00 UTC *plus* *one*.
#    The addition of one here is a historical artifact.  Also, note
#    that the Gregorian calendar is assumed; this is not universal
#    practice.  For details, see the module docstring.
#    Return value is a :class:`datetime` instance in timezone *tz* (default to
#    rcparams TZ value).
#    If *x* is a sequence, a sequence of :class:`datetime` objects will
#    be returned.
#    """
#
#    ix = int(x)
#    dt = datetime.datetime.fromordinal(ix)
#    remainder = float(x) - ix
#    hour, remainder = divmod(HOURS_PER_DAY * remainder, 1)
#    minute, remainder = divmod(MINUTES_PER_HOUR * remainder, 1)
#    second, remainder = divmod(SECONDS_PER_MINUTE * remainder, 1)
#    microsecond = int(MUSECONDS_PER_SECOND * remainder)
#    if microsecond < 10:
#        microsecond = 0  # compensate for rounding errors
#
#    if True and tz is not None:
#        dt = datetime.datetime(
#            dt.year, dt.month, dt.day, int(hour), int(minute), int(second),
#            microsecond, tzinfo=UTC)
#        dt = dt.astimezone(tz)
#        if naive:
#            dt = dt.replace(tzinfo=None)
#    else:
#        # If not tz has been passed return a non-timezoned dt
#        dt = datetime.datetime(
#            dt.year, dt.month, dt.day, int(hour), int(minute), int(second),
#            microsecond)
#
#    if microsecond > 999990:  # compensate for rounding errors
#        dt += datetime.timedelta(microseconds=1e6 - microsecond)
#
#    return dt

def num2date(x, tz=None, naive=True):
    # Same as matplotlib except if tz is None a naive datetime object
    # will be returned.
    """
    *x* is a float value which gives the number of days
    (fraction part represents hours, minutes, seconds) since
    0001-01-01 00:00:00 UTC *plus* *one*.
    The addition of one here is a historical artifact.  Also, note
    that the Gregorian calendar is assumed; this is not universal
    practice.  For details, see the module docstring.
    Return value is a :class:`datetime` instance in timezone *tz* (default to
    rcparams TZ value).
    If *x* is a sequence, a sequence of :class:`datetime` objects will
    be returned.
    """
    print("num2date------------------------------------------------------------------------------------------------------- ", x)
    dt = datetime.datetime.fromtimestamp(x, tz=pytz.timezone('Asia/Shanghai'))
    if tz is not None:
        tzinfo = pytz.timezone(tz) if isinstance(tz, str) else tz
        dt = dt.astimezone(tz=tzinfo)
    print("finish numdate :", dt)
    return dt

def num2dt(num, tz=None, naive=True):
    return num2date(num, tz=tz, naive=naive).date()

def num2time(num, tz=None, naive=True):
    return num2date(num, tz=tz, naive=naive).time()

def date2num(dt, tz=None):
    """
    Convert :mod:`datetime` to the Gregorian date as UTC float days,
    preserving hours, minutes, seconds and microseconds.  Return value
    is a :func:`float`.
    """
    if tz is not None:
        dt = tz.localize(dt)

    if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
        delta = dt.tzinfo.utcoffset(dt)
        if delta is not None:
            dt -= delta

    base = float(dt.toordinal())
    if hasattr(dt, 'hour'):
        # base += (dt.hour / HOURS_PER_DAY +
        #          dt.minute / MINUTES_PER_DAY +
        #          dt.second / SECONDS_PER_DAY +
        #          dt.microsecond / MUSECONDS_PER_DAY
        #         )
        base = math.fsum(
            (base, dt.hour / HOURS_PER_DAY, dt.minute / MINUTES_PER_DAY,
             dt.second / SECONDS_PER_DAY, dt.microsecond / MUSECONDS_PER_DAY))

    return base


def time2num(tm):
    """
    Converts the hour/minute/second/microsecond part of tm (datetime.datetime
    or time) to a num
    """
    num = (tm.hour / HOURS_PER_DAY +
           tm.minute / MINUTES_PER_DAY +
           tm.second / SECONDS_PER_DAY +
           tm.microsecond / MUSECONDS_PER_DAY)

    return num


def date2utc(date, tzinfo="Asia/Shanghai"):
    struct_dt = datetime.datetime.strptime(str(date), '%Y%m%d')
    struct_dt = struct_dt.astimezone(tz=pytz.timezone(tzinfo))
    struct_dt = struct_dt.replace(tzinfo=datetime.timezone.utc) 
    return struct_dt


def market_utc(date, tzinfo="Asia/Shanghai"):
    format_dt = date2utc(date, tzinfo=tzinfo)
    m_open = format_dt + datetime.timedelta(hours=9, minutes=30)
    m_close = format_dt + datetime.timedelta(hours=15, minutes=0)
    # trans to utc
    return m_open, m_close


# def transformat(dt, _format="%Y%m%d"):
#     """
#         e.g. 20240101 --> 202401010000
#     """
#     dt_time = datetime.datetime.strptime(str(dt), _format)
#     format_dt = dt_time.strftime("%Y%m%d%H%M")
#     return format_dt


def calc_distance(tick, _format="%Y%m%d%H%M"):
    # %-m 不补0
    formate_date = datetime.datetime.strptime(str(tick), _format)
    delta = formate_date - datetime.datetime(year=formate_date.year, month=formate_date.month, day=formate_date.day, hours=9, minutes=30)
    return delta.seconds, formate_date
    

def loc2ticker(dt, loc, _format="%Y%m%d"):
    struct_date = datetime.datetime.strptime(str(dt), _format)
    loc_date = struct_date + datetime.timedelta(hours=9, minutes=30) + datetime.timedelta(seconds=loc * 3)
    return loc_date 

def locate_pos(price, minutes, direction):
    print('minutes locate_pos', minutes)
    # 当卖出价格大于bid价格才会成交，买入价格低于bid价格才会成交
    loc = list(minutes[minutes <= price].index) if direction == '1' else \
        list(minutes[minutes >= price].index)
    # print('present minutes', minutes[minutes <= price])
    try:
        # pos = pd.Timestamp(datetime.datetime.utcfromtimestamp(loc[0]))
        pos = loc[0]
    except IndexError:
        print('price out of minutes')
        pos = None
    return pos


def parse_date_str_series(format_str, tz, date_str_series):
    tz_str = str(tz)
    if tz_str == pytz.utc.zone:

        parsed = pd.to_datetime(
            date_str_series.values,
            format=format_str,
            utc=True,
            errors='coerce',
        )
    else:
        parsed = pd.to_datetime(
            date_str_series.values,
            format=format_str,
            errors='coerce',
        ).tz_localize(tz_str).tz_convert('UTC')
    return parsed


def naive_to_utc(ts):
    """
    Converts a UTC tz-naive timestamp to a tz-aware timestamp.
    """
    # Drop the nanoseconds field. warn=False suppresses the warning
    # that we are losing the nanoseconds; however, this is intended.
    return pd.Timestamp(ts.to_pydatetime(warn=False), tz='UTC')


def ensure_utc(time, tz='UTC'):
    """
    Normalize a time. If the time is tz-naive, assume it is UTC.
    """
    if not time.tzinfo:
        time = time.replace(tzinfo=pytz.timezone(tz))
    return time.replace(tzinfo=pytz.utc)


def normalize_date(frame):
    frame['year'] = frame['dates'] // 2048 + 2004
    frame['month'] = (frame['dates'] % 2048) // 100
    frame['day'] = (frame['dates'] % 2048) % 100
    frame['hour'] = frame['sub_dates'] // 60
    frame['minutes'] = frame['sub_dates'] % 60
    frame['ticker'] = frame.apply(lambda x: pd.Timestamp(
        datetime.datetime(int(x['year']), int(x['month']), int(x['day']),
                          int(x['hour']), int(x['minutes']))),
                            axis=1)
    # raw['timestamp'] = raw['ticker'].apply(lambda x: x.timestamp())
    # return frame.loc[:, ['ticker', 'open', 'high', 'low', 'close', 'amount', 'volume']]
    return frame


def _out_of_range_error(a, b=None, var='offset'):
    start = 0
    if b is None:
        end = a - 1
    else:
        start = a
        end = b - 1
    return ValueError(
        '{var} must be in between {start} and {end} inclusive'.format(
            var=var,
            start=start,
            end=end,
        )
    )


def _td_check(td):
    seconds = td.total_seconds()

    # 43200 seconds = 12 hours
    if 60 <= seconds <= 43200:
        return td
    else:
        raise ValueError('offset must be in between 1 minute and 12 hours, '
                         'inclusive.')


def _build_offset(offset, kwargs, default):
    """
    Builds the offset argument for event rules.
    """
    # Filter down to just kwargs that were actually passed.
    kwargs = {k: v for k, v in kwargs.items() if v is not None}
    if offset is None:
        if not kwargs:
            return default  # use the default.
        else:
            return _td_check(datetime.timedelta(**kwargs))
    elif kwargs:
        raise ValueError('Cannot pass kwargs and an offset')
    elif isinstance(offset, datetime.timedelta):
        return _td_check(offset)
    else:
        raise TypeError("Must pass 'hours' and/or 'minutes' as keywords")


def _build_date(date, kwargs):
    """
    Builds the date argument for event rules.
    """
    if date is None:
        if not kwargs:
            raise ValueError('Must pass a date or kwargs')
        else:
            return datetime.date(**kwargs)

    elif kwargs:
        raise ValueError('Cannot pass kwargs and a date')
    else:
        return date


def _build_time(time, kwargs):
    """
    Builds the time argument for event rules.
    """
    tz = kwargs.pop('tz', 'UTC')
    if time:
        if kwargs:
            raise ValueError('Cannot pass kwargs and a time')
        else:
            return ensure_utc(time, tz)
    elif not kwargs:
        raise ValueError('Must pass a time or kwargs')
    else:
        return datetime.time(**kwargs)


def _time_to_micros(time):
    """Convert a time into microseconds since midnight.
    Parameters
    ----------
    time : datetime.time
        The time to convert.
    Returns
    -------
    us : int
        The number of microseconds since midnight.
    Notes
    -----
    This does not account for leap seconds or daylight savings.
    """
    seconds = time.hour * 60 * 60 + time.minute * 60 + time.second
    return 1000000 * seconds + time.microsecond


def timedelta_to_integral_seconds(delta):
    """
    Convert a pd.Timedelta to a number of seconds as an int.
    """
    return int(delta.total_seconds())


def timedelta_to_integral_minutes(delta):
    """
    Convert a pd.Timedelta to a number of minutes as an int.
    """
    return timedelta_to_integral_seconds(delta) // 60


def normalize_quarters(years, quarters):
    return years * 4 + quarters - 1


def split_normalized_quarters(normalized_quarters):
    years = normalized_quarters // 4
    quarters = normalized_quarters % 4
    return years, quarters + 1


def date_gen(start,
             end,
             trading_calendar,
             delta=timedelta(minutes=1),
             repeats=None):
    """
    Utility to generate a stream of dates.
    """
    daily_delta = not (delta.total_seconds()
                       % timedelta(days=1).total_seconds())
    cur = start
    if daily_delta:
        # if we are producing daily timestamps, we
        # use midnight
        cur = cur.replace(hour=0, minute=0, second=0,
                          microsecond=0)

    def advance_current(cur):
        """
        Advances the current dt skipping non market days and minutes.
        """
        cur = cur + delta

        currently_executing = \
            (daily_delta and (cur in trading_calendar.all_sessions)) or \
            (trading_calendar.is_open_on_minute(cur))

        if currently_executing:
            return cur
        else:
            if daily_delta:
                return trading_calendar.minute_to_session_label(cur)
            else:
                return trading_calendar.open_and_close_for_session(
                    trading_calendar.minute_to_session_label(cur)
                )[0]

    # yield count trade events, all on trading days, and
    # during trading hours.
    while cur < end:
        if repeats:
            for j in range(repeats):
                yield cur
        else:
            yield cur

        cur = advance_current(cur)


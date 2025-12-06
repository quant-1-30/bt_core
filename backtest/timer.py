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

import bisect
import collections
from datetime import date, datetime, timedelta
from itertools import islice

from .feed import AbstractDataBase
from .metabase import MetaParams, with_metaclass
from backtest.utils.dateintern import date2num, num2date


__all__ = ['SESSION_START', 'SESSION_END', 'Timer']

SESSION_START, SESSION_END = range(2)

TIME_MAX = datetime.max


class Timer(with_metaclass(MetaParams, object)):
    '''
        **Note**: can be called during ``__init__`` or ``start``

        Schedules a timer to invoke either a specified callback or the
        ``notify_timer`` of one or more strategies.

        Arguments:

          - ``when``: can be

            - ``datetime.time`` instance (see below ``tzdata``)
            - ``bt.timer.SESSION_START`` to reference a session start
            - ``bt.timer.SESSION_END`` to reference a session end

         - ``offset`` which must be a ``datetime.timedelta`` instance

           Used to offset the value ``when``. It has a meaningful use in
           combination with ``SESSION_START`` and ``SESSION_END``, to indicated
           things like a timer being called ``15 minutes`` after the session
           start.

          - ``repeat`` which must be a ``datetime.timedelta`` instance

            Indicates if after a 1st call, further calls will be scheduled
            within the same session at the scheduled ``repeat`` delta

            Once the timer goes over the end of the session it is reset to the
            original value for ``when``

          - ``weekdays``: a **sorted** iterable with integers indicating on
            which days (iso codes, Monday is 1, Sunday is 7) the timers can
            be actually invoked

            If not specified, the timer will be active on all days

          - ``weekcarry`` (default: ``False``). If ``True`` and the weekday was
            not seen (ex: trading holiday), the timer will be executed on the
            next day (even if in a new week)

          - ``monthdays``: a **sorted** iterable with integers indicating on
            which days of the month a timer has to be executed. For example
            always on day *15* of the month

            If not specified, the timer will be active on all days

          - ``monthcarry`` (default: ``True``). If the day was not seen
            (weekend, trading holiday), the timer will be executed on the next
            available day.

          - ``allow`` (default: ``None``). A callback which receives a
            `datetime.date`` instance and returns ``True`` if the date is
            allowed for timers or else returns ``False``

          - ``tzdata`` which can be either ``None`` (default), a ``pytz``
            instance or a ``data feed`` instance.

            ``None``: ``when`` is interpreted at face value (which translates
            to handling it as if it where UTC even if it's not)

            ``pytz`` instance: ``when`` will be interpreted as being specified
            in the local time specified by the timezone instance.

            ``data feed`` instance: ``when`` will be interpreted as being
            specified in the local time specified by the ``tz`` parameter of
            the data feed instance.

            **Note**: If ``when`` is either ``SESSION_START`` or
              ``SESSION_END`` and ``tzdata`` is ``None``, the 1st *data feed*
              in the system (aka ``self.data0``) will be used as the reference
              to find out the session times.

          - ``*args``: any extra args will be passed to ``notify_timer``

          - ``**kwargs``: any extra kwargs will be passed to ``notify_timer``

        Return Value:

          - The created timer

    '''
    params = (
        ('when', None),
        ('offset', timedelta()),
        ('repeat', timedelta()),
        ('weekdays', []),
        ('weekcarry', False),
        ('monthdays', []),
        ('monthcarry', True),
        ('allow', None),  # callable that allows a timer to take place
        ('tzdata', None),
    )

    SESSION_START, SESSION_END = range(2)

    def __init__(self, *args, **kwargs): # to tolerate abundant args or kwargs
        self.args = args
        self.kwargs = kwargs

    def start(self, data):
        # write down the 'reset when' value
        if not isinstance(self.p.when, int):  # expect time/datetime
            self._rstwhen = self.p.when
            self._tzdata = self.p.tzdata
        else:
            self._tzdata = data if self.p.tzdata is None else self.p.tzdata

            if self.p.when == SESSION_START:
                self._rstwhen = self._tzdata.p.sessionstart
            elif self.p.when == SESSION_END:
                self._rstwhen = self._tzdata.p.sessionend

        self._isdata = isinstance(self._tzdata, AbstractDataBase)
        self._reset_when()

        self._nexteos = None
        self._curdate = date.min

        self._curmonth = -1  # non-existent month
        self._monthmask = collections.deque()

        self._curweek = -1  # non-existent week
        self._weekmask = collections.deque()

    def _reset_when(self, ddate=datetime.min):
        self._when = self._rstwhen
        self._dtwhen = self._dwhen = None

        self._lastcall = ddate

    def _check_month(self, ddate):
        if not self.p.monthdays:
            return True

        mask = self._monthmask
        daycarry = False
        dmonth = ddate.month
        if dmonth != self._curmonth: # reset
            self._curmonth = dmonth  # write down new month
            daycarry = self.p.monthcarry and bool(mask)
            self._monthmask = mask = collections.deque(self.p.monthdays)

        dday = ddate.day
        dc = bisect.bisect_left(mask, dday)  # "left" for days before dday
        daycarry = daycarry or (self.p.monthcarry and dc > 0)
        if dc < len(mask):
            # curday = bisect.bisect_right(mask, dday, lo=dc) > 0  # check dday
            curday = bisect.bisect_right(mask, dday, lo=dc) > dc  # check dday
            dc += curday
        else:
            curday = False

        while dc:
            mask.popleft()
            dc -= 1

        return daycarry or curday

    def _check_week(self, ddate=date.min):
        if not self.p.weekdays:
            return True

        _, dweek, dwkday = ddate.isocalendar()

        mask = self._weekmask
        daycarry = False
        # reset mechanism
        if dweek != self._curweek:
            self._curweek = dweek  # write down new month
            daycarry = self.p.weekcarry and bool(mask)
            self._weekmask = mask = collections.deque(self.p.weekdays)

        dc = bisect.bisect_left(mask, dwkday)  # "left" for days before dday
        daycarry = daycarry or (self.p.weekcarry and dc > 0)
        if dc < len(mask):
            # curday = bisect.bisect_right(mask, dwkday, lo=dc) > 0  # check dday
            curday = bisect.bisect_right(mask, dwkday, lo=dc) > dc  # check dday
            dc += curday
        else:
            curday = False

        while dc:
            mask.popleft()
            dc -= 1

        return daycarry or curday

    def check(self, dt):
        d = num2date(dt)
        ddate = d.date()
        if self._lastcall == ddate:  # not repeating, awaiting date change
            return False

        if not self._nexteos or d > self._nexteos:
            if self._isdata:  # eos provided by data
                nexteos, _ = self._tzdata._getnexteos()
            else:  # generic eos
                # TIME_MAX 23:59:59.999999 means end of day
                nexteos = datetime.combine(ddate, TIME_MAX).replace(tzinfo=d.tzinfo)
            self._nexteos = nexteos
            self._reset_when()

        if ddate > self._curdate:  # day change
            self._curdate = ddate
            # month and week must be same 
            ret = self._check_month(ddate)
            if ret:
                ret = self._check_week(ddate)
            if ret and self.p.allow is not None:
                ret = self.p.allow(ddate)

            if not ret:
                self._reset_when(ddate)  # this day won't make it / update _lastcall 
                return False  # timer target not met

        # no day change or passed month, week and allow filters on date change
        dwhen = self._dwhen
        dtwhen = self._dtwhen
        if dtwhen is None:
            dwhen = datetime.combine(ddate, self._when).replace(tzinfo=d.tzinfo)
            if self.p.offset:
                dwhen += self.p.offset

            self._dwhen = dwhen

            if self._isdata:
                self._dtwhen = dtwhen = self._tzdata.date2num(dwhen)
            else:
                self._dtwhen = dtwhen = date2num(dwhen, tz=self._tzdata)

        if dt < dtwhen:
            return False  # timer target not met
        # trigger when dt >= dtwhen
        # following logic is to update dtwhen and dwhen for next trigger

        self.lastwhen = dwhen  # record when the last timer "when" happened

        if not self.p.repeat: 
            self._reset_when(ddate)  # reset and mark as called on ddate
        else:
            if d > self._nexteos:
                if self._isdata:  # eos provided by data
                    nexteos, _ = self._tzdata._getnexteos()
                else:  # generic eos
                    nexteos = datetime.combine(ddate, TIME_MAX).replace(tzinfo=d.tzinfo)

                self._nexteos = nexteos
            else:
                nexteos = self._nexteos

            while True:
                dwhen += self.p.repeat
                if dwhen > nexteos:
                    self._reset_when(ddate)  # reset to original point
                    break

                if dwhen > d:  # _rstwhen is activte / many times trigger
                    self._dtwhen = dtwhen = date2num(dwhen)  # float timestamp
                    # Get the localized expected next time
                    if self._isdata:
                        self._dwhen = self._tzdata.num2date(dtwhen)
                    else:  # assume pytz compatible or None
                        self._dwhen = num2date(dtwhen, tz=self._tzdata)
                    break

        return True  # timer target was met

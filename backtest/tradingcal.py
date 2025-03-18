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


from datetime import datetime, timedelta, time

from .metabase import MetaParams
from utils.dateintern import UTC


# Imprecission in the full time conversion to float would wrap over to next day
# if microseconds is 999999 as defined in time.max
_time_max = time(hour=23, minute=59, second=59, microsecond=999990)


MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = range(7)
(ISONODAY, ISOMONDAY, ISOTUESDAY, ISOWEDNESDAY, ISOTHURSDAY, ISOFRIDAY,
 ISOSATURDAY, ISOSUNDAY) = range(8)

WEEKEND = [SATURDAY, SUNDAY]
ISOWEEKEND = [ISOSATURDAY, ISOSUNDAY]
ONEDAY = timedelta(days=1)


class TradingCalendarBase(metaclass=MetaParams):
    def _nextday(self, day):
        '''
        Returns the next trading day (datetime/date instance) after ``day``
        (datetime/date instance) and the isocalendar components

        The return value is a tuple with 2 components: (nextday, (y, w, d))
        '''
        raise NotImplementedError

    def schedule(self, day):
        '''
        Returns a tuple with the opening and closing times (``datetime.time``)
        for the given ``date`` (``datetime/date`` instance)
        '''
        raise NotImplementedError

    def nextday(self, day):
        '''
        Returns the next trading day (datetime/date instance) after ``day``
        (datetime/date instance)
        '''
        return self._nextday(day)[0]  # 1st ret elem is next day

    def nextday_week(self, day):
        '''
        Returns the iso week number of the next trading day, given a ``day``
        (datetime/date) instance
        '''
        self._nextday(day)[1][1]  # 2 elem is isocal / 0 - y, 1 - wk, 2 - day

    def last_weekday(self, day):
        '''
        Returns ``True`` if the given ``day`` (datetime/date) instance is the
        last trading day of this week
        '''
        # Next day must be greater than day. If the week changes is enough for
        # a week change even if the number is smaller (year change)
        return day.isocalendar()[1] != self._nextday(day)[1][1]

    def last_monthday(self, day):
        '''
        Returns ``True`` if the given ``day`` (datetime/date) instance is the
        last trading day of this month
        '''
        # Next day must be greater than day. If the week changes is enough for
        # a week change even if the number is smaller (year change)
        return day.month != self._nextday(day)[0].month

    def last_yearday(self, day):
        '''
        Returns ``True`` if the given ``day`` (datetime/date) instance is the
        last trading day of this month
        '''
        # Next day must be greater than day. If the week changes is enough for
        # a week change even if the number is smaller (year change)
        return day.year != self._nextday(day)[0].year


class TradingCalendar(TradingCalendarBase):
    '''
    Wrapper of ``pandas_market_calendars`` for a trading calendar. The package
    ``pandas_market_calendar`` must be installed

    Params:

      - ``open`` (default ``time.min``)

        Regular start of the session

      - ``close`` (default ``time.max``)

        Regular end of the session

      - ``holidays`` (default ``[]``)

        List of non-trading days (``datetime.datetime`` instances)

      - ``earlydays`` (default ``[]``)

        List of tuples determining the date and opening/closing times of days
        which do not conform to the regular trading hours where each tuple has
        (``datetime.datetime``, ``datetime.time``, ``datetime.time`` )

      - ``offdays`` (default ``ISOWEEKEND``)

        A list of weekdays in ISO format (Monday: 1 -> Sunday: 7) in which the
        market doesn't trade. This is usually Saturday and Sunday and hence the
        default

    '''
    params = (
        ('open', time.min),
        ('close', _time_max),
        ('holidays', []),  # list of non trading days (date)
        ('earlydays', []),  # list of tuples (date, opentime, closetime)
        ('offdays', ISOWEEKEND),  # list of non trading (isoweekdays)
    )

    def __init__(self):
        self._earlydays = [x[0] for x in self.p.earlydays]  # speed up searches

    def _nextday(self, day):
        '''
        Returns the next trading day (datetime/date instance) after ``day``
        (datetime/date instance) and the isocalendar components

        The return value is a tuple with 2 components: (nextday, (y, w, d))
        '''
        while True:
            day += ONEDAY
            isocal = day.isocalendar()
            if isocal[2] in self.p.offdays or day in self.p.holidays:
                continue

            return day, isocal

    def schedule(self, day, tz=None):
        '''
        Returns the opening and closing times for the given ``day``. If the
        method is called, the assumption is that ``day`` is an actual trading
        day

        The return value is a tuple with 2 components: opentime, closetime
        '''
        while True:
            dt = day.date()
            try:
                i = self._earlydays.index(dt)
                o, c = self.p.earlydays[i][1:]
            except ValueError:  # not found
                o, c = self.p.open, self.p.close

            closing = datetime.combine(dt, c)
            if tz is not None:
                closing = tz.localize(closing).astimezone(UTC)
                closing = closing.replace(tzinfo=None)

            if day > closing:  # current time over eos
                day += ONEDAY
                continue
                # skip rest code

            opening = datetime.combine(dt, o)
            if tz is not None:
                opening = tz.localize(opening).astimezone(UTC)
                opening = opening.replace(tzinfo=None)

            return opening, closing


class PandasMarketCalendar(TradingCalendarBase):
    '''
    Wrapper of ``pandas_market_calendars`` for a trading calendar. The package
    ``pandas_market_calendar`` must be installed

    Params:

      - ``calendar`` (default ``None``)

        The param ``calendar`` accepts the following:

        - string: the name of one of the calendars supported, for example
          `NYSE`. The wrapper will attempt to get a calendar instance

        - calendar instance: as returned by ``get_calendar('NYSE')``

      - ``cachesize`` (default ``365``)

        Number of days to cache in advance for lookup

    See also:

      - https://github.com/rsheftel/pandas_market_calendars

      - http://pandas-market-calendars.readthedocs.io/

    '''
    params = (
        ('calendar', None),  # A pandas_market_calendars instance or exch name
        ('cachesize', 365),  # Number of days to cache in advance
    )

    def __init__(self):
        self._calendar = self.p.calendar

        # if isinstance(self._calendar, str):  # use passed mkt name
        #     import pandas_market_calendars as mcal  
        #     self._calendar = mcal.get_calendar(self._calendar)

        import pandas as pd  # guaranteed because of pandas_market_calendars
        self.dcache = pd.DatetimeIndex([0.0])
        self.idcache = pd.DataFrame(index=pd.DatetimeIndex([0.0]))
        self.csize = timedelta(days=self.p.cachesize)

    def _nextday(self, day):
        '''
        Returns the next trading day (datetime/date instance) after ``day``
        (datetime/date instance) and the isocalendar components

        The return value is a tuple with 2 components: (nextday, (y, w, d))
        '''
        day += ONEDAY
        while True:
            i = self.dcache.searchsorted(day)
            if i == len(self.dcache):
                # keep a cache of 1 year to speed up searching
                self.dcache = self._calendar.valid_days(day, day + self.csize)
                continue

            d = self.dcache[i].to_pydatetime()
            return d, d.isocalendar()

    def schedule(self, day, tz=None):
        '''
        Returns the opening and closing times for the given ``day``. If the
        method is called, the assumption is that ``day`` is an actual trading
        day

        The return value is a tuple with 2 components: opentime, closetime
        '''
        while True:
            i = self.idcache.index.searchsorted(day.date())
            if i == len(self.idcache):
                # keep a cache of 1 year to speed up searching
                self.idcache = self._calendar.schedule(day, day + self.csize)
                continue

            st = (x.tz_localize(None) for x in self.idcache.iloc[i, 0:2])
            opening, closing = st  # Get utc naive times
            if day > closing:  # passed time is over the sessionend
                day += ONEDAY  # wrap over to next day
                continue

            return opening.to_pydatetime(), closing.to_pydatetime()


# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Mar 12 15:37:47 2019

@author: python
"""
import enum
import pandas as pd
import pytz
import numpy as np
from weakref import WeakValueDictionary
from datetime import datetime
from dateutil import rrule
from toolz import partition_all


class Holiday(enum.Enum):
    new_year = 0 
    spring = 1
    tomb_sweep = 2
    labour = 3
    autumn = 4
    national = 5


class Spring(enum.Enum):
    
    spring = ['19900127', '19910215', '19920204', '19930123', '19940210',
          '19950131', '19960219', '19970207', '19980128', '19990216',
          '20000205', '20010124', '20020212', '20030201', '20040122',
          '20050209', '20060129', '20070218', '20080207', '20090126',
          '20100214', '20110203', '20120123', '20130210', '20140131',
          '20150219', '20160208', '20170128', '20180216', '20190205',
          '20200125', '20210212', '20220201', '20230122', '20240210',
          '20250129', '20260217', '20270206', '20280126', '20290213',
          '20300203', '20310123', '20320211', '20330131', '20340219',
          '20350208', '20360128', '20370215', '20380204', '20390124',
          '20400212', '20410201', '20420122', '20430210', '20440130',
          '20450217', '20460206', '20470126', '20480214', '20490202',
          '20500123', '20510211', '20520201', '20530219', '20540208',
          '20550128', '20560215', '20570204', '20580124', '20590212',
          '20600202', '20610121', '20620209', '20630129', '20640217',
          '20650205', '20660126', '20670214', '20680203', '20690123'] 


class Autumn(enum.Enum):
    
    autumn = ['19901003', '19910922', '19920911', '19930930', '19940920',
          '19950909', '19960927', '19970916', '19981005', '19990924',
          '20000912', '20011001', '20020921', '20030911', '20040928',
          '20050918', '20061006', '20070925', '20080914', '20091003',
          '20100922', '20110912', '20120930', '20130919', '20140908',
          '20150927', '20160915', '20171004', '20180924', '20190913',
          '20201001', '20210921', '20220910', '20230929', '20240917',
          '20251006', '20260925', '20270915', '20281003', '20290922',
          '20300912', '20311001', '20320919', '20330908', '20340927',
          '20350916', '20361004', '20370924', '20380913', '20391002',
          '20400920', '20410910', '20420928', '20430917', '20441005',
          '20450925', '20460915', '20471004', '20480922', '20490911', '20500930']


class Calendar (object):

    cache = WeakValueDictionary()

    def __init__(self, trading_days):
        self.all_sessions = trading_days
        return self

    def holiday_sessions(self):
        non_trading_rules = dict()
        tz = pytz.timezone('Asia/Shanghai')
        start = pd.Timestamp(min(self.all_sessions), tz=tz)
        end = pd.Timestamp(max(self.all_sessions), tz=tz)

        # 元旦
        new_year = rrule.rrule(
            rrule.YEARLY,
            byyearday=1,
            cache=True,
            dtstart=start,
            until=end
        )
        new_year = [d.strftime('%Y-%m-%d') for d in new_year]
        non_trading_rules.update({'new_year': new_year})

        # 清明节
        april_4 = rrule.rrule(
            rrule.YEARLY,
            bymonth= 4,
            bymonthday=4,
            cache=True,
            dtstart=start,
            until=end
        )
        april_4 = [d.strftime('%Y-%m-%d') for d in april_4]
        print('april_4', april_4)
        non_trading_rules.update({'qingming': april_4})

        # 劳动节
        may_day = rrule.rrule(
            rrule.YEARLY,
            bymonth=5,
            bymonthday=1,
            cache=True,
            dtstart=start,
            until=end
        )
        may_day = [d.strftime('%Y-%m-%d') for d in may_day]
        print('may_day', may_day)
        non_trading_rules.update({'labour': may_day})

        # 国庆节
        national_day = rrule.rrule(
            rrule.YEARLY,
            bymonth=10,
            bymonthday=1,
            cache=True,
            dtstart=start,
            until=end
        )
        national_day = [d.strftime('%Y-%m-%d') for d in national_day]
        print('national_day', national_day)
        non_trading_rules.update({'national': national_day})
        # append
        non_trading_rules['spring'] = Spring.spring.value
        non_trading_rules['autumn'] = Autumn.autumn.value
        return non_trading_rules

    def get_adjacent_trading_day_of_holiday(self, holiday_name, offset):
        if holiday_name not in Holiday:
            raise ValueError('unkown holiday name')
        holiday_days = self.holiday_sessions[holiday_name]
        adjacent_trading_days = [self._roll_forward(t, offset)[0] for t in holiday_days]
        return adjacent_trading_days

    def _roll_forward(self, dt, window):
        """
        Given a date, align it to the trading calendar
        dt = pd.Timestamp(dt, tz='UTC')

        Parameters
        ----------
        dt : str %Y-%m-%d
        window : int

        Returns
        -------
        pd.Timestamp
        """
        if window == 0:
            return dt
        if isinstance(dt, pd.Timestamp):
            dt = dt.strftime('%Y-%m-%d')
        pos = self.all_sessions.searchsorted(dt)
        try:
            loc = pos if self.all_sessions[pos] == dt else pos - 1
            forward = self.all_sessions[loc + window]
            # return pd.Timestamp(self.all_sessions[forward])
            return forward, loc
        except IndexError:
            raise ValueError(
                "Date {} was past the last session for {}. "
                "The last session for this domain is {}.".format(
                    dt,
                    self,
                    self.all_sessions[-1]
                )
            )

    def dt_window_size(self, dt, window):
        off_dt = self._roll_forward(dt, window)[0]
        return off_dt

    def session_in_range(self, start_date, end_date):
        """
        :param start_date: pd.Timestamp
        :param end_date: pd.Timestamp
        :return: sessions exclude end_date
        """
        # end_date = end_date.strftime('%Y-%m-%d') if isinstance(end_date, pd.Timestamp) else end_date
        if end_date < start_date:
            raise ValueError("End date %s cannot precede start date %s." %
                             (end_date.strftime("%Y-%m-%d"),
                              start_date.strftime("%Y-%m-%d")))
        s_loc = self._roll_forward(start_date, 0)[1]
        e_loc = self._roll_forward(end_date, 0)[1]
        sessions = self.all_sessions[s_loc: e_loc]
        return sessions

    def session_in_window(self, date, window):
        """
        :param end_date: '%Y-%m-%d'
        :param window:  int
        :return: sessions
        """
        if window == 0:
            return [date, date]
        start_date = self._roll_forward(date, window)[0]
        session_labels = self.session_in_range(start_date, date)
        return session_labels

    def compute_range_chunks(self, start_date, end_date, chunk_size):
        """Compute the start and end dates to run a pipe for.

        Parameters
        ----------
        start_date : pd.Timestamp
            The first date in the pipe.
        end_date : pd.Timestamp
            The last date in the pipe.
        chunk_size : int or None
            The size of the chunks to run. Setting this to None returns one chunk.
        """
        sessions = self.session_in_range(start_date, end_date)
        return (
            (r[0], r[-1]) for r in partition_all(chunk_size, sessions)
        )

    @staticmethod
    def execution_from_open(sessions):
        opens = [pd.Timestamp(dt) + pd.Timedelta(hours=9, minutes=30) for dt in sessions]
        return opens

    @staticmethod
    def execution_from_close(sessions):
        closes = [pd.Timestamp(dt) + pd.Timedelta(hours=15) for dt in sessions]
        # 熔断期间 --- 2次提前收市
        if '20160104' in sessions:
            idx = np.searchsorted('20160104', sessions)
            closes[idx] = pd.Timestamp('20160104') + pd.Timedelta(hours=13, minutes=34)
        elif '20160107' in sessions:
            idx = np.searchsorted('20160107', sessions)
            closes[idx] = pd.Timestamp('20160107') + pd.Timedelta(hours=10)
        return closes

    def open_and_close_for_session(self, dts):
        # 每天开盘，休盘，开盘，收盘的时间
        opens = self.execution_from_open(dts)
        # print('open', opens)
        closes = self.execution_from_close(dts)
        # print('close', closes)
        o_c = zip(opens, closes)
        return o_c

    @staticmethod
    def get_open_and_close(day):
        market_open = pd.Timestamp(
            datetime(
                year=day.year,
                month=day.month,
                day=day.day,
                hour=9,
                minute=30),
            tz='Asia/Shanghai')
        market_close = pd.Timestamp(
            datetime(
                year=day.year,
                month=day.month,
                day=day.day,
                hour=15,
                minute=0),
            tz='Asia/Shanghai')
        return market_open, market_close

    def get_early_close_days(self):
        """
            circuitBreaker --- 熔断机制 2016-01-01 2016-01-07
            自1月8日起暂停实施指数熔断机制
            具体：
                2016年1月4日, A股遇到史上首次“熔断”。早盘, 两市双双低开,随后沪指一度跳水大跌,跌破3500点与3400点,各大板块纷纷下挫。
                午后, 沪深300指数在开盘之后继续下跌, 并于13点13分超过5%, 引发熔断,三家交易所暂停交易15分钟, 恢复交易之后, 沪深300指数继续下跌,
                并于13点34分触及7%的关口，三个交易所暂停交易至收市。
                2016年1月7日, 早盘9点42分, 沪深300指数跌幅扩大至5%, 再度触发熔断线, 两市将在9点57分恢复交易。开盘后, 仅3分钟 10:00
                沪深300指数再度快速探底, 最大跌幅7.21%, 二度熔断触及阈值。这是2016年以来的第二次提前收盘, 同时也创造了休市最快记录
        """
        early_close_days = self.session_in_range('2016-01-01', '2016-01-07')
        return early_close_days
    
    @staticmethod
    def execution_from_open(sessions):
        opens = [pd.Timestamp(dt) + pd.Timedelta(hours=9, minutes=30) for dt in sessions]
        _opens = [pd.Timestamp(dt) + pd.Timedelta(hours=13) for dt in sessions]
        # 熔断期间 --- 2次提前收市
        if '20160107' in sessions:
            idx = np.searchsorted('20160107', sessions)
            _opens[idx] = np.nan
        return opens, _opens
    
    @staticmethod
    def execution_from_close(sessions):
        closes = [pd.Timestamp(dt) + pd.Timedelta(hours=11, minutes=30) for dt in sessions]
        _closes = [pd.Timestamp(dt) + pd.Timedelta(hours=15) for dt in sessions]
        # 熔断期间 --- 2次提前收市
        if '20160104' in sessions:
            idx = np.searchsorted('20160104', sessions)
            _closes[idx] = pd.Timestamp('20160104') + pd.Timedelta(hours=13, minutes=34)
        elif '20160107' in sessions:
            idx = np.searchsorted('20160107', sessions)
            closes[idx] = pd.Timestamp('20160107') + pd.Timedelta(hours=10)
            _closes[idx] = np.nan
        return closes, _closes


__all__ = ['TradingCalendarBase', 'TradingCalendar', 'PandasMarketCalendar']

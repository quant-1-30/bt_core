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

import warnings
import pytz
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, time
from dateutil import rrule
from toolz import partition_all

from ..backtest.metabase import MetaParams
from backtest.utils.dateintern import UTC
from backtest.utils.wrapper import singleton


# Imprecission in the full time conversion to float would wrap over to next day
# if microseconds is 999999 as defined in time.max
_atime_min = time(hour=9, minute=29, second=59, microsecond=999990)
_atime_max = time(hour=11, minute=29, second=59, microsecond=999990)
_ptime_min = time(hour=12, minute=59, second=59, microsecond=999990)
_ptime_max = time(hour=14, minute=59, second=59, microsecond=999990)


[NEW_YEAR, SPRING, TOMB_SWEEP, LABOUR, AUTUMN, NATIONAL] = range(6)

MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = range(7)
(ISONODAY, ISOMONDAY, ISOTUESDAY, ISOWEDNESDAY, ISOTHURSDAY, ISOFRIDAY,
 ISOSATURDAY, ISOSUNDAY) = range(8)

WEEKEND = [SATURDAY, SUNDAY]
ISOWEEKEND = [ISOSATURDAY, ISOSUNDAY]
ONEDAY = timedelta(days=1)


class Holiday:
    
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
    
    def holiday_sessions(self, all_sessions):
        non_trading_rules = dict()
        tz = pytz.timezone('Asia/Shanghai')
        start = pd.Timestamp(min(all_sessions), tz=tz)
        end = pd.Timestamp(max(all_sessions), tz=tz)

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
        non_trading_rules['spring'] = self.spring
        non_trading_rules['autumn'] = self.autumn
        return non_trading_rules


class TradingCalendarBase(MetaParams):

    def __donew__(cls, *args, **kwargs):
        _obj = super(TradingCalendarBase, cls).__new__(cls, *args, **kwargs)
        # via quoteapi
        trading_days = []
        _obj.holidays = Holiday.holiday_sessions(trading_days)
        _obj.trading_days = trading_days
        return _obj
 
    def _roll_forward(self, dt, offset):
        """
        Given a date, align it to the trading calendar
        dt = pd.Timestamp(dt, tz='UTC')

        Parameters
        ----------
        dt : str %Y-%m-%d
        offset : int

        Returns
        -------
        pd.Timestamp
        """
        if offset == 0:
            return dt
        if isinstance(dt, pd.Timestamp):
            dt = dt.strftime('%Y-%m-%d')
        pos = np.searchsorted(self.trading_days, dt, side='left')
        idx = pos + offset
        try:
            # loc = pos if self.trading_days[pos] == dt else pos - 1
            forward = self.trading_days[idx]
            # return pd.Timestamp(self.all_sessions[forward])
            return forward, pos
        except IndexError:
            warnings.warn(
                "{} beyond the trading_days ".format(idx)
            )
            return self.trading_days[-1], pos
        
    def get_range(self, start_date: str, end_date='', offset=0):
        """
        :param start_date: pd.Timestamp
        :param end_date: pd.Timestamp
        :return: sessions exclude end_date
        """
        if offset:
            end_date = self._roll_forward(start_date, offset)[0]
        # end_date = end_date.strftime('%Y-%m-%d') if isinstance(end_date, (pd.Timestamp, datetime)) else end_date
        start_date = start_date if start_date <= end_date else end_date
        
        start_loc = self._roll_forward(start_date, 0)[1]
        end_loc = self._roll_forward(end_date, 0)[1]
        sessions = self.trading_days[start_loc: end_loc]
        return sessions
    
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
        sessions = self.get_range(start_date, end_date)
        return (
            (r[0], r[-1]) for r in partition_all(chunk_size, sessions)
        )
    
    def next_holiday(self, holiday:int, offset:int):
        """
        Given a holiday name, return the next holiday date
        """
        if holiday not in Holiday:
            raise ValueError('unkown holiday name')
        holiday_days = self.holidays[holiday]
        adjacent_trading_days = [self._roll_forward(t, offset)[0] for t in holiday_days]
        return adjacent_trading_days
    
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


@singleton
class TradingCalendar(metaclass=TradingCalendarBase):
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
        # ('open', time.min),
        ('open', (_atime_min, _ptime_min)),
        ('close', (_atime_max, _ptime_max)),
        ('tz', 'Asia/Shanghai'),
        # ('holidays', []),  # list of non trading days (date)
        # list of tuples (opentime, closetime)
        ('earlydays', {'20160104': (_atime_max, time(hour=13, minute=34, second=0)), 
                       '20160107': (time(hour=10, minute=0, second=0), None)}), 
        ('offdays', ISOWEEKEND),  # list of non trading (isoweekdays)
    )

    def __init__(self):
    #     self.dcache = pd.DatetimeIndex([0.0])
    #     self.idcache = pd.DataFrame(index=pd.DatetimeIndex([0.0]))
    #     self.csize = timedelta(days=self.p.cachesize)
          # #to_pydatetime()
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
        
        circuitBreaker --- 熔断机制 2016-01-01 2016-01-07 / 1月8日起暂停实施指数熔断机制
        熔断期间 --- 2次提前收市
        2016年1月4日, A股遇到史上首次“熔断”。早盘, 两市双双低开,随后沪指一度跳水大跌,跌破3500点与3400点,各大板块纷纷下挫。
        午后, 沪深300指数在开盘之后继续下跌, 并于13点13分超过5%, 引发熔断,三家交易所暂停交易15分钟, 恢复交易之后, 沪深300指数继续下跌,
        并于13点34分触及7%的关口，三个交易所暂停交易至收市。
        2016年1月7日, 早盘9点42分, 沪深300指数跌幅扩大至5%, 再度触发熔断线, 两市将在9点57分恢复交易。开盘后, 仅3分钟 10:00
        沪深300指数再度快速探底, 最大跌幅7.21%, 二度熔断触及阈值。这是2016年以来的第二次提前收盘, 同时也创造了休市最快记录
        '''
        dt = day.strftime('%Y-%m-%d') if isinstance(day, pd.Timestamp) else day
        markets = []
        try:
            i = self.p._earlydays[dt]
            o, c = self.p.opens, i
        except ValueError:  # not found
            o, c = self.p.open, self.p.close

        for _o, _c in zip(o, c):
            opening = datetime.combine(dt, _o)
            if tz is not None:
                opening = tz.localize(opening).astimezone(UTC)
                opening = opening.replace(tzinfo=None)

            if _c:
                closing = datetime.combine(dt, _c)
                if tz is not None:
                    closing = tz.localize(closing).astimezone(UTC)
                    closing = closing.replace(tzinfo=None)
                markets.append((opening, closing))
        return markets
        

__all__ = ['TradingCalendar']

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
from .basicops import PeriodN
from bt_core.indicator import Indicator


class _EmaState(object):
    """Minimal incremental EMA used to chain DEMA/TEMA stages.

    Seeds with the SMA of the first `period` values (talib convention),
    then recurses ema = a*x + (1-a)*ema."""
    __slots__ = ('alpha', 'value', 'seed_sum', 'seed_cnt', 'period')

    def __init__(self, period):
        self.period = period
        self.alpha = 2.0 / (1.0 + period)
        self.value = None
        self.seed_sum = 0.0
        self.seed_cnt = 0

    def update(self, x):
        if x != x:
            return self.value
        if self.value is not None:
            self.value = self.alpha * x + (1.0 - self.alpha) * self.value
            return self.value
        self.seed_sum += x
        self.seed_cnt += 1
        if self.seed_cnt >= self.period:
            self.value = self.seed_sum / self.period
        return self.value


class DEMA(PeriodN):
    '''
    DEMA was first time introduced in 1994, in the article "Smoothing Data with
    Faster Moving Averages" by Patrick G. Mulloy in "Technical Analysis of
    Stocks & Commodities" magazine.

    It attempts to reduce the inherent lag associated to Moving Averages

    Formula:
      - dema = (2.0 - ema(data, period) - ema(ema(data, period), period)

    See:
      (None)
    '''
    alias = ('MovingAverageDoubleExponential',)

    lines = ('dema',)
    params = (('period', 14),)

    def __init__(self):
        super(DEMA, self).__init__()
        # ema2 needs p ema1 values -> first valid output at 2p-1 bars
        self.addminperiod(self.p.period)
        self._e1 = _EmaState(self.p.period)
        self._e2 = _EmaState(self.p.period)

    def _acc(self):
        v1 = self._e1.update(self.data[0])
        if v1 is not None:
            v2 = self._e2.update(v1)
            if v2 is not None:
                return 2.0 * v1 - v2
        return None

    def prenext(self):
        self._acc()

    def next(self):
        v = self._acc()
        self.line[0] = v if v is not None else float('nan')


class TEMA(PeriodN):
    '''
    TEMA was first time introduced in 1994, in the article "Smoothing Data with
    Faster Moving Averages" by Patrick G. Mulloy in "Technical Analysis of
    Stocks & Commodities" magazine.

    It attempts to reduce the inherent lag associated to Moving Averages

    Formula:
      - ema1 = ema(data, period)
      - ema2 = ema(ema1, period)
      - ema3 = ema(ema2, period)
      - tema = 3 * ema1 - 3 * ema2 + ema3

    See:
      (None)
    '''
    alias = ('MovingAverageTripleExponential',)

    lines = ('tema',)
    params = (('period', 14),)

    def __init__(self):
        super(TEMA, self).__init__()
        # ema3 needs p ema2 values (each needing p ema1 values) -> 3p-2 bars
        self.addminperiod(2 * self.p.period - 1)
        self._e1 = _EmaState(self.p.period)
        self._e2 = _EmaState(self.p.period)
        self._e3 = _EmaState(self.p.period)

    def _acc(self):
        v1 = self._e1.update(self.data[0])
        if v1 is None:
            return None
        v2 = self._e2.update(v1)
        if v2 is None:
            return None
        v3 = self._e3.update(v2)
        if v3 is None:
            return None
        return 3.0 * v1 - 3.0 * v2 + v3

    def prenext(self):
        self._acc()

    def next(self):
        v = self._acc()
        self.line[0] = v if v is not None else float('nan')

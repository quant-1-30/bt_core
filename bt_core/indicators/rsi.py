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


class RelativeStrengthIndex(PeriodN):
    '''Defined by J. Welles Wilder, Jr. in 1978 in his book *"New Concepts in
    Technical Trading Systems"*.

    It measures momentum by calculating the ration of higher closes and
    lower closes after having been smoothed by an average, normalizing
    the result between 0 and 100

    Formula:
      - up = upday(data)
      - down = downday(data)
      - maup = movingaverage(up, period)
      - madown = movingaverage(down, period)
      - rs = maup / madown
      - rsi = 100 - 100 / (1 + rs)

    The moving average used is the one originally defined by Wilder,
    the SmoothedMovingAverage

    See:
      - http://en.wikipedia.org/wiki/Relative_strength_index

    Notes:
      - ``safediv`` (default: False) If this parameter is True the division
        rs = maup / madown will be checked for the special cases in which a
        ``0 / 0`` or ``x / 0`` division will happen

      - ``safehigh`` (default: 100.0) will be used as RSI value for the
        ``x / 0`` case

      - ``safelow``  (default: 50.0) will be used as RSI value for the
        ``0 / 0`` case
    '''
    alias = ('RSI',)

    lines = ('rsi',)
    params = (('period', 14),)

    def __init__(self):
        super(RelativeStrengthIndex, self).__init__()
        # talib.RSI lookback == period (first valid output needs period+1
        # samples); PeriodN already added `period`, so net +1 via addminperiod(2)
        # (LineSingle.addminperiod subtracts the overlapping base period)
        self.addminperiod(2)
        # Wilder running state, seeded with the mean of the first `period`
        # gains/losses (identical to the talib seeding convention)
        self._prev = None
        self._avg_gain = None
        self._avg_loss = None
        self._sg = 0.0
        self._sl = 0.0
        self._n = 0

    def _acc(self):
        x = self.data[0]
        if x != x:
            return
        if self._prev is not None:
            d = x - self._prev
            g = d if d > 0.0 else 0.0
            l = -d if d < 0.0 else 0.0
            p = self.p.period
            if self._avg_gain is None:
                self._sg += g
                self._sl += l
                self._n += 1
                if self._n >= p:
                    self._avg_gain = self._sg / p
                    self._avg_loss = self._sl / p
            else:
                self._avg_gain = (self._avg_gain * (p - 1) + g) / p
                self._avg_loss = (self._avg_loss * (p - 1) + l) / p
        self._prev = x

    def _rsi(self):
        if self._avg_gain is None:
            return float('nan')
        if self._avg_loss == 0.0:
            # no losses in window: pure uptrend -> 100, flat -> 50
            return 100.0 if self._avg_gain > 0.0 else 50.0
        rs = self._avg_gain / self._avg_loss
        return 100.0 - 100.0 / (1.0 + rs)

    def prenext(self):
        self._acc()

    def next(self):
        self._acc()
        self.line[0] = self._rsi()

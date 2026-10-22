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
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)
import collections
from .basicops import PeriodN
from bt_core.indicator import Indicator


class AdaptiveMovingAverage(PeriodN):
    '''
    Defined by Perry Kaufman in his book `"Smarter Trading"`.

    It is A Moving Average with a continuously scaled smoothing factor by
    taking into account market direction and volatility. The smoothing factor
    is calculated from 2 ExponetialMovingAverage smoothing factors, a fast one
    and slow one.

    If the market trends the value will tend to the fast ema smoothing
    period. If the market doesn't trend it will move towards the slow EMA
    smoothing period.

    It is a subclass of SmoothingMovingAverage, overriding once to account for
    the live nature of the smoothing factor

    Formula:
      - direction = close - close_period
      - volatility = sumN(abs(close - close_n), period)
      - effiency_ratio = abs(direction / volatility)
      - fast = 2 / (fast_period + 1)
      - slow = 2 / (slow_period + 1)

      - smfactor = squared(efficienty_ratio * (fast - slow) + slow)
      - smfactor1 = 1.0  - smfactor

      - The initial seed value is a SimpleMovingAverage

    See also:
      - http://fxcodebase.com/wiki/index.php/Kaufman's_Adaptive_Moving_Average_(KAMA)
      - http://www.metatrader5.com/en/terminal/help/analytics/indicators/trend_indicators/ama
      - http://help.cqg.com/cqgic/default.htm#!Documents/adaptivemovingaverag2.htm
    '''
    alias = ('KAMA', 'MovingAverageAdaptive',)
    lines = ('kama',)
    params = (('period', 30),)

    # talib KAMA internal fast/slow constants
    _FAST_SC = 2.0 / 3.0        # 2 / (2 + 1)
    _SLOW_SC = 2.0 / 31.0       # 2 / (30 + 1)

    def __init__(self):
        super(AdaptiveMovingAverage, self).__init__()
        # talib.KAMA lookback == period+1 (seed SMA at period-1, first
        # recursion output one bar later)
        self.addminperiod(2)
        self._kama = None
        self._seed_cnt = 0
        # incremental state: last p closes (for direction) and last p
        # abs-deltas with their running sum (for volatility) - both O(1)/bar
        self._closes = collections.deque(maxlen=self.p.period)
        self._deltas = collections.deque(maxlen=self.p.period)
        self._dsum = 0.0

    def _acc(self):
        x = self.data[0]
        if x != x:
            return
        p = self.p.period

        prev = self._closes[-1] if self._closes else None
        if prev is not None:
            d = abs(x - prev)
            if len(self._deltas) == p:
                self._dsum -= self._deltas[0]
            self._deltas.append(d)
            self._dsum += d

        if self._kama is None:
            self._seed_cnt += 1
            self._closes.append(x)
            if self._seed_cnt >= p:
                # talib convention (verified numerically): seed with the
                # price at index period-1 itself, NOT with an SMA; the
                # recursion starts on the following bar
                self._kama = x
            return

        # direction = |x[t] - x[t-p]|: _closes currently holds x[t-p..t-1]
        if len(self._closes) == p:
            direction = abs(x - self._closes[0])
            er = direction / self._dsum if self._dsum > 0.0 else 0.0
            sc = (er * (self._FAST_SC - self._SLOW_SC) + self._SLOW_SC) ** 2
            self._kama += sc * (x - self._kama)

        self._closes.append(x)

    def prenext(self):
        self._acc()

    def next(self):
        self._acc()
        self.line[0] = self._kama if self._kama is not None else float('nan')

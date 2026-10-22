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


class AverageTrueRange(PeriodN):
    '''
    Defined by J. Welles Wilder, Jr. in 1978 in his book *"New Concepts in
    Technical Trading Systems"*.

    The idea is to take the close into account to calculate the range if it
    yields a larger range than the daily range (High - Low) / high - prelcose / low - preclose

    smooth 1/n not ema 2/(n+1)

    Formula:
      - SmoothedMovingAverage(TrueRange, period)

    See:
      - http://en.wikipedia.org/wiki/Average_true_range

    '''
    alias = ('ATR',)
    lines = ('atr', 'natr')

    params = (('period', 14),)

    def __init__(self):
        super(AverageTrueRange, self).__init__()
        # talib.ATR lookback == period (TR needs prev close -> period+1 bars)
        self.addminperiod(2)
        self._prev_close = None
        self._atr = None
        self._str = 0.0
        self._n = 0

    def _tr(self):
        h, l, c = self.data.high[0], self.data.low[0], self.data.close[0]
        if h != h or l != l or c != c:
            return None
        if self._prev_close is None:
            # first bar has no prev close: TA-Lib's atr.c starts accumulating
            # TR at the SECOND bar (the degenerate h-l of bar 0 is NOT part
            # of the seed) - occupy no seed slot here
            self._prev_close = c
            return None
        pc = self._prev_close
        self._prev_close = c
        return max(h - l, abs(h - pc), abs(l - pc))

    def _acc(self):
        tr = self._tr()
        if tr is None:
            return
        p = self.p.period
        if self._atr is None:
            self._str += tr
            self._n += 1
            if self._n >= p:
                self._atr = self._str / p
        else:
            self._atr = (self._atr * (p - 1) + tr) / p

    def prenext(self):
        self._acc()

    def next(self):
        self._acc()
        c = self.data.close[0]
        if self._atr is None:
            self.lines.atr[0] = self.lines.natr[0] = float('nan')
            return
        self.lines.atr[0] = self._atr
        self.lines.natr[0] = (100.0 * self._atr / c) if c != 0.0 \
            else float('nan')

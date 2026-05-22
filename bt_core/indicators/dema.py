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
import talib
import numpy as np
from .basicops import PeriodN
from bt_core.indicator import Indicator


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
        # self.addminperiod(self.p.period) 

    def next(self):
        # np.array slice ---> view and zero_copy
        _arr  = np.asarray(self.data.array, dtype=np.float64)

        _dema = talib.DEMA(_arr, timeperiod=self.p.period) # same size / nan fill
        self.lines.dema[0] = _dema[-1]


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
        # self.addminperiod(self.p.period) 

    def next(self):
        # np.array slice ---> view and zero_copy
        _arr  = np.asarray(self.data.array, dtype=np.float64)

        _tema = talib.TEMA(_arr, timeperiod=self.p.period) # same size / nan fill
        # self.lines.dema[0] = _tema[-1]
        self.line[0] = _tema[-1]

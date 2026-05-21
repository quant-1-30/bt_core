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
from backtest.indicator import Indicator


class WeightedMovingAverage(PeriodN):
    '''
    A Moving Average which gives an arithmetic weighting to values with the
    newest having the more weight

    Formula:
      - weights = range(1, period + 1)
      - coef = 2 / (period * (period + 1))
      - movav = coef * Sum(weight[i] * data[period - i] for i in range(period))

    See also:
      - http://en.wikipedia.org/wiki/Moving_average#Weighted_moving_average
    '''
    alias = ('WMA', 'MovingAverageWeighted',)
    lines = ('wma',)
    
    params = (('period', 30),)

    def __init__(self):
        super(WeightedMovingAverage, self).__init__()
        # self.addminperiod(self.p.period)

    def next(self):
        # np.array slice ---> view and zero_copy
        _arr  = np.asarray(self.data.array, dtype=np.float64)
        _wma = talib.WMA(_arr, timeperiod=self.p.period)

        # self.lines.wma[0] = _wma[-1]
        self.line[0] = _wma[-1]

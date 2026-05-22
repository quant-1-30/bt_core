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


class ExponentialMovingAverage(PeriodN):
    '''
    A Moving Average that smoothes data exponentially over time.

    It is a subclass of SmoothingMovingAverage.

      - self.smfactor -> 2 / (1 + period)
      - self.smfactor1 -> `1 - self.smfactor`

    Formula:
      - movav = prev * (1.0 - smoothfactor) + newdata * smoothfactor

    See also:
      - http://en.wikipedia.org/wiki/Moving_average#Exponential_moving_average
    '''
    alias = ('EMA', 'MovingAverageExponential',)

    params = (('period', 14),)
    lines = ('ema',)

    def __init__(self):
        super(ExponentialMovingAverage, self).__init__()
        # self.addminperiod(self.p.period)

    def next(self):
        # np.array slice ---> view and zero_copy
        _arr  = np.asarray(self.data.array, dtype=np.float64)
        _ema = talib.EMA(_arr, timeperiod=self.p.period) # same size / nan fill

        # self.lines.ema[0] = _ema[-1]
        self.line[0] = _ema[-1]

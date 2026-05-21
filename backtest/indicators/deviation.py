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
# from backtest.indicator import Indicator


class StandardDeviation(PeriodN):
    '''
    Calculates the standard deviation of the passed data for a given period

    Note:
      - If 2 datas are provided as parameters, the 2nd is considered to be the
        mean of the first

      - ``safepow`` (default: False) If this parameter is True, the standard
        deviation will be calculated as pow(abs(meansq - sqmean), 0.5) to safe
        guard for possible negative results of ``meansq - sqmean`` caused by
        the floating point representation.

    Formula:
      - meansquared = SimpleMovingAverage(pow(data, 2), period)
      - squaredmean = pow(SimpleMovingAverage(data, period), 2)
      - stddev = pow(meansquared - squaredmean, 0.5)  # square root

    See:
      - http://en.wikipedia.org/wiki/Standard_deviation
    '''
    alias = ('StdDev',)

    lines = ('stddev',)
    params = (('period', 20), ('nbev', 1.0),)

    def __init__(self):
        super(StandardDeviation, self).__init__() 
        # self.addminperiod(self.p.period)

    def next(self):
        _arr = np.asarray(self.data.array, dtype=np.float64)
        _std = talib.STDDEV(_arr, self.p.period, self.p.nbev)

        # self.lines.stddev[0] = _std[-1]
        self.line[0] = _std[-1]

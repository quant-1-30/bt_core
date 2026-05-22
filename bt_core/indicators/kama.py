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
import talib
import numpy as np
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

    def __init__(self):
        super(AdaptiveMovingAverage, self).__init__()
        # self.addminperiod(self.p.period)

    def next(self):
        # np.array slice ---> view and zero_copy
        _arr  = np.asarray(self.data.array, dtype=np.float64)
        _kama = talib.KAMA(_arr, timeperiod=self.p.period)

        # self.lines.kama[0] = _kama[-1]
        self.line[0] = _kama[-1]

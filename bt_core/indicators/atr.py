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
from bt_core.logic import Max, Min
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
        # self.addminperiod(self.p.period) # ATR recursive smoothing 2/(n+1)

    def next(self):
        # np.array slice ---> view and zero_copy
        h = np.asarray(self.data.high.array, dtype=np.float64)
        l = np.asarray(self.data.low.array, dtype=np.float64)
        c = np.asarray(self.data.close.array, dtype=np.float64)

        _atr = talib.ATR(h, l, c, timeperiod=self.p.period) 
        _natr = talib.NATR(h, l, c, timeperiod=self.p.period) # normalize atr

        self.lines.atr[0] = _atr[-1]
        self.lines.natr[0] = _natr[-1]

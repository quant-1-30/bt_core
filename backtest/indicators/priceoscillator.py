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
from backtest.indicator import Indicator


class AbsolutePriceOscillator(Indicator):
    '''
    Shows the difference between a short and long exponential moving
    averages expressed in points. 

    Formula:
      - apo = ema(short) - ema(long)
      - ppo = 100 * (ema(short) - ema(long)) / ema(long)

    See:
      - http://www.metastock.com/Customer/Resources/TAAZ/?c=3&p=94
    '''
    alias = ('PriceOsc', 'AbsolutePriceOscillator', 'APO', 'AbsPriceOsc',)
    lines = ('apo',)
    
    params = (('fast', 12), ('slow', 26), ('matype', 0), ) # MA_TypeSMA

    def __init__(self):
        super(MACD, self).__init__()
        period = self.p.fast + self.p.slow
        self.addminperiod(period) 

    def next(self):
        _arr  = np.asarray(self.data.array, dtype=np.float64)
        _apo = talib.APO(_arr, self.p.fast, self.p.slow, self.p.matype)

        # self.lines.apo[0] = _apo[-1]
        self.line[0] = _apo[-1]

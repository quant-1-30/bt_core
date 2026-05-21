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
import backtest.indicator as btind


class MACD(btind.Indicator):
    '''
    Moving Average Convergence Divergence. Defined by Gerald Appel in the 70s.

    It measures the distance of a short and a long term moving average to
    try to identify the trend.

    A second lagging moving average over the convergence-divergence should
    provide a "signal" upon being crossed by the macd

    Formula:
      - macd = ema(data, me1_period) - ema(data, me2_period)
      - signal = ema(macd, signal_period)
      - histo = macd - signal

    See:
      - http://en.wikipedia.org/wiki/MACD
    '''
    lines = ('macd', 'signal', 'histo')
    params = (('fast', 12), ('slow', 26), ('period', 9),)

    def __init__(self):
        super(MACD, self).__init__()
        period = self.p.fast + self.p.slow + self.p.period 
        self.addminperiod(period) 
        
    def next(self):
        _arr  = np.asarray(self.data.array, dtype=np.float64)
        macd, signal, histo = talib.MACD(_arr, self.p.fast, self.p.slow, self.p.period)

        self.lines.macd[0] = macd[-1]
        self.lines.signal[0] = signal[-1]
        self.lines.histo[0] = histo[-1]

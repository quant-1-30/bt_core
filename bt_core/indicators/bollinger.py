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


class BollingerBands(PeriodN):
    alias = ('BBands',)
    lines = ('up', 'mid', 'low',)

    params = (('period', 20), ('devfactor', 2.0), ('matype', 0),) # matype=0 Simple Moving Average (SMA)

    def __init__(self):
        super(BollingerBands, self).__init__()
        # self.addminperiod(self.p.period)

    def next(self):
        _arr = np.asarray(self.data.array, dtype=np.float64)

        upper, middle, lower = talib.BBANDS(
            _arr, 
            timeperiod=self.p.period, 
            nbdevup=self.p.devfactor, # N times std 
            nbdevdn=self.p.devfactor, 
            matype=self.p.matype
        )
        self.lines.up[0] = upper[-1]
        self.lines.mid[0] = middle[-1]
        self.lines.low[0] = lower[-1]

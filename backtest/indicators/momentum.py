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


class Momentum(PeriodN):
    '''
    Measures the change in price by calculating the difference between the
    current price and the price from a given period ago


    Formula:
      - momentum = data - data_period

    See:
      - http://en.wikipedia.org/wiki/Momentum_(technical_analysis)
    '''
    lines = ('momentum',)
    params = (('period', 12),)

    def __init__(self):
        super(Momentum, self).__init__()
        # self.addminperiod(self.p.period) 
        
    def next(self):
        _mom = talib.MOM(self.data.array, timeperiod=self.p.period) # Momentum

        # self.lines.momentum[0] = _mom[-1]
        self.line[0] = _mom[-1]

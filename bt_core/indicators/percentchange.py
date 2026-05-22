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


__all__ = ['PercentChange']


class PercentChange(PeriodN):
    '''
      Measures the perccentage change of the current value with respect to that
      of period bars ago
      ROC	Rate of change : ((price/prevPrice)-1)*100
      ROCP	Rate of change Percentage: (price-prevPrice)/prevPrice
      ROCR	Rate of change ratio: (price/prevPrice)

    '''
    alias = ('PctChange',)
    lines = ('roc', 'rocp', 'rocr')

    # Fancy plotting name
    plotlines = dict(pctchange=dict(_name='%change'))

    # update value to standard for Moving Averages
    params = (('period', 30),)

    def __init__(self):
        super(PercentChange, self).__init__()
        # self.addminperiod(self.p.period)

    def next(self):
        _arr  = np.asarray(self.data.array, dtype=np.float64)

        _roc = talib.ROC(_arr, self.p.period)
        _rocp = talib.ROCP(_arr, self.p.period)
        _rocr = talib.ROCR(_arr, self.p.period)

        self.lines.roc[0] = _roc[-1]
        self.lines.rocp[0] = _rocp[-1]
        self.lines.rocr[0] = _rocr[-1]

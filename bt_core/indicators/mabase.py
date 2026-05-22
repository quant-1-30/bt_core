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
import bt_core.indicator as btind
from .basicops import PeriodN


class MovingAverage(PeriodN):

    alias = ('EMA', 'MovingAverage',)

    lines = ('ma',)
    params = (('period', 30),)

    def __init__(self):
        super(ExponentialMovingAverage, self).__init__()
        # self.addminperiod(self.p.period)

    def next(self):
        # np.array slice ---> view and zero_copy
        _arr  = np.asarray(self.data.array, dtype=np.float64)
        _ma = talib.MA(_arr, timeperiod=self.p.period) # same size / nan fill

        # self.lines.ma[0] = _ma[-1]
        self.line[0] = _ma[-1]

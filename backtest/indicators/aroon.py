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


class AroonOscillator(PeriodN):
    '''
    Base class which does the calculation of the AroonUp/AroonDown values and
    defines the common parameters.

    It uses the class attributes _up and _down (boolean flags) to decide which
    value has to be calculated.

    Values are not assigned to lines but rather stored in the "up" and "down"
    instance variables, which can be used by subclasses to for assignment or
    further calculations
    '''
    alias = ('AroonUpDownOsc',)
    params = (('period', 14),)
    lines = ('aroonup', 'aroondown', 'aroonosc')

    def __init__(self):
        super(_AroonBase, self).__init__()
        # self.addminperiod(self.p.period) # period + 1 

    def next(self):
        # np.array slice ---> view and zero_copy
        h = np.asarray(self.data.high.array, dtype=np.float64)
        l = np.asarray(self.data.low.array, dtype=np.float64)

        (down, up)= talib.AROON(h, l, timeperiod=self.p.period) # same size / nan fill
        self.lines.aroondown[0] = down[-1]
        self.lines.aroonup[0] = up[-1]

        osc = talib.AROONOSC(h, l, timeperiod=self.p.period)
        self.lines.aroonosc[0] = osc[-1]

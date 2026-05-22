#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015-2023 Daniel Rodriguez
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Ssoftware Foundation, either version 3 of the License, or
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
from bt_core.indicator import Indicator


__all__ = ['AccelerationDecelerationOscillator', 'AccDeOsc']


class AccelerationDecelerationOscillator(Indicator):
    '''
    Acceleration/Deceleration Technical Indicator (AC) measures acceleration
    and deceleration of the current driving force. This indicator will change
    direction before any changes in the driving force, which, it its turn, will
    change its direction before the price.

    Formula:
     - AcdDecOsc = AwesomeOscillator - SMA(AwesomeOscillator, period)

    See:
      - https://www.metatrader5.com/en/terminal/help/indicators/bw_indicators/ao
      - https://www.ifcmarkets.com/en/ntx-indicators/ntx-indicators-accelerator-decelerator-oscillator

    '''
    alias = ('AccDeOsc', 'AC')
    lines = ('accde', )

    params = (
        ('period', 5),  
        ('fast', 5),    
        ('slow', 34),   
    )

    def __init__(self):
        super(AccelerationDecelerationOscillator, self).__init__()
        self.addminperiod(self.p.slow + self.p.period - 1)

    def next(self):
        h = np.asarray(self.data.high.array, dtype=np.float64)
        l = np.asarray(self.data.low.array, dtype=np.float64)

        # ao
        median = (h + l) / 2.0
        ao_array = talib.SMA(median, self.p.fast) - talib.SMA(median, self.p.slow)
        ao_sma = talib.SMA(ao_array, timeperiod=self.p.period)

        self.lines.accde[0] = ao_array[-1] - ao_sma[-1]

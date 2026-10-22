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
import collections
import math
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
        # ring of the last `period` AO values for the SMA of AO; filled from
        # the first bar where AO exists (slow) so the window is full exactly
        # at minperiod
        self._ao_hist = collections.deque(maxlen=self.p.period)
        self._ao_sum = 0.0

    def _ao(self):
        fast, slow = self.p.fast, self.p.slow
        hf = math.fsum(self.data.high.get(size=fast))
        lf = math.fsum(self.data.low.get(size=fast))
        hs = math.fsum(self.data.high.get(size=slow))
        ls = math.fsum(self.data.low.get(size=slow))
        return (hf + lf) / (2.0 * fast) - (hs + ls) / (2.0 * slow)

    def _push_ao(self):
        if len(self.data) >= self.p.slow:
            ao = self._ao()
            if ao == ao:
                if len(self._ao_hist) == self.p.period:
                    self._ao_sum -= self._ao_hist[0]
                self._ao_hist.append(ao)
                self._ao_sum += ao

    def prenext(self):
        self._push_ao()

    def next(self):
        self._push_ao()
        if not self._ao_hist:
            self.lines.accde[0] = float('nan')
            return
        ao = self._ao_hist[-1]
        ao_sma = self._ao_sum / len(self._ao_hist)
        self.lines.accde[0] = ao - ao_sma

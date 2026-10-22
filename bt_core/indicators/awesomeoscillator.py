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
import math
from bt_core.indicator import Indicator


class AwesomeOscillator(Indicator):
    '''
    Awesome Oscillator (AO) is a momentum indicator reflecting the precise
    changes in the market driving force which helps to identify the trends
    strength up to the points of formation and reversal.


    Formula:
     - median price = (high + low) / 2
     - AO = SMA(median price, 5)- SMA(median price, 34)

    See:
      - https://www.metatrader5.com/en/terminal/help/indicators/bw_indicators/awesome
      - https://www.ifcmarkets.com/en/ntx-indicators/awesome-oscillator

    '''
    alias = ('AwesomeOsc', 'AO')
    lines = ('ao',)

    params = (
        ('fast', 5),
        ('slow', 34),
    )

    plotlines = dict(ao=dict(_method='bar', alpha=0.50, width=1.0))

    def __init__(self):
        super(AwesomeOscillator, self).__init__()
        self.addminperiod(self.p.slow)

    def next(self):
        # logical windows via get(); SMA(median, n) = (sum_h + sum_l) / (2n)
        fast, slow = self.p.fast, self.p.slow
        hf = math.fsum(self.data.high.get(size=fast))
        lf = math.fsum(self.data.low.get(size=fast))
        hs = math.fsum(self.data.high.get(size=slow))
        ls = math.fsum(self.data.low.get(size=slow))
        sma_fast = (hf + lf) / (2.0 * fast)
        sma_slow = (hs + ls) / (2.0 * slow)

        self.line[0] = sma_fast - sma_slow

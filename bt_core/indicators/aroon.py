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
        super(AroonOscillator, self).__init__()
        # talib.AROON/AROONOSC lookback == period: first valid output needs
        # period+1 samples (PeriodN already added `period`, net +1 here)
        self.addminperiod(2)

    def next(self):
        # logical windows via get(); talib AROON uses p+1 samples:
        # aroon = 100 * (period - bars_since_extreme) / period
        p = self.p.period
        hw = self.data.high.get(size=p + 1)
        lw = self.data.low.get(size=p + 1)
        hl = list(hw)
        ll = list(lw)
        # reversed index == bars-ago (0 = current bar), ties -> most recent
        up_bars_ago = hl[::-1].index(max(hl))
        dn_bars_ago = ll[::-1].index(min(ll))
        self.lines.aroonup[0] = 100.0 * (p - up_bars_ago) / p
        self.lines.aroondown[0] = 100.0 * (p - dn_bars_ago) / p
        self.lines.aroonosc[0] = self.lines.aroonup[0] - self.lines.aroondown[0]

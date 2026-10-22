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
import math
from bt_core.indicator import Indicator
from .dema import _EmaState


class AbsolutePriceOscillator(Indicator):
    '''
    Shows the difference between a short and long exponential moving
    averages expressed in points. 

    Formula:
      - apo = ema(short) - ema(long)
      - ppo = 100 * (ema(short) - ema(long)) / ema(long)

    See:
      - http://www.metastock.com/Customer/Resources/TAAZ/?c=3&p=94
    '''
    alias = ('PriceOsc', 'AbsolutePriceOscillator', 'APO', 'AbsPriceOsc',)
    lines = ('apo',)
    
    params = (('fast', 12), ('slow', 26), ('matype', 0), ) # MA_TypeSMA

    def __init__(self):
        super(AbsolutePriceOscillator, self).__init__()
        period = self.p.fast + self.p.slow
        self.addminperiod(period)
        # matype 0 (default) keeps the historical SMA-based output;
        # any other matype uses the documented EMA form. Both are
        # incremental and ring-safe.
        self._st_f = _EmaState(self.p.fast)
        self._st_s = _EmaState(self.p.slow)

    def _update_ema(self):
        if self.p.matype != 0:
            x = self.data[0]
            self._st_f.update(x)
            self._st_s.update(x)

    def prenext(self):
        self._update_ema()

    def next(self):
        self._update_ema()
        if self.p.matype == 0:
            fast, slow = self.p.fast, self.p.slow
            sf = math.fsum(self.data.get(size=fast)) / fast
            ss = math.fsum(self.data.get(size=slow)) / slow
            self.line[0] = sf - ss
            return
        vf, vs = self._st_f.value, self._st_s.value
        self.line[0] = float('nan') if (vf is None or vs is None) else (vf - vs)

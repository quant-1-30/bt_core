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
from .basicops import PeriodN


class CommodityChannelIndex(PeriodN):
    '''
    Introduced by Donald Lambert in 1980 to measure variations of the
    "typical price" (see below) from its mean to identify extremes and
    reversals

    Formula:
      - tp = typical_price = (high + low + close) / 3
      - tpmean = MovingAverage(tp, period)
      - deviation = tp - tpmean
      - meandev = MeanDeviation(tp)
      - cci = deviation / (meandeviation * factor)

    See:
      - https://en.wikipedia.org/wiki/Commodity_channel_index
    '''
    alias = ('CCI',)

    lines = ('cci',)
    params = (('period', 14),)

    def __init__(self):
        super(CommodityChannelIndex, self).__init__()
        # self.addminperiod(self.p.period)

    def next(self):
        # logical windows via get(); talib constant 0.015
        p = self.p.period
        hw = self.data.high.get(size=p)
        lw = self.data.low.get(size=p)
        cw = self.data.close.get(size=p)
        tps = [(h + l + c) / 3.0 for h, l, c in zip(hw, lw, cw)]
        tp0 = tps[-1]
        tmean = math.fsum(tps) / p
        mdev = math.fsum(abs(tp - tmean) for tp in tps) / p
        if mdev == 0.0:
            self.line[0] = 0.0
        else:
            self.line[0] = (tp0 - tmean) / (0.015 * mdev)

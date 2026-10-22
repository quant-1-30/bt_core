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
import bt_core.indicator as btind
from .dema import _EmaState


class MACD(btind.Indicator):
    '''
    Moving Average Convergence Divergence. Defined by Gerald Appel in the 70s.

    It measures the distance of a short and a long term moving average to
    try to identify the trend.

    A second lagging moving average over the convergence-divergence should
    provide a "signal" upon being crossed by the macd

    Formula:
      - macd = ema(data, me1_period) - ema(data, me2_period)
      - signal = ema(macd, signal_period)
      - histo = macd - signal

    See:
      - http://en.wikipedia.org/wiki/MACD
    '''
    lines = ('macd', 'signal', 'histo')
    params = (('fast', 12), ('slow', 26), ('period', 9),)

    def __init__(self):
        super(MACD, self).__init__()
        period = self.p.fast + self.p.slow + self.p.period
        self.addminperiod(period)
        # incremental stages; each EMA seeds with the SMA of its first
        # `period` values (talib convention), so the values are exact
        self._st_f = _EmaState(self.p.fast)
        self._st_s = _EmaState(self.p.slow)
        self._st_sig = _EmaState(self.p.period)

    def _acc(self):
        x = self.data[0]
        vf = self._st_f.update(x)
        vs = self._st_s.update(x)
        if vf is None or vs is None:
            return None, None
        m = vf - vs
        vsg = self._st_sig.update(m)
        return m, vsg

    def prenext(self):
        self._acc()

    def next(self):
        m, vsg = self._acc()
        self.lines.macd[0] = m if m is not None else float('nan')
        self.lines.signal[0] = vsg if vsg is not None else float('nan')
        self.lines.histo[0] = (m - vsg) if (m is not None and vsg is not None) else float('nan')

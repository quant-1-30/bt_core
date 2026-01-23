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
import datetime
import numpy as np
import backtest as bt
from backtest.observer import Observer

__all__ = ["Benchmark"]


class Benchmark(Observer):
    '''This observer stores the *returns* of the strategy and the *return* of a
    reference asset which is one of the datas passed to the system.

    Params:

      - ``timeframe`` (default: ``None``)
        If ``None`` then the complete return over the entire backtested period
        will be reported

      - ``compression`` (default: ``None``)

        Only used for sub-day timeframes to for example work on an hourly
        timeframe by specifying "TimeFrame.Minutes" and 60 as compression

      - ``data`` (default: ``None``)

        Reference asset to track to allow for comparison.

        .. note:: this data must have been added to a ``cerebro`` instance with
                  ``addata``, ``resampledata`` or ``replaydata``.

    Remember that at any moment of a ``run`` the current values can be checked
    by looking at the *lines* by name at index ``0``.

    '''

    lines = ('benchmark',)
    plotlines = dict(benchmark=dict(_name='Benchmark'))

    params = (
        ('barplot', False),
    )

    def _plotlabel(self):
        labels = super(Benchmark, self)._plotlabel()
        return labels

    def __init__(self, **kwargs):
        super(Benchmark, self).__init__()  # kwargs = self.p._getkwargs()
        self.rbench = self._owner._addanalyzer(bt.analyzers.Benchmark, **kwargs)
        self.dtcmp = np.iinfo(np.int_).min

    def next(self):
        dtcmp = self.rbench.dtcmp
        if dtcmp > self.dtcmp:
            self.lines.benchmark[0] = self.rbench.rets.get(self.rbench.dtkey1, float('NaN')) 
            self.dtcmp = dtcmp

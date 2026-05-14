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
from backtest.dataseries import TimeFrame


class TimeReturn(Observer):
    '''This observer stores the *returns* of the strategy.

    Params:

      - ``timeframe`` (default: ``None``)
        If ``None`` then the complete return over the entire backtested period
        will be reported

        Pass ``TimeFrame.NoTimeFrame`` to consider the entire dataset with no
        time constraints

      - ``compression`` (default: ``None``)

        Only used for sub-day timeframes to for example work on an hourly
        timeframe by specifying "TimeFrame.Minutes" and 60 as compression

      - ``fund`` (default: ``None``)

        If ``None`` the actual mode of the broker (fundmode - True/False) will
        be autodetected to decide if the returns are based on the total net
        asset value or on the fund value. See ``set_fundmode`` in the broker
        documentation

        Set it to ``True`` or ``False`` for a specific behavior

    Remember that at any moment of a ``run`` the current values can be checked
    by looking at the *lines* by name at index ``0``.

    '''

    lines = ('timereturn',)
    plotinfo = dict(plot=True, subplot=True)
    plotlines = dict(timereturn=dict(_name='Return'))

    params = (
        ('barplot', False), 
    )

    def _plotlabel(self):
        return [
            # Use the final tf/comp values calculated by the return analyzer
            TimeFrame.getname(self.treturn.timeframe,
                              self.treturn.compression),
            str(self.treturn.compression)
        ]

    def __init__(self, **kwargs):
        # kwargs = self.p._getkwargs()
        self.treturn = self._owner._addanalyzer(
            bt.analyzers.TimeReturn, **kwargs)
        self.dtcmp = np.iinfo(np.int_).min

    def next(self):
        dtcmp = self.treturn.dtcmp
        if dtcmp > self.dtcmp:
            self.lines.timereturn[0] = tr = self.treturn.rets.get(dtcmp, float('NaN'))

            self.dtcmp = dtcmp
            self.log_shm.publish_metric(b"TimeReturn", tr, dtcmp) # log the time return for the current datetime

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

import backtest as bt
from backtest.observer import Observer


__all__ = ["Broker"]


class Broker(Observer):
    '''This observer keeps track of the current cash amount and portfolio value in
    the broker (including the cash)

    Params:

        Set it to ``True`` or ``False`` for a specific behavior

    Params: None
    '''
    params = (
        ('timeframe', bt.TimeFrame.Days),
    )

    alias = ('CashValue',)
    lines = ('cash', 'value')

    plotinfo = dict(plot=True, subplot=True)

    def __init__(self):
        kwargs = self.p._getkwargs()
        self.vb = self._owner._addanalyzer(bt.analyzers.Broker, **kwargs)
        self.dtkey = datetime.datetime.min

    def start(self):
        self.plotlines.cash._plotskip = True
        self.plotlines.value._name = 'FundValue'

    def next(self):
        dtkey = self.vb.dtkey
        if dtkey > self.dtkey:
            v = self.vb.rets.get(dtkey, None)
            if v:
                # print("obs broker v", v)
                self.lines.value[0] = v.portfolio_value
                self.lines.cash[0] = v.cash
            
            self.dtkey = dtkey

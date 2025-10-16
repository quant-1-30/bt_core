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
from backtest.analyzers import Analyzer, TimeFrameAnalyzerBase


# class GrossLeverage(Analyzer):
class GrossLeverage(TimeFrameAnalyzerBase):
    '''This analyzer calculates the Gross Leverage of the current strategy
    on a timeframe basis

    Params:

    Methods:

      - get_analysis

        Returns a dictionary with returns as values and the datetime points for
        each return as keys
    '''

    params = (
        # ('fund', None),
    )

    def start(self):
        super(GrossLeverage, self).start()
        
    # def notify_fund(self):
    #     fundvalue, cash = self.notify.store.get_value()
    #     self._value = fundvalue
    #     self._cash = cash

    # def next(self):
    #     self.notify_fund()
    #     # Updates the leverage for "dtkey" (see base class) for each cycle
    #     # 0.0 if 100% in cash, 1.0 if no short selling and fully invested
    #     lev = (self._value - self._cash) / self._value
    #     self.rets[self.data0.datetime.datetime()] = lev

    def on_dt_over(self):
        self.notify_fund()
        v = self.strategy.get_value()
        # Updates the leverage for "dtkey" (see base class) for each cycle
        # 0.0 if 100% in cash, 1.0 if no short selling and fully invested
        lev = (v.portfolio_value - v.cash) / v.portfolio_value
        self.rets[self.dtkey] = lev

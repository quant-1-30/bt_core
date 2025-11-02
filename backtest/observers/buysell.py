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
import datetime

import backtest as bt
from backtest.observer import Observer

__all__ = ["BuySell"]


class BuySell(Observer):
    '''
    This observer keeps track of the individual buy/sell orders (individual
    executions) and will plot them on the chart along the data around the
    execution price level

    Params:
      - ``barplot`` (default: ``False``) Plot buy signals below the minimum and
        sell signals above the maximum.

        If ``False`` it will plot on the average price of executions during a
        bar

      - ``bardist`` (default: ``0.015`` 1.5%) Distance to max/min when
    '''
    lines = ('buy', 'sell', 'comm', 'pnlplus', 'pnlminus')

    plotinfo = dict(plot=True, subplot=False, plotlinelabels=True)
    plotlines = dict(
        buy=dict(marker='^', markersize=8.0, color='lime',
                 fillstyle='full', ls=''),
        sell=dict(marker='v', markersize=8.0, color='red',
                  fillstyle='full', ls='')
    )

    params = (
        ('barplot', False),  # plot above/below max/min for clarity in bar plot
        ('timeframe', bt.TimeFrame.Days),
    )

    def __init__(self):
        self.txns = self._owner._addanalyzer(bt.analyzers.Transactions)
        self.dtkey = datetime.datetime.min

    def next(self):
        dtkey = self.txns.dtkey
        if dtkey > self.dtkey:
            _trades = self.txns.rets(self.txns.dtkey, [])
            buy = list()
            sell = list()
            comm = 0.0

            for order_bit in _trades: # records
                if not order_bit.executed_zie:
                    continue
                comm += order_bit.comm

                if order_bit.direction> 0:
                    buy.append(order_bit)
                else:
                    sell.append(order_bit)

            # Write comm
            self.lines.comm[0] = comm
            # BUY
            curbuy = self.lines.buy[0]
            if curbuy != curbuy:  # NaN
                curbuy = 0.0
                self.curbuylen = curbuylen = 0
            else:
                curbuylen = self.curbuylen

            buyops = (curbuy + math.fsum(buy))
            buylen = curbuylen + len(buy)

            buyops =math.fsum([b.executed_price * b.executed_size for b in buy]) # fsum is suitable for floats
            buylen = sum([b.executed_size for b in buy])  

            value = buyops / float(buylen or 'NaN')
            self.lines.buy[0] = (value + curbuy)/2

            # SELL
            cursell = self.lines.sell[0]
            if cursell != cursell:  # NaN
                cursell = 0.0

            sellops =math.fsum([s.executed_price * s.executed_size for s in sell]) # fsum is suitable for floats
            selllen = sum([s.executed_size for s in sell])  

            value = sellops / float(selllen or 'NaN')
            self.lines.sell[0] = (value + cursell)/2

            # Pnl
            for pobj in self._owner.store.get_position():
                pnl = pobj.pnl

                if pnl >= 0.0:
                    self.lines.pnlplus[0] = pnl
                else:
                    self.lines.pnlminus[0] = pnl

            self.dtkey = dtkey

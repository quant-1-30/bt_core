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
import numpy as np
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
    lines = ('buy', 'sell') # 'comm'

    plotinfo = dict(plot=True, subplot=False, plotlinelabels=True)

    plotlines = dict(
        buy=dict(marker='^', markersize=8.0, color='lime',
                 fillstyle='full', ls=''),
        sell=dict(marker='v', markersize=8.0, color='red',
                  fillstyle='full', ls='')
    )

    params = (
        ('barplot', False), 
    )

    def __init__(self):
        self.txns = self._owner._addanalyzer(bt.analyzers.Transactions)
        self.dtcmp = np.iinfo(np.int_).min

    def next(self):
        dtcmp = self.txns.dtcmp
        
        if dtcmp > self.dtcmp:
            comm = 0.0
            buy,sell = [], []

            trades = self.txns.rets.get(dtcmp, [])
            if trades:
                for trade in trades:
                    print("trade ", trade)
                    if not trade["executed_size"]:
                        continue
                    comm += trade["comm"]

                    if trade["isbuy"]:
                        buy.append(trade)
                    else:
                        sell.append(trade)

                # curbuy = self.lines.avg_buy[0]
                # if curbuy != curbuy:  # NaN
                #     curbuy = 0.0

                # buyops =math.fsum([b.executed_price * b.executed_size for b in buy]) # fsum is suitable for floats
                # buylen = sum([b.executed_size for b in buy])  
                buyops = np.sum([b["executed_price"] * b["executed_size"] for b in buy]) # fsum is suitable for floats
                buylen = np.sum([b["executed_size"] for b in buy])  

                value = buyops / float(buylen or 'NaN') # buylen = 0 -> NaN
                self.lines.buy[0] = value 
                
                self.log_shm.publish_metric(b"BuyPrice", value, dtcmp) # log the buy price for the current datetime

                # sellops =math.fsum([s.executed_price * s.executed_size for s in sell]) # fsum is suitable for floats
                # selllen = sum([s.executed_size for s in sell])  
                sellops = np.sum([s["executed_price"] * s["executed_size"] for s in sell]) # fsum is suitable for floats
                selllen = np.sum([s["executed_size"] for s in sell])  

                value = sellops / float(selllen or 'NaN')
                self.lines.sell[0] = value 
                
                self.log_shm.publish_metric(b"SellPrice", value, dtcmp) # log the sell price for the current datetime
            
                # # Write comm
                # self.lines.comm[0] = comm
                self.log_shm.publish_metric(b"Commission", comm, dtcmp) # log the commission for the current datetime

            self.dtcmp = dtcmp

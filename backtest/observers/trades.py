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
import numpy as np
import datetime

import backtest as bt
# from backtest import analyzers
from backtest.observer import Observer


class Trades(Observer):
    '''This observer keeps track of full trades and plot the PnL level achieved
    when a trade is closed.

    A trade is open when a position goes from 0 (or crossing over 0) to X and
    is then closed when it goes back to 0 (or crosses over 0 in the opposite
    direction)

    Params:
      - ``pnlcomm`` (def: ``True``)

        Show net/profit and loss, i.e.: after commission. If set to ``False``
        if will show the result of trades before commission
    '''
    
    # # Generate plotlines info
    # markers = ['o', 'v', '^', '<', '>', '1', '2', '3', '4', '8', 's', 'p',
    #            '*', 'h', 'H', '+', 'x', 'D', 'd']

    # colors = ['b', 'g', 'r', 'c', 'm', 'y', 'k', 'b', 'g', 'r', 'c', 'm',
    #           'y', 'k', 'b', 'g', 'r', 'c', 'm']

    # basedict = dict(ls='', markersize=8.0, fillstyle='full')

    # plines = dict()
    # for lname, marker, color in zip(lnames, markers, colors):
    #     plines[lname] = d = basedict.copy()
    #     d.update(marker=marker, color=color)

    _stclock = True

    lines = ('pnlplus', 'pnlminus')

    params = (
        ("pnlcomm", True),
        ('timeframe', bt.TimeFrame.Days),
    )

    plotinfo = dict(plot=True, subplot=True,
                    plotname='Trades - Net Profit/Loss',
                    plotymargin=0.10,
                    plothlines=[0.0])

    plotlines = dict(
        pnlplus=dict(_name='Positive',
                     ls='', marker='o', color='blue',
                     markersize=8.0, fillstyle='full'),
        pnlminus=dict(_name='Negative',
                      ls='', marker='o', color='red',
                      markersize=8.0, fillstyle='full')
    )
    def __init__(self):
        self.preturn = self._owner._addanalyzer(
            bt.analyzers.PositionsValue)
        self.dtkey = datetime.datetime.min

    def next(self):
        dtkey = self.preturn.dtkey
        pnl_obj = self.preturn.rets.get(dtkey, None)
        if dtkey > self.dtkey and pnl_obj:
            pnls = np.array([p.pnl for p in pnl_obj]) if pnl_obj else np.zeros([])
            pnl = np.sum(pnls)

            if pnl >= 0.0:
                self.lines.pnlplus[0] = pnl
            else:
                self.lines.pnlminus[0] = pnl

            self.dtkey = dtkey

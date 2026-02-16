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

import backtest as bt
from backtest.utils import AutoOrderedDict


class TradeAnalyzer(bt.TimeFrameAnalyzerBase):
    '''
    Provides statistics on closed trades (keeps also the count of open ones)

      - Total Open/Closed Trades

      - Streak Won/Lost Current/Longest

      - ProfitAndLoss Total/Average

      - Won/Lost Count/ Total PNL/ Average PNL / Max PNL

      - Length (bars in the market)

        - Total/Average/Max/Min

        - Won/Lost Total/Average/Max/Min

    Note:

      The analyzer uses an "auto"dict for the fields, which means that if no
      trades are executed, no statistics will be generated.

      In that case there will be a single field/subfield in the dictionary
      returned by ``get_analysis``, namely:

        - dictname['total']['total'] which will have a value of 0 (the field is
          also reachable with dot notation dictname.total.total
    '''
    params = (
        ('timeframe', bt.TimeFrame.Days),
        ('compression', None),
    )
    
    def __init__(self):
        self.rets.total.total = 0

    def on_dt_over(self):
        snap = self._owner.get_snapshot()
        p = snap.positions
        for p_obj in p:
            pnl = p_obj.pnl

            if p_obj.isclosed:
                # Trade just closed
                self.total.closed += 1
                won = int(p_obj.pnl >= 0.0)
                if won:
                    ret_won = self.rets.won
                    ret_won.count += won
                    ret_won.net.total += pnl
                    ret_won.max = max(pnl, ret_won.max)
                else:
                    ret_loss = self.rets.loss
                    ret_loss.count = int(not won)
                    ret_loss.net.total += pnl
                    ret_loss.min = min(pnl, ret_loss.min)

                trpnl = self.rets.pnl
                trpnl.net.total += pnl
                trpnl.net.average = self.rets.pnl.net.total / self.rets.total.closed

    def calcuate_total(self):
        # caculate total
        _trades = self._owner._trades

        _size = np.array([_t.executed_size for _t in _trades])
        _isbuy = np.array([1 if _t.isbuy else -1 for _t in _trades ])
        executed_size = _size * _isbuy
        cum_size = np.cumsum(executed_size)
        zero_indices = np.nonzero(cum_size == 0)
        total = len(zero_indices) + 1
        return total

    def stop(self):
        super(TradeAnalyzer, self).stop()
        self.rets.total.total = self.calcuate_total()

        # Won/Lost statistics
        self.rets.won.won_rate = self.rets.won.count / self.rets.total.total
        self.rets.loss.lost_rate = self.rets.lost.count / self.rets.total.total

        self.rets._close()  # . notation cannot create more keys

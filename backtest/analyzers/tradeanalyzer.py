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

from backtest.analyzer import Analyzer, TimeFrameAnalyzerBase
from backtest.utils import AutoOrderedDict, AutoDict


# class TradeAnalyzer(Analyzer):
class TradeAnalyzer(TimeFrameAnalyzerBase):
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
    def create_analysis(self):
        self.rets = AutoOrderedDict()
        self.rets.total.total = 0

    def on_dt_over(self):
        _, v = self._owner.getvalue()
        for p_obj in v:
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

    def stop(self):
        super(TradeAnalyzer, self).stop()
        # estimate total

        # _trades = self._owner._trades
        # self.rets.total.total += 1

        # Won/Lost statistics
        self.rets.won.won_rate = self.rets.won.count / self.rets.total.total
        self.rets.loss.lost_rate = self.rets.lost.count / self.rets.total.total

        self.rets._close()  # . notation cannot create more keys

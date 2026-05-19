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

import backtest as bt
from backtest.utils.mathsupport import average, standarddev


class SQN(bt.TimeFrameAnalyzerBase):
    '''SQN or SystemQualityNumber. Defined by Van K. Tharp to categorize trading
    systems.

      - 1.6 - 1.9 Below average
      - 2.0 - 2.4 Average
      - 2.5 - 2.9 Good
      - 3.0 - 5.0 Excellent
      - 5.1 - 6.9 Superb
      - 7.0 -     Holy Grail?

    The formula:

      - SquareRoot(NumberTrades) * Average(TradesProfit) / StdDev(TradesProfit)

    The sqn value should be deemed reliable when the number of trades >= 30

    Methods:

      - get_analysis

        Returns a dictionary with keys "sqn" and "trades" (number of
        considered trades)

    '''
    alias = ('SystemQualityNumber',)
    params = (
        ('timeframe', bt.TimeFrame.Days),
        ('compression', None),
    )

    def __init__(self):
        super().__init__()
        self._realized_pnls = [] # all positions pnl

    def _drain(self):
        events = self.get_shm_events()  
        for e in events:
            if e['type'] == 'position':
                pos = e['data']
                if pos['size'] == 0 and pos['pnl'] != 0:
                    self._realized_pnls.append(pos['pnl'])

    def notify_timer(self, dt0):
        self._drain()

    def on_dt_over(self, dt0):
        self._drain()
        
        n_trades = len(self._realized_pnls)
        if n_trades > 1:
            pnl_avg = np.mean(self._realized_pnls)
            pnl_std = np.std(self._realized_pnls)
            
            if pnl_std > 0:
                sqn = (math.sqrt(n_trades) * pnl_avg) / pnl_std
                self.log_shm.publish_metric(b"SQN", sqn, dt0)

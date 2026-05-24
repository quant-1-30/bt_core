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

import bt_core as bt


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
        super().__init__()
        
        self.closed_count = 0
        self.won_count = 0
        self.loss_count = 0
        self.net_pnl = 0.0

    def _drain(self):
        events = self.get_shm_events() 

        for e in events:
            if e['type'] == 'position':
                pos = e['data']
                if pos['size'] == 0 and pos['pnl'] != 0:  
                    pnl = pos['pnl']
                    self.closed_count += 1
                    self.net_pnl += pnl
                    
                    if pnl > 0:
                        self.won_count += 1
                    else:
                        self.loss_count += 1

    def notify_timer(self, dt0: int):
        self._drain()

    def on_dt_over(self, dt0: int):
        self._drain()
        
        if self.closed_count > 0:
            won_rate = self.won_count / self.closed_count
            self.log_shm.publish_metric(b"TradeAnalyzer WonRate", won_rate, dt0)
            self.log_shm.publish_metric( b"TradeAnalyzer NetPnl", self.net_pnl, dt0)

    def stop(self):
        super(TradeAnalyzer, self).stop()

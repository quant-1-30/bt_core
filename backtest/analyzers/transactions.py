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
# from __future__ import (absolute_import, division, print_function,
#                         unicode_literals)

import backtest as bt


class Transactions(bt.TimeFrameAnalyzerBase):
    '''This analyzer reports the transactions occurred with each an every data in
    the system

    It looks at the order execution bits to create a ``Position`` starting from
    0 during each ``next`` cycle.

    The result is used during next to record the transactions

    Params:

      - headers (default: ``True``)

        Add an initial key to the dictionary holding the results with the names
        of the datas

    Methods:

      - get_analysis

        Returns a dictionary with returns as values and the datetime points for
        each return as keys
    '''
    params = (
        ('headers', False),
        ('timeframe', bt.TimeFrame.Days),
        ('compression', 1),
    )
    def __init__(self):
        self.trades_cnt = 0

    def notify_timer(self):
        events = self.get_shm_events() 
        trades_cnt = len([_t for _t in events if _t["type"] == "trade"])
        self.trades_cnt += trades_cnt
        if trades_cnt > 0:
            self.log_shm.publish_metric(b"Intraday_Trades", self.trades_cnt, self.data.datetime[0]) # slope

    def on_dt_over(self):
        _ = self.get_shm_events() # timer on session end 
          
        self.log_shm.publish_metric(b"Transactions", self.trades_cnt, self.data.datetime[0]) 
        self.trades_cnt = 0 # reset

    def stop(self):
        super(Transactions, self).stop()

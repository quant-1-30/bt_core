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
import logging
import math
import numpy as np
from collections import defaultdict

import bt_core as bt
from bt_protocol._protocol import SnapshotBody

logger = logging.getLogger(__name__)


class SQN(bt.TimeFrameAnalyzerBase):
    consumes_shm = True  # drains shm events; registers a ring consumer
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
        self._order_to_sid = {}
        self._last_positions = {}

        # --- SQN Welford ---
        self._sqn_n = 0
        self._sqn_mean = 0.0
        self._sqn_M2 = 0.0

    def _process_events(self):
        trades_by_sid = defaultdict(list)
        events = self.get_shm_events()
        if not events:
            return trades_by_sid

        unmapped_trades = []
        for e in events:
            etype = e.get('type')
            body = e.get('data')
            if etype == 'order':
                self._order_to_sid[body["order_id"]] = body["sid"]
            elif etype == 'trade':
                unmapped_trades.append(body)

        for tb in unmapped_trades:
            sid = self._order_to_sid.get(tb["order_id"], None)
            if sid:
                trades_by_sid[sid].append(tb)
            else:
                logger.warning(
                    "SQN: unmapped order_id %s (merger sid switch / pruned "
                    "history) - trade skipped", tb['order_id'])
        return trades_by_sid

    def on_dt_over(self, dt0: int, snapshot: SnapshotBody):
        trades_by_sid = self._process_events()

        current_positions = {p.sid: p for p in snapshot.positions if p.size != 0}
        hold_sids = set(current_positions.keys())
        last_sids = set(self._last_positions.keys())

        closed_sids = (last_sids | set(trades_by_sid.keys())) - hold_sids

        for sid in closed_sids:
            realized_pnl = 0.0
            pos_y = self._last_positions.get(sid)
            if pos_y:
                realized_pnl -= (pos_y.size * pos_y.cost_basis)

            for tb in trades_by_sid.get(sid, ()):
                direction = -1.0 if tb["isbuy"] else 1.0
                realized_pnl += (direction * tb["executed_size"] * tb["executed_price"]) - tb["comm"]

            self._sqn_n += 1
            delta = realized_pnl - self._sqn_mean
            self._sqn_mean += delta / self._sqn_n
            self._sqn_M2 += delta * (realized_pnl - self._sqn_mean)

        sqn_score = float('nan')
        if self._sqn_n > 1:
            variance = self._sqn_M2 / (self._sqn_n - 1)
            if variance > 0:
                std_pnl = math.sqrt(variance)
                sqn_score = (math.sqrt(self._sqn_n) * self._sqn_mean) / std_pnl

        self.log_shm.publish_metric(b"SQN", sqn_score, dt0)

        # reset on next day
        self._last_positions = current_positions
        
        if closed_sids:
            self._order_to_sid = {
                oid: s for oid, s in self._order_to_sid.items() if s not in closed_sids
            }

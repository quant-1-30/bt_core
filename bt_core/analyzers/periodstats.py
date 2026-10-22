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
import bt_core as bt

from bt_protocol._protocol import SnapshotBody

__all__ = ['PeriodStats']


class PeriodStats(bt.Analyzer):
    '''Calculates basic statistics for given timeframe

    Params:

      - ``timeframe`` (default: ``Years``)
        If ``None`` the ``timeframe`` of the 1st data in the system will be
        used

        Pass ``TimeFrame.NoTimeFrame`` to consider the entire dataset with no
        time constraints

      - ``compression`` (default: ``1``)

        Only used for sub-day timeframes to for example work on an hourly
        timeframe by specifying "TimeFrame.Minutes" and 60 as compression

        If ``None`` then the compression of the 1st data of the system will be
        used

    ``get_analysis`` returns a dictionary containing the keys:

      - ``average``
      - ``stddev``
      - ``positive``
      - ``negative``
      - ``nochange``
      - ``best``
      - ``worst``

    If the parameter ``zeroispos`` is set to ``True``, periods with no change
    will be counted as positive
    '''
    params = (
        ('timeframe', bt.TimeFrame.Days), 
        ('compression', 1),
        ('zeroispos', False),
    )

    def __init__(self):
        super().__init__()

        self.last_value = 0.0
        self._n = 0
        self._mean = 0.0
        self._m2 = 0.0
        self._best = float('-inf')
        self._worst = float('inf')
        self._pos_cnt = 0
        self._neg_cnt = 0
        self._nochange_cnt = 0

    def start(self):
        snap = self._owner.snapshot
        self.last_value = snap.account.portfolio_value + snap.account.cash

    def on_dt_over(self, dt0: int, snapshot: SnapshotBody):
        current_value = snapshot.account.portfolio_value + snapshot.account.cash
        
        if self.last_value <= 0:
            self._publish_nan(dt0)
            self.last_value = current_value
            return
            
        ret = (current_value / self.last_value) - 1.0
        self.last_value = current_value

        self._n += 1
        delta = ret - self._mean
        self._mean += delta / self._n
        self._m2 += delta * (ret - self._mean)

        if ret > self._best:
            self._best = ret
        if ret < self._worst:
            self._worst = ret

        if ret > 0.0:
            self._pos_cnt += 1
        elif ret < 0.0:
            self._neg_cnt += 1
        else:
            self._nochange_cnt += 1

        std_ret = math.sqrt(self._m2 / (self._n - 1)) if self._n > 1 else float('nan')
        pos_cnt = self._pos_cnt + (self._nochange_cnt if self.p.zeroispos else 0)

        self.log_shm.publish_metric(b"PeriodStatsAvgRet", self._mean, dt0)
        self.log_shm.publish_metric(b"PeriodStatsStd", std_ret, dt0)
        self.log_shm.publish_metric(b"PeriodStatsBest", self._best, dt0)
        self.log_shm.publish_metric(b"PeriodStatsWorst", self._worst, dt0)
        self.log_shm.publish_metric(b"PeriodStatsPosCnt", pos_cnt, dt0)
        self.log_shm.publish_metric(b"PeriodStatsNegCnt", self._neg_cnt, dt0)
        self.log_shm.publish_metric(b"PeriodStatsNoChangeCnt", self._nochange_cnt, dt0)

    def _publish_nan(self, dt0: int):
        nan = float('nan')
        self.log_shm.publish_metric(b"PeriodStatsAvgRet", nan, dt0)
        self.log_shm.publish_metric(b"PeriodStatsStd", nan, dt0)
        self.log_shm.publish_metric(b"PeriodStatsBest", nan, dt0)
        self.log_shm.publish_metric(b"PeriodStatsWorst", nan, dt0)
        
        self.log_shm.publish_metric(b"PeriodStatsPosCnt", 0, dt0)
        self.log_shm.publish_metric(b"PeriodStatsNegCnt", 0, dt0)
        self.log_shm.publish_metric(b"PeriodStatsNoChangeCnt", 0, dt0)

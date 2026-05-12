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
import datetime
import numpy as np

import backtest as bt
from backtest.observer import Observer


__all__ = ["Trades"]


class Trades(Observer):
    '''This observer keeps track of the current cash amount and portfolio value in
    the broker (including the cash)

    Params:

        Set it to ``True`` or ``False`` for a specific behavior

    Params: None
    '''
    params = (
        ('barplot', False),
    )

    lines = ('pnlplus', 'pnlminus')

    plotinfo = dict(plot=True, subplot=True)

    def __init__(self, **kwargs):
        # kwargs = self.p._getkwargs()
        self.preturn = self._owner._addanalyzer(bt.analyzers.PositionsValue, **kwargs)
        self.dtcmp = np.iinfo(np.int_).min

    def next(self):
        dtcmp = self.preturn.dtcmp
        pnl_obj = self.preturn.rets.get(dtcmp, None)
        if dtcmp > self.dtcmp:
            pnl = np.sum([p["pnl"] for p in pnl_obj]) if pnl_obj else np.nan

            if pnl > 0.0:
                self.lines.pnlplus[0] = pnl
            elif pnl <= 0.0 :
                self.lines.pnlminus[0] = pnl

            self.dtcmp = dtcmp

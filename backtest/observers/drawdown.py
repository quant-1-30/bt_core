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

__all__ = ["DrawDown", "DrawDownLength"]


class DrawDown(Observer):
    '''This observer keeps track of the current drawdown level (plotted) and
    the maxdrawdown (not plotted) levels

    Params:

      - ``fund`` (default: ``None``)

        If ``None`` the actual mode of the broker (fundmode - True/False) will
        be autodetected to decide if the returns are based on the total net
        asset value or on the fund value. See ``set_fundmode`` in the broker
        documentation

        Set it to ``True`` or ``False`` for a specific behavior

    '''
    params = (
        ('barplot', False),
    )

    lines = ('drawdown', 'maxdrawdown',)

    plotinfo = dict(plot=True, subplot=True)

    plotlines = dict(maxdrawdown=dict(_plotskip=True,))

    def __init__(self, **kwargs):
        # kwargs = self.p._getkwargs()
        self._dd = self._owner._addanalyzer(bt.analyzers.DrawDown, **kwargs)
        self.dtcmp = np.iinfo(np.int_).min

    # def forward(self, value=np.nan, size=1):
    #     # 保留当前值，避免在 forward 后变成 np.nan。
    #     # 这使得其他在 observer 之前执行的 indicators（如 Signal）
    #     # 能读取到上一周期的有效值，而不是 np.nan。
    #     if len(self.lines.drawdown) > 0:
    #         dd_val = self.lines.drawdown[-1]
    #         maxdd_val = self.lines.maxdrawdown[-1]
    #     else:
    #         dd_val = value
    #         maxdd_val = value

    #     super(DrawDown, self).forward(value=value, size=size)

    #     if len(self.lines.drawdown) > 0:
    #         self.lines.drawdown[0] = dd_val
    #         self.lines.maxdrawdown[0] = maxdd_val

    def next(self):
        dtcmp = self._dd.dtcmp
        if dtcmp > self.dtcmp:
            # import pdb; pdb.set_trace()
            dd, _ = self._dd.rets[dtcmp]
            self.lines.drawdown[0] = dd # update drawdown
            self.lines.maxdrawdown[0] = self._dd.rets["maxDrawdown"]  # update max
            self.dtcmp = dtcmp
            print("DrawDown next ", dd, self.lines.maxdrawdown[0])


class DrawDownLength(Observer):
    '''This observer keeps track of the current drawdown length (plotted) and
    the drawdown max length (not plotted)

    Params: None
    '''

    lines = ('len', 'maxlen',)

    params = (
        ('barplot', False),
    )

    plotinfo = dict(plot=True, subplot=True)
    plotlines = dict(maxlength=dict(_plotskip=True,))

    def __init__(self, **kwargs):
        # kwargs = self.p._getkwargs()
        self._dd = self._owner._addanalyzer(bt.analyzers.DrawDown, **kwargs)
        self.dtcmp = np.iinfo(np.int_).min

    # def forward(self, value=np.nan, size=1):
    #     if len(self.lines.len) > 0:
    #         len_val = self.lines.len[-1]
    #         maxlen_val = self.lines.maxlen[-1]
    #     else:
    #         len_val = value
    #         maxlen_val = value

    #     super(DrawDownLength, self).forward(value=value, size=size)

    #     if len(self.lines.len) > 0:
    #         self.lines.len[0] = len_val
    #         self.lines.maxlen[0] = maxlen_val

    def next(self):
        dtcmp = self._dd.dtcmp
        if dtcmp > self.dtcmp:
            _, ddlen = self._dd.rets[dtcmp]
            self.lines.len[0] = ddlen  
            self.lines.maxlen[0] = self._dd.rets["maxDrawdownLength"]
            self.dtcmp = dtcmp

            self.log_shm.publish_metric(b"DrawDownLength", ddlen, dtcmp) # log the drawdown length for the current datetime

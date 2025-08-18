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
import warnings
from backtest.feed import DataBase
from backtest.dataseries import TimeFrame
from backtest.metabase import with_metaclass
from backtest.stores.btstore import BTStore


__all__ = ["MdData"]


class MetaMdData(DataBase.__class__):

    def __init__(cls, name, bases, dct):
        """auto Register with the store when type class __import__"""
        super(MetaMdData, cls).__init__(name, bases, dct)
        BTStore.DataCls = cls


class MdData(with_metaclass(MetaMdData, DataBase)):
    
    params = (
        ('rtbar', False),  # use RealTime 5 seconds bars
        ("buffer", None)
    )

    RTBAR_MINSIZE = (TimeFrame.Seconds, 3) # Minimum size supported by real-time bars

    def _load_bar(self, msg):
        line = msg["msg"]["line"][0]
        dt = line[0]
        if dt < self.lines.datetime[-1] :
            return False  # cannot deliver earlier than already delivered

        self.lines.datetime[0] = dt
        self.lines.open[0] = line[1]
        self.lines.high[0] = line[2]
        self.lines.low[0] = line[3]
        self.lines.close[0] = line[4]
        self.lines.volume[0] = line[5]
        self.lines.amount[0] = line[6]
        # self.lines.openinterest[0] = 0
        return True

    def _load_rtbar(self, rtbar): # tick 3s
        dt = rtbar[0]
        if dt < self.lines.datetime[-1]:
            return False  # cannot deliver earlier than already delivered

        self.lines.datetime[0] = dt
        # Put the tick into the bar
        tick = rtbar[1]
        self.lines.open[0] = tick
        self.lines.high[0] = tick
        self.lines.low[0] = tick
        self.lines.close[0] = tick
        self.lines.volume[0] = rtbar[2]
        self.lines.amount[0] = rtbar[3]
        return True

    def _load(self):
        if self.p.buffer is None:
            warnings.warn("qlive is None, must subscribe first")
            return
        msg = self.p.buffer.get()
        if msg == "eof":
            return False  # Conn broken during historical/backfilling
        if self.p.rtbar:
            self._load_rtbar(msg)
        else:
            self._load_bar(msg)
        return True


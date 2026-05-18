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
import backtest as bt
from .timereturn import TimeReturn
from .positions import PositionsValue
# from .transactions import Transactions
from .leverage import GrossLeverage
from backtest.dataseries import TimeFrame


class PyFolio(bt.Analyzer):
    '''This analyzer uses 4 children analyzers to collect data and transforms it
    in to a data set compatible with ``pyfolio``

    Children Analyzer

      - ``TimeReturn``

        Used to calculate the returns of the global portfolio value

      - ``PositionsValue``

        Used to calculate the value of the positions per data. It sets the
        ``headers`` and ``cash`` parameters to ``True``

      - ``Transactions``

        Used to record each transaction on a data (size, price, value). Sets
        the ``headers`` parameter to ``True``

      - ``GrossLeverage``

        Keeps track of the gross leverage (how much the strategy is invested)

    Params:
      These are passed transparently to the children

      - timeframe (default: ``bt.TimeFrame.Days``)

        If ``None`` then the timeframe of the 1st data of the system will be
        used

      - compression (default: `1``)

        If ``None`` then the compression of the 1st data of the system will be
        used

    Both ``timeframe`` and ``compression`` are set following the default
    behavior of ``pyfolio`` which is working with *daily* data and upsample it
    to obtaine values like yearly returns.

    Methods:

      - get_analysis

        Returns a dictionary with returns as values and the datetime points for
        each return as keys
    '''
    params = (
        ('timeframe', TimeFrame.Days),
        ('compression', 1)
    )

    def __init__(self):
        dtfcomp = dict(timeframe=self.p.timeframe,
                       compression=self.p.compression)

        self._returns = TimeReturn(**dtfcomp)
        self._positions = PositionsValue(headers=True, cash=True)
        self._gross_lev = GrossLeverage()

    def stop(self):
        super(PyFolio, self).stop()
        self.rets['returns'] = self._returns.get_analysis()
        self.rets['positions'] = self._positions.get_analysis()
        self.rets['gross_lev'] = self._gross_lev.get_analysis()
        
        self.log_shm.publish_metric(b"LogReturnsRolling", logret, self.dtcmp) 


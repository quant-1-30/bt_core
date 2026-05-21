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
import functools
import math
import operator

import talib
import backtest.indicator as btind


class PeriodN(btind.Indicator):
    '''
    Base class for indicators which take a period (__init__ has to be called
    either via super or explicitly)

    This class has no defined lines
    '''
    params = (('period', 1),)

    def __init__(self):
        # super(PeriodN, self).__init__()
        self.addminperiod(self.p.period) # nested indicators to add _minperiod


class OperationN(PeriodN):
    '''
    Calculates "func" for a given period

    Serves as a base for classes that work with a period and can express the
    logic in a callable object

    Note:
      Base classes must provide a "func" attribute which is a callable

    Formula:
      - line = func(data, period)
    '''
    def next(self):
        self.line[0] = self.func(self.data.get(size=self.p.period))


class BaseApplyN(OperationN):
    '''
    Base class for ApplyN and others which may take a ``func`` as a parameter
    but want to define the lines in the indicator.

    Calculates ``func`` for a given period where func is given as a parameter,
    aka named argument or ``kwarg``

    Formula:
      - lines[0] = func(data, period)

    Any extra lines defined beyond the first (index 0) are not calculated
    '''
    params = (('func', None),)

    def __init__(self):
        self.func = self.p.func
        super(BaseApplyN, self).__init__()


class Highest(PeriodN):
    '''
    Calculates the highest value for the data in a given period

    Uses the built-in ``max`` for the calculation

    Formula:
      - highest = max(data, period)
    '''
    alias = ('MaxN',)
    lines = ('highest',)

    params = (('period', 14),)

    def __init__(self):
        super(Highest, self).__init__()
        
    def next(self):
        # np.array slice ---> view and zero_copy
        _arr = np.asarray(self.data.array, dtype=np.float64)
        _h = talib.MAX(_arr, timeperiod=self.p.period)
        # self.lines.highest[0] = _h[-1]
        self.line[0] = _h[-1] # only one line simplify


class Lowest(PeriodN):
    '''
    Calculates the lowest value for the data in a given period

    Uses the built-in ``min`` for the calculation

    Formula:
      - lowest = min(data, period)
    '''
    alias = ('MinN',)
    lines = ('lowest',)
    
    params = (('period', 14),)

    def __init__(self):
        super(Lowest, self).__init__()

    def next(self):
        # np.array slice ---> view and zero_copy
        _arr = np.asarray(self.data.array, dtype=np.float64)
        _l = talib.MIN(_arr, timeperiod=self.p.period)
        # self.lines.lowest[0] = _l[-1]
        self.line[0] = _l[-1]


class FindIndexHighest(PeriodN):
    '''
    Returns the index of the last data that is the highest in the period

    Note:
      Returned indexes look backwards. 0 is the current index and 1 is
      the previous bar.

    Formula:
      - index = index of last data which is the highest
    '''
    alias = ('MaxIndex',)
    lines = ('max',)
    
    params = (('period', 14),)

    def __init__(self):
        super(FindIndexHighest, self).__init__()
        
    def next(self):
        # np.array slice ---> view and zero_copy
        _arr = np.asarray(self.data.array, dtype=np.float64)
        _m = talib.MAXINDEX(_arr, timeperiod=self.p.period)
        # self.lines.max[0] = _m[-1]
        self.line[0] = _m[-1]


class FindIndexLowest(PeriodN):
    '''
    Returns the index of the last data that is the lowest in the period

    Note:
      Returned indexes look backwards. 0 is the current index and 1 is
      the previous bar.

    Formula:
      - index = index of last data which is the lowest
    '''
    alias = ('MinN',)
    lines = ('lowest',)
    
    params = (('period', 14),)

    def __init__(self):
        super(FindIndexLowest, self).__init__()

    def next(self):
        # np.array slice ---> view and zero_copy
        _arr = np.asarray(self.data.array, dtype=np.float64)
        _l = talib.MININDEX(_arr, timeperiod=self.p.period)
        # self.lines.lowest[0] = _l[-1]
        self.line[0] = _l[-1]

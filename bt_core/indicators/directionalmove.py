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
import talib
import numpy as np
from .basicops import PeriodN
from bt_core.indicator import Indicator
from bt_core.logic import And, If


class PlusDirectionalIndicator(PeriodN):
    '''
    Defined by J. Welles Wilder, Jr. in 1978 in his book *"New Concepts in
    Technical Trading Systems"*.

    Intended to measure trend strength

    This indicator shows +DI:
      - Use MinusDirectionalIndicator (MinusDI) to get -DI
      - Use Directional Indicator (DI) to get +DI, -DI
      - Use AverageDirectionalIndex (ADX) to get ADX
      - Use AverageDirectionalIndexRating (ADXR) to get ADX, ADXR
      - Use DirectionalMovementIndex (DMI) to get ADX, +DI, -DI
      - Use DirectionalMovement (DM) to get ADX, ADXR, +DI, -DI

    Formula:
      - upmove = high - high(-1)
      - downmove = low(-1) - low
      - +dm = upmove if upmove > downmove and upmove > 0 else 0
      - +di = 100 * MovingAverage(+dm, period) / atr(period)

    The moving average used is the one originally defined by Wilder,
    the SmoothedMovingAverage

    See:
      - https://en.wikipedia.org/wiki/Average_directional_movement_index
    '''
    alias = (('PlusDI', '+DI'),)
    lines = ('plusDI',)
    
    params = (('period', 14),)

    plotinfo = dict(plotname='+DirectionalIndicator')

    def __init__(self):
        super(PlusDirectionalIndicator, self).__init__()
        # self.addminperiod(self.p.period)
    
    def next(self):
        # np.array slice ---> view and zero_copy
        h = np.asarray(self.data.high.array, dtype=np.float64)
        l = np.asarray(self.data.low.array, dtype=np.float64)
        c = np.asarray(self.data.close.array, dtype=np.float64)


        _di = talib.PLUS_DI(h, l, c, self.p.period) 
        self.line[0] = _di[-1]


class MinusDirectionalIndicator(PeriodN):
    '''
    Defined by J. Welles Wilder, Jr. in 1978 in his book *"New Concepts in
    Technical Trading Systems"*.

    Intended to measure trend strength

    This indicator shows -DI:
      - Use PlusDirectionalIndicator (PlusDI) to get +DI
      - Use Directional Indicator (DI) to get +DI, -DI
      - Use AverageDirectionalIndex (ADX) to get ADX
      - Use AverageDirectionalIndexRating (ADXR) to get ADX, ADXR
      - Use DirectionalMovementIndex (DMI) to get ADX, +DI, -DI
      - Use DirectionalMovement (DM) to get ADX, ADXR, +DI, -DI

    Formula:
      - upmove = high - high(-1)
      - downmove = low(-1) - low
      - -dm = downmove if downmove > upmove and downmove > 0 else 0
      - -di = 100 * MovingAverage(-dm, period) / atr(period)

    The moving average used is the one originally defined by Wilder,
    the SmoothedMovingAverage

    See:
      - https://en.wikipedia.org/wiki/Average_directional_movement_index
    '''
    alias = (('MinusDI', '-DI'),)
    lines = ('minusDI',)

    params = (('period', 14),)

    plotinfo = dict(plotname='+DirectionalIndicator')

    def __init__(self):
        super(MinusDirectionalIndicator, self).__init__()
        # self.addminperiod(self.p.period)
    
    def next(self):
        # np.array slice ---> view and zero_copy
        h = np.asarray(self.data.high.array, dtype=np.float64)
        l = np.asarray(self.data.low.array, dtype=np.float64)
        c = np.asarray(self.data.close.array, dtype=np.float64)

        _di = talib.MINUS_DI(h, l, c, self.p.period)
        self.line[0] = _di[-1]


class AverageDirectionalMovementIndex(PeriodN):
    '''
    Defined by J. Welles Wilder, Jr. in 1978 in his book *"New Concepts in
    Technical Trading Systems"*.

    Intended to measure trend strength

    This indicator only shows ADX:
      - Use PlusDirectionalIndicator (PlusDI) to get +DI
      - Use MinusDirectionalIndicator (MinusDI) to get -DI
      - Use Directional Indicator (DI) to get +DI, -DI
      - Use AverageDirectionalIndexRating (ADXR) to get ADX, ADXR
      - Use DirectionalMovementIndex (DMI) to get ADX, +DI, -DI
      - Use DirectionalMovement (DM) to get ADX, ADXR, +DI, -DI

    Formula:
      - upmove = high - high(-1)
      - downmove = low(-1) - low
      - +dm = upmove if upmove > downmove and upmove > 0 else 0
      - -dm = downmove if downmove > upmove and downmove > 0 else 0
      - +di = 100 * MovingAverage(+dm, period) / atr(period)
      - -di = 100 * MovingAverage(-dm, period) / atr(period)
      - dx = 100 * abs(+di - -di) / (+di + -di)
      - adx = MovingAverage(dx, period)

    The moving average used is the one originally defined by Wilder,
    the SmoothedMovingAverage

    See:
      - https://en.wikipedia.org/wiki/Average_directional_movement_index
    '''
    alias = ('ADX',)

    lines = ('adx',)
    params = (('period', 14),)

    plotlines = dict(adx=dict(_name='ADX'))

    def __init__(self):
        super(AverageDirectionalMovementIndex, self).__init__()
        # self.addminperiod(self.p.period)
    
    def next(self):
        # np.array slice ---> view and zero_copy
        h = np.asarray(self.data.high.array, dtype=np.float64)
        l = np.asarray(self.data.low.array, dtype=np.float64)
        c = np.asarray(self.data.close.array, dtype=np.float64)

        _adx = talib.ADX(h, l, c, self.p.period)
        self.line[0] = _adx[-1]


class AverageDirectionalMovementIndexRating(PeriodN):
    '''
    Defined by J. Welles Wilder, Jr. in 1978 in his book *"New Concepts in
    Technical Trading Systems"*.

    Intended to measure trend strength.

    ADXR is the average of ADX with a value period bars ago

    This indicator shows the ADX and ADXR:
      - Use PlusDirectionalIndicator (PlusDI) to get +DI
      - Use MinusDirectionalIndicator (MinusDI) to get -DI
      - Use Directional Indicator (DI) to get +DI, -DI
      - Use AverageDirectionalIndex (ADX) to get ADX
      - Use DirectionalMovementIndex (DMI) to get ADX, +DI, -DI
      - Use DirectionalMovement (DM) to get ADX, ADXR, +DI, -DI

    Formula:
      - upmove = high - high(-1)
      - downmove = low(-1) - low
      - +dm = upmove if upmove > downmove and upmove > 0 else 0
      - -dm = downmove if downmove > upmove and downmove > 0 else 0
      - +di = 100 * MovingAverage(+dm, period) / atr(period)
      - -di = 100 * MovingAverage(-dm, period) / atr(period)
      - dx = 100 * abs(+di - -di) / (+di + -di)
      - adx = MovingAverage(dx, period)
      - adxr = (adx + adx(-period)) / 2

    The moving average used is the one originally defined by Wilder,
    the SmoothedMovingAverage

    See:
      - https://en.wikipedia.org/wiki/Average_directional_movement_index
    '''
    alias = ('ADXR',)

    lines = ('adxr',)
    params = (('period', 14),)
    
    plotlines = dict(adxr=dict(_name='ADXR'))

    def __init__(self):
        super(AverageDirectionalMovementIndexRating, self).__init__()
        # self.addminperiod(self.p.period)
    
    def next(self):
        # np.array slice ---> view and zero_copy
        h = np.asarray(self.data.high.array, dtype=np.float64)
        l = np.asarray(self.data.low.array, dtype=np.float64)
        c = np.asarray(self.data.close.array, dtype=np.float64)

        _adxr = talib.ADXR(h, l, c, self.p.period)
        self.line[0] = _adxr[-1]


# class DirectionalMovementIndex(AverageDirectionalMovementIndex,
#                                DirectionalIndicator):
#     '''
#     Defined by J. Welles Wilder, Jr. in 1978 in his book *"New Concepts in
#     Technical Trading Systems"*.

#     Intended to measure trend strength

#     This indicator shows the ADX, +DI, -DI:
#       - Use PlusDirectionalIndicator (PlusDI) to get +DI
#       - Use MinusDirectionalIndicator (MinusDI) to get -DI
#       - Use Directional Indicator (DI) to get +DI, -DI
#       - Use AverageDirectionalIndex (ADX) to get ADX
#       - Use AverageDirectionalIndexRating (ADXRating) to get ADX, ADXR
#       - Use DirectionalMovement (DM) to get ADX, ADXR, +DI, -DI

#     Formula:
#       - upmove = high - high(-1)
#       - downmove = low(-1) - low
#       - +dm = upmove if upmove > downmove and upmove > 0 else 0
#       - -dm = downmove if downmove > upmove and downmove > 0 else 0
#       - +di = 100 * MovingAverage(+dm, period) / atr(period)
#       - -di = 100 * MovingAverage(-dm, period) / atr(period)
#       - dx = 100 * abs(+di - -di) / (+di + -di)
#       - adx = MovingAverage(dx, period)

#     The moving average used is the one originally defined by Wilder,
#     the SmoothedMovingAverage

#     See:
#       - https://en.wikipedia.org/wiki/Average_directional_movement_index
#     '''
#     alias = ('DMI',)


# class DirectionalMovement(AverageDirectionalMovementIndexRating,
#                           DirectionalIndicator):
#     '''
#     Defined by J. Welles Wilder, Jr. in 1978 in his book *"New Concepts in
#     Technical Trading Systems"*.

#     Intended to measure trend strength

#     This indicator shows ADX, ADXR, +DI, -DI.

#       - Use PlusDirectionalIndicator (PlusDI) to get +DI
#       - Use MinusDirectionalIndicator (MinusDI) to get -DI
#       - Use Directional Indicator (DI) to get +DI, -DI
#       - Use AverageDirectionalIndex (ADX) to get ADX
#       - Use AverageDirectionalIndexRating (ADXR) to get ADX, ADXR
#       - Use DirectionalMovementIndex (DMI) to get ADX, +DI, -DI

#     Formula:
#       - upmove = high - high(-1)
#       - downmove = low(-1) - low
#       - +dm = upmove if upmove > downmove and upmove > 0 else 0
#       - -dm = downmove if downmove > upmove and downmove > 0 else 0
#       - +di = 100 * MovingAverage(+dm, period) / atr(period)
#       - -di = 100 * MovingAverage(-dm, period) / atr(period)
#       - dx = 100 * abs(+di - -di) / (+di + -di)
#       - adx = MovingAverage(dx, period)

#     The moving average used is the one originally defined by Wilder,
#     the SmoothedMovingAverage

#     See:
#       - https://en.wikipedia.org/wiki/Average_directional_movement_index
#     '''



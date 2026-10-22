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
import collections
from .basicops import PeriodN


class _WilderDMI(object):
    """Shared incremental Wilder directional-movement state.

    Consumes one (high, low, close) triple per bar from bar 0 on
    (via prenext) so every stage seeds exactly where talib seeds it:
      - TR/+DM/-DM sums seeded with the first `period` values
      - DI  = 100 * S_x / S_TR
      - DX  = 100 * |+DI - -DI| / (+DI + -DI)
      - ADX seeded with the mean of the first `period` DX values,
        then adx = (adx*(p-1) + dx) / p
      - ADXR = (adx + adx(-period)) / 2
    All state lives in instance attributes (never in line buffers), so the
    computation is ring-mode agnostic and O(1) per bar."""
    __slots__ = ('p', '_ph', '_pl', '_pc', '_str', '_spdm', '_smdm', '_n',
                 '_smoothed', 'S_TR', 'S_PDM', 'S_MDM', '_dx_seed', '_adx',
                 '_adx_hist')

    def __init__(self, period):
        self.p = period
        self._ph = self._pl = self._pc = None
        self._str = self._spdm = self._smdm = 0.0
        self._n = 0
        self._smoothed = False
        self.S_TR = self.S_PDM = self.S_MDM = None
        self._dx_seed = []
        self._adx = None
        self._adx_hist = collections.deque(maxlen=period)

    def update(self, h, l, c):
        if h != h or l != l or c != c:
            return None, None, None, None, None
        p = self.p
        just_seeded = False
        if self._ph is None:
            tr = pdm = mdm = 0.0
        else:
            up = h - self._ph
            dn = self._pl - l
            pdm = up if (up > dn and up > 0.0) else 0.0
            mdm = dn if (dn > up and dn > 0.0) else 0.0
            pc = self._pc
            tr = max(h - l, abs(h - pc), abs(l - pc))

        if not self._smoothed:
            self._str += tr
            self._spdm += pdm
            self._smdm += mdm
            self._n += 1
            if self._n >= p:
                self.S_TR = self._str
                self.S_PDM = self._spdm
                self.S_MDM = self._smdm
                self._smoothed = True
                just_seeded = True
        else:
            self.S_TR = self.S_TR - self.S_TR / p + tr
            self.S_PDM = self.S_PDM - self.S_PDM / p + pdm
            self.S_MDM = self.S_MDM - self.S_MDM / p + mdm
        self._ph, self._pl, self._pc = h, l, c

        plusdi = minusdi = dx = adx = adxr = None
        if self._smoothed and not just_seeded and self.S_TR > 0.0:
            # `not just_seeded`: TA-Lib's ADX/DI outputs start one bar after
            # the seed completes; the DX series feeding the ADX seed starts
            # there too (verified numerically against talib.ADX)
            plusdi = 100.0 * self.S_PDM / self.S_TR
            minusdi = 100.0 * self.S_MDM / self.S_TR
            s = plusdi + minusdi
            dx = 100.0 * abs(plusdi - minusdi) / s if s != 0.0 else 0.0
            p = self.p
            if self._adx is None:
                self._dx_seed.append(dx)
                if len(self._dx_seed) >= p:
                    self._adx = sum(self._dx_seed) / p
                    self._dx_seed = []
            else:
                self._adx = (self._adx * (p - 1) + dx) / p
            adx = self._adx
            if adx is not None:
                self._adx_hist.append(adx)
                # talib adxr: (adx[i] + adx[i-(p-1)]) / 2 -> the p-th most
                # recent history entry (verified numerically)
                if len(self._adx_hist) >= p:
                    adxr = (adx + self._adx_hist[-p]) / 2.0
        return plusdi, minusdi, dx, adx, adxr


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
        # talib.PLUS_DI lookback == period (needs period+1 bars)
        self.addminperiod(2)
        self._dmi = _WilderDMI(self.p.period)

    def prenext(self):
        self._dmi.update(self.data.high[0], self.data.low[0],
                         self.data.close[0])

    def next(self):
        r = self._dmi.update(self.data.high[0], self.data.low[0],
                             self.data.close[0])
        self.line[0] = r[0] if r[0] is not None else float('nan')


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
        # talib.MINUS_DI lookback == period (needs period+1 bars)
        self.addminperiod(2)
        self._dmi = _WilderDMI(self.p.period)

    def prenext(self):
        self._dmi.update(self.data.high[0], self.data.low[0],
                         self.data.close[0])

    def next(self):
        r = self._dmi.update(self.data.high[0], self.data.low[0],
                             self.data.close[0])
        self.line[0] = r[1] if r[1] is not None else float('nan')


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
        # first ADX = mean of the first `period` DX values; DX itself starts
        # at period+1 bars -> keep a generous warmup, values stay exact
        self.addminperiod(self.p.period + 2)
        self._dmi = _WilderDMI(self.p.period)

    def prenext(self):
        self._dmi.update(self.data.high[0], self.data.low[0],
                         self.data.close[0])

    def next(self):
        r = self._dmi.update(self.data.high[0], self.data.low[0],
                             self.data.close[0])
        self.line[0] = r[3] if r[3] is not None else float('nan')


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
        # adxr = (adx + adx(-period)) / 2: needs `period` extra ADX values
        self.addminperiod(2 * self.p.period + 2)
        self._dmi = _WilderDMI(self.p.period)

    def prenext(self):
        self._dmi.update(self.data.high[0], self.data.low[0],
                         self.data.close[0])

    def next(self):
        r = self._dmi.update(self.data.high[0], self.data.low[0],
                             self.data.close[0])
        self.line[0] = r[4] if r[4] is not None else float('nan')


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



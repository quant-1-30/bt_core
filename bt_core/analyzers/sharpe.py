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


class SharpeRatio(bt.Analyzer):
    '''This analyzer calculates the SharpeRatio of a strategy using a risk free
    asset which is simply an interest rate

    See also:

      - https://en.wikipedia.org/wiki/Sharpe_ratio

    Params:

      - ``timeframe``: (default: ``TimeFrame.Years``)

      - ``compression`` (default: ``1``)

        Only used for sub-day timeframes to for example work on an hourly
        timeframe by specifying "TimeFrame.Minutes" and 60 as compression

      - ``riskfreerate`` (default: 0.01 -> 1%)

        Expressed in annual terms (see ``convertrate`` below)

      - ``convertrate`` (default: ``True``)

        Convert the ``riskfreerate`` from annual to monthly, weekly or daily
        rate. Sub-day conversions are not supported

      - ``factor`` (default: ``None``)

        If ``None``, the conversion factor for the riskfree rate from *annual*
        to the chosen timeframe will be chosen from a predefined table

          Days: 252, Weeks: 52, Months: 12, Years: 1

        Else the specified value will be used

      - ``annualize`` (default: ``False``)

        If ``convertrate`` is ``True``, the *SharpeRatio* will be delivered in
        the ``timeframe`` of choice.

        In most occasions the SharpeRatio is delivered in annualized form.
        Convert the ``riskfreerate`` from annual to monthly, weekly or daily
        rate. Sub-day conversions are not supported

      - ``stddev_sample`` (default: ``False``)

        If this is set to ``True`` the *standard deviation* will be calculated
        decreasing the denominator in the mean by ``1``. This is used when
        calculating the *standard deviation* if it's considered that not all
        samples are used for the calculation. This is known as the *Bessels'
        correction*

      - ``daysfactor`` (default: ``None``)

        Old naming for ``factor``. If set to anything else than ``None`` and
        the ``timeframe`` is ``TimeFrame.Days`` it will be assumed this is old
        code and the value will be used

      - ``legacyannual`` (default: ``False``)

        Use the ``AnnualReturn`` return analyzer, which as the name implies
        only works on years

      - ``fund`` (default: ``None``)

        If ``None`` the actual mode of the broker (fundmode - True/False) will
        be autodetected to decide if the returns are based on the total net
        asset value or on the fund value. See ``set_fundmode`` in the broker
        documentation

        Set it to ``True`` or ``False`` for a specific behavior

    Methods:

      - get_analysis

        Returns a dictionary with key "sharperatio" holding the ratio

    '''
    params = (
        ('timeframe', bt.TimeFrame.Days),
        ('compression', 1),
        ('annualize', True),
        ('riskfreerate', 0.01)
    )

    RATEFACTORS = {
        bt.TimeFrame.Days: 252,
        bt.TimeFrame.Weeks: 52,
        bt.TimeFrame.Months: 12,
        bt.TimeFrame.Years: 1,
    }

    def __init__(self):
        super().__init__()
        self._last_value = 0.0
        self._excess_returns = []
        
        factor = self.RATEFACTORS.get(self.p.timeframe, 252.0)
        self._period_rf = math.pow(1.0 + self.p.riskfreerate, 1.0 / factor) - 1.0
        self._annualize_factor = math.sqrt(factor) if self.p.annualize else 1.0

    def start(self):
        self._last_value = self._owner.get_snapshot().account.portfolio_value

    def on_dt_over(self, dt0):
        current_value = self._owner.get_snapshot().account.portfolio_value
        
        if self._last_value > 0:
            period_ret = (current_value / self._last_value) - 1.0
            excess_ret = period_ret - self._period_rf
            self._excess_returns.append(excess_ret)
            
            if len(self._excess_returns) > 1:
                ret_avg = np.mean(self._excess_returns)
                ret_std = np.std(self._excess_returns)
                
                if ret_std > 0:
                    ratio = (ret_avg / ret_std) * self._annualize_factor

                    self.log_shm.publish_metric(b"SharpeRatio", ratio, dt0)

        self._last_value = current_value

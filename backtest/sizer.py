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
from backtest.metabase import MetaParams, with_metaclass


__all__ = ['sizers']


class Sizer(with_metaclass(MetaParams, object)):
    '''This is the base class for *Sizers*. Any *sizer* should subclass this
    and override the ``_getsizing`` method

    Member Attribs:

      - ``strategy``: will be set by the strategy in which the sizer is working

        Gives access to the entire api of the strategy, for example if the
        actual data position would be needed in ``_getsizing``::

           position = self.strategy.getposition(data)

      - ``broker``: will be set by the strategy in which the sizer is working

        Gives access to information some complex sizers may need like portfolio
        value, ..
    '''
    params = (("reserve", 0.0), )  # reserve a fraction of cash

    def getsizing(self, strats, datas={}):
        return self._getsizing(strats, datas)

    def _getsizing(self, strats, datas):
        '''This method has to be overriden by subclasses of Sizer to provide
        the sizing functionality

        Params:
          - ``comminfo``: The CommissionInfo instance that contains
            information about the commission for the data and allows
            calculation of position value, operation cost, commision for the
            operation

          - ``cash``: current available cash in the *broker*

          - ``data``: target of the operation

          - ``isbuy``: will be ``True`` for *buy* operations and ``False``
            for *sell* operations

        The method has to return the actual size (an int) to be executed. If
        ``0`` is returned nothing will be executed.

        The absolute value of the returned value will be used

        '''
        raise NotImplementedError


SizerBase = Sizer  # alias for old naming


class NoSizer(Sizer):
    '''This is the default sizer used by ``backtrader`` if no other sizer is
    set

    It will simply return a size of ``1`` for each operation
    '''

    def _getsizing(self, strats, datas):
        sizers = {strat._id: 1/(len(strats)) for strat in strats}
        return sizers
    

class KellySizer(Sizer):
    '''This sizer will return a size based on the Kelly Criterion

    The Kelly Criterion is a formula used to determine the optimal size of a
    series of bets in order to maximize the logarithm of wealth. It is often
    used in gambling and investing to help manage risk and maximize returns.

    The formula for the Kelly Criterion is:

    f* = (bp - q) / b

    where:

      - f* is the fraction of the current bankroll to wager

      - b is the net odds received on the wager (i.e., "b to 1") - this is
        calculated as (1 / (price - 1)) for buy operations and (1 / price) for
        sell operations

      - p is the probability of winning (i.e., the probability that the bet
        will pay off)

      - q is the probability of losing, which is equal to 1 - p

    The Kelly Criterion suggests that you should bet a fraction of your
    bankroll equal to f* in order to maximize your long-term growth rate. If
    f* is negative, it means that you should not place the bet at all.

    Note that the Kelly Criterion assumes that you have an edge over the house
    or market, meaning that your probability of winning (p) is greater than
    your probability of losing (q). If you do not have an edge, then betting
    according to the Kelly Criterion may lead to losses over time.

    This sizer requires that ``self.strategy`` has two methods implemented:

      - ``kelly_p(self, data)``: returns the probability of winning for the
        given data

      - ``kelly_q(self, data)``: returns the probability of losing for the
        given data

    '''

    def _getsizing(self, strats, datas):
        # datas represent stats of strats
        raise NotImplementedError("KellySizer not implemented yet")
    

sizers = {
    'default': NoSizer,
    'kelly': KellySizer
    }

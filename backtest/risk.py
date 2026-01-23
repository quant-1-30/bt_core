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
from backtest.metabase import MetaParams, with_metaclass, findowner
import backtest as bt


class MetaRisk(MetaParams):
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
    def donew(cls, *args, **kwargs):
        '''
        Intercept the strategy parameter
        '''
        # Create the object and set the params in place
        _obj, args, kwargs = super(MetaRisk, cls).donew(*args, **kwargs)
        _obj._owner = env = findowner(_obj, bt.Cerebro)

        return _obj, args, kwargs

    def dopostinit(cls, _obj, *args, **kwargs):
        _obj, args, kwargs = \
            super(MetaRisk, cls).dopostinit(_obj, *args, **kwargs)

        # Return to the normal chain
        return _obj, args, kwargs


class RiskBase(with_metaclass(MetaRisk, object)):
    '''
        Base class for Risk Control systems
    '''
    params = ()

    def check_risk(self) -> bool:
        '''This method has to be overriden by subclasses of RiskControl to provide
        the riks functionality

        Params:

          - ``strat``: StrategyBase

        The method has to return bool to indicator whether violate risk control.
        '''
        return self._check(self)

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
from toolz import valmap
from backtest.metabase import MetaParams, with_metaclass


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
    params = (
        ('loopback', 7),  # calc volatility over last n days
        ('stage', False), # sell on stage
        ('stage_reserve', 0)
    )

    store = None
    
    def set(self, store):
        self.store = store

    def getsizing(self, sids, isbuy=True):
        cash = self.store.get_cash()
        positions = self.store.get_positions()
        datas = self.store.loopbacks(self.p.loopback, sids)
        meta = {"cash": cash, "positions": positions, "datas": datas}
        return self._getsizing(meta, sids, isbuy)

    def _getsizing(self, meta, sids, isbuy):
        '''This method has to be overriden by subclasses of Sizer to provide
        the sizing functionality

        Params:

          - ``cash``: current available cash in the *broker*

          - ``data``: target of the operation

          - ``isbuy``: will be ``True`` for *buy* operations and ``False``
            for *sell* operations

        The method has to return the actual size (an int) to be executed. If
        ``0`` is returned nothing will be executed.

        The absolute value of the returned value will be used

        '''
        raise NotImplementedError
    
    def _sellout_sizing(self, positions):
        _sizer = valmap(lambda x: -1 * x, positions) if not self.p.stage else valmap(lambda x: -x * (1 - self.p.stage_reserve), positions)
        return _sizer
    
    def set(self, store):
        self.store = store


SizerBase = Sizer  # alias for old naming

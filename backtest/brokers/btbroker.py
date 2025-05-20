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
import httpx
import queue

from backtest.metabase import with_metaclass, MetaBase
from bt_sdk.core.client import TdApi
from backtest.stores.btstore import BTStore
from bt_sdk.core.model import OrderType, OrderMeta


class MetaBTBroker(MetaBase):

    def __init__(cls, name, bases, dct):
        '''Class has already been created ... register'''
        # Initialize the class
        super(MetaBTBroker, cls).__init__(name, bases, dct)
        BTStore.BrokerCls = cls


class IBBroker(with_metaclass(MetaBTBroker, object)):
    '''Broker implementation for Interactive Brokers.

    This class maps the orders/positions from Interactive Brokers to the
    internal API of ``backtrader``.

    Notes:

      - ``tradeid`` is not really supported, because the profit and loss are
        taken directly from IB. Because (as expected) calculates it in FIFO
        manner, the pnl is not accurate for the tradeid.

      - Position

        If there is an open position for an asset at the beginning of
        operaitons or orders given by other means change a position, the trades
        calculated in the ``Strategy`` in cerebro will not reflect the reality.

        To avoid this, this broker would have to do its own position
        management which would also allow tradeid with multiple ids (profit and
        loss would also be calculated locally), but could be considered to be
        defeating the purpose of working with a live broker
    '''
    params = ()

    def __init__(self, tdapi, **kwargs):
        super(IBBroker, self).__init__()
        self.tdapi = tdapi

    def start(self):
        if not self.tdapi.connected():
            raise Exception("TDAPI not connected")

    def stop(self):
        self.tdapi.disconnected()

    def cancel(self, vtorder_id):
        self.tdapi.cancelOrder(vtorder_id)
    
    def get_account(self):
        return self.tdapi.get_account()

    def getposition(self):
        return self.tdapi.get_position()

    def submit(self, order):
        qty = self.tdapi.placeOrder(order)
        self.notify(order)
        return qty

    def _makeorder(self, sid='', size=0, sizer_cash=0, price=None, plimit=None,
                   exectype=None, order_type=None, created_at=None,
                   **kwargs):

        order = OrderMeta(sid=sid, size=size, size_cash=sizer_cash, price=price, pricelimit=plimit, 
                          exec_type=exectype, order_type=order_type, created_at=created_at,
                          **kwargs)

        return order

    def buy(self, sid, size, sizer_cash=0, price=None, plimit=None,
            exec_type=None, **kwargs):
        order = self._makeorder(
            sid, size, sizer_cash, price, plimit, exec_type, OrderType.Buy, **kwargs)
        return self.submit(order)

    def sell(self, sid, size, sizer_cash=0, price=None, plimit=None,
             exec_type=None, **kwargs):
        order = self._makeorder(
            sid, size, sizer_cash, price, plimit, exec_type, OrderType.Sell, **kwargs)
        return self.submit(order)

    def notify(self, order):
        self.notifs.put(order.clone())

    def get_notification(self):
        try:
            return self.notifs.get(False)
        except queue.Empty:
            pass

        return None

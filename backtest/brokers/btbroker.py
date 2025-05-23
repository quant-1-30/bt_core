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
import queue
import copy

from backtest.metabase import with_metaclass, MetaBase
from backtest.stores.btstore import BTStore
# from bt_sdk.core.client import TdApi
from bt_sdk.core.model import OrderMeta
from bt_sdk.core.constant import ExecType, OrderType


class MetaBTBroker(MetaBase):

    def __init__(cls, name, bases, dct):
        '''Class has already been created ... register'''
        # Initialize the class
        super(MetaBTBroker, cls).__init__(name, bases, dct)
        BTStore.BrokerCls = cls

    def donew(cls, *args, **kwargs):
        _obj, args, kwargs = super(MetaBTBroker, cls).donew(*args, **kwargs)
        _obj.get_data = cls.get_data
        return _obj, args, kwargs
    
    @staticmethod
    def get_data(q, timeout=-1):
        data = []
        while True:
            # msg = q.get(self.p.cal_tmout) // queue.Empty:  # tmout -> time to refresh 
            msg = q.get(timeout)
            if msg == "eof":
                break
            data.append(msg)
        return data


class BTBroker(with_metaclass(MetaBTBroker, object)):
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
        super(BTBroker, self).__init__()
        self.tdapi = tdapi

        self.notifs = queue.Queue()  # holds orders which are notified

    def _start(self):
        if not self.tdapi.connected():
            raise Exception("TDAPI not connected")

    def stop(self):
        self.tdapi.disconnected()

    def cancel(self, vtorder_id):
        self.tdapi.cancel(vtorder_id)
    
    def getAccount(self, timeout=-1):
        q = self.tdapi.getAccount()
        return self.get_data(q, timeout)

    def getPosition(self, timeout=-1):
        q = self.tdapi.getPosition()
        return self.get_data(q, timeout)

    def submit(self, order):
        qty = self.tdapi.placeOrder(order)
        self.notify(order)
        return qty

    def _makeorder(self, sid, size, sizer_cash, price, pricelimit,
                   exectype, order_type, created_at):

        order = OrderMeta(sid=sid, size=size, sizer_cash=sizer_cash, price=price, pricelimit=pricelimit, 
                          exec_type=exectype, order_type=order_type, created_at=created_at
                          )
        return order

    def buy(self, sid='', size=0 , sizer_cash=0, price=None, pricelimit=None,
            exec_type=None, created_at=None, **kwargs):
        order = self._makeorder(
            sid, size, sizer_cash, price, pricelimit, exec_type, OrderType.Buy, created_at)
        return self.submit(order)

    def sell(self, sid='', size=0, sizer_cash=0, price=None, pricelimit=None,
             exec_type=None, created_at=None, **kwargs):
        order = self._makeorder(
            sid, size, sizer_cash, price, pricelimit, exec_type, OrderType.Sell, created_at)
        return self.submit(order)

    def notify(self, order):
        self.notifs.put(copy.deepcopy(order))

    def get_notification(self):
        try:
            return self.notifs.get(False)
        except queue.Empty:
            pass
        return None
    
    def subscribeOrder(self, reqmeta):
        q = self.tdapi.subscribe("order", reqmeta)
        return q
    
    def subscribePosition(self, reqmeta):
        q = self.tdapi.subscribe("position", reqmeta)
        return q
    
    def subscribeAccount(self, reqmeta):
        q = self.tdapi.subscribe("account", reqmeta)
        return q
    
    def on_timer(self, tick, timeout=-1):
        q = self.tdapi.onTimer(tick)
        return self.get_data(q, timeout)

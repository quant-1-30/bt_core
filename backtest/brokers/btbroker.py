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

from backtest.metabase import with_metaclass, MetaParams
from backtest.stores.btstore import BTStore
from bt_sdk.core.model import OrderMeta, ReqMeta


class MetaBTBroker(MetaParams):

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
            msg = q.get()
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
    params = (
        ("timeout", -1),
        )

    def __init__(self, tdapi, **kwargs):
        super(BTBroker, self).__init__()
        self.tdapi = tdapi
        self.notifs = queue.Queue()  # holds orders which are notified
        # self.notifs = collections.deque()  # not thread safe

    def _start(self):
        if not self.tdapi.connected():
            raise Exception("TDAPI not connected")

    def stop(self):
        print("stop btbroker")
        self.tdapi.disconnected()

    def cancel(self, vtorder_id):
        self.tdapi.cancel(vtorder_id)
    
    def getAccount(self):
        q = self.tdapi.getAccount()
        return self.get_data(q, self.p.timeout)

    def getPosition(self):
        q = self.tdapi.getPosition()
        return self.get_data(q, self.p.timeout)

    def submit(self, order_meta: OrderMeta):
        qty = self.tdapi.trade(order_meta)
        # self.notify((order_meta, qty)) # pydantic contain _thread.lock
        return qty

    def subscribe(self, topic:str, reqmeta: ReqMeta):
        q = self.tdapi.subscribe(topic, reqmeta)
        return q
    
    def on_timer(self, reqmeta):
        q = self.tdapi.pesudo_timer(reqmeta)
        return self.get_data(q, self.p.timeout)

    def notify(self, order):
        self.notifs.put(copy.deepcopy(order))

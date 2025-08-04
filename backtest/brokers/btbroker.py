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
import threading

from backtest.metabase import with_metaclass, MetaParams
from backtest.stores.btstore import BTStore
from bt_sdk.core.model import OrderMeta, ReqMeta


class AcctDescr(object):

    def __init__(self):
        self._evt_acct = threading.Event()
        self._cash = 0.0
        self.portfolio_value = 0.0

    def broker_threads(self, inst):
        t = threading.Thread(target=self._t_account, args=(inst,))
        t.daemon = True
        t.start()
        self._evt_acct.wait() # wait for account data to be set

    def _t_account(self, inst):
        data = inst.getAccount()
        if data:
            msg = data[0]["msg"]
            self._cash = msg["cash"]
            self.portfolio_value = msg["portfolio_value"]
        else:
            self._cash = 0.0
            self.portfolio_value = 0.0
        self._evt_acct.set()

    def __set__(self, instance, value):
        raise AttributeError("can't set attribute")
    
    def __get__(self, instance, owner):
        if instance is None:
            return self
        self.broker_threads(instance)
        return (self._cash, self.portfolio_value)


class MetaBTBroker(MetaParams):

    def __init__(cls, name, bases, dct):
        '''Class has already been created ... register'''
        # Initialize the class
        super(MetaBTBroker, cls).__init__(name, bases, dct)
        BTStore.BrokerCls = cls

    def donew(cls, *args, **kwargs):
        _obj, args, kwargs = super(MetaBTBroker, cls).donew(*args, **kwargs)
        return _obj, args, kwargs
    

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
    
    acct = AcctDescr()

    def __init__(self, tdapi, **kwargs):
        super(BTBroker, self).__init__()
        self.tdapi = tdapi
        # self.notifs = queue.Queue()  # holds orders which are notified thread safe

    def _start(self):
        if not self.tdapi.connected():
            raise Exception("TDAPI not connected")

    def set_cash(self, session,cash):
        self.tdapi.set_cash(session, cash)

    def get_cash(self):
        return self.acct[0]

    def get_portfolio(self):
        return self.acct[1]
    
    def get_position(self):
        pos = self.tdapi.get_position()
        return pos

    def submit(self, order_meta: OrderMeta):
        trades = self.tdapi.trade(order_meta)
        # self.notify((order_meta, qty)) # pydantic contain _thread.lock
        return trades

    def subscribe(self, topic:str, reqmeta: ReqMeta):
        q = self.tdapi.subscribe(topic, reqmeta)
        return q
    
    def check(self, session):
        status = self.tdapi.check(session)
        return status

    # def notify(self, order):
    #     self.notifs.put(copy.deepcopy(order))
    
    def cancel(self, vtorder_id):
        self.tdapi.cancel(vtorder_id)

    def stop(self):
        print("stop btbroker")
        self.tdapi.disconnected()

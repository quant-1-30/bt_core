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
import threading
import collections

from backtest.broker import BrokerBase
from bt_sdk.core.model import OrderMeta, ReqMeta, CashMeta

__all__ = ["BTBroker"]


class Acct(object):

    def __init__(self):
        self._evt_acct = threading.Event()
        self._cash = 0.0
        self.portfolio_value = 0.0

    def __set__(self, instance, value):
        raise AttributeError("can't set attribute")
    
    def __get__(self, instance, owner):
        if instance is None:
            return self
        self.acct_thd(instance.tdapi)
        return (self._cash, self.portfolio_value)
    
    def acct_thd(self, api):
        t = threading.Thread(target=self._t_account, args=(api,))
        t.daemon = True
        t.start()
        self._evt_acct.wait() # wait for account data to be set
    
    def _t_account(self, api):
        act = api.fetch("account")
        if act:
            msg = act[0]["body"]
            self._cash = msg["cash"]
            self.portfolio_value = msg["portfolio_value"]
        else:
            self._cash = 0.0
            self.portfolio_value = 0.0
        self._evt_acct.set()


class BTBroker(BrokerBase):
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
        ("tdapi", None),
    )
    
    acct = Acct()

    def __init__(self, **kwargs): # kwargs - params left keys
        self._notifs = collections.deque()

    def set_cash(self, cashmeta: CashMeta):
        status = self.tdapi.set_cash(cashmeta)
        return status

    def fetch(self, topic:str):
        o = self.tdapi.fetch(topic)
        return o
    
    def subscribe(self, topic:str, req: ReqMeta): # contextlib
        q = self.tdapi.subscribe(topic, req)
        return q

    def submit(self, order_meta:OrderMeta):
        order_bits = self.tdapi.trade(order_meta.model_dump()) # pydantic contain _thread.lock
        self.put_notification(order_bits)

    def chain(self, req: ReqMeta):
        # to keep trading sequence
        status = self.tdapi.chain(req)
        return status
    
    def stop(self):
        super().stop()
        self.tdapi.disconnected()

    def put_notification(self, msg):
        self.notifs.append(msg)

    def get_notification(self):
        return self._notifs.pop()

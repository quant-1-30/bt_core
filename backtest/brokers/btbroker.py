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

from backtest.broker import BrokerBase
from bt_sdk.core.model import OrderMeta, CashMeta, ExpMeta, ReqMeta

__all__ = ["BTBroker"]


class Acct(object):

    def __init__(self):
        self._evt_acct = threading.Event()
        self.fundval = []

    def __set__(self, instance, value):
        raise AttributeError("can't set attribute")
    
    def __get__(self, instance, owner):
        if instance is None:
            return self
        self.acct_thd(instance.tdapi)
        return self.fundval
    
    def acct_thd(self, api):
        t = threading.Thread(target=self._t_account, args=(api,))
        t.daemon = True
        t.start()
        self._evt_acct.wait() # wait for account data to be set
    
    def _t_account(self, api):
        act = api.get_value("account")
        if act:
            msg = act[0]["body"]
            self.fundval = msg
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

    def register(self, exp: ExpMeta):
        status = self.tdapi.register(exp)
        return status

    def set_cash(self, cashmeta: CashMeta, experiment_id: str):
        status = self.tdapi.set_cash(cashmeta, experiment_id)
        return status

    def get_value(self, topic:str, experiment_id=''):
        o = self.tdapi.fetch(topic, experiment_id) 
        return o
    
    def subscribe(self, topic:str, req: ReqMeta, experiment_id:str): # contextlib
        q = self.tdapi.subscribe(topic, req, experiment_id)
        return q

    def submit(self, order_meta:OrderMeta, experiment_id:str):
        order_bits = self.tdapi.trade(order_meta, experiment_id) # pydantic contain _thread.lock
        self.put_notification(order_bits)

    def on_dt_over(self, req: ReqMeta, experiment_id:str):
        status = self.tdapi.on_dt_over(req, experiment_id) # staisfy T + 1 and update logic 
        return status
    
    def stop(self):
        super().stop()
        self.tdapi.disconnected()
        print("btbroker stop")



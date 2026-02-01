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
from backtest.metabase import with_metaclass
from typing import List, Union, Generator

from backtest.broker import BrokerBase
from backtest.stores.btstore import BTStore
from bt_sdk.core.protocol import RegisterBody, CashBody, OrderBody, QueryBody, Resp

__all__ = ["BTBroker"]


class MetaBtBroker(BrokerBase.__class__):
    
    def __init__(cls, name, bases, dct):
        super(MetaBtBroker, cls).__init__(name, bases, dct)
        BTStore.BrokerCls = cls # auto Register with the store when type class __import__

    def donew(cls, *args, **kwargs):
        print("MetaBtBroker donew kwargs ", kwargs)
        _obj, args, kwargs = super(MetaBtBroker, cls).donew(*args, **kwargs)
        print("MetaBtBroker donew kwargs after", kwargs)
        return _obj, args, kwargs
    
    def dopostinit(cls, _obj, *args, **kwargs):
        print("MetaBtBroker dopostinit kwargs ", kwargs)
        _obj, args, kwargs = super().dopostinit(_obj, *args, **kwargs) 
        print("MetaBtBroker dopostinit kwargs ", kwargs)
        _obj.tdapi = _obj.p.tdapi
        return _obj, args, kwargs


class BTBroker(with_metaclass(MetaBtBroker, BrokerBase)):
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
        ("tdapi", ""),
    )
    
    @staticmethod
    def get_body(data: list):
        return [r.body for r in data]
    
    def register(self, body:RegisterBody) -> List[Resp]:
        data = self.tdapi.register(body)
        body = self.get_body(data) # body=ExperimentBody
        return body[0].experiment_id
    
    def set_cash(self, experiment_id:bytes, body:CashBody) -> List[Resp]:
        data = self.tdapi.set_cash(experiment_id, body)
        body = self.get_body(data) # None
        return body

    def getvalue(self, topic:int, experiment_id:bytes) -> List[Resp]:
        data = self.tdapi.getvalue(topic, experiment_id) 
        body = self.get_body(data) # PositionBody / AccountBody 
        return body
    
    def subscribe(self, topic:int, experiment_id:bytes) -> List[Resp]: 
        data = self.tdapi.subscribe(topic, experiment_id, body)
        body = self.get_body(data) # TradeBody / PositionBody / AccountBody 
        return body

    def submit(self, experiment_id:bytes, body:OrderBody) -> List[Resp]:
        data = self.tdapi.submit(experiment_id, body) 
        body = self.get_body(data) # TradeBody 
        return body

    def on_dt_over(self, experiment_id:bytes, body:QueryBody) -> List[Resp]:
        data = self.tdapi.on_dt_over(experiment_id, body)
        body = self.get_body(data) # None 
        return body
    
    def stop(self):
        super().stop()
        self.tdapi.disconnect()

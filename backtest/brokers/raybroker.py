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
import ray
from typing import List, Union, Generator

from backtest.broker import BrokerBase
from backtest.metabase import with_metaclass
from backtest.stores.raystore import RayBtStore
from bt_sdk.core.protocol import RegisterBody, CashBody, OrderBody, QueryBody, Resp

__all__ = ["RayBtBroker"]


class MetaRayBtBroker(BrokerBase.__class__):
    
    def __init__(cls, name, bases, dct):
        super(MetaRayBtBroker, cls).__init__(name, bases, dct)
        RayBtStore.RayBrokerCls = cls # auto Register with the store when type class __import__

    def donew(cls, *args, **kwargs):
        print("MetaRayBtBroker donew kwargs ", kwargs)
        _obj, args, kwargs = super(MetaRayBtBroker, cls).donew(*args, **kwargs)
        print("MetaRayBtBroker donew kwargs after", kwargs)
        return _obj, args, kwargs
    
    def dopostinit(cls, _obj, *args, **kwargs):
        print("MetaRayBtBroker dopostinit kwargs ", kwargs)
        _obj, args, kwargs = super().dopostinit(_obj, *args, **kwargs) 
        print("MetaRayBtBroker dopostinit kwargs ", kwargs)
        _obj.agent = _obj.p.agent
        return _obj, args, kwargs


class RayBtBroker(with_metaclass(MetaRayBtBroker, BrokerBase)):
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
        ("agent", ""), 
        ("tdapi", ""),
    )
    
    def register(self, body:RegisterBody) -> List[Resp]:
        resp = self.agent.register.remote(body)
        return resp # ObjectRef
    
    def set_cash(self, experiment_id:bytes, body:CashBody) -> List[Resp]:
        resp = self.agent.set_cash.remote(experiment_id, body)
        return resp

    def getvalue(self, topic:int, experiment_id:bytes) -> List[Resp]:
        resp = self.agent.getvalue.remote(topic, experiment_id)
        return resp
    
    def subscribe(self, topic:int, experiment_id:bytes, body:QueryBody) -> List[Resp]: 
        resp = self.agent.subscribe.remote(topic, experiment_id, body)
        return resp

    def submit(self, experiment_id:bytes, body:OrderBody) -> List[Resp]:
        resp = self.agent.submit.remote(experiment_id, body)
        return resp

    def on_dt_over(self, experiment_id:bytes, body:QueryBody) -> List[Resp]:
        resp = self.agent.on_dt_over.remote(experiment_id, body)
        return resp
    
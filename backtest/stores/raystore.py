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
import os
import ray
import numpy as np
import pyarrow as pa
from typing import Union, List, Mapping, Any, Generator, Tuple

from backtest.store import Store
from bt_sdk.core.client import MdApi, TdApi, SubTopic, OrderType, ExecType
from bt_sdk.core.protocol import *
from typing import List

__all__ = ["BTStore"]


class RayBtStore(Store):
    '''Singleton class wrapping to control the connections.

    Params:

      - ``token`` (default:``None``): API access token

      - ``account`` (default: ``None``): account id

      - ``practice`` (default: ``False``): use the test environment

      - ``account_tmout`` (default: ``10.0``): refresh period for account
        value/cash refresh
    '''
    # autoregister when metaclass init 
    RayBrokerCls = None  
    RayDataCls = None 

    params = (
        ("md_addr", ("127.0.0.1:9000")),
        ("td_addr", ("127.0.0.1:8888")),
        ("timeout", 10),
        ("client_id", b""),
    )

    def __init__(self): 
        agent = self._start()

        self._feed = self.RayDataCls(agent=agent, timeout=self.p.timeout) 
        self.broker = self.RayBrokerCls(agent=agent)

    def _start(self):
        super().__init__()
        agent_handle = self._connect_to_agent()
        return agent_handle

    def _connect_to_agent(self):
        try:
            current_node_id = ray.get_runtime_context().get_node_id()
            
            actor_name = f"StoreAgent_{current_node_id}"
            agent = ray.get_actor(actor_name, namespace="backtest")
            return agent
        except Exception as e:
            raise RuntimeError(f"Failed to connect to local StoreAgent. "
                               f"Make sure agents are started! Error: {e}")

    def setenvironment(self, env):
        '''Receives an environment (cerebro) and passes it over to the store it
        belongs to'''
        super(BTStore, self).setenvironment(env)

    def get_feed(self):
        '''Returns a feed with the given parameters'''
        return self._feed

# ------------------------------------------------------------------- data api ---------------------------------------------------------------------

    def get_calendar(self) -> np.array:
        '''Returns the calendar data'''
        return self._feed.calendar
    
    def get_instrument(self) -> Dict[str, Any]:
        '''Returns the assets data'''
        return self._feed.instrument
    
    def get_benchmark(self) -> pa.Table:
        table = self._feed.bench
        return table
    
# ------------------------------------------------------------------- broker api --------------------------------------------------------------------

    def register(self, strategy, strat_info) -> List[Resp]:
        extra_info = f"Strategy: {strat_info}; Feed: {self._feed.extra_info}"
        body = RegisterBody(strategy=strategy, extra_info=extra_info, client_id=self.p.client_id)
        resp = self.broker.register(body)
        return resp
    
    def set_cash(self, experiment_id, session, cash) -> List[Resp]:
        body = CashBody(cash=cash, session=session)
        self.broker.set_cash(body, experiment_id)
    
    def getaccount(self, experiment_id) -> List[Resp]:
        acct = self.broker.getvalue(SubTopic.Account, experiment_id)
        return acct[0]
    
    def getposition(self, experiment_id) -> List[Resp]:
        o = self.broker.getvalue(SubTopic.Position, experiment_id)
        return o
    
    def subscribe(self, experiment_id, topic, body: QueryBody) -> List[Resp]:
        return self.broker.subscribe(topic, body, experiment_id)
    
    def submit(self, experiment_id, body: OrderBody) -> List[Resp]:
        trades = self.broker.submit(body, experiment_id)
        return trades

    def on_dt_over(self, experiment_id) -> List[Resp]:
        body = self._feed.on_dt_over()
        if body:
            self.broker.on_dt_over(body, experiment_id)
        return []
    
    def cancel(self, order_id):
        raise NotImplementedError("cancel not implemented in BTStore")
    
    def stop(self, experiment_id):
        '''Stops and tells the store to stop'''
        self.on_dt_over(experiment_id) # sync last 
        super().stop()

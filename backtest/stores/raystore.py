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
        ("client_id", b""),
    )

    def __init__(self): 
        agent = self._resolve_agent()

        self._feed = self.RayDataCls(agent=agent, timeout=self.p.timeout) 
        self.broker = self.RayBrokerCls(agent=agent)

    def _resolve_agent(self):
            if self.p.agent is not None: # local Round-Robin
                return self.p.agent
            return self._connect_to_local_agent() # cluster Local Affinity 

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

    @staticmethod
    def get_body(data: list):
        return [r.body for r in data]

# ------------------------------------------------------------------- data api ---------------------------------------------------------------------

    def get_calendar(self) -> np.array:
        '''Returns the calendar data'''
        return self._feed.get_calendar()
    
    def get_instrument(self) -> Dict[str, Any]:
        '''Returns the assets data'''
        return self._feed.get_instrument()
    
    def get_benchmark(self) -> pa.Table:
        return self._feed.bench

# ------------------------------------------------------------------- broker api --------------------------------------------------------------------

    def register(self, strategy:str, strat_info:str) -> List[Resp]:
        extra_info = f"Strategy: {strat_info}; Feed: {self._feed.extra_info}"
        body = RegisterBody(strategy=strategy, extra_info=extra_info, client_id=self.p.client_id)

        resp = ray.get(self.broker.register(body)) # block until finish
        data = self.get_body(resp) 
        return data[0].experiment_id # body=ExperimentBody
    
    def set_cash(self, experiment_id:bytes, session:int, cash:float) -> List[Resp]:
        body = CashBody(cash=cash, session=session)
        resp = ray.get(self.broker.set_cash(experiment_id, body))
        data = self.get_body(resp) 
        return resp[0]
    
    def getvalue(self, experiment_id:bytes) -> List[SnapshotBody]:
        resp = ray.get(self.broker.getvalue(experiment_id))
        data = self.get_body(resp) 
        return data[0]
    
    def subscribe(self, topic:int, experiment_id:bytes, body:QueryBody) -> List[Union[TradeBody, PositionBody, AccountBody]]:
        resp = ray.get(self.broker.subscribe(topic, experiment_id, body))
        data = self.get_body(resp) 
        return data
    
    def submit(self, experiment_id:bytes, body:OrderBody) -> List[Resp]:
        resp = ray.get(self.broker.submit(experiment_id, body))
        data = self.get_body(resp) # TradeBody 
        return data[0]
    
    def on_dt_over(self, experiment_id:bytes) -> List[Resp]:
        body = self._feed.on_dt_over()
        if body:
            ray.get(self.broker.on_dt_over(experiment_id, body))
        return [] 

    def cancel(self, order_id:bytes):
        raise NotImplementedError("cancel not implemented in BTStore")
    
    def stop(self, experiment_id:bytes):
        '''Stops and tells the store to stop'''
        self.on_dt_over(experiment_id) # sync last 
        super().stop()

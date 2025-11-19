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
from typing import Union, List, Mapping, Any, Generator, Tuple

from bt_sdk.core.client import MdApi, TdApi
from backtest.store import Store
from bt_sdk.core.data import Resp, Account, Position, Trade
from bt_sdk.core.model import Order, Cash, Experiment, Query
from typing import List


class BTStore(Store):
    '''Singleton class wrapping to control the connections.

    Params:

      - ``token`` (default:``None``): API access token

      - ``account`` (default: ``None``): account id

      - ``practice`` (default: ``False``): use the test environment

      - ``account_tmout`` (default: ``10.0``): refresh period for account
        value/cash refresh
    '''
    
    BrokerCls = None  # broker class will autoregister
    DataCls = None  # data class will auto register

    params = (
        ("md_addr", ("127.0.0.1:9000")),
        ("td_addr", ("127.0.0.1:8888")),
        ("client_id", "")
    )

    def __init__(self, *args, **kwargs): # 多余参数保留
        # print("store initialize kwargs ", kwargs)

        md_addr = os.getenv("MD_ADDR", self.p.md_addr)
        kwargs["mdapi"] = MdApi(addr=md_addr.split(":"))
        self._feed = self.DataCls(*args, **kwargs) 

        td_addr = os.getenv("TD_ADDR", self.p.td_addr) 
        tdapi = TdApi(addr=td_addr.split(":"), client_id=self.p.client_id)
        self.broker = self.BrokerCls(tdapi=tdapi)
    
    def _start(self, *args, **kwargs):
        pass
   
    def setenvironment(self, env):
        '''Receives an environment (cerebro) and passes it over to the store it
        belongs to'''
        super(BTStore, self).setenvironment(env)

    def get_feed(self):
        '''Returns a feed with the given parameters'''
        return self._feed

# ------------------------------------------------------------------- data api ---------------------------------------------------------------------

    def get_calendar(self) -> List[int]:
        '''Returns the calendar data'''
        return self._feed.descr[0]
    
    def get_instrument(self) -> List[Mapping[str, Any]]:
        '''Returns the assets data'''
        return self._feed.descr[1]
    
    def get_index(self, index) -> List[Mapping[str, Any]]:
        # 000001 000680 399006 399001
        dlines = self._feed.get_index(index=index)
        return dlines
    
# ------------------------------------------------------------------- broker api --------------------------------------------------------------------

    def make_experiment(self, strat_id) -> Resp:
        body = Experiment(strategy=strat_id, extra_info=self._feed.extra_info, client_id=self.p.client_id)
        resp = self.broker.register(body)
        return resp
    
    def set_cash(self, strat, cash) -> Resp:
        body = Cash(cash=cash, session=self._feed.fromdate)
        resp = self.broker.set_cash(body, strat.experiment_id)
        return resp
    
    def getaccount(self, experiment_id) -> List[Account]:
        acct = self.broker.acct
        return acct.get(experiment_id, None)
    
    def getposition(self, experiment_id) -> List[Position]:
        o = self.broker.get_data("position", experiment_id)
        return o
    
    def subscribe(self, experiment_id, topic) -> Generator:
        return self.broker.subscribe(topic, Query(), experiment_id)
    
    def submit(self, experiment_id, order: Order) -> Tuple[Order, Trade]:
        trades = self.broker.submit(order, experiment_id)
        return order, trades

    def _dt_over(self, last=False) -> Tuple[bool, Tuple[int, int]]:
        dtover, (dtkey, dt) = self._feed._dt_over(last)
        return dtover, (dtkey, dt)
    
    def on_dt_over(self, experiment_id, last=False) -> bool: 
        dt_over, dts = self._dt_over(last)
        if dt_over:
            qry = Query(start_date=dts[0], end_date=dts[-1], sid=[]) # on_dt_over ---> timestamp under utc
            _ = self.broker.on_dt_over(qry, experiment_id)
        return dt_over
    
    def cancel(self, order_id):
        raise NotImplementedError("cancel not implemented in BTStore")
    
    def stop(self, experiment_id):
        '''Stops and tells the store to stop'''
        self.on_dt_over(experiment_id, last=True) # sync end_of_session
        super().stop()

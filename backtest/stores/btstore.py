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
import numpy as np

from datetime import datetime
from bt_sdk.core.client import MdApi, TdApi
from backtest.store import Store
from bt_sdk.core.model import OrderMeta, ReqMeta, CashMeta, ExpMeta
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
        ('md_addr', ("127.0.0.1", 9000)),
        ('td_addr', ("127.0.0.1", 8888)),
    )

    def start(self, *args, **kwargs):
        kwargs["tdapi"] = TdApi(addr=self.p.td_addr, client_id=self.p.client_id)
        kwargs["mdapi"] = MdApi(addr=self.p.md_addr)
        self._feed = self.DataCls(*args, **kwargs)
        self.broker = self.BrokerCls(*args, **kwargs)
 
    def register(self, strategy, assets):
        exp = ExpMeta(strategy=strategy, assets=assets, client_id=self.p.client_id)
        self.broker.register(exp)
    
    def setenvironment(self, env):
        '''Receives an environment (cerebro) and passes it over to the store it
        belongs to'''
        super(BTStore, self).setenvironment(env)

# ------------------------------------------------------------------- data api ---------------------------------------------------------------------

    def get_calendar(self):
        '''Returns the calendar data'''
        return self._feed.descr[0]
    
    def get_instrument(self):
        '''Returns the assets data'''
        return self._feed.descr[1]
    
    def get_benchmark(self, index="000001"):
        # 000001 000680 399006 399001
        dlines = self._feed.get_benchmark(index=index)
        return dlines
    
    def get_feed(self):
        '''Returns a feed with the given parameters'''
        return self._feed

# ------------------------------------------------------------------- broker api --------------------------------------------------------------------
    
    def set_cash(self, session, cash):
        cashmeta = CashMeta(session=session, cash=cash)
        status = self.broker.set_cash(cashmeta)
        return status
    
    def get_value(self):
        # acct [cash, portfolio]
        acct = self.broker.acct
        return np.sum(acct), acct[0] 
    
    def get_position(self):
        o = self.broker.fetch("position")
        return o
    
    def get_account(self):
        o = self.broker.fetch("account")
        return o
    
    def subscribe(self, topic, sdate=0, edate=0, sid=[]):
        start_date = sdate if sdate >0 else datetime.strptime("19900101", "%Y%m%d")
        end_date = edate if edate > 0 else datetime.now().timestamp()
        req = ReqMeta(start_date=start_date, end_date=end_date, sid=sid)
        return self.broker.subscribe(topic, req)
    
    def submit(self, sid="", size=0, price=0.0, sizer_ratio=0, 
               pricelimit=0, exec_type=0, order_type=0, created_at=0):
        order_meta = OrderMeta(sid=sid,
                                size=abs(size), 
                                price=price,
                                sizer_ratio=sizer_ratio, 
                                pricelimit=pricelimit,
                                exec_type=exec_type, 
                                order_type=order_type,
                                created_at=created_at)

        order_bits = self.broker.submit(order_meta)
        self.qucknotify.notify_order((order_meta, order_bits)) # notify order
        return order_bits
    
    def on_dt_over(self, last=False): 
        isover, interval, data = self._feed.on_dt_over(last)
        self.quicknotify.notify_data(data) # notify daily data
        if isover:
            req = ReqMeta(*interval, sid=[])
            data = self.broker.on_dt_over(req)
            self.quicknotify.notify_account(data) # notify account and position
    
    def cancel(self, order_id):
        raise NotImplementedError("cancel not implemented in BTStore")
    
    def stop(self):
        '''Stops and tells the store to stop'''
        self.on_dt_over(last=True) # sync end_of_session
        super().stop()

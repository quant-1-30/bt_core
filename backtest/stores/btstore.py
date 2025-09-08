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
from bt_sdk.core.model import OrderMeta, ReqMeta, CashMeta


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
        ('md_addr', "tcp://127.0.0.1:9000"),
        ('td_addr', ("127.0.0.1", 8888)),
    )

    def _start(self, *args, **kwargs):
        kwargs["tdapi"] = TdApi(addr=self.p.td_addr, client_id=self.p.client_id)
        kwargs["mdapi"] = MdApi(addr=self.p.md_addr)
        self.data = self.DataCls(*args, **kwargs)
        self.broker = self.BrokerCls(*args, **kwargs)
    
    def setenvironment(self, env):
        '''Receives an environment (cerebro) and passes it over to the store it
        belongs to'''
        super(BTStore, self).setenvironment(env)

# ----------------------------------------------------------- data api -----------------------------------------------------

    def get_calendar(self):
        '''Returns the calendar data'''
        return self.data.descr[0]
    
    def get_instrument(self):
        '''Returns the assets data'''
        return self.data.descr[1]
    
    def get_feed(self):
        '''Returns a feed with the given parameters'''
        return self.data
    
    def set_cash(self, session, cash):
        cashmeta = CashMeta(session=session, cash=cash)
        status = self.broker.set_cash(cashmeta)
        return status
    
    def get_value(self):
        # acct [cash, portfolio]
        acct = self.broker.acct
        return np.sum(acct), acct[0]
    
    def get_position(self):
        return self.broker.fetch("position")
    
    def subscribe(self, topic, sdate=0, edate=0, sid=[]):
        start_date = sdate if sdate >0 else datetime.strptime("19900101", "%Y%m%d")
        end_date = edate if edate > 0 else datetime.now().timestamp()
        req = ReqMeta(start_date=start_date, end_date=end_date, sid=sid)
        return self.broker.subscribe(topic, req)
    
    def submit(self, sid="", size=0, price=0.0, sizer_cash=0, 
               pricelimit=0, exec_type=0, order_type=0, created_at=0):
        order_meta = OrderMeta(sid=sid,
                                size=abs(size), 
                                price=price,
                                sizer_cash=sizer_cash, 
                                pricelimit=pricelimit,
                                exec_type=exec_type, 
                                order_type=order_type,
                                created_at=created_at)
        self.broker.submit(order_meta)
    
    def chain(self, sdate, edate): 
        # check if adj / rght occurred
        req = ReqMeta(start_date=sdate, end_date=edate, sid=[])
        return self.broker.chain(req)
    
    def cancel(self, order_id):
        raise NotImplementedError("cancel not implemented in BTStore")
    
    def stop(self):
        '''Stops and tells the store to stop'''
        print("stop mdapi")
        self.data.stop()
        self.broker.stop()

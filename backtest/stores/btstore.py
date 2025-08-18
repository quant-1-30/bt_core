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
from bt_sdk.core.client import MdApi, TdApi
from backtest.store import Store
from bt_sdk.core.model import OrderMeta, ReqMeta, CashMeta


class MD(object):
    '''Descriptor for calendar and instrument data'''
    def __init__(self):
        self.calendar = ()
        self.assets = ()

        self._evt_cal = threading.Event()
        self._evt_asset = threading.Event()

    def data_thd(self, api):
        t = threading.Thread(target=self._t_cal, args=(api,), daemon=True)
        t_ = threading.Thread(target=self._t_asset, args=(api,), daemon=True)
        t.start()
        self._evt_cal.wait() # api async run in same thread and event loop

        t_.start()
        self._evt_asset.wait()

    def _t_cal(self, api):
        msg = api.get_calendar()
        print("calendar msg: ", msg)
        self.calendar = msg
        self._evt_cal.set()

    def _t_asset(self, api):
        msg = api.get_instrument()
        print("asset msg ", msg)
        self.assets = msg
        self._evt_asset.set()

    def __set__(self, instance, value):
        raise AttributeError("can't set attribute")
    
    def __get__(self, instance, owner):
        if len(self.calendar) ==0 or len(self.assets) ==0:
            self.data_thd(instance._mdapi)
        return self.calendar, self.assets
    

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

    md = MD()

    params = (
        ('md_addr', ("127.0.0.1", 8888)),
        ('td_addr', ("127.0.0.1", 8888)),
    )

    def __init__(self):
        super(BTStore, self).__init__()
        self._mdapi = None

    def _start(self, client_id, *args, **kwargs):
        self._mdapi = MdApi(addr=self.p.md_addr)
        tdapi = TdApi(addr=self.p.td_addr, client_id=client_id)
        self.broker = self.BrokerCls(tdapi)
        self.data = self.DataCls(*args, **kwargs)
    
    def setenvironment(self, env):
        '''Receives an environment (cerebro) and passes it over to the store it
        belongs to'''
        super(BTStore, self).setenvironment(env)

# ----------------------------------------------------------- data api -----------------------------------------------------

    def get_calendar(self):
        '''Returns the calendar data'''
        return self.md[0]
    
    def get_instrument(self):
        '''Returns the assets data'''
        return self.md[1]
    
    def get_feed(self, sid, start_date, end_date):
        '''Returns a feed with the given parameters'''
        buffer =self._mdapi.subscribe(sid, start_date, end_date)
        feed = self.DataCls(
            dataname=sid,
            fromdate=start_date,
            todate=end_date,
            buffer=buffer) 
        return feed
    
    def set_cash(self, session, cash):
        cashmeta = CashMeta(session=session, cash=cash)
        status = self.broker.set_cash(cashmeta)
        return status
    
    def get_cash(self):
        return self.broker.acct[0]

    def get_portfolio(self):
        return self.broker.acct[1]
    
    def get_position(self):
        return self.broker.fetch("position")
    
    def subscribe(self, topic, sdate, edate, sid=[]):
        req = ReqMeta(start_date=sdate, end_date=edate, sid=sid)
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
        
        return self.broker.submit(order_meta)
    
    def check(self, sdate, edate): # check if adj / rght occurred
        req = ReqMeta(start_date=sdate, end_date=edate, sid=[])
        return self.broker.check(req)
    
    def cancel(self, order_id):
        raise NotImplementedError("cancel not implemented in BTStore")
    
    def stop(self):
        '''Stops and tells the store to stop'''
        print("stop mdapi")
        self.mdapi.disconnected()
        self.broker.disconnected()

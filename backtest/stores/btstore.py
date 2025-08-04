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
import datetime
import collections
import threading
import queue
from typing import List
from backtest.dataseries import TimeFrame
from bt_sdk.core.model import ReqMeta, OrderMeta
from bt_sdk.core.client import MdApi, TdApi
from backtest.store import Store


class Descriptor(object):
    '''Descriptor for calendar and instrument data'''
    def __init__(self):
        self.cal = None
        self.assets = None

        self._evt_asset = threading.Event()
        self._evt_cal = threading.Event()

    def data_threads(self, api):
        t = threading.Thread(target=self._t_cal, args=(api,), daemon=True)
        t_ = threading.Thread(target=self._t_asset, args=(api,), daemon=True)
        t.start()
        t_.start()
        self._evt_cal.wait()
        self._evt_asset.wait()

    def _t_cal(self, api):
        msg = api.getCalendar()
        self.cal = msg
        self._evt_cal.set()

    def _t_asset(self, api):
        msg = api.getInstrument()
        if msg:
            self.assets = msg[0]["msg"]["assets"]
        else:
            self.assets = []
        self._evt_asset.set()

    def __set__(self, instance, value):
        raise AttributeError("can't set attribute")
    
    def __get__(self, instance, owner):
        if self.cal is None or self.assets is None:
            self.data_threads(instance._mdapi)
        return self.cal, self.assets


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

    descriptor = Descriptor()

    params = (
        ('md_addr', ("127.0.0.1", 8888)),
        ('td_addr', ("127.0.0.1", 8888)),
    )

    def __init__(self, **kwargs):
        super(BTStore, self).__init__()
        self.notifs = collections.deque()  # store notifications for cerebro
        self._mdapi = None

    def _start(self, client_id):
        self._mdapi = MdApi(self.p.md_addr)

        tdapi = TdApi(self.p.td_addr, client_id=client_id)
        self.broker = self.BrokerCls(tdapi)

    def get_feed(self, sid, start_date, end_date):
        '''Returns a feed with the given parameters'''
        chan =self._mdapi.subscribe(sid, start_date, end_date)
        feed = self.DataCls(fromdate=start_date,
                            todate=end_date, 
                            name=sid,
                            chan=chan)
        return feed
    
    def setenvironment(self, env):
        '''Receives an environment (cerebro) and passes it over to the store it
        belongs to'''
        super(BTStore, self).setenvironment(env)

# -------------------------------------------------core api-----------------------------------------------------

    def set_cash(self, session, cash):
        self.broker.set_cash(session, cash)

    def get_calendar(self):
        '''Returns the calendar data'''
        return self.descriptor[0]
    
    def get_instrument(self):
        '''Returns the assets data'''
        return self.descriptor[1]
    
    def check(self, session): # check if adj / rght occurred
        return self.broker.check(session)
    
    def get_cash(self):
        return self.broker.get_cash()
    
    def get_position(self):
        return self.broker.getPosition()

    def get_portfolio_value(self):
        return self.broker.get_portfolio()
    
    def submit(self, meta: OrderMeta):
        return self.broker.submit(meta)
    
    def trade_history(self, topic, reqmeta):
        return self.broker.subscribe(topic, reqmeta)
    
    def amend(self, session):
        '''Amends the session, e.g. to update the cash value'''
        self.broker.amend(session)
    
    def put_notification(self, msg, *args, **kwargs):
        self.notifs.put((msg, args, kwargs))
    
    def get_notification(self):
        try:
            return self.broker.notifs.get(False)
        except queue.Empty:
            pass
        return None
    
    def cancel(self, order_id):
        raise NotImplementedError("cancel not implemented in BTStore")
    
    def stop(self):
        '''Stops and tells the store to stop'''
        print("stop mdapi")
        self.mdapi.disconnected()
        self.broker.disconnected()
